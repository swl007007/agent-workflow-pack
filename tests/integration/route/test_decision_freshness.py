from __future__ import annotations

import copy
import dataclasses

import pytest

from agent_stack.core.api import digest
from agent_stack.route.calculator import RouteCalculationInputs, calculate_route
from agent_stack.route.errors import RouteFailure
from agent_stack.route.verifier import verify_route_decision
from tests.unit.route.test_calculator import authorities, intent


def test_complete_replay_accepts_policy_consistent_hand_constructed_envelope() -> None:
    auth = authorities()
    calculated = calculate_route(
        "execute-light", RouteCalculationInputs(intent=intent()), auth
    )
    reconstructed = copy.deepcopy(dict(calculated))

    verified = verify_route_decision(reconstructed, auth, "execute-light")

    assert verified["verification_kind"] == "verified-execute-light"
    assert verified["decision_digest"] == calculated["decision_digest"]


def test_consumer_workspace_adapter_and_policy_freshness_are_rechecked() -> None:
    auth = authorities()
    light = calculate_route(
        "execute-light", RouteCalculationInputs(intent=intent()), auth
    )
    with pytest.raises(RouteFailure, match="AWP_ROUTE_OPERATION_MISMATCH"):
        verify_route_decision(light, auth, "task-admit")
    with pytest.raises(RouteFailure, match="AWP_ROUTE_POLICY_MISMATCH"):
        verify_route_decision(
            light, dataclasses.replace(auth, workspace_instance_id="8f066113-9c71-420e-b21d-db2b2e9c7e7f"), "execute-light"
        )
    with pytest.raises(RouteFailure, match="AWP_ROUTE_POLICY_MISMATCH"):
        verify_route_decision(
            light, dataclasses.replace(auth, adapter_version="1.0.1"), "execute-light"
        )

    classified = calculate_route(
        "classify-only", RouteCalculationInputs(candidate_signals=()), auth
    )
    with pytest.raises(RouteFailure, match="classify-only"):
        verify_route_decision(classified, auth, "execute-light")


def test_integrated_ref_task_state_and_surface_freshness_are_rechecked() -> None:
    auth = authorities()
    decision = calculate_route(
        "create-integrated-task",
        RouteCalculationInputs(
            intent=intent(requested_mode="trellis-native"),
            requested_task_ref=".trellis/tasks/example",
        ),
        auth,
    )
    changed_inventory = {
        "tasks": [
            {
                "task_id": "8f066113-9c71-420e-b21d-db2b2e9c7e7f",
                "task_ref": ".trellis/tasks/example",
            }
        ],
        "unfinished_task_journals": [],
        "active_pointers": [],
    }
    stale = dataclasses.replace(
        auth,
        task_inventory=changed_inventory,
        task_state_digest=digest(
            "agent-workflow.route-task-state.v1", changed_inventory
        ),
    )
    with pytest.raises(RouteFailure, match="AWP_ROUTE_TASK_STATE_STALE"):
        verify_route_decision(decision, stale, "task-admit")

    changed_surface = tuple(
        {**surface, "surface_digest": "f" * 64}
        if surface["surface_id"] == "runtime-control-plane"
        else surface
        for surface in auth.task_surface_closures["trellis-native"]
    )
    surface_stale = dataclasses.replace(
        auth,
        task_surface_closures={
            **auth.task_surface_closures,
            "trellis-native": changed_surface,
        },
    )
    with pytest.raises(RouteFailure, match="AWP_ROUTE_TASK_STATE_STALE"):
        verify_route_decision(decision, surface_stale, "task-admit")
