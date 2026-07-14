"""Immutable normalized Core domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any


class CapabilityLevel(str, Enum):
    UNSUPPORTED = "unsupported"
    INSTRUCTION_ONLY = "instruction-only"
    ENFORCED = "enforced"

    @property
    def rank(self) -> int:
        return {
            CapabilityLevel.UNSUPPORTED: 0,
            CapabilityLevel.INSTRUCTION_ONLY: 1,
            CapabilityLevel.ENFORCED: 2,
        }[self]

    @classmethod
    def parse(cls, value: object) -> CapabilityLevel:
        if not isinstance(value, str):
            raise ValueError("capability level must be a string")
        return cls(value)


def frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class ResolvedProfile:
    schema_version: int
    profile_id: str
    route_admission: Mapping[str, Any]
    bindings: Mapping[str, Mapping[str, str]]
    skills_enable: tuple[str, ...]
    skills_disable: tuple[str, ...]
    artifact_policy: str
    default_platforms: tuple[str, ...]
    required_capabilities: Mapping[str, CapabilityLevel]
    approval_policy: Mapping[str, Any]
    provider_security_policy: Mapping[str, Any]


@dataclass(frozen=True)
class CatalogEntry:
    entry_id: str
    kind: str
    dependencies: tuple[str, ...]
    conflicts: tuple[str, ...]
    references: tuple[str, ...]
    platforms: tuple[str, ...]
    required_capabilities: Mapping[str, CapabilityLevel]
    mandatory: bool
    discoverable: bool


@dataclass(frozen=True)
class CatalogClosure:
    ordered_ids: tuple[str, ...]
    reference_ids: tuple[str, ...]
    discoverable_ids: tuple[str, ...]
    entries: Mapping[str, CatalogEntry]


@dataclass(frozen=True)
class CapabilityResult:
    capability_id: str
    required: CapabilityLevel
    observed: CapabilityLevel
    platform: str


@dataclass(frozen=True)
class WorkflowComponent:
    component_id: str
    version: str
    source_sha256: str
    content_digest: str
    provider_id: str
    acquisition_id: str


@dataclass(frozen=True)
class WorkflowLock:
    schema_version: int
    components: tuple[WorkflowComponent, ...]
