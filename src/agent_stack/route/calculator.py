"""Canonical unsigned Route Decision calculator."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import digest, normalize_path
from agent_stack.core.errors import CoreFailure

from .errors import RouteFailure
from .intent import VerifiedTaskIntent
from .signals import CompiledRoutePolicy, PolicyResult, evaluate_compiled_policy, normalize_signals


_ROUTE_NAMESPACE = uuid.UUID("c7c2dd65-7073-5e38-8004-fe6b9b4af8f5")
_OPERATIONS = {"classify-only", "execute-light", "create-integrated-task"}


@dataclass(frozen=True)
class RouteCalculationInputs:
    intent: VerifiedTaskIntent | None = None
    candidate_signals: tuple[str, ...] = ()
    explicit_modes: tuple[str, ...] = ()
    requested_task_ref: str | None = None


@dataclass(frozen=True)
class VerifiedRouteAuthoritySnapshot:
    project_id: str
    workspace_instance_id: str
    manifest_generation: int
    manifest_digest: str
    profile_digest: str
    lock_digest: str
    artifact_bundle_digest: str
    policy: CompiledRoutePolicy
    policy_digest: str
    platform: str
    adapter_id: str
    adapter_version: str
    router_contract_version: int
    entry_owners: Mapping[str, str]
    task_inventory: Mapping[str, object]
    task_state_digest: str
    task_surface_closures: Mapping[str, tuple[Mapping[str, object], ...]]
    maintenance: bool
    unfinished_task_transaction: bool
    extra_authorities: Mapping[str, object] = field(default_factory=dict)


def _failure(code: str, message: str, **details: object) -> RouteFailure:
    return RouteFailure(code, message, details=details)


def _validate_authorities(authorities: VerifiedRouteAuthoritySnapshot) -> None:
    if authorities.policy_digest != authorities.policy.policy_digest:
        raise _failure("AWP_ROUTE_POLICY_MISMATCH", "compiled policy digest is inconsistent")
    actual_task_state = digest(
        "agent-workflow.route-task-state.v1", authorities.task_inventory
    )
    if authorities.task_state_digest != actual_task_state:
        raise _failure("AWP_ROUTE_TASK_STATE_STALE", "task-state digest is inconsistent")
    if authorities.maintenance:
        raise _failure("AWP_ROUTE_POLICY_MISMATCH", "maintenance blocks Route Decision calculation")
    if authorities.unfinished_task_transaction:
        raise _failure(
            "AWP_ROUTE_TASK_STATE_STALE",
            "unfinished task transaction blocks Route Decision calculation",
        )


def _policy_inputs(
    operation: str,
    inputs: RouteCalculationInputs,
    policy: CompiledRoutePolicy,
) -> tuple[PolicyResult, VerifiedTaskIntent | None, tuple[str, ...]]:
    if operation == "classify-only":
        if inputs.intent is not None or inputs.requested_task_ref is not None:
            raise _failure(
                "AWP_ROUTE_DECISION_INVALID", "classify-only cannot contain executable fields"
            )
        result = evaluate_compiled_policy(
            normalize_signals(inputs.candidate_signals, policy),
            inputs.explicit_modes,
            policy,
        )
        return result, None, tuple(inputs.explicit_modes)
    if inputs.intent is None:
        raise _failure("AWP_ROUTE_DECISION_INVALID", "executable operation requires TaskIntent")
    if inputs.candidate_signals:
        raise _failure(
            "AWP_ROUTE_SIGNAL_INVALID", "TaskIntent is the sole executable signal source"
        )
    requested = inputs.intent.requested_mode
    explicit = (
        (requested,)
        if requested in {"trellis-native", "speckit-superpowers"}
        else ()
    )
    result = evaluate_compiled_policy(inputs.intent.signals, explicit, policy)
    return result, inputs.intent, explicit


def _common_payload(
    operation: str,
    result: PolicyResult,
    explicit_modes: Sequence[str],
    authorities: VerifiedRouteAuthoritySnapshot,
) -> dict[str, object]:
    owner = authorities.entry_owners.get(result.route)
    if owner is None:
        raise _failure("AWP_ROUTE_POLICY_MISMATCH", "calculated route has no entry owner")
    return {
        "schema_id": "agent-workflow.route-decision",
        "schema_version": 1,
        "operation": operation,
        "route": result.route,
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
        "entry_owner": owner,
        "matched_rule_ids": list(result.matched_rule_ids),
        "signals": list(result.signals),
        "explicit_modes": list(explicit_modes),
        "reasons": list(result.reasons),
        "task_state_digest": authorities.task_state_digest,
    }


def _task_inventory_sets(inventory: Mapping[str, object]) -> tuple[set[str], set[str]]:
    raw_tasks = inventory.get("tasks")
    if not isinstance(raw_tasks, list):
        raise _failure("AWP_ROUTE_TASK_STATE_STALE", "task inventory tasks are invalid")
    ids: set[str] = set()
    refs: set[str] = set()
    for raw in raw_tasks:
        if not isinstance(raw, Mapping):
            raise _failure("AWP_ROUTE_TASK_STATE_STALE", "task inventory entry is invalid")
        task_id = raw.get("task_id")
        task_ref = raw.get("task_ref")
        if isinstance(task_id, str):
            ids.add(task_id)
        if isinstance(task_ref, str):
            refs.add(task_ref)
    return ids, refs


def _surface_closure(
    route: str, authorities: VerifiedRouteAuthoritySnapshot
) -> tuple[dict[str, object], ...]:
    raw = authorities.task_surface_closures.get(route)
    if raw is None:
        raise _failure(
            "AWP_ROUTE_SURFACE_CLOSURE_INVALID", "integrated route has no verified surface closure"
        )
    surfaces: list[dict[str, object]] = []
    for surface in raw:
        if set(surface) != {"surface_id", "surface_digest"}:
            raise _failure(
                "AWP_ROUTE_SURFACE_CLOSURE_INVALID", "task surface fields are not closed"
            )
        surfaces.append(dict(surface))
    if surfaces != sorted(surfaces, key=lambda item: cast(str, item["surface_id"])):
        raise _failure("AWP_ROUTE_SURFACE_CLOSURE_INVALID", "task surfaces are not sorted")
    identifiers = [surface["surface_id"] for surface in surfaces]
    if len(identifiers) != len(set(identifiers)):
        raise _failure("AWP_ROUTE_SURFACE_CLOSURE_INVALID", "task surfaces contain duplicates")
    if {"runtime-control-plane", "surface-registry"} - set(identifiers):
        raise _failure(
            "AWP_ROUTE_SURFACE_CLOSURE_INVALID", "task surfaces omit mandatory meta-surfaces"
        )
    return tuple(surfaces)


def decision_payload(decision: Mapping[str, object]) -> dict[str, object]:
    """Return the exact payload projection excluding derived identity fields."""

    return {
        key: value
        for key, value in decision.items()
        if key not in {"route_payload_digest", "decision_id", "decision_digest", "verification_kind"}
    }


def finalize_decision(payload: Mapping[str, object]) -> Mapping[str, object]:
    """Attach the frozen payload digest, UUIDv5 identity, and Decision digest."""

    payload_digest = digest("agent-workflow.route-decision-payload.v1", payload)
    decision_id = str(uuid.uuid5(_ROUTE_NAMESPACE, payload_digest))
    final_projection = {
        **dict(payload),
        "route_payload_digest": payload_digest,
        "decision_id": decision_id,
    }
    final_projection["decision_digest"] = digest(
        "agent-workflow.route-decision.v1", final_projection
    )
    return MappingProxyType(final_projection)


def calculate_route(
    operation: str,
    normalized_inputs: RouteCalculationInputs,
    authorities: VerifiedRouteAuthoritySnapshot,
) -> Mapping[str, object]:
    """Calculate one closed unsigned Decision from verified current authority."""

    if operation not in _OPERATIONS:
        raise _failure("AWP_ROUTE_DECISION_INVALID", "route operation is invalid")
    _validate_authorities(authorities)
    result, intent, explicit = _policy_inputs(operation, normalized_inputs, authorities.policy)
    if operation == "execute-light" and result.route != "native-light":
        raise _failure(
            "AWP_ROUTE_OPERATION_MISMATCH", "execute-light calculated an integrated route"
        )
    if operation == "create-integrated-task" and result.route not in {
        "trellis-native",
        "speckit-superpowers",
    }:
        raise _failure(
            "AWP_ROUTE_OPERATION_MISMATCH", "task creation calculated native-light"
        )
    payload = _common_payload(operation, result, explicit, authorities)
    if intent is not None:
        payload.update(
            intent_id=intent.intent_id,
            intent_digest=intent.intent_digest,
            requested_mode=intent.requested_mode,
        )
    if operation == "create-integrated-task":
        if normalized_inputs.requested_task_ref is None:
            raise _failure("AWP_ROUTE_DECISION_INVALID", "task creation requires a task ref")
        try:
            task_ref = normalize_path(normalized_inputs.requested_task_ref)
        except CoreFailure as error:
            raise _failure("AWP_ROUTE_DECISION_INVALID", "requested task ref is invalid") from error
        _, refs = _task_inventory_sets(authorities.task_inventory)
        if task_ref in refs:
            raise _failure("AWP_ROUTE_TASK_STATE_STALE", "requested task ref already exists")
        task_id = str(uuid.uuid4())
        task_ids, _ = _task_inventory_sets(authorities.task_inventory)
        while task_id in task_ids:
            task_id = str(uuid.uuid4())
        surfaces = _surface_closure(result.route, authorities)
        payload.update(
            requested_task_id=task_id,
            requested_task_ref=task_ref,
            task_ref_precondition="absent",
            task_id_precondition="unique",
            task_contract_surfaces=[dict(surface) for surface in surfaces],
            task_contract_surfaces_digest=digest(
                "agent-workflow.task-surfaces.v1", surfaces
            ),
            approval_challenge=secrets.token_hex(32),
            task_creation_approval="required",
        )
    return finalize_decision(payload)
