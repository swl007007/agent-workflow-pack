from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_stack.runtime.recovery import TaskRecoveryRequest, recover_task_transaction
from agent_stack.runtime.task_service import admit_task, archive_task
from tests.integration.runtime.test_task_admission import (
    TASK_ID,
    TRANSACTION_ID,
    admission_request,
    initialize_project,
)
from tests.integration.runtime.test_task_archive import (
    archive_request,
    complete_trellis_task,
)


@pytest.mark.parametrize(
    "point",
    [
        "after_planned",
        "after_reserved",
        "after_staged",
        "after_task_moved",
        "after_metadata_applied",
        "after_admission_committed",
    ],
)
def test_every_admission_killpoint_resumes_to_one_active_task(
    tmp_path: Path, monkeypatch, point: str
) -> None:
    initialize_project(tmp_path)

    def crash(candidate: str) -> None:
        if candidate == point:
            raise RuntimeError("kill")

    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", crash)
    with pytest.raises(RuntimeError, match="kill"):
        admit_task(admission_request(tmp_path))
    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", lambda _: None)

    recovered = recover_task_transaction(
        TaskRecoveryRequest(tmp_path, TRANSACTION_ID, "resume")
    )

    assert recovered.lifecycle_status == "active"
    integration = json.loads(
        (tmp_path / ".trellis/tasks/example/integration.yaml").read_text()
    )
    assert integration["lifecycle"]["state_revision"] == 2
    assert list((tmp_path / ".trellis/tasks").glob("example"))


def test_admission_rollback_after_journal_before_reservation_writes_consumed_tombstone(
    tmp_path: Path, monkeypatch
) -> None:
    initialize_project(tmp_path)

    def crash(point: str) -> None:
        if point == "after_planned":
            raise RuntimeError("kill")

    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", crash)
    with pytest.raises(RuntimeError):
        admit_task(admission_request(tmp_path))
    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", lambda _: None)

    recovered = recover_task_transaction(
        TaskRecoveryRequest(tmp_path, TRANSACTION_ID, "rollback")
    )

    replay = json.loads(
        (tmp_path / ".agent-workflow/local/approval-replay.json").read_text()
    )
    assert recovered.outcome == "rolled-back"
    assert list(replay["entries"].values())[0]["state"] == "consumed"
    assert not (tmp_path / ".trellis/tasks/example").exists()


@pytest.mark.parametrize(
    "point",
    [
        "after_archive_planned",
        "after_archive_state_marked",
        "after_archive_task_moved",
        "after_archive_metadata_applied",
        "after_archive_committed",
    ],
)
def test_every_archive_killpoint_resumes_to_one_archived_task(
    tmp_path: Path, monkeypatch, point: str
) -> None:
    initialize_project(tmp_path)
    completed = complete_trellis_task(tmp_path)
    request = archive_request(tmp_path, completed.state_revision)

    def crash(candidate: str) -> None:
        if candidate == point:
            raise RuntimeError("kill")

    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", crash)
    with pytest.raises(RuntimeError, match="kill"):
        archive_task(request)
    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", lambda _: None)

    recovered = recover_task_transaction(
        TaskRecoveryRequest(tmp_path, request.transaction_id, "resume")
    )

    assert recovered.lifecycle_status == "archived"
    matches = list((tmp_path / ".trellis/tasks/archive").glob(f"*--{TASK_ID}"))
    assert len(matches) == 1
