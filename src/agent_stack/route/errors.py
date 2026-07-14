"""Structured Route/Adapter failures."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


_EXIT_CODES = {
    "AWP_ROUTE_OPERATION_MISMATCH": 2,
    "AWP_ROUTE_SIGNAL_INVALID": 2,
    "AWP_ROUTE_POLICY_MISMATCH": 40,
    "AWP_ROUTE_DECISION_INVALID": 2,
    "AWP_ROUTE_TASK_STATE_STALE": 40,
    "AWP_ROUTE_SURFACE_CLOSURE_INVALID": 2,
    "AWP_ROUTE_APPROVAL_INVALID": 22,
    "AWP_ROUTE_APPROVAL_EXPIRED": 22,
    "AWP_ADAPTER_CONTRACT_INVALID": 2,
    "AWP_ADAPTER_CAPABILITY_UNVERIFIED": 23,
    "AWP_ADAPTER_BYPASS_DETECTED": 23,
    "AWP_ADAPTER_PROJECTION_INVALID": 2,
}


class RouteFailure(ValueError):
    """One closed Route/Adapter error with its frozen CLI exit category."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.exit_code = _EXIT_CODES.get(code, 70)
        self.details = MappingProxyType(dict(details or {}))
        super().__init__(f"{code}: {message}")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.route-failure",
            "schema_version": 1,
            "code": self.code,
            "exit_code": self.exit_code,
            "message": self.message,
            "details": dict(self.details),
        }
