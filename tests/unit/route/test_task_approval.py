from __future__ import annotations

import copy
import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from agent_stack.route.approval import (
    VerifiedPlatformRuntimeContext,
    verify_task_creation_approval,
)
from agent_stack.route.calculator import RouteCalculationInputs, calculate_route
from agent_stack.route.errors import RouteFailure
from agent_stack.route.verifier import verify_route_decision
from tests.unit.route.test_calculator import authorities, intent


NOW = datetime(2026, 7, 13, 15, 0, tzinfo=UTC)
APPROVAL_ID = "89f80752-d34e-46c4-bbcc-2d805be9d919"


class ReceiptVerifier:
    def __init__(self, expected_receipt: str) -> None:
        self.expected_receipt = expected_receipt
        self.projections: list[dict[str, object]] = []

    def __call__(self, receipt: str, projection: dict[str, object]) -> bool:
        self.projections.append(copy.deepcopy(projection))
        return receipt == self.expected_receipt


def verified_decision(*, platform: str = "codex") -> dict[str, object]:
    auth = authorities()
    surfaces = tuple(
        {
            **surface,
            "surface_id": (
                f"platform-adapter:{platform}"
                if surface["surface_id"] == "platform-adapter:codex"
                else surface["surface_id"]
            ),
        }
        for surface in auth.task_surface_closures["trellis-native"]
    )
    auth = dataclasses.replace(
        auth,
        platform=platform,
        adapter_id=platform,
        task_surface_closures={
            "trellis-native": surfaces,
            "speckit-superpowers": surfaces,
        },
    )
    calculated = calculate_route(
        "create-integrated-task",
        RouteCalculationInputs(
            intent=intent(requested_mode="trellis-native"),
            requested_task_ref=".trellis/tasks/example",
        ),
        auth,
    )
    return dict(verify_route_decision(calculated, auth, "task-admit"))


def capability(
    *,
    platform: str = "codex",
    harness_version: str = "1.2.3",
    task_gate: str = "enforced",
    confirmation: str = "enforced",
) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.capability-manifest",
        "schema_version": 1,
        "platform": platform,
        "adapter_id": platform,
        "adapter_version": "1.0.0",
        "harness_id": f"{platform}-cli",
        "harness_version": harness_version,
        "probe_suite_id": f"{platform}-approval-probes",
        "probe_suite_version": 1,
        "capabilities": {
            "task_admission_gate": task_gate,
            "direct_human_confirmation": confirmation,
        },
        "approval_verifiers": {
            "task_creation": {
                "verifier_id": f"{platform}-human-verifier",
                "verifier_version": "1.0.0",
                "actor_source": "direct-human",
                "receipt_source": f"{platform}-confirmation",
            }
        },
        "evidence_digest": "9" * 64,
    }


def runtime_context(
    verifier: ReceiptVerifier,
    *,
    platform: str = "codex",
    harness_version: str = "1.2.3",
    confirmation_capable: bool = True,
) -> VerifiedPlatformRuntimeContext:
    return VerifiedPlatformRuntimeContext(
        platform=platform,
        harness_id=f"{platform}-cli",
        harness_version=harness_version,
        confirmation_mechanism=f"{platform}-confirmation",
        direct_confirmation_capable=confirmation_capable,
        now=NOW,
        max_approval_ttl=timedelta(minutes=15),
        max_clock_skew=timedelta(seconds=60),
        receipt_verifier=verifier,
    )


def proof(decision: dict[str, object], *, platform: str = "codex") -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.approval-proof",
        "schema_version": 1,
        "approval_id": APPROVAL_ID,
        "verifier_id": f"{platform}-human-verifier",
        "verifier_version": "1.0.0",
        "platform": platform,
        "harness_version": "1.2.3",
        "actor": {"id": "human-actor", "kind": "direct-human"},
        "issued_at": (NOW - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "workspace_instance_id": decision["workspace_instance_id"],
        "operation": "create-integrated-task",
        "task_id": decision["requested_task_id"],
        "task_ref": decision["requested_task_ref"],
        "task_contract_surfaces_digest": decision["task_contract_surfaces_digest"],
        "intent_digest": decision["intent_digest"],
        "route_decision_digest": decision["decision_digest"],
        "approval_challenge": decision["approval_challenge"],
        "verifier_receipt": "codex-receipt:opaque",
    }


