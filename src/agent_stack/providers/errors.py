"""Structured provider/cache failures."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


_EXIT_CODES = {
    "AWP_PROVIDER_PLAN_INVALID": 2,
    "AWP_PROVIDER_APPROVAL_REQUIRED": 23,
    "AWP_PROVIDER_APPROVAL_INVALID": 23,
    "AWP_PROVIDER_DOWNLOAD_LIMIT": 31,
    "AWP_PROVIDER_HASH_MISMATCH": 30,
    "AWP_PROVIDER_ARCHIVE_UNSAFE": 31,
    "AWP_PROVIDER_CACHE_CORRUPT": 31,
    "AWP_PROVIDER_ATTEMPT_CORRUPT": 31,
    "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS": 31,
    "AWP_INITIALIZER_NONDETERMINISTIC": 31,
    "AWP_PROVENANCE_INCOMPLETE": 30,
}


class ProviderFailure(ValueError):
    """Closed, sanitized Provider/Cache failure projection."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if code not in _EXIT_CODES:
            raise ValueError(f"unknown provider failure code: {code}")
        self.code = code
        self.message = message
        self.exit_code = _EXIT_CODES[code]
        self.details = MappingProxyType(dict(details or {}))
        super().__init__(f"{code}: {message}")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_id": "agent-workflow.provider-failure",
            "schema_version": 1,
            "code": self.code,
            "exit_code": self.exit_code,
            "message": self.message,
            "details": dict(self.details),
        }
