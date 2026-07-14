"""Structured Runtime/Task-state failures."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


_EXIT_CODES = {
    "AWP_RUNTIME_BOOTSTRAP_PREREQUISITE_MISSING": 30,
    "AWP_RUNTIME_BINDING_MISMATCH": 30,
    "AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED": 21,
    "AWP_CALLER_CONTEXT_INVALID": 2,
    "AWP_WORKSPACE_REGISTRATION_REQUIRED": 21,
    "AWP_WORKSPACE_REGISTRATION_RECOVERY_REQUIRED": 21,
    "AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED": 21,
    "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED": 21,
    "AWP_TASK_ID_CONFLICT": 22,
    "AWP_TASK_REF_CONFLICT": 22,
    "AWP_TASK_STATE_STALE": 40,
    "AWP_TASK_TRANSITION_INVALID": 2,
    "AWP_APPROVAL_REPLAY_BLOCKED": 22,
    "AWP_TASK_RUNTIME_LOAD_DENIED": 22,
    "AWP_TASK_SURFACE_MISMATCH": 22,
    "AWP_TASK_ARCHIVE_BLOCKED": 22,
}


class RuntimeFailure(ValueError):
    """A closed, user-facing Runtime/Task-state contract failure."""

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
            "schema_id": "agent-workflow.runtime-failure",
            "schema_version": 1,
            "code": self.code,
            "exit_code": self.exit_code,
            "message": self.message,
            "details": dict(self.details),
        }