def test_direct_human_proof_binds_every_task_decision_field() -> None:
    decision = verified_decision()
    receipt_verifier = ReceiptVerifier("codex-receipt:opaque")
    raw = proof(decision)

    verified = verify_task_creation_approval(
        raw,
        decision,
        capability(),
        runtime_context(receipt_verifier),
    )

    assert verified["schema_id"] == "agent-workflow.approval-verification-result"
    assert verified["approval_id"] == APPROVAL_ID
    assert verified["actor_id"] == "human-actor"
    assert verified["validated_at"] == "2026-07-13T15:00:00Z"
    assert verified["proof_expires_at"] == raw["expires_at"]
    assert len(receipt_verifier.projections) == 1
    assert "verifier_receipt" not in receipt_verifier.projections[0]
    with pytest.raises(TypeError):
        verified["actor_id"] = "changed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "approve-provider-execution"),
        ("workspace_instance_id", "55555555-5555-4555-8555-555555555555"),
        ("task_id", "55555555-5555-4555-8555-555555555555"),
        ("task_ref", ".trellis/tasks/other"),
        ("task_contract_surfaces_digest", "0" * 64),
        ("intent_digest", "0" * 64),
        ("route_decision_digest", "0" * 64),
        ("approval_challenge", "0" * 64),
        ("verifier_id", "model-verifier"),
        ("verifier_version", "2.0.0"),
        ("platform", "opencode"),
        ("harness_version", "9.9.9"),
        ("verifier_receipt", "yes"),
    ],
)
def test_changed_cross_branch_or_generic_approval_is_rejected(
    field: str, value: str
) -> None:
    decision = verified_decision()
    raw = proof(decision)
    raw[field] = value

    with pytest.raises(RouteFailure, match="AWP_ROUTE_APPROVAL_INVALID"):
        verify_task_creation_approval(
            raw,
            decision,
            capability(),
            runtime_context(ReceiptVerifier("codex-receipt:opaque")),
        )


def test_unknown_model_stdin_and_provider_fields_are_rejected() -> None:
    decision = verified_decision()
    for extra in (
        {"model_authored": True},
        {"stdin_confirmation": "yes"},
        {"provider_plan_digest": "0" * 64},
    ):
        raw = {**proof(decision), **extra}
        with pytest.raises(RouteFailure, match="AWP_ROUTE_APPROVAL_INVALID"):
            verify_task_creation_approval(
                raw,
                decision,
                capability(),
                runtime_context(ReceiptVerifier("codex-receipt:opaque")),
            )


def test_expiry_future_issue_invalid_window_and_cancellation_fail_closed() -> None:
    decision = verified_decision()
    cases: list[dict[str, object]] = []
    expired = proof(decision)
    expired["expires_at"] = (NOW - timedelta(seconds=1)).isoformat().replace(
        "+00:00", "Z"
    )
    cases.append(expired)
    future = proof(decision)
    future["issued_at"] = (NOW + timedelta(minutes=2)).isoformat().replace(
        "+00:00", "Z"
    )
    cases.append(future)
    too_long = proof(decision)
    too_long["expires_at"] = (NOW + timedelta(minutes=16)).isoformat().replace(
        "+00:00", "Z"
    )
    cases.append(too_long)
    cases.append({})

    for raw in cases:
        with pytest.raises(RouteFailure):
            verify_task_creation_approval(
                raw,
                decision,
                capability(),
                runtime_context(ReceiptVerifier("codex-receipt:opaque")),
            )


def test_instruction_only_or_noninteractive_context_cannot_satisfy_strict_gate() -> None:
    decision = verified_decision()
    raw = proof(decision)
    contexts = (
        (capability(task_gate="instruction-only"), runtime_context(ReceiptVerifier("codex-receipt:opaque"))),
        (capability(confirmation="instruction-only"), runtime_context(ReceiptVerifier("codex-receipt:opaque"))),
        (capability(), runtime_context(ReceiptVerifier("codex-receipt:opaque"), confirmation_capable=False)),
    )

    for measured, context in contexts:
        with pytest.raises(RouteFailure, match="AWP_ROUTE_APPROVAL_INVALID"):
            verify_task_creation_approval(raw, decision, measured, context)
