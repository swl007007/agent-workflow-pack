from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import agent_stack.reconcile.apply as apply_module
from agent_stack.core.api import canonical_json_bytes
from agent_stack.reconcile.api import apply_plan, plan_reconcile, recover_transaction
from agent_stack.reconcile.errors import RendererFailure
from agent_stack.reconcile.models import StagedRenderTree
from tests.integration.reconcile.apply_helpers import RecordingScanner, scanner_inputs
from tests.unit.reconcile.test_ownership import staged, state
from tests.unit.reconcile.test_plan import (
    PROJECT_ID,
    WORKSPACE_ID,
    empty_task_state,
    ir_for,
    observed_for,
)


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _init_case(root: Path):
    record = staged("generated/config.txt", b"created\n", definition_id="config")
    task_state = empty_task_state()
    observed = observed_for(record, "init")
    contract_projection = {
        "release_id": "a" * 64,
        "release_version": "0.1.0",
        "workspace_schema": 1,
        "approval_replay_schema": 1,
        "task_outbox_schema": 1,
        "trellis_task_layout_digest": "5" * 64,
    }
    contract = {
        **contract_projection,
        "contract_digest": hashlib.sha256(
            canonical_json_bytes(contract_projection)
        ).hexdigest(),
    }
    observed["candidate_local_state_contract"] = contract
    empty_replay = {
        "schema_id": "agent-workflow.approval-replay",
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "workspace_instance_id": WORKSPACE_ID,
        "entries": {},
    }
    observed["empty_replay_ledger_candidate_digest"] = hashlib.sha256(
        canonical_json_bytes(empty_replay)
    ).hexdigest()
    envelope = plan_reconcile(
        ir_for("init", record),
        StagedRenderTree((record,), "a" * 64),
        None,
        observed,
        task_state,
    )
    source_layout, target_layout, source_schemas, target_schemas = scanner_inputs()
    approval = {
        "plan_digest": envelope.plan_digest,
        "project_root": str(root),
        "bootstrap_lock_root": str(root.parent / ".bootstrap-locks"),
        "source_layout": source_layout,
        "target_layout": target_layout,
        "source_schemas": source_schemas,
        "target_schemas": target_schemas,
    }
    return envelope, task_state, approval


def test_first_init_commits_manifest_workspace_and_replay_as_one_contract(
    tmp_path: Path,
) -> None:
    envelope, task_state, approval = _init_case(tmp_path)

    result = apply_plan(
        envelope,
        approval,
        scanner=RecordingScanner([task_state, task_state]),
    )

    assert result["committed"] is True
    manifest = _read(tmp_path / ".agent-workflow/manifest.json")
    workspace = _read(tmp_path / ".agent-workflow/local/workspace.json")
    replay = _read(tmp_path / ".agent-workflow/local/approval-replay.json")
    assert manifest["project_id"] == workspace["project_id"] == replay["project_id"]
    assert workspace["workspace_instance_id"] == replay["workspace_instance_id"]
    assert workspace["local_state_contract_digest"] == manifest["local_state_contract"][
        "contract_digest"
    ]
    assert hashlib.sha256(canonical_json_bytes(replay)).hexdigest() == envelope.plan_core[
        "empty_replay_ledger_candidate_digest"
    ]
    assert state("generated/config.txt", b"created\n")["byte_hash"] == manifest[
        "files"
    ][0]["file_state"]["byte_hash"]


class InjectedTermination(BaseException):
    pass


def _interrupt_init(
    root: Path, monkeypatch: pytest.MonkeyPatch, killpoint: str
):
    envelope, task_state, approval = _init_case(root)

    def terminate(point: str) -> None:
        if point == killpoint:
            raise InjectedTermination(point)

    monkeypatch.setattr(apply_module, "_crash_at", terminate)
    with pytest.raises(InjectedTermination):
        apply_plan(
            envelope,
            approval,
            scanner=RecordingScanner([task_state, task_state]),
        )
    return envelope, task_state, approval


@pytest.mark.parametrize("killpoint", ["after_workspace", "after_replay"])
def test_first_init_precommit_crash_rolls_back_manifest_and_local_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, killpoint: str
) -> None:
    envelope, task_state, approval = _interrupt_init(tmp_path, monkeypatch, killpoint)

    result = recover_transaction(
        str(envelope.plan_core["transaction_id"]),
        "rollback",
        root=tmp_path,
        scanner=RecordingScanner([task_state]),
        scanner_context=approval,
    )

    assert result["rolled_back"] is True
    assert not (tmp_path / ".agent-workflow/manifest.json").exists()
    assert not (tmp_path / ".agent-workflow/local/workspace.json").exists()
    assert not (tmp_path / ".agent-workflow/local/approval-replay.json").exists()


def test_first_init_postcommit_crash_keeps_complete_contract_and_only_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    envelope, task_state, approval = _interrupt_init(
        tmp_path, monkeypatch, "after_manifest"
    )

    with pytest.raises(RendererFailure, match="AWP_RECONCILE_RECOVERY_REQUIRED"):
        recover_transaction(
            str(envelope.plan_core["transaction_id"]),
            "rollback",
            root=tmp_path,
            scanner=RecordingScanner([task_state]),
            scanner_context=approval,
        )
    result = recover_transaction(
        str(envelope.plan_core["transaction_id"]),
        "resume",
        root=tmp_path,
        scanner=RecordingScanner([task_state]),
        scanner_context=approval,
    )

    assert result["committed"] is True
    assert (tmp_path / ".agent-workflow/manifest.json").is_file()
    assert (tmp_path / ".agent-workflow/local/workspace.json").is_file()
    assert (tmp_path / ".agent-workflow/local/approval-replay.json").is_file()
