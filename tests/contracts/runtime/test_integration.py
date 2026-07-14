from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agent_stack._vendor import fastjsonschema
from agent_stack.core.api import digest
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.integration import validate_integration


ROOT = Path(__file__).resolve().parents[3]
TASK_ID = "5f477c7f-a1dc-4a16-8f75-39f153170222"
TRANSACTION_ID = "6ea415f2-3823-4a36-9d25-cf00b82f1f70"
WORKSPACE_ID = "78d71641-c23d-45b3-aabb-1c7f4ad8c808"
DECISION_ID = "89f80752-d34e-46c4-bbcc-2d805be9d919"
APPROVAL_ID = "9a091863-e45f-47d5-8cdd-3e916cf0ea2a"


def integration_document(*, mode: str = "trellis-native") -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "mode": mode,
        "workflow_contract": {
            "version": 1,
            "profile_digest_at_admission": "1" * 64,
            "lock_digest_at_admission": "2" * 64,
            "artifact_bundle_digest_at_admission": "3" * 64,
            "policy_digest_at_admission": "4" * 64,
            "adapter_id": "codex",
            "adapter_version_at_admission": "1.0.0",
            "route_contract_version": 1,
            "task_contract_surfaces": [
                {"surface_id": "platform-adapter:codex", "surface_digest": "5" * 64},
                {"surface_id": "runtime-control-plane", "surface_digest": "6" * 64},
                {"surface_id": "surface-registry", "surface_digest": "7" * 64},
            ],
        },
        "lifecycle": {
            "status": "active",
            "state_revision": 2,
            "admitted_at": "2026-07-13T15:00:00Z",
            "archived_at": None,
            "blocked_reason": None,
            "last_transition": {},
        },
        "admission": {
            "operation": "create-integrated-task",
            "task_id": TASK_ID,
            "task_ref": ".trellis/tasks/example",
            "intent_id": "feature-intent-id",
            "intent_digest": "8" * 64,
            "task_transaction_id": TRANSACTION_ID,
            "candidate_tree_digest": "9" * 64,
            "workspace_instance_id_at_admission": WORKSPACE_ID,
            "route_decision_id": DECISION_ID,
            "route_decision_digest": "a" * 64,
            "approval_id": APPROVAL_ID,
            "approval_challenge": "b" * 64,
            "approval_proof_digest": "c" * 64,
            "approval_verifier_id": "platform-approval-verifier",
            "approval_verifier_version": "1.0.0",
            "approved_by": "human-actor",
            "approval_mechanism": "platform-user-confirmation",
            "approved_at": "2026-07-13T15:00:00Z",
        },
    }
    if mode == "trellis-native":
        document["trellis_native"] = {"task_ref": ".trellis/tasks/example"}
    else:
        document["speckit_superpowers"] = {
            "router_contract_version": 1,
            "phase": "implementing",
            "executor_claim": None,
            "authority": {"active_feature": "feature-id"},
            "canonical_artifacts": {},
            "reference_only_artifacts": [],
            "completion_flags": {},
        }
    return document


def test_integration_schema_and_validator_accept_both_closed_branches() -> None:
    schema = json.loads(
        (ROOT / "schemas/runtime/integration.v1.json").read_text(encoding="utf-8")
    )
    validator = fastjsonschema.compile(schema)

    for mode in ("trellis-native", "speckit-superpowers"):
        document = integration_document(mode=mode)
        assert validator(copy.deepcopy(document)) == document
        verified = validate_integration(document)
        assert verified.mode == mode
        assert verified.task_id == TASK_ID
        assert verified.task_ref == ".trellis/tasks/example"
        assert verified.state_revision == 2
        assert verified.task_contract_digest == digest(
            "agent-workflow.task-contract.v1", document["workflow_contract"]
        )


def test_union_unknown_fields_and_cross_branch_fields_fail_closed() -> None:
    both = integration_document()
    both["speckit_superpowers"] = integration_document(mode="speckit-superpowers")[
        "speckit_superpowers"
    ]
    unknown = integration_document()
    unknown["model_override"] = True

    for document in (both, unknown):
        with pytest.raises(RuntimeFailure, match="AWP_TASK_TRANSITION_INVALID"):
            validate_integration(document)


def test_mandatory_surface_uuid_ref_and_surface_order_are_enforced() -> None:
    missing_surface = integration_document()
    workflow = missing_surface["workflow_contract"]
    assert isinstance(workflow, dict)
    surfaces = workflow["task_contract_surfaces"]
    assert isinstance(surfaces, list)
    workflow["task_contract_surfaces"] = surfaces[:-1]

    invalid_uuid = integration_document()
    admission = invalid_uuid["admission"]
    assert isinstance(admission, dict)
    admission["task_id"] = "not-a-uuid"

    mismatched_ref = integration_document()
    trellis = mismatched_ref["trellis_native"]
    assert isinstance(trellis, dict)
    trellis["task_ref"] = ".trellis/tasks/other"

    unsorted = integration_document()
    unsorted_workflow = unsorted["workflow_contract"]
    assert isinstance(unsorted_workflow, dict)
    unsorted_surfaces = unsorted_workflow["task_contract_surfaces"]
    assert isinstance(unsorted_surfaces, list)
    unsorted_workflow["task_contract_surfaces"] = list(reversed(unsorted_surfaces))

    for document in (missing_surface, invalid_uuid, mismatched_ref, unsorted):
        with pytest.raises(RuntimeFailure):
            validate_integration(document)


def test_lifecycle_revision_blocked_and_claim_invariants_are_closed() -> None:
    admitting = integration_document()
    lifecycle = admitting["lifecycle"]
    assert isinstance(lifecycle, dict)
    lifecycle.update(
        status="admitting",
        state_revision=1,
        admitted_at=None,
        archived_at=None,
    )
    validate_integration(admitting)

    impossible_admitting = copy.deepcopy(admitting)
    impossible_lifecycle = impossible_admitting["lifecycle"]
    assert isinstance(impossible_lifecycle, dict)
    impossible_lifecycle["state_revision"] = 2

    blocked_without_reason = integration_document()
    blocked_lifecycle = blocked_without_reason["lifecycle"]
    assert isinstance(blocked_lifecycle, dict)
    blocked_lifecycle["status"] = "blocked"

    claim_outside_implementation = integration_document(mode="speckit-superpowers")
    heavy = claim_outside_implementation["speckit_superpowers"]
    assert isinstance(heavy, dict)
    heavy["phase"] = "verifying"
    heavy["executor_claim"] = {
        "claim_id": "ab1a2974-f560-48e6-9dee-4fa27d01fb3b",
        "executor": "speckit-implement",
        "actor": "human-actor",
        "claimed_at": "2026-07-13T16:00:00Z",
        "base_revision": 1,
    }

    for document in (impossible_admitting, blocked_without_reason, claim_outside_implementation):
        with pytest.raises(RuntimeFailure, match="AWP_TASK_TRANSITION_INVALID"):
            validate_integration(document)
