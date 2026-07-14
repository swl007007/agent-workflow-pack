from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from agent_stack.core.api import canonical_json_bytes
from agent_stack.reconcile.models import FileState
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.task_service import (
    MetadataMutation,
    TaskArchiveRequest,
    TaskTransitionRequest,
    admit_task,
    archive_task,
    derive_archive_ref,
    transition_task,
)
from tests.integration.runtime.test_task_admission import (
    NOW,
    TASK_ID,
    admission_request,
    initialize_project,
)


def complete_trellis_task(root: Path):
    admitted = admit_task(admission_request(root))
    return transition_task(
        TaskTransitionRequest(
            root,
            admitted.task_ref,
            TASK_ID,
            admitted.state_revision,
            "task-completed",
            target_lifecycle_status="completed",
            target_phase=None,
            completion_flags=None,
            changed_at=NOW + timedelta(minutes=1),
        )
    )


def archive_metadata(task_id: str = TASK_ID) -> MetadataMutation:
    before = canonical_json_bytes({"active": [task_id]})
    after = canonical_json_bytes({"active": [], "archived": [task_id]})
    import hashlib

    return MetadataMutation(
        original=FileState(
            ".trellis/task-index.json",
            True,
            "regular",
            hashlib.sha256(before).hexdigest(),
            "0644",
            True,
        ),
        candidate=FileState(
            ".trellis/task-index.json",
            True,
            "regular",
            hashlib.sha256(after).hexdigest(),
            "0644",
            True,
        ),
        original_bytes=before,
        candidate_bytes=after,
    )


def archive_request(root: Path, revision: int) -> TaskArchiveRequest:
    return TaskArchiveRequest(
        project_root=root,
        transaction_id="1a7a8fda-5bc6-4e4c-9344-a508d3675191",
        task_ref=".trellis/tasks/example",
        task_id=TASK_ID,
        expected_revision=revision,
        archive_root=".trellis/tasks/archive",
        metadata_mutations=(archive_metadata(),),
        archived_at=NOW + timedelta(minutes=2),
    )


def test_archive_commit_is_archived_integration_after_move_and_metadata(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    completed = complete_trellis_task(tmp_path)

    archived = archive_task(archive_request(tmp_path, completed.state_revision))

    expected_ref = derive_archive_ref(".trellis/tasks/archive", TASK_ID, completed.task_ref)
    assert archived.task_ref == expected_ref
    assert archived.lifecycle_status == "archived"
    assert archived.state_revision == completed.state_revision + 2
    assert not (tmp_path / completed.task_ref).exists()
    integration = json.loads((tmp_path / expected_ref / "integration.yaml").read_text())
    assert integration["lifecycle"]["status"] == "archived"
    assert json.loads((tmp_path / ".trellis/task-index.json").read_text()) == {
        "active": [],
        "archived": [TASK_ID],
    }


def test_archive_requires_completed_no_claim_and_absent_destination(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    admitted = admit_task(admission_request(tmp_path))
    with pytest.raises(RuntimeFailure, match="AWP_TASK_ARCHIVE_BLOCKED"):
        archive_task(archive_request(tmp_path, admitted.state_revision))

    completed = transition_task(
        TaskTransitionRequest(
            tmp_path,
            admitted.task_ref,
            TASK_ID,
            admitted.state_revision,
            "task-completed",
            target_lifecycle_status="completed",
            target_phase=None,
            completion_flags=None,
            changed_at=NOW + timedelta(minutes=1),
        )
    )
    destination = tmp_path / derive_archive_ref(
        ".trellis/tasks/archive", TASK_ID, completed.task_ref
    )
    destination.mkdir(parents=True)
    with pytest.raises(RuntimeFailure, match="AWP_TASK_ARCHIVE_BLOCKED"):
        archive_task(archive_request(tmp_path, completed.state_revision))


def test_task_move_alone_remains_archiving_and_gating(tmp_path: Path, monkeypatch) -> None:
    initialize_project(tmp_path)
    completed = complete_trellis_task(tmp_path)

    def crash(point: str) -> None:
        if point == "after_archive_task_moved":
            raise RuntimeError("kill")

    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", crash)
    with pytest.raises(RuntimeError, match="kill"):
        archive_task(archive_request(tmp_path, completed.state_revision))

    destination = tmp_path / derive_archive_ref(
        ".trellis/tasks/archive", TASK_ID, completed.task_ref
    )
    integration = json.loads((destination / "integration.yaml").read_text())
    assert integration["lifecycle"]["status"] == "archiving"
    assert integration["lifecycle"]["archived_at"] is None
