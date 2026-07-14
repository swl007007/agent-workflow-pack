"""Direct-human task-creation approval verification."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import digest, normalize_path
from agent_stack.core.errors import CoreFailure

from .errors import RouteFailure


_PROOF_FIELDS = {
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
    "task_id",
    "task_ref",
    "task_contract_surfaces_digest",
    "intent_digest",
    "route_decision_digest",
    "approval_challenge",
    "verifier_receipt",
}
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")


ApprovalReceiptVerifier = Callable[[str, dict[str, object]], bool]


@dataclass(frozen=True)
class VerifiedPlatformRuntimeContext(Mapping[str, object]):
    """Post-authority platform context with one mandatory receipt verifier."""

    platform: str
    harness_id: str
    harness_version: str
    confirmation_mechanism: str
    direct_confirmation_capable: bool
    now: datetime
    max_approval_ttl: timedelta
    max_clock_skew: timedelta
    receipt_verifier: ApprovalReceiptVerifier

    def __post_init__(self) -> None:
        for value, field in (
            (self.platform, "platform"),
            (self.harness_id, "harness_id"),
            (self.harness_version, "harness_version"),
            (self.confirmation_mechanism, "confirmation_mechanism"),
        ):
            _token(value, field)
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise _failure("platform runtime clock is not timezone aware")
        if self.max_approval_ttl <= timedelta(0) or self.max_clock_skew < timedelta(0):
            raise _failure("platform approval time policy is invalid")
        if not callable(self.receipt_verifier):
            raise _failure("platform receipt verifier is unavailable")

    def _public(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "harness_id": self.harness_id,
            "harness_version": self.harness_version,
            "confirmation_mechanism": self.confirmation_mechanism,
            "direct_confirmation_capable": self.direct_confirmation_capable,
        }

    def __getitem__(self, key: str) -> object:
        return self._public()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._public())

    def __len__(self) -> int:
        return len(self._public())


def _failure(message: str, *, expired: bool = False, **details: object) -> RouteFailure:
    return RouteFailure(
        "AWP_ROUTE_APPROVAL_EXPIRED" if expired else "AWP_ROUTE_APPROVAL_INVALID",
        message,
        details=details,
    )


def _token(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise _failure("approval token is invalid", field=field)
    return value


def _uuid(value: object, field: str) -> str:
    token = _token(value, field)
    try:
        parsed = uuid.UUID(token)
    except ValueError as error:
        raise _failure("approval UUID is invalid", field=field) from error
    if str(parsed) != token:
        raise _failure("approval UUID is not canonical", field=field)
    return token


def _digest(value: object, field: str) -> str:
    token = _token(value, field)
    if _DIGEST.fullmatch(token) is None:
        raise _failure("approval digest is invalid", field=field)
    return token


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _failure("approval timestamp is not UTC RFC3339", field=field)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise _failure("approval timestamp is not UTC RFC3339", field=field) from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise _failure("approval timestamp is not UTC RFC3339", field=field)
    return parsed.astimezone(UTC)


def _format(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("approval object is invalid", field=field)
    return cast(Mapping[str, object], value)


def _verifier_contract(capability: Mapping[str, object]) -> Mapping[str, object]:
    if capability.get("schema_id") != "agent-workflow.capability-manifest" or capability.get(
        "schema_version"
    ) != 1:
        raise _failure("CapabilityManifest is absent or unsupported")
    levels = _mapping(capability.get("capabilities"), "capabilities")
    if levels.get("task_admission_gate") != "enforced" or levels.get(
        "direct_human_confirmation"
    ) != "enforced":
        raise _failure("direct-human task admission is not technically enforced")
    verifiers = _mapping(capability.get("approval_verifiers"), "approval_verifiers")
    verifier = _mapping(verifiers.get("task_creation"), "approval_verifiers.task_creation")
    if set(verifier) != {
        "verifier_id",
        "verifier_version",
        "actor_source",
        "receipt_source",
    } or verifier.get("actor_source") != "direct-human":
        raise _failure("task approval verifier contract is invalid")
    for field in ("verifier_id", "verifier_version", "receipt_source"):
        _token(verifier.get(field), field)
    return verifier


def _validate_decision(decision: Mapping[str, object]) -> None:
    if (
        decision.get("verification_kind") != "verified-create-integrated-task"
        or decision.get("operation") != "create-integrated-task"
        or decision.get("route") not in {"trellis-native", "speckit-superpowers"}
        or decision.get("task_creation_approval") != "required"
    ):
        raise _failure("approval does not target a verified integrated Decision")


def verify_task_creation_approval(
    proof: Mapping[str, object],
    decision: Mapping[str, object],
    capability: Mapping[str, object],
    runtime_context: Mapping[str, object],
) -> Mapping[str, object]:
    """Verify one finite direct-human receipt without editing replay state."""

    if not isinstance(runtime_context, VerifiedPlatformRuntimeContext):
        raise _failure("verified platform runtime context is required")
    if not isinstance(proof, Mapping) or set(proof) != _PROOF_FIELDS:
        raise _failure("task approval fields are not closed")
    if proof.get("schema_id") != "agent-workflow.approval-proof" or proof.get(
        "schema_version"
    ) != 1:
        raise _failure("task approval schema identity/version is invalid")
    _validate_decision(decision)
    verifier = _verifier_contract(capability)
    if not runtime_context.direct_confirmation_capable:
        raise _failure("caller context cannot perform direct confirmation")

    actor = _mapping(proof.get("actor"), "actor")
    if set(actor) != {"id", "kind"} or actor.get("kind") != "direct-human":
        raise _failure("task approval actor is not a direct human")
    actor_id = _token(actor.get("id"), "actor.id")

    expected = {
        "operation": "create-integrated-task",
        "workspace_instance_id": decision.get("workspace_instance_id"),
        "task_id": decision.get("requested_task_id"),
        "task_ref": decision.get("requested_task_ref"),
        "task_contract_surfaces_digest": decision.get("task_contract_surfaces_digest"),
        "intent_digest": decision.get("intent_digest"),
        "route_decision_digest": decision.get("decision_digest"),
        "approval_challenge": decision.get("approval_challenge"),
        "verifier_id": verifier.get("verifier_id"),
        "verifier_version": verifier.get("verifier_version"),
        "platform": capability.get("platform"),
        "harness_version": capability.get("harness_version"),
    }
    mismatches = sorted(field for field, value in expected.items() if proof.get(field) != value)
    if mismatches:
        raise _failure("task approval binding mismatch", fields=mismatches)
    if capability.get("adapter_id") != decision.get("adapter_id") or capability.get(
        "adapter_version"
    ) != decision.get("adapter_version"):
        raise _failure("task approval adapter contract differs from Decision")
    if (
        runtime_context.platform != capability.get("platform")
        or runtime_context.harness_id != capability.get("harness_id")
        or runtime_context.harness_version != capability.get("harness_version")
        or runtime_context.confirmation_mechanism != verifier.get("receipt_source")
    ):
        raise _failure("task approval runtime context differs from capability evidence")

    approval_id = _uuid(proof.get("approval_id"), "approval_id")
    _uuid(proof.get("workspace_instance_id"), "workspace_instance_id")
    _uuid(proof.get("task_id"), "task_id")
    _digest(proof.get("task_contract_surfaces_digest"), "task_contract_surfaces_digest")
    _digest(proof.get("intent_digest"), "intent_digest")
    _digest(proof.get("route_decision_digest"), "route_decision_digest")
    _digest(proof.get("approval_challenge"), "approval_challenge")
    if _SEMVER.fullmatch(_token(proof.get("verifier_version"), "verifier_version")) is None:
        raise _failure("approval verifier version is invalid")
    try:
        normalized_ref = normalize_path(cast(str, proof.get("task_ref")))
    except (CoreFailure, TypeError) as error:
        raise _failure("approval task ref is invalid") from error
    if normalized_ref != proof.get("task_ref"):
        raise _failure("approval task ref is not canonical")

    issued = _time(proof.get("issued_at"), "issued_at")
    expires = _time(proof.get("expires_at"), "expires_at")
    now = runtime_context.now.astimezone(UTC)
    if expires <= now:
        raise _failure("task approval has expired", expired=True)
    if issued > now + runtime_context.max_clock_skew:
        raise _failure("task approval was issued too far in the future")
    if expires <= issued or expires - issued > runtime_context.max_approval_ttl:
        raise _failure("task approval validity window is invalid")

    receipt = _token(proof.get("verifier_receipt"), "verifier_receipt")
    authenticated_projection = {
        key: value for key, value in proof.items() if key != "verifier_receipt"
    }
    try:
        authenticated = runtime_context.receipt_verifier(receipt, authenticated_projection)
    except Exception as error:
        raise _failure("platform approval receipt verification failed") from error
    if authenticated is not True:
        raise _failure("platform approval receipt is not authenticated")

    result: dict[str, object] = {
        "schema_id": "agent-workflow.approval-verification-result",
        "schema_version": 1,
        "operation": "create-integrated-task",
        "approval_id": approval_id,
        "verifier_id": verifier["verifier_id"],
        "verifier_version": verifier["verifier_version"],
        "actor_id": actor_id,
        "mechanism": runtime_context.confirmation_mechanism,
        "validated_at": _format(now),
        "proof_expires_at": _format(expires),
    }
    result["verification_digest"] = digest(
        "agent-workflow.approval-verification-result.v1",
        {
            "result": result,
            "approval_proof_digest": digest("agent-workflow.approval-proof.v1", proof),
            "route_decision_digest": decision.get("decision_digest"),
        },
    )
    return MappingProxyType(result)
