from __future__ import annotations

import json
from pathlib import Path

import pytest

import agent_stack.runtime.workspace as workspace_module
from agent_stack.runtime.errors import RuntimeFailure
from tests.integration.runtime.test_workspace_migrate import (
    MIGRATION_ID,
    SOURCE_RELEASE,
    TARGET_RELEASE,
    _migrate,
    _migration_inputs,
)


class InjectedTermination(BaseException):
    pass


def _recover(inputs: dict[str, object], *, action: str):
    return workspace_module.recover_workspace_migration(
        inputs["project"],
        MIGRATION_ID,
        action=action,
        source_layout=inputs["source_layout"],
        target_layout=inputs["target_layout"],
        source_schemas=inputs["schemas"],
        target_schemas=inputs["schemas"],
        scanner=inputs["scanner"],
    )


@pytest.mark.parametrize(
    ("killpoint", "committed"),
    [
        ("migration_planned", False),
        ("before_replay_candidate", False),
        ("after_replay_candidate", False),
        ("local_candidates_applied", False),
        ("before_workspace_candidate", False),
        ("after_workspace_candidate", True),
        ("workspace_committed", True),
        ("migration_cleanup_pending", True),
    ],
)
def test_every_workspace_migration_killpoint_resumes_to_target_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    killpoint: str,
    committed: bool,
) -> None:
    inputs = _migration_inputs(tmp_path)

    def terminate(point: str) -> None:
        if point == killpoint:
            raise InjectedTermination(point)

    monkeypatch.setattr(workspace_module, "_crash_at", terminate)
    with pytest.raises(InjectedTermination):
        _migrate(inputs)
    workspace_path = (
        Path(inputs["project"]) / ".agent-workflow/local/workspace.json"
    )
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    assert (workspace["local_state_release_id"] == TARGET_RELEASE) is committed

    monkeypatch.setattr(workspace_module, "_crash_at", lambda _: None)
    result = _recover(inputs, action="resume")
    assert result.committed is True
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    assert workspace["local_state_release_id"] == TARGET_RELEASE


def test_precommit_rollback_restores_exact_local_preimages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _migration_inputs(tmp_path)
    project = Path(inputs["project"])
    workspace_before = (project / ".agent-workflow/local/workspace.json").read_bytes()
    replay_before = (project / ".agent-workflow/local/approval-replay.json").read_bytes()

    monkeypatch.setattr(
        workspace_module,
        "_crash_at",
        lambda point: (_ for _ in ()).throw(InjectedTermination(point))
        if point == "after_replay_candidate"
        else None,
    )
    with pytest.raises(InjectedTermination):
        _migrate(inputs)

    monkeypatch.setattr(workspace_module, "_crash_at", lambda _: None)
    result = _recover(inputs, action="rollback")
    assert result.committed is False
    assert (project / ".agent-workflow/local/workspace.json").read_bytes() == workspace_before
    assert (project / ".agent-workflow/local/approval-replay.json").read_bytes() == replay_before


def test_postcommit_rollback_and_external_third_state_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = _migration_inputs(tmp_path / "committed")
    monkeypatch.setattr(
        workspace_module,
        "_crash_at",
        lambda point: (_ for _ in ()).throw(InjectedTermination(point))
        if point == "after_workspace_candidate"
        else None,
    )
    with pytest.raises(InjectedTermination):
        _migrate(committed)
    monkeypatch.setattr(workspace_module, "_crash_at", lambda _: None)
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED"):
        _recover(committed, action="rollback")

    third = _migration_inputs(tmp_path / "third")
    monkeypatch.setattr(
        workspace_module,
        "_crash_at",
        lambda point: (_ for _ in ()).throw(InjectedTermination(point))
        if point == "after_replay_candidate"
        else None,
    )
    with pytest.raises(InjectedTermination):
        _migrate(third)
    replay = Path(third["project"]) / ".agent-workflow/local/approval-replay.json"
    replay.write_text('{"external":true}', encoding="utf-8")
    monkeypatch.setattr(workspace_module, "_crash_at", lambda _: None)
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED"):
        _recover(third, action="resume")


def test_recovery_revalidates_bound_task_snapshot_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.unit.runtime.test_scanner import write_integration

    inputs = _migration_inputs(tmp_path)
    monkeypatch.setattr(
        workspace_module,
        "_crash_at",
        lambda point: (_ for _ in ()).throw(InjectedTermination(point))
        if point == "local_candidates_applied"
        else None,
    )
    with pytest.raises(InjectedTermination):
        _migrate(inputs)
    write_integration(Path(inputs["project"]), ".trellis/tasks/raced")

    monkeypatch.setattr(workspace_module, "_crash_at", lambda _: None)
    with pytest.raises(RuntimeFailure) as captured:
        _recover(inputs, action="resume")
    assert captured.value.code == "AWP_TASK_QUIESCENCE_CHANGED"
    workspace = json.loads(
        (
            Path(inputs["project"]) / ".agent-workflow/local/workspace.json"
        ).read_text(encoding="utf-8")
    )
    assert workspace["local_state_release_id"] == SOURCE_RELEASE
