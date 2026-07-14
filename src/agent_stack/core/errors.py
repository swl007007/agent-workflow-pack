"""Structured Core/Resolver failures."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


class CoreFailure(ValueError):
    """A closed, user-facing Core/Resolver contract failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int = 2,
        path: str = "<input>",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.path = path
        self.details = MappingProxyType(dict(details or {}))
        super().__init__(f"{code}: {message} [{path}]")

    def to_document(self) -> dict[str, Any]:
        """Return the closed resolution-failure projection."""

        return {
            "schema_id": "agent-workflow.resolution-failure",
            "schema_version": 1,
            "code": self.code,
            "exit_code": self.exit_code,
            "message": self.message,
            "path": self.path,
            "details": dict(self.details),
        }
