"""Canonical Route Decision replay verifier."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import canonical_json_bytes, digest

from .calculator import (
    VerifiedRouteAuthoritySnapshot,
    _surface_closure,
    _task_inventory_sets,
    _validate_authorities,
    decision_payload,
    finalize_decision,
)
from .errors import RouteFailure
from .signals import evaluate_compiled_policy


_COMMON = {
    "schema_id",
    "schema_version",
    "operation",
    "route",
    "project_id",
    "workspace_instance_id",
    "manifest_generation",
    "manifest_digest",
    "profile_digest",
    "lock_digest",
    "artifact_bundle_digest",
    "policy_digest",
    "platform",
    "adapter_id",
    "adapter_version",
    "router_contract_version",
    "entry_owner",
    "matched_rule_ids",
    "signals",
    "explicit_modes",
    "reasons",
    "task_state_digest",
    "route_payload_digest",
    "decision_id",
    "decision_digest",
}
_INTENT = {"intent_id", "intent_digest", "requested_mode"}
_TASK = {
    "requested_task_id",
    "requested_task_ref",
    "task_ref_precondition",
    "task_id_precondition",
    "task_contract_surfaces",
    "task_contract_surfaces_digest",
    "approval_challenge",
    "task_creation_approval",
}


def _failure(code: str, message: str, **details: object) -> RouteFailure:
    return RouteFailure(code, message, details=details)


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _failure("AWP_ROUTE_DECISION_INVALID", "Decision array is invalid", field=field)
    return value


def _validate_shape(decision: Mapping[str, object]) -> str:
    operation = decision.get("operation")
    if operation == "classify-only":
        expected = _COMMON
    elif operation == "execute-light":
        expected = _COMMON | _INTENT
    elif operation == "create-integrated-task":
        expected = _COMMON | _INTENT | _TASK
    else:
        raise _failure("AWP_ROUTE_DECISION_INVALID", "Decision operation is invalid")
    if set(decision) != expected:
        raise _failure(
            "AWP_ROUTE_DECISION_INVALID",
            "Decision branch fields are not closed",
            missing=sorted(expected - set(decision)),
            unknown=sorted(set(decision) - expected),
        )
    if decision.get("schema_id") != "agent-workflow.route-decision" or decision.get(
        "schema_version"
    ) != 1:
        raise _failure("AWP_ROUTE_DECISION_INVALID", "Decision schema is unsupported")
    return operation


def _verify_identity(decision: Mapping[str, object]) -> None:
    expected = finalize_decision(decision_payload(decision))
    for field in ("route_payload_digest", "decision_id", "decision_digest"):
        if decision.get(field) != expected.get(field):
            raise _failure(
                "AWP_ROUTE_DECISION_INVALID", "Decision derived identity is invalid", field=field
            )


def _verify_authority(
    decision: Mapping[str, object], authorities: VerifiedRouteAuthoritySnapshot
) -> None:
    expected = {
        "project_id": authorities.project_id,
        "workspace_instance_id": authorities.workspace_instance_id,
        "manifest_generation": authorities.manifest_generation,
        "manifest_digest": authorities.manifest_digest,
        "profile_digest": authorities.profile_digest,
        "lock_digest": authorities.lock_digest,
        "artifact_bundle_digest": authorities.artifact_bundle_digest,
        "policy_digest": authorities.policy_digest,
        "platform": authorities.platform,
        "adapter_id": authorities.adapter_id,
        "adapter_version": authorities.adapter_version,
        "router_contract_version": authorities.router_contract_version,
    }
    for field, value in expected.items():
        if decision.get(field) != value:
            raise _failure(
                "AWP_ROUTE_POLICY_MISMATCH", "Decision authority is stale", field=field
            )


def _verify_policy(
    decision: Mapping[str, object], authorities: VerifiedRouteAuthoritySnapshot
) -> None:
    signals = tuple(cast(Sequence[str], _sequence(decision.get("signals"), "signals")))
    explicit = tuple(
        cast(Sequence[str], _sequence(decision.get("explicit_modes"), "explicit_modes"))
    )
    result = evaluate_compiled_policy(signals, explicit, authorities.policy)
    owner = authorities.entry_owners.get(result.route)
    comparisons = {
        "route": result.route,
        "entry_owner": owner,
        "matched_rule_ids": list(result.matched_rule_ids),
        "signals": list(result.signals),
        "reasons": list(result.reasons),
    }
    for field, value in comparisons.items():
        if canonical_json_bytes(decision.get(field)) != canonical_json_bytes(value):
            raise _failure(
                "AWP_ROUTE_POLICY_MISMATCH", "Decision policy replay differs", field=field
            )


def _verify_task_state(
    decision: Mapping[str, object], authorities: VerifiedRouteAuthoritySnapshot
) -> None:
    if decision.get("task_state_digest") != authorities.task_state_digest:
        raise _failure("AWP_ROUTE_TASK_STATE_STALE", "Decision task state is stale")
    if decision.get("operation") != "create-integrated-task":
        return
    task_ids, refs = _task_inventory_sets(authorities.task_inventory)
    if decision.get("requested_task_id") in task_ids or decision.get("requested_task_ref") in refs:
        raise _failure("AWP_ROUTE_TASK_STATE_STALE", "Decision task identity is no longer available")
    route = cast(str, decision["route"])
    current_surfaces = _surface_closure(route, authorities)
    if canonical_json_bytes(decision.get("task_contract_surfaces")) != canonical_json_bytes(
        current_surfaces
    ) or decision.get("task_contract_surfaces_digest") != digest(
        "agent-workflow.task-surfaces.v1", current_surfaces
    ):
        raise _failure("AWP_ROUTE_TASK_STATE_STALE", "Decision task surfaces are stale")


def verify_route_decision(
    decision: Mapping[str, object],
    current_authorities: VerifiedRouteAuthoritySnapshot,
    consumer: str,
) -> Mapping[str, object]:
    """Replay schema, derived identity, policy, authority, task state, and consumer."""

    operation = _validate_shape(decision)
    if operation == "classify-only":
        raise _failure("AWP_ROUTE_OPERATION_MISMATCH", "classify-only is not executable")
    expected_consumer = "execute-light" if operation == "execute-light" else "task-admit"
    if consumer != expected_consumer:
        raise _failure("AWP_ROUTE_OPERATION_MISMATCH", "Decision consumer is invalid")
    _validate_authorities(current_authorities)
    _verify_identity(decision)
    _verify_authority(decision, current_authorities)
    _verify_policy(decision, current_authorities)
    _verify_task_state(decision, current_authorities)
    verified = dict(decision)
    verified["verification_kind"] = (
        "verified-execute-light"
        if operation == "execute-light"
        else "verified-create-integrated-task"
    )
    return MappingProxyType(verified)
