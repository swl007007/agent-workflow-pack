"""Structured Renderer/Reconciler failures."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


_EXIT_CODES = {
    "AWP_RENDER_NONDETERMINISTIC": 2,
    "AWP_OWNERSHIP_DRIFT": 20,
    "AWP_OWNERSHIP_CONFLICT": 20,
    "AWP_RECONCILE_LOCKED": 21,
    "AWP_RECONCILE_RECOVERY_REQUIRED": 21,
    "AWP_FILE_CAS_MISMATCH": 40,
    "AWP_FILESYSTEM_UNSUPPORTED": 20,
    "AWP_MAINTENANCE_CORRUPT": 21,
    "AWP_ROLLBACK_CONFLICT": 21,
    "AWP_TASK_QUIESCENCE_CHANGED": 40,
}


class RendererFailure(ValueError):
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
            "schema_id": "agent-workflow.renderer-failure",
            "schema_version": 1,
            "code": self.code,
            "exit_code": self.exit_code,
            "message": self.message,
            "details": dict(self.details),
        }
