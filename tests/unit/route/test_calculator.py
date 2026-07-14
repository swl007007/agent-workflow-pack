from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from agent_stack.core.api import digest
from agent_stack.route.calculator import (
    RouteCalculationInputs,
    VerifiedRouteAuthoritySnapshot,
    calculate_route,
)
from agent_stack.route.errors import RouteFailure
from agent_stack.route.intent import validate_task_intent
from agent_stack.route.signals import load_compiled_policy


ROOT = Path(__file__).resolve().parents[3]
PROJECT_ID = "4e3d0530-901a-4f65-8c41-5faf017026c4"
WORKSPACE_ID = "5f477c7f-a1dc-4a16-8f75-39f153170222"


def task_inventory() -> dict[str, object]:
    return {"tasks": [], "unfinished_task_journals": [], "active_pointers": []}


def authorities() -> VerifiedRouteAuthoritySnapshot:
    policy = load_compiled_policy(ROOT / "catalog/route-policy.yaml")
    inventory = task_inventory()
    surfaces = (
        {"surface_id": "platform-adapter:codex", "surface_digest": "1" * 64},
        {"surface_id": "runtime-control-plane", "surface_digest": "2" * 64},
        {"surface_id": "surface-registry", "surface_digest": "3" * 64},
    )
    return VerifiedRouteAuthoritySnapshot(
        project_id=PROJECT_ID,
        workspace_instance_id=WORKSPACE_ID,
        manifest_generation=1,
        manifest_digest="4" * 64,
        profile_digest="5" * 64,
        lock_digest="6" * 64,
        artifact_bundle_digest="7" * 64,
        policy=policy,
        policy_digest=policy.policy_digest,
        platform="codex",
        adapter_id="codex",
        adapter_version="1.0.0",
        router_contract_version=1,
        entry_owners={
            "native-light": "sol-native",
            "trellis-native": "trellis-implement",
            "speckit-superpowers": "heavy-development-router",
        },
        task_inventory=inventory,
        task_state_digest=digest("agent-workflow.route-task-state.v1", inventory),
        task_surface_closures={
            "trellis-native": surfaces,
            "speckit-superpowers": surfaces,
        },
        maintenance=False,
        unfinished_task_transaction=False,
    )


def intent(*, signals=(), requested_mode=None):
    policy = load_compiled_policy(ROOT / "catalog/route-policy.yaml")
    return validate_task_intent(
        {
            "schema_id": "agent-workflow.task-intent",
            "schema_version": 1,
            "intent_id": "intent-id",
            "title": "Task",
            "objective": "Do the work",
            "requested_mode": requested_mode,
            "acceptance_summary": "Tests pass",
            "signals": list(signals),
        },
        policy=policy,
    )


def test_closed_operation_route_pairs_and_intent_only_executable_signals() -> None:
    auth = authorities()
    classified = calculate_route(
        "classify-only", RouteCalculationInputs(candidate_signals=()), auth
    )
    assert classified["route"] == "native-light"
    assert "intent_id" not in classified

    light = calculate_route(
        "execute-light", RouteCalculationInputs(intent=intent()), auth
    )
    assert light["route"] == "native-light"
    assert light["intent_id"] == "intent-id"

    with pytest.raises(RouteFailure, match="AWP_ROUTE_OPERATION_MISMATCH"):
        calculate_route(
            "execute-light",
            RouteCalculationInputs(intent=intent(signals=("public_contract_change",))),
            auth,
        )
    with pytest.raises(RouteFailure, match="AWP_ROUTE_OPERATION_MISMATCH"):
        calculate_route(
            "create-integrated-task", RouteCalculationInputs(intent=intent()), auth
        )
    with pytest.raises(RouteFailure, match="Intent is the sole executable signal source"):
        calculate_route(
            "execute-light",
            RouteCalculationInputs(
                intent=intent(), candidate_signals=("public_contract_change",)
            ),
            auth,
        )


def test_integrated_decisions_bind_unique_task_challenge_surface_and_uuidv5_identity() -> None:
    auth = authorities()
    inputs = RouteCalculationInputs(
        intent=intent(requested_mode="trellis-native"),
        requested_task_ref=".trellis/tasks/example",
    )

    first = calculate_route("create-integrated-task", inputs, auth)
    second = calculate_route("create-integrated-task", inputs, auth)

    assert first["route"] == "trellis-native"
    assert uuid.UUID(first["requested_task_id"]).version == 4
    assert len(first["approval_challenge"]) == 64
    assert first["requested_task_id"] != second["requested_task_id"]
    assert first["approval_challenge"] != second["approval_challenge"]
    assert first["task_creation_approval"] == "required"
    assert first["task_contract_surfaces_digest"] == digest(
        "agent-workflow.task-surfaces.v1", first["task_contract_surfaces"]
    )
    namespace = uuid.UUID("c7c2dd65-7073-5e38-8004-fe6b9b4af8f5")
    assert first["decision_id"] == str(uuid.uuid5(namespace, first["route_payload_digest"]))


def test_maintenance_unfinished_transaction_and_ref_conflict_block_calculation() -> None:
    auth = authorities()
    inputs = RouteCalculationInputs(
        intent=intent(requested_mode="trellis-native"),
        requested_task_ref=".trellis/tasks/example",
    )
    with pytest.raises(RouteFailure, match="maintenance"):
        calculate_route("create-integrated-task", inputs, auth.__class__(**{**auth.__dict__, "maintenance": True}))
    with pytest.raises(RouteFailure, match="unfinished task transaction"):
        calculate_route(
            "create-integrated-task",
            inputs,
            auth.__class__(**{**auth.__dict__, "unfinished_task_transaction": True}),
        )
    conflict_inventory = {
        "tasks": [{"task_id": "8f066113-9c71-420e-b21d-db2b2e9c7e7f", "task_ref": ".trellis/tasks/example"}],
        "unfinished_task_journals": [],
        "active_pointers": [],
    }
    conflict = auth.__class__(
        **{
            **auth.__dict__,
            "task_inventory": conflict_inventory,
            "task_state_digest": digest(
                "agent-workflow.route-task-state.v1", conflict_inventory
            ),
        }
    )
    with pytest.raises(RouteFailure, match="task ref"):
        calculate_route("create-integrated-task", inputs, conflict)
