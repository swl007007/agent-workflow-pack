"""Version-bound platform capability measurement."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack._vendor import yaml
from agent_stack.core.api import digest
from agent_stack.runtime.caller_context import VerifiedCallerContext

from .adapter_contract import VerifiedPlatformAdapterContract, validate_platform_adapter
from .errors import RouteFailure


_LEVELS = {"unsupported": 0, "instruction-only": 1, "enforced": 2}
_PROBE_RESULT_FIELDS = {
    "probe_id",
    "capability_id",
    "read_only",
    "supported",
    "instruction_present",
    "enforcement_verified",
    "bypass_closed",
    "integration_evidence_id",
}


CapabilityProbe = Callable[[str, str, VerifiedCallerContext], Mapping[str, object]]


@dataclass(frozen=True)
class LockedPlatformBinding:
    adapter: VerifiedPlatformAdapterContract
    harness_id: str
    harness_version: str
    caller_platform_id: str
    version_probe_id: str
    default_platform: bool
    probes: Mapping[str, str]
    minimum_capabilities: Mapping[str, str]


@dataclass(frozen=True)
class PlatformProbeInputs:
    binding: LockedPlatformBinding
    caller_context: VerifiedCallerContext
    observed_harness_version: str
    probe: CapabilityProbe
    enforce_minimums: bool = False


def _failure(message: str, **details: object) -> RouteFailure:
    return RouteFailure("AWP_ADAPTER_CAPABILITY_UNVERIFIED", message, details=details)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("platform capability object is invalid", field=field)
    return cast(Mapping[str, object], value)


def _token(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise _failure("platform capability token is invalid", field=field)
    return value


def _string_map(value: object, field: str) -> Mapping[str, str]:
    raw = _mapping(value, field)
    normalized = {
        _token(key, f"{field}.key"): _token(item, f"{field}.{key}")
        for key, item in raw.items()
    }
    return MappingProxyType(dict(sorted(normalized.items())))


def _load_platform_binding(root: Path, platform: str) -> LockedPlatformBinding:
    """Load one immutable platform row from the sole declarative catalog."""

    path = root / "catalog/platforms.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[no-untyped-call]
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise _failure("platform catalog cannot be loaded") from error
    if not isinstance(document, Mapping) or set(document) != {
        "schema_id",
        "schema_version",
        "platforms",
    }:
        raise _failure("platform catalog fields are not closed")
    if document.get("schema_id") != "agent-workflow.platform-catalog" or document.get(
        "schema_version"
    ) != 1:
        raise _failure("platform catalog identity/version is invalid")
    rows = document.get("platforms")
    if not isinstance(rows, list):
        raise _failure("platform catalog rows are invalid")
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and isinstance(row.get("adapter"), Mapping)
        and row["adapter"].get("platform") == platform
    ]
    if len(matches) != 1:
        raise _failure("platform catalog does not contain one exact platform", platform=platform)
    row = cast(Mapping[str, object], matches[0])
    if set(row) != {
        "adapter",
        "harness_id",
        "harness_version",
        "caller_platform_id",
        "version_probe_id",
        "default_platform",
        "probes",
        "minimum_capabilities",
    }:
        raise _failure("platform catalog row fields are not closed", platform=platform)
    adapter = validate_platform_adapter(_mapping(row.get("adapter"), "adapter"))
    harness_id = _token(row.get("harness_id"), "harness_id")
    harness_version = _token(row.get("harness_version"), "harness_version")
    if adapter.tested_harness_versions != (harness_version,):
        raise _failure("platform tested harness set differs from locked version")
    caller_platform_id = _token(row.get("caller_platform_id"), "caller_platform_id")
    version_probe_id = _token(row.get("version_probe_id"), "version_probe_id")
    default_platform = row.get("default_platform")
    if not isinstance(default_platform, bool):
        raise _failure("default platform marker is invalid")
    probes = _string_map(row.get("probes"), "probes")
    minimums = _string_map(row.get("minimum_capabilities"), "minimum_capabilities")
    capability_ids = set(cast(list[str], adapter.capability_probe_suite["capability_ids"]))
    if set(probes) != capability_ids or set(minimums) != capability_ids:
        raise _failure("platform probe/minimum inventory differs from adapter contract")
    if len(set(probes.values())) != len(probes):
        raise _failure("platform probe IDs are duplicated")
    if set(minimums.values()) - set(_LEVELS):
        raise _failure("platform minimum capability level is invalid")
    return LockedPlatformBinding(
        adapter=adapter,
        harness_id=harness_id,
        harness_version=harness_version,
        caller_platform_id=caller_platform_id,
        version_probe_id=version_probe_id,
        default_platform=default_platform,
        probes=probes,
        minimum_capabilities=minimums,
    )


def _measure_result(
    binding: LockedPlatformBinding,
    capability_id: str,
    raw: Mapping[str, object],
) -> tuple[str, dict[str, object]]:
    if set(raw) != _PROBE_RESULT_FIELDS:
        raise _failure("capability probe result fields are not closed", capability=capability_id)
    if raw.get("probe_id") != binding.probes[capability_id] or raw.get(
        "capability_id"
    ) != capability_id:
        raise _failure("capability probe identity differs", capability=capability_id)
    booleans = {
        field: raw.get(field)
        for field in (
            "read_only",
            "supported",
            "instruction_present",
            "enforcement_verified",
            "bypass_closed",
        )
    }
    if not all(isinstance(value, bool) for value in booleans.values()):
        raise _failure("capability probe facts are invalid", capability=capability_id)
    if booleans["read_only"] is not True:
        raise _failure("ordinary capability probe attempted a write", capability=capability_id)
    evidence_id = _token(raw.get("integration_evidence_id"), "integration_evidence_id")
    if booleans["supported"] is not True:
        level = "unsupported"
    elif booleans["enforcement_verified"] is True:
        if booleans["bypass_closed"] is not True:
            raise RouteFailure(
                "AWP_ADAPTER_BYPASS_DETECTED",
                "capability bypass remains reachable",
                details={"capability": capability_id},
            )
        level = "enforced"
    elif booleans["instruction_present"] is True:
        level = "instruction-only"
    else:
        level = "unsupported"
    evidence = {
        "capability_id": capability_id,
        "probe_id": binding.probes[capability_id],
        "level": level,
        "integration_evidence_id": evidence_id,
        "bypass_closed": booleans["bypass_closed"],
    }
    return level, evidence


def measure_capability_manifest(inputs: PlatformProbeInputs) -> Mapping[str, object]:
    """Run only locked read-only probes and normalize their finite evidence."""

    if not isinstance(inputs, PlatformProbeInputs) or not isinstance(
        inputs.caller_context, VerifiedCallerContext
    ):
        raise _failure("verified platform probe inputs are required")
    binding = inputs.binding
    context = inputs.caller_context
    if (
        context.platform != binding.caller_platform_id
        or context.harness_version_probe_id != binding.version_probe_id
    ):
        raise _failure("caller context differs from platform contract")
    if (
        inputs.observed_harness_version != binding.harness_version
        or inputs.observed_harness_version not in binding.adapter.tested_harness_versions
    ):
        raise _failure("harness version is outside the locked tested contract")
    if not callable(inputs.probe):
        raise _failure("capability probe implementation is unavailable")

    levels: dict[str, str] = {}
    evidence: list[dict[str, object]] = []
    for capability_id in sorted(binding.probes):
        try:
            raw = inputs.probe(binding.probes[capability_id], capability_id, context)
        except Exception as error:
            raise _failure("capability probe failed", capability=capability_id) from error
        level, normalized = _measure_result(binding, capability_id, _mapping(raw, "probe"))
        levels[capability_id] = level
        evidence.append(normalized)

    if inputs.enforce_minimums:
        unmet = [
            capability_id
            for capability_id, required in binding.minimum_capabilities.items()
            if _LEVELS[levels[capability_id]] < _LEVELS[required]
        ]
        if unmet:
            raise _failure("default platform minimum capabilities are unmet", capabilities=unmet)

    approval_verifiers = {
        key: dict(cast(Mapping[str, object], value))
        for key, value in binding.adapter.approval_verifiers.items()
    }
    manifest: dict[str, object] = {
        "schema_id": "agent-workflow.capability-manifest",
        "schema_version": 1,
        "platform": binding.adapter.platform.value,
        "adapter_id": binding.adapter.adapter_id,
        "adapter_version": binding.adapter.adapter_version,
        "harness_id": binding.harness_id,
        "harness_version": binding.harness_version,
        "probe_suite_id": binding.adapter.capability_probe_suite["probe_suite_id"],
        "probe_suite_version": binding.adapter.capability_probe_suite[
            "probe_suite_version"
        ],
        "capabilities": dict(sorted(levels.items())),
        "approval_verifiers": approval_verifiers,
    }
    manifest["evidence_digest"] = digest(
        "agent-workflow.capability-evidence.v1",
        {
            "platform": manifest["platform"],
            "adapter_id": manifest["adapter_id"],
            "adapter_version": manifest["adapter_version"],
            "harness_id": manifest["harness_id"],
            "harness_version": manifest["harness_version"],
            "probe_suite_id": manifest["probe_suite_id"],
            "probe_suite_version": manifest["probe_suite_version"],
            "evidence": evidence,
        },
    )
    manifest["capabilities"] = MappingProxyType(cast(dict[str, str], manifest["capabilities"]))
    manifest["approval_verifiers"] = MappingProxyType(approval_verifiers)
    return MappingProxyType(manifest)
