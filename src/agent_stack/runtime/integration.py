"""Closed integration contract validation and immutable task identity."""

from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import digest, normalize_path
from agent_stack.core.errors import CoreFailure

from .errors import RuntimeFailure


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MODES = {"trellis-native", "speckit-superpowers"}
_STATUSES = {"admitting", "active", "blocked", "completed", "archiving", "archived"}
_HEAVY_PHASES = {"specifying", "planning", "implementing", "verifying", "finishing"}
_MANDATORY_SURFACES = {"runtime-control-plane", "surface-registry"}
_WORKFLOW_FIELDS = {
    "version",
    "profile_digest_at_admission",
    "lock_digest_at_admission",
    "artifact_bundle_digest_at_admission",
    "policy_digest_at_admission",
    "adapter_id",
    "adapter_version_at_admission",
    "route_contract_version",
    "task_contract_surfaces",
}
_LIFECYCLE_FIELDS = {
    "status",
    "state_revision",
    "admitted_at",
    "archived_at",
    "blocked_reason",
    "last_transition",
}
_ADMISSION_FIELDS = {
    "operation",
    "task_id",
    "task_ref",
    "intent_id",
    "intent_digest",
    "task_transaction_id",
    "candidate_tree_digest",
    "workspace_instance_id_at_admission",
    "route_decision_id",
    "route_decision_digest",
    "approval_id",
    "approval_challenge",
    "approval_proof_digest",
    "approval_verifier_id",
    "approval_verifier_version",
    "approved_by",
    "approval_mechanism",
    "approved_at",
}


@dataclass(frozen=True)
class SurfacePin:
    """One normalized runtime surface pinned at task admission."""

    surface_id: str
    surface_digest: str


@dataclass(frozen=True)
class VerifiedIntegration:
    """Immutable projection of a schema-valid integration document."""

    document: Mapping[str, object]
    mode: str
    task_id: str
    task_ref: str
    lifecycle_status: str
    state_revision: int
    task_contract_digest: str
    task_contract_surfaces: tuple[SurfacePin, ...]
    phase: str | None
    executor_claim: Mapping[str, object] | None


