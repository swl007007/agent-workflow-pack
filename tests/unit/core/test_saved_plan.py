from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.core.canonical import canonical_json_bytes
from agent_stack.core.errors import CoreFailure
from agent_stack.core.saved_plan import (
    SavedPlanEnvelope,
    compute_candidate_manifest_digest,
    compute_journal_binding_digest,
    compute_plan_core_digest,
    compute_plan_digest,
    validate_plan_core,
    validate_saved_plan_envelope,
)
from agent_stack.core.schema_catalog import SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]
TX_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PROJECT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
WORKSPACE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _release(seed: str) -> dict[str, str]:
    return {"release_id": seed * 64, "release_manifest_digest": seed * 64}


def _plan_core(operation: str) -> dict[str, object]:
    common: dict[str, object] = {
        "operation": operation,
        "transaction_id": TX_ID,
        "candidate_release": _release("a" if operation != "upgrade" else "b"),
        "release_trust_policy_id": "github-immutable-release-v1",
        "release_trust_policy_digest": "1" * 64,
        "profile_digest": "2" * 64,
        "lock_digest": "3" * 64,
        "artifact_bundle_digest": "4" * 64,
        "pack_version": "0.1.0",
        "source_trellis_task_layout_digest": "5" * 64,
        "target_trellis_task_layout_digest": "5" * 64,
        "source_schema_bundle_digest": "6" * 64,
        "target_schema_bundle_digest": "6" * 64,
        "task_quiescence_snapshot": {},
        "task_findings": {"schema_id": "agent-workflow.task-findings", "schema_version": 1, "findings": []},
        "task_quiescence_digest": "7" * 64,
        "candidate_impact": {
            "schema_id": "agent-workflow.candidate-impact",
            "schema_version": 1,
            "impact_kind": "none",
            "authority_changes": [],
            "surface_changes": [],
            "candidate_impact_digest": "8" * 64,
        },
        "workspace_state_evaluation": {
            "evaluator_id": "agent-workflow.workspace-state-quiescence",
            "evaluator_version": 1,
            "task_quiescence": "quiescent",
            "blockers": [],
        },
        "task_gate_evaluation": {
            "evaluator_id": "agent-workflow.task-gate",
            "evaluator_version": 1,
            "blockers": [],
            "primary_evaluator_blocker": None,
        },
        "preconditions": [],
        "candidate_file_states": [],
        "candidate_local_state_contract": {},
        "provider_approval_bindings": [],
        "recovery_runtime": {
            "release_id": "a" * 64,
            "release_manifest_digest": "a" * 64,
            "runtime_role": "committed",
        },
        "candidate_manifest_generation": 1,
    }
    if operation == "init":
        common.update(
            {
                "project_id_precondition": "absent",
                "candidate_project_id": PROJECT_ID,
                "workspace_instance_precondition": "absent",
                "candidate_workspace_instance_id": WORKSPACE_ID,
                "manifest_precondition": "absent",
                "approval_replay_precondition": "absent",
                "empty_replay_ledger_candidate_digest": "9" * 64,
                "target_path_digest": "a" * 64,
            }
        )
    else:
        common.update(
            {
                "project_id": PROJECT_ID,
                "workspace_instance_id": WORKSPACE_ID,
                "manifest_generation": 0,
                "manifest_digest": "b" * 64,
                "installed_release": _release("a"),
            }
        )
    if operation == "repair":
        common["repair_surface_ids"] = ["skill:tdd"]
    if operation == "upgrade":
        common.update(
            {
                "compatibility_identity": "c" * 64,
                "target_trellis_task_layout_digest": "d" * 64,
                "target_schema_bundle_digest": "e" * 64,
            }
        )
    return common


