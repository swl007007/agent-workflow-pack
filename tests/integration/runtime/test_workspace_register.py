from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import MappingProxyType

import pytest

from agent_stack.core.api import SchemaCatalog, canonical_json_bytes, validate_trellis_layout
from agent_stack.release.compatibility import RuntimeJournalReference
from agent_stack.runtime.caller_context import VerifiedCallerContext


ROOT = Path(__file__).resolve().parents[3]
LAYOUT_FIXTURE = ROOT / "tests/fixtures/core/trellis_layouts/valid.json"
IGNORE_BLOCK = """# BEGIN AGENT-WORKFLOW-PACK EPHEMERAL
.agent-workflow/local/
.agent-workflow/task-transactions/
.agent-workflow/transactions/
.agent-workflow/reconcile.lock
.agent-workflow/runtime-state.lock
.agent-workflow/maintenance.json
# END AGENT-WORKFLOW-PACK EPHEMERAL
"""
TRANSACTION_ID = "11111111-1111-4111-8111-111111111111"
WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_ID = "33333333-3333-4333-8333-333333333333"


def _layout():
    return validate_trellis_layout(
        json.loads(LAYOUT_FIXTURE.read_text(encoding="utf-8")),
        artifact_targets=("AGENTS.md",),
    )


def _manifest(layout) -> dict[str, object]:
    contract = {
        "release_id": "a" * 64,
        "release_version": "0.1.0",
        "workspace_schema": 1,
        "approval_replay_schema": 1,
        "task_outbox_schema": 1,
        "trellis_task_layout_digest": layout.layout_digest,
    }
    contract["contract_digest"] = hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
    return {
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "generation": 1,
        "pack_version": "0.1.0",
        "release_id": "a" * 64,
        "release_manifest_digest": "b" * 64,
        "local_state_contract": contract,
    }


def _caller(tmp_path: Path) -> VerifiedCallerContext:
    home = tmp_path / "home"
    config = home / "codex"
    harness = home / "bin/codex"
    config.mkdir(parents=True, exist_ok=True)
    harness.parent.mkdir(parents=True, exist_ok=True)
    harness.write_text("#!/bin/sh\n", encoding="utf-8")
    harness.chmod(0o755)
    return VerifiedCallerContext(
        "codex",
        home,
        MappingProxyType({"codex_home": config}),
        harness,
        "codex-version-v1",
        MappingProxyType(
            {
                "direct_confirmation_capable": False,
                "stderr": False,
                "stdin": False,
                "stdout": False,
            }
        ),
    )


def _project(tmp_path: Path, *, valid_ignore: bool = True) -> Path:
    project = tmp_path / "project"
    (project / ".agent-workflow").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / ".gitignore").write_text(
        IGNORE_BLOCK if valid_ignore else ".agent-workflow/cache/\n", encoding="utf-8"
    )
    return project


def _register(project: Path, tmp_path: Path):
    from agent_stack.runtime.workspace import register_workspace

    layout = _layout()
    return register_workspace(
        project,
        _manifest(layout),
        _caller(tmp_path),
        trellis_task_layout=layout,
        bootstrap_lock_root=tmp_path / "bootstrap-locks",
        transaction_id=TRANSACTION_ID,
        workspace_instance_id=WORKSPACE_ID,
        recovery_runtime=RuntimeJournalReference("committed", "a" * 64, "b" * 64),
    )


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_registration_commits_workspace_and_empty_replay_as_one_pair(tmp_path: Path) -> None:
    project = _project(tmp_path)
    layout = _layout()
    manifest = _manifest(layout)
    before = canonical_json_bytes(manifest)

    result = _register(project, tmp_path)

    workspace = _read(project / ".agent-workflow/local/workspace.json")
    replay = _read(project / ".agent-workflow/local/approval-replay.json")
    journal = _read(
        project
        / f".agent-workflow/local/workspace-transactions/{TRANSACTION_ID}.json"
    )
    assert result.committed is True
    assert workspace["project_id"] == replay["project_id"] == PROJECT_ID
    assert workspace["workspace_instance_id"] == replay["workspace_instance_id"] == WORKSPACE_ID
    assert workspace["local_state_release_id"] == "a" * 64
    assert workspace["local_state_release_manifest_digest"] == "b" * 64
    assert workspace["trellis_task_layout"]["layout_digest"] == layout.layout_digest  # type: ignore[index]
    assert replay["entries"] == {}
    assert journal["phase"] == "complete"
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.load_and_validate(workspace) == workspace
    assert catalog.load_and_validate(replay) == replay
    assert catalog.load_and_validate(journal) == journal
    assert canonical_json_bytes(manifest) == before
    assert not (project / ".trellis").exists()


def test_duplicate_registration_and_invalid_committed_pair_fail_closed(tmp_path: Path) -> None:
    from agent_stack.runtime.errors import RuntimeFailure

    project = _project(tmp_path)
    _register(project, tmp_path)
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_REGISTRATION_REQUIRED"):
        _register(project, tmp_path)

    replay_path = project / ".agent-workflow/local/approval-replay.json"
    replay = _read(replay_path)
    replay["workspace_instance_id"] = "44444444-4444-4444-8444-444444444444"
    replay_path.write_bytes(canonical_json_bytes(replay))
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_REGISTRATION_REQUIRED"):
        _register(project, tmp_path)


def test_tracked_local_path_or_missing_managed_ignore_marker_is_rejected(
    tmp_path: Path,
) -> None:
    from agent_stack.runtime.errors import RuntimeFailure

    tracked_project = _project(tmp_path / "tracked")
    tracked_path = tracked_project / ".agent-workflow/local/workspace.json"
    tracked_path.parent.mkdir(parents=True)
    tracked_path.write_text("tracked\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tracked_project), "add", "-f", str(tracked_path)], check=True
    )
    tracked_path.unlink()
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_REGISTRATION_REQUIRED"):
        _register(tracked_project, tmp_path / "tracked")

    ignored_project = _project(tmp_path / "ignore", valid_ignore=False)
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_REGISTRATION_REQUIRED"):
        _register(ignored_project, tmp_path / "ignore")


def test_maintenance_or_unrelated_transaction_blocks_registration(tmp_path: Path) -> None:
    from agent_stack.runtime.errors import RuntimeFailure

    maintenance_project = _project(tmp_path / "maintenance")
    (maintenance_project / ".agent-workflow/maintenance.json").write_text(
        "{}", encoding="utf-8"
    )
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_REGISTRATION_RECOVERY_REQUIRED"):
        _register(maintenance_project, tmp_path / "maintenance")

    transaction_project = _project(tmp_path / "transaction")
    unrelated = transaction_project / ".agent-workflow/transactions/unrelated.json"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text('{"phase":"applying"}', encoding="utf-8")
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_REGISTRATION_RECOVERY_REQUIRED"):
        _register(transaction_project, tmp_path / "transaction")