def _failure(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure("AWP_TASK_TRANSITION_INVALID", message, details=details)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("integration object is invalid", field=field)
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _failure("integration array is invalid", field=field)
    return cast(Sequence[object], value)


def _closed(value: Mapping[str, object], expected: set[str], field: str) -> None:
    if set(value) != expected:
        raise _failure(
            "integration object fields are not closed",
            field=field,
            missing=sorted(expected - set(value)),
            unknown=sorted(set(value) - expected),
        )


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or any(ord(character) < 0x20 for character in value):
        raise _failure("integration string is invalid", field=field)
    return value


def _sha256(value: object, field: str) -> str:
    candidate = _string(value, field)
    if _DIGEST.fullmatch(candidate) is None:
        raise _failure("integration digest is invalid", field=field)
    return candidate


def _uuid(value: object, field: str) -> str:
    candidate = _string(value, field)
    try:
        parsed = str(uuid.UUID(candidate))
    except ValueError as error:
        raise _failure("integration UUID is invalid", field=field) from error
    if parsed != candidate:
        raise _failure("integration UUID is not canonical", field=field)
    return candidate


def _timestamp(value: object, field: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    candidate = _string(value, field)
    if not candidate.endswith("Z"):
        raise _failure("integration timestamp is not UTC RFC3339", field=field)
    try:
        parsed = datetime.fromisoformat(candidate[:-1] + "+00:00")
    except ValueError as error:
        raise _failure("integration timestamp is invalid", field=field) from error
    if parsed.tzinfo is None or parsed.astimezone(UTC).utcoffset() is None:
        raise _failure("integration timestamp has no timezone", field=field)
    return candidate


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _failure("integration integer is invalid", field=field)
    return value


def _task_ref(value: object, field: str) -> str:
    try:
        return normalize_path(_string(value, field))
    except CoreFailure as error:
        raise _failure("integration task ref is invalid", field=field) from error


def _validate_workflow(value: object) -> tuple[Mapping[str, object], tuple[SurfacePin, ...]]:
    workflow = _mapping(value, "workflow_contract")
    _closed(workflow, _WORKFLOW_FIELDS, "workflow_contract")
    if workflow.get("version") != 1 or workflow.get("route_contract_version") != 1:
        raise _failure("workflow contract version is unsupported")
    for field in (
        "profile_digest_at_admission",
        "lock_digest_at_admission",
        "artifact_bundle_digest_at_admission",
        "policy_digest_at_admission",
    ):
        _sha256(workflow.get(field), f"workflow_contract.{field}")
    _string(workflow.get("adapter_id"), "workflow_contract.adapter_id")
    _string(
        workflow.get("adapter_version_at_admission"),
        "workflow_contract.adapter_version_at_admission",
    )

    pins: list[SurfacePin] = []
    for raw in _sequence(workflow.get("task_contract_surfaces"), "task_contract_surfaces"):
        surface = _mapping(raw, "task_contract_surfaces[]")
        _closed(surface, {"surface_id", "surface_digest"}, "task_contract_surfaces[]")
        pins.append(
            SurfacePin(
                _string(surface.get("surface_id"), "surface_id"),
                _sha256(surface.get("surface_digest"), "surface_digest"),
            )
        )
    if not pins:
        raise _failure("task contract surface set is empty")
    if pins != sorted(pins, key=lambda pin: pin.surface_id):
        raise _failure("task contract surfaces are not sorted")
    identifiers = [pin.surface_id for pin in pins]
    if len(identifiers) != len(set(identifiers)):
        raise _failure("task contract surfaces contain duplicates")
    missing = _MANDATORY_SURFACES - set(identifiers)
    if missing:
        raise _failure("mandatory task contract surfaces are missing", surfaces=sorted(missing))
    return workflow, tuple(pins)


def _validate_lifecycle(value: object) -> tuple[str, int]:
    lifecycle = _mapping(value, "lifecycle")
    _closed(lifecycle, _LIFECYCLE_FIELDS, "lifecycle")
    status = _string(lifecycle.get("status"), "lifecycle.status")
    if status not in _STATUSES:
        raise _failure("lifecycle status is not closed", status=status)
    revision = _positive_int(lifecycle.get("state_revision"), "lifecycle.state_revision")
    admitted_at = _timestamp(
        lifecycle.get("admitted_at"), "lifecycle.admitted_at", nullable=True
    )
    archived_at = _timestamp(
        lifecycle.get("archived_at"), "lifecycle.archived_at", nullable=True
    )
    blocked_reason = lifecycle.get("blocked_reason")
    _mapping(lifecycle.get("last_transition"), "lifecycle.last_transition")

    if status == "admitting":
        if revision != 1 or admitted_at is not None or archived_at is not None:
            raise _failure("admitting lifecycle must be uncommitted revision 1")
    else:
        if revision < 2 or admitted_at is None:
            raise _failure("committed lifecycle requires admitted revision 2 or later")
        if status == "archived":
            if archived_at is None:
                raise _failure("archived lifecycle requires archived_at")
        elif archived_at is not None:
            raise _failure("non-archived lifecycle cannot set archived_at")
    if status == "blocked":
        _string(blocked_reason, "lifecycle.blocked_reason")
    elif blocked_reason is not None:
        raise _failure("blocked_reason is legal only for blocked lifecycle")
    return status, revision


def _validate_admission(value: object) -> tuple[str, str]:
    admission = _mapping(value, "admission")
    _closed(admission, _ADMISSION_FIELDS, "admission")
    if admission.get("operation") != "create-integrated-task":
        raise _failure("integration admission operation is invalid")
    task_id = _uuid(admission.get("task_id"), "admission.task_id")
    task_ref = _task_ref(admission.get("task_ref"), "admission.task_ref")
    _string(admission.get("intent_id"), "admission.intent_id")
    for field in (
        "intent_digest",
        "candidate_tree_digest",
        "route_decision_digest",
        "approval_proof_digest",
    ):
        _sha256(admission.get(field), f"admission.{field}")
    for field in (
        "task_transaction_id",
        "workspace_instance_id_at_admission",
        "route_decision_id",
        "approval_id",
    ):
        _uuid(admission.get(field), f"admission.{field}")
    _sha256(admission.get("approval_challenge"), "admission.approval_challenge")
    for field in (
        "approval_verifier_id",
        "approval_verifier_version",
        "approved_by",
        "approval_mechanism",
    ):
        _string(admission.get(field), f"admission.{field}")
    _timestamp(admission.get("approved_at"), "admission.approved_at")
    return task_id, task_ref


def _validate_heavy_branch(
    value: object, revision: int
) -> tuple[str, Mapping[str, object] | None]:
    branch = _mapping(value, "speckit_superpowers")
    _closed(
        branch,
        {
            "router_contract_version",
            "phase",
            "executor_claim",
            "authority",
            "canonical_artifacts",
            "reference_only_artifacts",
            "completion_flags",
        },
        "speckit_superpowers",
    )
    if branch.get("router_contract_version") != 1:
        raise _failure("heavy router contract version is unsupported")
    phase = _string(branch.get("phase"), "speckit_superpowers.phase")
    if phase not in _HEAVY_PHASES:
        raise _failure("heavy phase is not closed", phase=phase)
    authority = _mapping(branch.get("authority"), "speckit_superpowers.authority")
    _closed(authority, {"active_feature"}, "speckit_superpowers.authority")
    _string(authority.get("active_feature"), "active_feature")
    _mapping(branch.get("canonical_artifacts"), "canonical_artifacts")
    _sequence(branch.get("reference_only_artifacts"), "reference_only_artifacts")
    _mapping(branch.get("completion_flags"), "completion_flags")

    raw_claim = branch.get("executor_claim")
    if raw_claim is None:
        return phase, None
    claim = _mapping(raw_claim, "executor_claim")
    _closed(
        claim,
        {"claim_id", "executor", "actor", "claimed_at", "base_revision"},
        "executor_claim",
    )
    if phase != "implementing":
        raise _failure("executor claim is legal only during implementing")
    _uuid(claim.get("claim_id"), "executor_claim.claim_id")
    _string(claim.get("executor"), "executor_claim.executor")
    _string(claim.get("actor"), "executor_claim.actor")
    _timestamp(claim.get("claimed_at"), "executor_claim.claimed_at")
    base_revision = _positive_int(claim.get("base_revision"), "executor_claim.base_revision")
    if base_revision >= revision:
        raise _failure("executor claim base revision must precede current revision")
    return phase, MappingProxyType(dict(claim))


def validate_integration(document: Mapping[str, object]) -> VerifiedIntegration:
    """Validate the complete closed union and recompute its task contract identity."""

    candidate = _mapping(document, "integration")
    mode = _string(candidate.get("mode"), "mode")
    if mode not in _MODES:
        raise _failure("integration mode is not closed", mode=mode)
    branch_field = "trellis_native" if mode == "trellis-native" else "speckit_superpowers"
    expected = {
        "schema_version",
        "mode",
        "workflow_contract",
        "lifecycle",
        "admission",
        branch_field,
    }
    _closed(candidate, expected, "integration")
    if candidate.get("schema_version") != 1:
        raise _failure("integration schema version is unsupported")

    workflow, surfaces = _validate_workflow(candidate.get("workflow_contract"))
    status, revision = _validate_lifecycle(candidate.get("lifecycle"))
    task_id, task_ref = _validate_admission(candidate.get("admission"))

    phase: str | None = None
    claim: Mapping[str, object] | None = None
    if mode == "trellis-native":
        branch = _mapping(candidate.get(branch_field), branch_field)
        _closed(branch, {"task_ref"}, branch_field)
        if _task_ref(branch.get("task_ref"), f"{branch_field}.task_ref") != task_ref:
            raise _failure("mode-specific task ref differs from admission-time task ref")
    else:
        phase, claim = _validate_heavy_branch(candidate.get(branch_field), revision)

    frozen = MappingProxyType(copy.deepcopy(dict(candidate)))
    return VerifiedIntegration(
        document=frozen,
        mode=mode,
        task_id=task_id,
        task_ref=task_ref,
        lifecycle_status=status,
        state_revision=revision,
        task_contract_digest=digest("agent-workflow.task-contract.v1", workflow),
        task_contract_surfaces=surfaces,
        phase=phase,
        executor_claim=claim,
    )
