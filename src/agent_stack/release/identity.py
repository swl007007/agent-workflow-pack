"""Non-self-referential logical release identity."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from agent_stack.core.api import canonical_json_bytes

from .errors import LifecycleFailure


def _authority_string(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LifecycleFailure(
            "AWP_RELEASE_IDENTITY_INVALID",
            "release identity field is invalid",
            exit_code=30,
            details={"field": field},
        )
    return value


def release_id(repository_id: str, distribution_name: str, version: str) -> str:
    """Hash only the three logical authority fields shared by every distribution form."""

    projection = {
        "repository_id": _authority_string(repository_id, "repository_id"),
        "distribution_name": _authority_string(distribution_name, "distribution_name"),
        "version": _authority_string(version, "version"),
    }
    return hashlib.sha256(canonical_json_bytes(projection)).hexdigest()


@dataclass(frozen=True)
class ReleaseIdentity:
    repository_id: str
    distribution_name: str
    version: str

    def __post_init__(self) -> None:
        _authority_string(self.repository_id, "repository_id")
        _authority_string(self.distribution_name, "distribution_name")
        _authority_string(self.version, "version")

    @property
    def release_id(self) -> str:
        return release_id(self.repository_id, self.distribution_name, self.version)

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.release-identity",
            "schema_version": 1,
            "repository_id": self.repository_id,
            "distribution_name": self.distribution_name,
            "version": self.version,
            "release_id": self.release_id,
        }
