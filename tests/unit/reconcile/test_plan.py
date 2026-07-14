from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from agent_stack.core.api import (
    CandidateImpact,
    TaskSnapshotAndFindings,
    digest,
    validate_saved_plan_envelope,
)
from agent_stack.core.impact import SurfaceChange
from agent_stack.reconcile.api import plan_reconcile
from agent_stack.reconcile.plan import render_candidate_manifest
from agent_stack.reconcile.models import StagedRenderTree
from tests.unit.reconcile.test_ownership import definition, staged, state
from tests.unit.reconcile.test_render import make_ir


TX_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PROJECT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
WORKSPACE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def empty_task_state() -> TaskSnapshotAndFindings:
    findings = {
        "schema_id": "agent-workflow.task-findings",
        "schema_version": 1,
        "findings": [],
    }
    projection = {
        "schema_id": "agent-workflow.task-quiescence-snapshot",
        "schema_version": 1,
        "source_layout_digest": "5" * 64,
        "target_layout_digest": "5" * 64,
        "source_schema_bundle_digest": "6" * 64,
        "target_schema_bundle_digest": "6" * 64,
        "tasks": [],
        "metadata": [],
        "task_journals": [],
        "finding_ids": [],
    }
    task_digest = digest("agent-workflow.task-quiescence.v1", projection)
    snapshot = {**projection, "task_quiescence_digest": task_digest}
    return TaskSnapshotAndFindings(
        MappingProxyType(snapshot), MappingProxyType(findings), task_digest
    )


def ir_for(operation: str, record) -> object:
    impact = CandidateImpact("none", (), (), False, "8" * 64)
    base = make_ir([], [])
    return replace(
        base,
        operation=operation,
        release_contract=MappingProxyType(
            {
                "release_id": ("b" if operation == "upgrade" else "a") * 64,
                "release_manifest_digest": ("b" if operation == "upgrade" else "a") * 64,
                "release_trust_policy_id": "github-immutable-release-v1",
                "release_trust_policy_digest": "1" * 64,
                "version": "0.1.1" if operation == "upgrade" else "0.1.0",
            }
        ),
        resolved_profile=MappingProxyType({"profile_id": "default"}),
        authority_digests=MappingProxyType(
            {"profile": "2" * 64, "workflow-lock": "3" * 64, "artifact-bundle": "4" * 64}
        ),
        artifact_definitions=(MappingProxyType(definition(record.definition_id, record.path)),),
        candidate_impact=impact,
        workspace_state_evaluation=MappingProxyType(
            {
                "evaluator_id": "agent-workflow.workspace-state-quiescence",
                "evaluator_version": 1,
                "task_quiescence": "quiescent",
                "blockers": [],
            }
        ),
        task_gate_evaluation=MappingProxyType(
            {
                "evaluator_id": "agent-workflow.task-gate",
                "evaluator_version": 1,
                "blockers": [],
                "primary_evaluator_blocker": None,
            }
        ),
    )


def manifest_for(record, *, generation: int = 2) -> dict[str, object]:
    current = state(record.path, b"before\n")
    return {
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "generation": generation,
        "pack_version": "0.1.0",
        "release_id": "a" * 64,
        "release_manifest_digest": "a" * 64,
        "release_trust_policy_id": "github-immutable-release-v1",
        "release_trust_policy_digest": "1" * 64,
        "profile": "default",
        "profile_digest": "2" * 64,
        "lock_digest": "3" * 64,
        "artifact_bundle_digest": "4" * 64,
        "local_state_contract": {"contract_digest": "9" * 64},
        "platforms": [],
        "last_transaction_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "last_transaction_binding_digest": "d" * 64,
        "previous_manifest_digest": "e" * 64,
        "files": [
            {
                "path": record.path,
                "definition_id": record.definition_id,
                "ownership": "managed",
                "file_state": current,
                "managed_block_hash": "canonical-null",
                "created_once": False,
            }
        ],
    }


