"""Injected Route verifier ports consumed by Runtime task admission."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class RouteDecisionVerifierPort(Protocol):
    """Frozen Route Decision verification callable; Runtime supplies no default."""

    def __call__(
        self,
        decision: Mapping[str, object],
        current_authorities: Mapping[str, object],
        consumer: str,
    ) -> Mapping[str, object]: ...


@runtime_checkable
class TaskCreationApprovalVerifierPort(Protocol):
    """Frozen direct-human task approval verification callable."""

    def __call__(
        self,
        proof: Mapping[str, object],
        decision: Mapping[str, object],
        capability: Mapping[str, object],
        runtime_context: Mapping[str, object],
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class RouteVerifierPorts:
    """The two mandatory production bindings used by task admission."""

    decision: RouteDecisionVerifierPort
    approval: TaskCreationApprovalVerifierPort


def bind_route_verifier_ports(
    decision: RouteDecisionVerifierPort | None,
    approval: TaskCreationApprovalVerifierPort | None,
) -> RouteVerifierPorts:
    """Reject optional/fallback composition and bind explicit verifier implementations."""

    if decision is None or approval is None or not callable(decision) or not callable(approval):
        raise TypeError("explicit Route verifier ports are required")
    return RouteVerifierPorts(decision, approval)
