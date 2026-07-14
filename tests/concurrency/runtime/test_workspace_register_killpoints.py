from __future__ import annotations

import json
from pathlib import Path

import pytest

import agent_stack.runtime.workspace as workspace_module
from agent_stack.release.compatibility import RuntimeJournalReference
from tests.integration.runtime.test_workspace_register import (
    PROJECT_ID,
    TRANSACTION_ID,
    WORKSPACE_ID,
    _caller,
    _layout,
    _manifest,
    _project,
)


class InjectedTermination(BaseException):
    pass


def _register(project: Path, tmp_path: Path) -> None:
    layout = _layout()
    workspace_module.register_workspace(
        project,
        _manifest(layout),
        _caller(tmp_path),
        trellis_task_layout=layout,
        bootstrap_lock_root=tmp_path / "bootstrap-locks",
        transaction_id=TRANSACTION_ID,
        workspace_instance_id=WORKSPACE_ID,
        recovery_runtime=RuntimeJournalReference("committed", "a" * 64, "b" * 64),
    )


@pytest.mark.parametrize(
    ("killpoint", "committed"),
    [
        ("planned", False),
        ("before_workspace", False),
        ("after_workspace", False),
        ("workspace_written", False),
        ("before_replay", False),
        ("after_replay", True),
        ("registration_committed", True),
        ("cleanup_pending", True),
    ],
)
def test_every_registration_killpoint_resumes_to_one_committed_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    killpoint: str,
    committed: bool,
) -> None:
    project = _project(tmp_path)

    def terminate(point: str) -> None:
        if point == killpoint:
            raise InjectedTermination(point)

    monkeypatch.setattr(workspace_module, "_crash_at", terminate)
    with pytest.raises(InjectedTermination):
        _register(project, tmp_path)
    replay = project / ".agent-workflow/local/approval-replay.json"
    assert replay.is_file() is committed

    monkeypatch.setattr(workspace_module, "_crash_at", lambda _: None)
    result = workspace_module.recover_workspace_registration(
        project,
        TRANSACTION_ID,
        action="resume",
        bootstrap_lock_root=tmp_path / "bootstrap-locks",
    )
    assert result.committed is True
    workspace = json.loads(
        (project / ".agent-workflow/local/workspace.json").read_text(encoding="utf-8")
    )
    replay_document = json.loads(replay.read_text(encoding="utf-8"))
    assert workspace["project_id"] == replay_document["project_id"] == PROJECT_ID


def test_precommit_rollback_removes_only_matching_workspace_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(
        workspace_module,
        "_crash_at",
        lambda point: (_ for _ in ()).throw(InjectedTermination(point))
        if point == "after_workspace"
        else None,
    )
    with pytest.raises(InjectedTermination):
        _register(project, tmp_path)

    monkeypatch.setattr(workspace_module, "_crash_at", lambda _: None)
    result = workspace_module.recover_workspace_registration(
        project,
        TRANSACTION_ID,
        action="rollback",
        bootstrap_lock_root=tmp_path / "bootstrap-locks",
    )
    assert result.committed is False
    assert not (project / ".agent-workflow/local/workspace.json").exists()
    assert not (project / ".agent-workflow/local/approval-replay.json").exists()


def test_recovery_refuses_external_third_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_stack.runtime.errors import RuntimeFailure

    project = _project(tmp_path)
    monkeypatch.setattr(
        workspace_module,
        "_crash_at",
        lambda point: (_ for _ in ()).throw(InjectedTermination(point))
        if point == "after_workspace"
        else None,
    )
    with pytest.raises(InjectedTermination):
        _register(project, tmp_path)
    (project / ".agent-workflow/local/workspace.json").write_text(
        '{"external":true}', encoding="utf-8"
    )

    monkeypatch.setattr(workspace_module, "_crash_at", lambda _: None)
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_REGISTRATION_RECOVERY_REQUIRED"):
        workspace_module.recover_workspace_registration(
            project,
            TRANSACTION_ID,
            action="resume",
            bootstrap_lock_root=tmp_path / "bootstrap-locks",
        )


def test_postcommit_recovery_never_recreates_a_missing_replay_ledger(tmp_path: Path) -> None:
    from agent_stack.runtime.errors import RuntimeFailure

    project = _project(tmp_path)
    _register(project, tmp_path)
    (project / ".agent-workflow/local/approval-replay.json").unlink()

    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_REGISTRATION_RECOVERY_REQUIRED"):
        workspace_module.recover_workspace_registration(
            project,
            TRANSACTION_ID,
            action="resume",
            bootstrap_lock_root=tmp_path / "bootstrap-locks",
        )
