from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_stack.core.api import digest
from agent_stack.providers.approval import provider_risk_report_digest, verify_provider_approval
from agent_stack.providers.errors import ProviderFailure
from agent_stack.providers.models import ProviderPlan


NOW = datetime(2026, 7, 13, 16, 0, tzinfo=UTC)


def _plan() -> ProviderPlan:
    return ProviderPlan(
        provider_id="trellis-initializer",
        provider_version="1.0.0",
        provider_artifact_digest="a" * 64,
        command_digest="b" * 64,
        command={"executable_id": "trellis:init", "arguments": []},
        project_id="11111111-1111-4111-8111-111111111111",
        workspace_instance_id="22222222-2222-4222-8222-222222222222",
        workflow_lock_digest="c" * 64,
        input_digests=("d" * 64,),
        requested_controls={"network-isolation": "approval-required"},
        measured_isolation_gaps=("network-isolation",),
        approval_challenge="e" * 64,
        prospective_transaction_id="33333333-3333-4333-8333-333333333333",
        deterministic_output_contract={"expected_content_root_digest": "f" * 64},
    )


def _capability(level: str = "enforced") -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.capability-manifest",
        "schema_version": 1,
        "platform": "codex",
        "adapter_id": "codex",
        "adapter_version": "1.0.0",
        "harness_id": "codex-cli",
        "harness_version": "1.2.3",
        "probe_suite_id": "approval-probes",
        "probe_suite_version": 1,
        "capabilities": {"provider_exception_approval": level},
        "approval_verifiers": {
            "approve-provider-execution": {
                "verifier_id": "codex-human-verifier",
                "verifier_version": "1.0.0",
                "receipt_prefix": "human-receipt:",
            }
        },
        "evidence_digest": "9" * 64,
    }


def _proof(plan: ProviderPlan) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.provider-approval",
        "schema_version": 1,
        "approval_id": "44444444-4444-4444-8444-444444444444",
        "verifier_id": "codex-human-verifier",
        "verifier_version": "1.0.0",
        "platform": "codex",
        "harness_version": "1.2.3",
        "actor": {"id": "user-123", "kind": "direct-human"},
        "issued_at": (NOW - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "workspace_instance_id": plan.workspace_instance_id,
        "operation": "approve-provider-execution",
        "provider_plan_digest": plan.provider_plan_digest,
        "risk_report_digest": provider_risk_report_digest(plan),
        "prospective_transaction_id": plan.prospective_transaction_id,
        "approval_challenge": plan.approval_challenge,
        "verifier_receipt": "human-receipt:opaque-value",
    }


def test_direct_human_provider_approval_binds_the_complete_plan() -> None:
    plan = _plan()
    proof = _proof(plan)

    verified = verify_provider_approval(plan, proof, _capability(), NOW)

    assert verified.approval_id == proof["approval_id"]
    assert verified.provider_plan_digest == plan.provider_plan_digest
    assert verified.approval_digest == digest("agent-workflow.provider-approval.v1", proof)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_instance_id", "55555555-5555-4555-8555-555555555555"),
        ("operation", "approve-task-creation"),
        ("provider_plan_digest", "0" * 64),
        ("risk_report_digest", "0" * 64),
        ("prospective_transaction_id", "55555555-5555-4555-8555-555555555555"),
        ("approval_challenge", "0" * 64),
        ("verifier_id", "other-verifier"),
        ("verifier_version", "2.0.0"),
        ("platform", "claude"),
        ("harness_version", "9.0.0"),
        ("verifier_receipt", "model-authored:yes"),
    ],
)
def test_changed_or_cross_branch_approval_is_rejected(field: str, value: str) -> None:
    plan = _plan()
    proof = _proof(plan)
    proof[field] = value
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_APPROVAL_INVALID"):
        verify_provider_approval(plan, proof, _capability(), NOW)


def test_expired_future_or_model_actor_approval_is_rejected() -> None:
    plan = _plan()
    expired = _proof(plan)
    expired["expires_at"] = (NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_APPROVAL_INVALID"):
        verify_provider_approval(plan, expired, _capability(), NOW)

    future = _proof(plan)
    future["issued_at"] = (NOW + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_APPROVAL_INVALID"):
        verify_provider_approval(plan, future, _capability(), NOW)

    model = _proof(plan)
    model["actor"] = {"id": "assistant", "kind": "model"}
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_APPROVAL_INVALID"):
        verify_provider_approval(plan, model, _capability(), NOW)


def test_instruction_only_capability_cannot_authorize_exception() -> None:
    plan = _plan()
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_APPROVAL_REQUIRED"):
        verify_provider_approval(plan, _proof(plan), _capability("instruction-only"), NOW)
