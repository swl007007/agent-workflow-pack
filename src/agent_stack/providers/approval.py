"""Direct-human provider exception approval verification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agent_stack.core.api import digest

from .errors import ProviderFailure
from .models import ProviderPlan


_APPROVAL_FIELDS = {
    "schema_id",
    "schema_version",
    "approval_id",
    "verifier_id",
    "verifier_version",
    "platform",
    "harness_version",
    "actor",
    "issued_at",
    "expires_at",
    "workspace_instance_id",
    "operation",
    "provider_plan_digest",
    "risk_report_digest",
    "prospective_transaction_id",
    "approval_challenge",
    "verifier_receipt",
}
_MAX_APPROVAL_WINDOW = timedelta(minutes=15)
_MAX_CLOCK_SKEW = timedelta(seconds=60)


@dataclass(frozen=True)
class VerifiedProviderApproval:
    approval_id: str
    provider_plan_digest: str
    risk_report_digest: str
    prospective_transaction_id: str
    issued_at: datetime
    expires_at: datetime
    approval_digest: str


def provider_risk_report_digest(plan: ProviderPlan) -> str:
    """Bind the exact requested controls and measured enforcement gaps."""

    return digest(
        "agent-workflow.provider-risk-report.v1",
        {
            "provider_plan_digest": plan.provider_plan_digest,
            "requested_controls": dict(plan.requested_controls),
            "measured_isolation_gaps": list(plan.measured_isolation_gaps),
        },
    )


def _invalid(message: str, **details: object) -> ProviderFailure:
    return ProviderFailure("AWP_PROVIDER_APPROVAL_INVALID", message, details=details)


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _invalid(f"{label} must be UTC RFC3339")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise _invalid(f"{label} must be UTC RFC3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise _invalid(f"{label} must be UTC RFC3339")
    return parsed.astimezone(UTC)


def _verifier_contract(
    capability: Mapping[str, object], operation: str
) -> Mapping[str, object]:
    if capability.get("schema_id") != "agent-workflow.capability-manifest" or capability.get(
        "schema_version"
    ) != 1:
        raise ProviderFailure(
            "AWP_PROVIDER_APPROVAL_REQUIRED", "CapabilityManifest is absent or unsupported"
        )
    capabilities = capability.get("capabilities")
    if not isinstance(capabilities, Mapping) or capabilities.get(
        "provider_exception_approval"
    ) != "enforced":
        raise ProviderFailure(
            "AWP_PROVIDER_APPROVAL_REQUIRED",
            "provider exception approval is not enforced by the platform",
        )
    verifiers = capability.get("approval_verifiers")
    if not isinstance(verifiers, Mapping):
        raise ProviderFailure(
            "AWP_PROVIDER_APPROVAL_REQUIRED", "provider approval verifier is unavailable"
        )
    verifier = verifiers.get(operation)
    if not isinstance(verifier, Mapping) or set(verifier) != {
        "verifier_id",
        "verifier_version",
        "receipt_prefix",
    }:
        raise ProviderFailure(
            "AWP_PROVIDER_APPROVAL_REQUIRED", "provider approval verifier is unavailable"
        )
    return verifier


def verify_provider_approval(
    plan: ProviderPlan,
    proof: Mapping[str, object],
    capability: Mapping[str, object],
    now: datetime,
) -> VerifiedProviderApproval:
    """Verify one finite-window direct-human exception without mutating replay state."""

    if set(proof) != _APPROVAL_FIELDS:
        raise _invalid("provider approval fields are not closed")
    if proof.get("schema_id") != "agent-workflow.provider-approval" or proof.get(
        "schema_version"
    ) != 1:
        raise _invalid("provider approval schema identity/version is invalid")
    operation = proof.get("operation")
    if operation != "approve-provider-execution":
        raise _invalid("provider approval operation is invalid")
    verifier = _verifier_contract(capability, operation)
    actor = proof.get("actor")
    if (
        not isinstance(actor, Mapping)
        or set(actor) != {"id", "kind"}
        or actor.get("kind") != "direct-human"
        or not isinstance(actor.get("id"), str)
        or not actor.get("id")
    ):
        raise _invalid("provider approval actor is not a direct human")
    expected = {
        "verifier_id": verifier.get("verifier_id"),
        "verifier_version": verifier.get("verifier_version"),
        "platform": capability.get("platform"),
        "harness_version": capability.get("harness_version"),
        "workspace_instance_id": plan.workspace_instance_id,
        "provider_plan_digest": plan.provider_plan_digest,
        "risk_report_digest": provider_risk_report_digest(plan),
        "prospective_transaction_id": plan.prospective_transaction_id,
        "approval_challenge": plan.approval_challenge,
    }
    mismatches = sorted(field for field, value in expected.items() if proof.get(field) != value)
    if mismatches:
        raise _invalid("provider approval binding mismatch", fields=mismatches)
    receipt = proof.get("verifier_receipt")
    prefix = verifier.get("receipt_prefix")
    if (
        not isinstance(receipt, str)
        or not isinstance(prefix, str)
        or not prefix
        or not receipt.startswith(prefix)
        or len(receipt) <= len(prefix)
    ):
        raise _invalid("provider verifier receipt is not authenticated")
    issued_at = _parse_time(proof.get("issued_at"), "issued_at")
    expires_at = _parse_time(proof.get("expires_at"), "expires_at")
    normalized_now = now.astimezone(UTC)
    if issued_at > normalized_now + _MAX_CLOCK_SKEW:
        raise _invalid("provider approval was issued too far in the future")
    if expires_at <= normalized_now:
        raise _invalid("provider approval has expired")
    if expires_at <= issued_at or expires_at - issued_at > _MAX_APPROVAL_WINDOW:
        raise _invalid("provider approval validity window is invalid")
    approval_id = proof.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        raise _invalid("provider approval id is invalid")
    return VerifiedProviderApproval(
        approval_id=approval_id,
        provider_plan_digest=plan.provider_plan_digest,
        risk_report_digest=provider_risk_report_digest(plan),
        prospective_transaction_id=plan.prospective_transaction_id,
        issued_at=issued_at,
        expires_at=expires_at,
        approval_digest=digest("agent-workflow.provider-approval.v1", proof),
    )