def _envelope(operation: str = "sync") -> tuple[SavedPlanEnvelope, dict[str, object]]:
    core = _plan_core(operation)
    plan_core_digest = compute_plan_core_digest(core)
    immutable_header: dict[str, object] = {
        "transaction_id": TX_ID,
        "operation": operation,
        "plan_core_digest": plan_core_digest,
        "candidate_manifest_generation": 1,
        "task_quiescence_digest": "7" * 64,
        "recovery_runtime": core["recovery_runtime"],
    }
    if operation == "init":
        immutable_header.update(
            {
                "candidate_project_id": PROJECT_ID,
                "candidate_workspace_instance_id": WORKSPACE_ID,
                "baseline_manifest_digest": "absent",
            }
        )
    else:
        immutable_header.update(
            {
                "project_id": PROJECT_ID,
                "workspace_instance_id": WORKSPACE_ID,
                "baseline_manifest_digest": "b" * 64,
            }
        )
    journal_binding_digest = compute_journal_binding_digest(immutable_header)
    candidate_manifest = {
        "schema_id": "agent-workflow.manifest",
        "schema_version": 1,
        "generation": 1,
        "last_transaction_binding_digest": journal_binding_digest,
    }
    candidate_manifest_digest = compute_candidate_manifest_digest(candidate_manifest)
    candidate_manifest_file_state = {
        "path": ".agent-workflow/manifest.json",
        "byte_hash": candidate_manifest_digest,
        "mode": "0644",
        "file_type": "regular",
        "non_symlink": True,
    }
    without_plan_digest = {
        "schema_id": "agent-workflow.saved-plan",
        "schema_version": 1,
        "operation": operation,
        "plan_core": core,
        "plan_core_digest": plan_core_digest,
        "immutable_header": immutable_header,
        "journal_binding_digest": journal_binding_digest,
        "candidate_manifest_digest": candidate_manifest_digest,
        "candidate_manifest_file_state": candidate_manifest_file_state,
    }
    envelope = SavedPlanEnvelope(
        operation=operation,
        plan_core=core,
        plan_core_digest=plan_core_digest,
        immutable_header=immutable_header,
        journal_binding_digest=journal_binding_digest,
        candidate_manifest_digest=candidate_manifest_digest,
        candidate_manifest_file_state=candidate_manifest_file_state,
        plan_digest=compute_plan_digest(without_plan_digest),
    )
    return envelope, candidate_manifest


@pytest.mark.parametrize("operation", ["init", "sync", "repair", "upgrade"])
def test_all_four_saved_plan_operation_branches_are_closed(operation: str) -> None:
    core = _plan_core(operation)

    validate_plan_core(core)

    invalid = dict(core)
    invalid["project_id_precondition" if operation != "init" else "project_id"] = "absent"
    with pytest.raises(CoreFailure, match="AWP_SAVED_PLAN_GRAPH_INVALID"):
        validate_plan_core(invalid)


def test_digest_dag_is_acyclic_and_fully_revalidated() -> None:
    envelope, candidate_manifest = _envelope("upgrade")

    validate_saved_plan_envelope(envelope.to_document(), candidate_manifest)

    changed = dict(envelope.to_document())
    changed["journal_binding_digest"] = "0" * 64
    with pytest.raises(CoreFailure, match="AWP_SAVED_PLAN_MISMATCH"):
        validate_saved_plan_envelope(changed, candidate_manifest)


def test_reverse_edges_and_derived_fields_are_rejected() -> None:
    for field in (
        "plan_core_digest",
        "journal_binding_digest",
        "candidate_manifest_digest",
        "plan_digest",
        "candidate_manifest",
    ):
        core = _plan_core("sync")
        core[field] = "0" * 64
        with pytest.raises(CoreFailure, match="AWP_SAVED_PLAN_GRAPH_INVALID"):
            compute_plan_core_digest(core)


def test_candidate_manifest_digest_is_over_canonical_utf8_bytes() -> None:
    manifest = {"b": 2, "a": 1}
    assert compute_candidate_manifest_digest(manifest) == __import__("hashlib").sha256(
        canonical_json_bytes(manifest)
    ).hexdigest()


def test_saved_plan_schema_is_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.supported_versions("agent-workflow.saved-plan") == (1,)
    envelope, _ = _envelope("sync")
    catalog.load_and_validate(envelope.to_document())
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**envelope.to_document(), "unknown": True})
