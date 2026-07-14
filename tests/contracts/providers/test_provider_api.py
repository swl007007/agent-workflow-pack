from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from agent_stack.core.api import CoreFailure, SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]


def _provider_plan() -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.provider-plan",
        "schema_version": 1,
        "provider_id": "trellis-initializer",
        "provider_version": "1.0.0",
        "provider_artifact_digest": "a" * 64,
        "command_digest": "b" * 64,
        "command": {"executable_id": "trellis:init", "arguments": ["--quiet"]},
        "project_id": "11111111-1111-4111-8111-111111111111",
        "workspace_instance_id": "22222222-2222-4222-8222-222222222222",
        "workflow_lock_digest": "c" * 64,
        "input_digests": ["d" * 64],
        "requested_controls": {"network-isolation": "approval-required"},
        "measured_isolation_gaps": ["network-isolation"],
        "approval_challenge": "e" * 64,
        "prospective_transaction_id": "33333333-3333-4333-8333-333333333333",
        "deterministic_output_contract": {
            "schema_id": "agent-workflow.initializer-output-contract",
            "schema_version": 1,
            "expected_content_root_digest": "f" * 64,
        },
    }


def test_provider_api_exports_frozen_callables_and_models() -> None:
    from agent_stack.providers import api
    from agent_stack.providers.models import (
        AcquisitionRequest,
        AcquisitionResult,
        ProviderExecutionResult,
        ProviderPlan,
    )

    assert callable(api.acquire)
    assert callable(api.execute_provider)
    assert tuple(inspect.signature(api.acquire).parameters) == ("request",)
    assert tuple(inspect.signature(api.execute_provider).parameters) == ("plan", "approval")
    assert {AcquisitionRequest, AcquisitionResult, ProviderExecutionResult, ProviderPlan} <= set(
        api.PUBLIC_MODELS
    )


@pytest.mark.parametrize(
    "forbidden",
    [
        {"target_path": "project"},
        {"environment": {"HOME": "/home/user"}},
        {"source_url": "https://caller.invalid/archive"},
        {"reconcile_plan_id": "44444444-4444-4444-8444-444444444444"},
        {"unknown": True},
    ],
)
def test_provider_plan_schema_rejects_authority_leaks(forbidden: dict[str, object]) -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    plan = _provider_plan()
    plan.update(forbidden)

    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate(plan)


def test_provider_schemas_are_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.supported_versions("agent-workflow.provider-plan") == (1,)
    assert catalog.supported_versions("agent-workflow.provider-execution-result") == (1,)
    assert catalog.supported_versions("agent-workflow.provider-failure") == (1,)
    catalog.load_and_validate(_provider_plan())


def test_provider_failure_is_structured_and_sanitized() -> None:
    from agent_stack.providers.errors import ProviderFailure

    failure = ProviderFailure(
        "AWP_PROVIDER_PLAN_INVALID",
        "invalid provider plan",
        details={"field": "command"},
    )

    assert failure.exit_code == 2
    assert failure.to_document() == {
        "schema_id": "agent-workflow.provider-failure",
        "schema_version": 1,
        "code": "AWP_PROVIDER_PLAN_INVALID",
        "exit_code": 2,
        "message": "invalid provider plan",
        "details": {"field": "command"},
    }
