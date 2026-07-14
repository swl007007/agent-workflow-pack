"""Structured lifecycle and release-kernel failures."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


class LifecycleFailure(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = MappingProxyType(dict(details or {}))
        super().__init__(f"{code}: {message}")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.lifecycle-failure",
            "schema_version": 1,
            "code": self.code,
            "exit_code": self.exit_code,
            "message": self.message,
            "details": dict(self.details),
        }