def observed_for(record, operation: str) -> dict[str, object]:
    observed: dict[str, object] = {
        "transaction_id": TX_ID,
        "workspace_instance_id": WORKSPACE_ID,
        "manifest_digest": "f" * 64,
        "files": {
            record.path: {
                "state": state(record.path, None if operation == "init" else b"before\n"),
                "content": None if operation == "init" else "before\n",
            }
        },
        "candidate_local_state_contract": {"contract_digest": "9" * 64},
        "provider_approval_bindings": [],
        "recovery_runtime": {
            "release_id": ("b" if operation == "upgrade" else "a") * 64,
            "release_manifest_digest": ("b" if operation == "upgrade" else "a") * 64,
            "runtime_role": "candidate" if operation == "upgrade" else "committed",
        },
    }
    if operation == "init":
        observed.update(
            {
                "candidate_project_id": PROJECT_ID,
                "candidate_workspace_instance_id": WORKSPACE_ID,
                "empty_replay_ledger_candidate_digest": "7" * 64,
                "target_path_digest": "a" * 64,
            }
        )
    if operation == "upgrade":
        observed["compatibility_identity"] = "c" * 64
    return observed


@pytest.mark.parametrize("operation", ["init", "sync", "upgrade"])
def test_plan_reconcile_builds_closed_operation_envelope(operation: str) -> None:
    record = staged("generated/config.txt", b"after\n", definition_id="config")
    manifest = None if operation == "init" else manifest_for(record)
    envelope = plan_reconcile(
        ir_for(operation, record),
        StagedRenderTree((record,), "a" * 64),
        manifest,
        observed_for(record, operation),
        empty_task_state(),
    )
    candidate_manifest = render_candidate_manifest(envelope)

    validate_saved_plan_envelope(envelope.to_document(), candidate_manifest)
    assert envelope.operation == operation
    assert envelope.plan_core["candidate_file_states"]
    assert envelope.plan_core["preconditions"]


def test_plan_reconcile_refuses_ownership_or_task_gate_blockers() -> None:
    record = staged("generated/config.txt", b"after\n", definition_id="config")
    ir = ir_for("sync", record)
    blocked_ir = replace(
        ir,
        task_gate_evaluation=MappingProxyType(
            {
                "evaluator_id": "agent-workflow.task-gate",
                "evaluator_version": 1,
                "blockers": [{"code": "AWP_ACTIVE_TASK_BLOCK"}],
                "primary_evaluator_blocker": "AWP_ACTIVE_TASK_BLOCK",
            }
        ),
    )
    with pytest.raises(Exception, match="AWP_ACTIVE_TASK_BLOCK"):
        plan_reconcile(
            blocked_ir,
            StagedRenderTree((record,), "a" * 64),
            manifest_for(record),
            observed_for(record, "sync"),
            empty_task_state(),
        )


def test_true_noop_sync_has_no_non_manifest_candidate_changes() -> None:
    record = staged("generated/config.txt", b"before\n", definition_id="config")
    envelope = plan_reconcile(
        ir_for("sync", record),
        StagedRenderTree((record,), "a" * 64),
        manifest_for(record),
        observed_for(record, "sync"),
        empty_task_state(),
    )

    assert envelope.plan_core["candidate_file_states"] == []


def test_repair_plan_uses_restorative_surface_branch() -> None:
    record = staged("generated/config.txt", b"before\n", definition_id="config")
    ir = ir_for("repair", record)
    surface_digest = "4" * 64
    repair_impact = CandidateImpact(
        "runtime-visible",
        (),
        (
            SurfaceChange(
                record.surface_id,
                "repair",
                surface_digest,
                "canonical-null",
                surface_digest,
            ),
        ),
        False,
        "8" * 64,
    )
    ir = replace(ir, candidate_impact=repair_impact)
    observed = observed_for(record, "repair")
    observed["files"] = {
        record.path: {
            "state": state(record.path, b"drifted\n"),
            "content": "drifted\n",
        }
    }

    envelope = plan_reconcile(
        ir,
        StagedRenderTree((record,), "a" * 64),
        manifest_for(record),
        observed,
        empty_task_state(),
    )

    assert envelope.plan_core["repair_surface_ids"] == [record.surface_id]
    file_precondition = envelope.plan_core["preconditions"][1]
    assert file_precondition["ownership_decision"]["action"] == "restorative-repair"
