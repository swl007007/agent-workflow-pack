from __future__ import annotations

import inspect

from agent_stack.route import api
from agent_stack.route.errors import RouteFailure


def test_public_route_api_has_the_frozen_callable_signatures() -> None:
    expected = {
        "calculate_route": ["operation", "normalized_inputs", "authorities"],
        "verify_route_decision": ["decision", "current_authorities", "consumer"],
        "verify_task_creation_approval": [
            "proof",
            "decision",
            "capability",
            "runtime_context",
        ],
        "derive_task_surface_closure": ["route", "platform", "entry_owner", "registry"],
        "measure_capability_manifest": ["inputs"],
        "project_platform_adapter": ["ir", "adapter"],
        "invoke_execute_light": ["decision", "runtime_context"],
        "invoke_integrated_wrapper": ["invocation"],
    }

    assert {
        name: list(inspect.signature(getattr(api, name)).parameters) for name in expected
    } == expected


def test_route_failure_namespace_and_exit_categories_are_closed() -> None:
    failure = RouteFailure("AWP_ROUTE_POLICY_MISMATCH", "stale")

    assert failure.exit_code == 40
    assert failure.to_document() == {
        "schema_id": "agent-workflow.route-failure",
        "schema_version": 1,
        "code": "AWP_ROUTE_POLICY_MISMATCH",
        "exit_code": 40,
        "message": "stale",
        "details": {},
    }
    unknown = RouteFailure("AWP_NOT_ROUTE", "bad")
    assert unknown.exit_code == 70
