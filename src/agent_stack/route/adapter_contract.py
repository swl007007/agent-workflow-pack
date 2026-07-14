"""Closed immutable platform adapter contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import normalize_mode, normalize_path
from agent_stack.core.errors import CoreFailure

from .errors import RouteFailure


class StablePlatformID(str, Enum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    OPENCODE = "opencode"


_FIELDS = {
    "schema_id",
    "schema_version",
    "platform",
    "adapter_id",
    "adapter_version",
    "tested_harness_versions",
    "native_light_entry_id",
    "caller_context_fields",
    "capability_probe_suite",
    "approval_verifiers",
    "render_projections",
    "wrapper_entries",
    "blocked_bypass_entries",
    "trellis_adapter_contract",
    "golden_contract_id",
}
_CAPABILITIES = {
    "project_instructions",
    "explicit_runtime_load",
    "maintenance_gate",
    "task_admission_gate",
    "task_archive_gate",
    "provider_exception_approval",
    "project_skills",
    "native_light_binding",
    "route_gated_catalog",
    "direct_human_confirmation",
}
_MODES = {"native-light", "trellis-native", "speckit-superpowers"}
_SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")


@dataclass(frozen=True)
class VerifiedPlatformAdapterContract:
    platform: StablePlatformID
    adapter_id: str
    adapter_version: str
    tested_harness_versions: tuple[str, ...]
    native_light_entry_id: str
    caller_context_fields: tuple[str, ...]
    capability_probe_suite: Mapping[str, object]
    approval_verifiers: Mapping[str, object]
    render_projections: tuple[Mapping[str, object], ...]
    wrapper_entries: tuple[Mapping[str, object], ...]
    blocked_bypass_entries: tuple[str, ...]
    trellis_adapter_contract: Mapping[str, object]
    golden_contract_id: str


def _failure(message: str, **details: object) -> RouteFailure:
    return RouteFailure("AWP_ADAPTER_CONTRACT_INVALID", message, details=details)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("adapter object is invalid", field=field)
    return cast(Mapping[str, object], value)


def _array(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _failure("adapter array is invalid", field=field)
    return cast(Sequence[object], value)


def _strings(value: object, field: str, *, sorted_values: bool = False) -> tuple[str, ...]:
    values = _array(value, field)
    if not all(isinstance(item, str) and item for item in values):
        raise _failure("adapter string array is invalid", field=field)
    result = tuple(cast(Sequence[str], values))
    if len(result) != len(set(result)):
        raise _failure("adapter string array contains duplicates", field=field)
    if sorted_values and result != tuple(sorted(result)):
        raise _failure("adapter string array is not sorted", field=field)
    return result


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or any(ord(character) < 0x20 for character in value):
        raise _failure("adapter token is invalid", field=field)
    return value


def _render_projection(raw: object) -> Mapping[str, object]:
    projection = _mapping(raw, "render_projections[]")
    expected = {
        "unit_id",
        "target_path",
        "ownership",
        "merge_strategy",
        "mode",
        "owning_surface_id",
        "template_id",
        "validator_ids",
        "discoverable",
    }
    if set(projection) != expected:
        raise _failure("render projection fields are not closed")
    try:
        path = normalize_path(_token(projection.get("target_path"), "target_path"))
        mode = normalize_mode(cast(str, projection.get("mode")))
    except CoreFailure as error:
        raise _failure("render projection path or mode is invalid") from error
    if projection.get("ownership") not in {"pack-managed", "overlay-managed"}:
        raise _failure("render projection ownership is invalid")
    if projection.get("merge_strategy") not in {"replace", "managed-block", "create-once"}:
        raise _failure("render projection merge strategy is invalid")
    if not isinstance(projection.get("discoverable"), bool):
        raise _failure("render projection discoverability is invalid")
    normalized = dict(projection)
    normalized["target_path"] = path
    normalized["mode"] = mode
    normalized["validator_ids"] = list(_strings(projection.get("validator_ids"), "validator_ids"))
    for field in ("unit_id", "owning_surface_id", "template_id"):
        _token(projection.get(field), field)
    return MappingProxyType(normalized)


def _wrapper(raw: object) -> Mapping[str, object]:
    wrapper = _mapping(raw, "wrapper_entries[]")
    expected = {
        "operation",
        "runtime_entry_id",
        "allowed_modes",
        "allowed_phases",
        "claim_policy",
        "command",
    }
    if set(wrapper) != expected:
        raise _failure("wrapper entry fields are not closed")
    if wrapper.get("operation") not in {"execute-light", "integrated-runtime-load"}:
        raise _failure("wrapper operation is invalid")
    modes = _strings(wrapper.get("allowed_modes"), "allowed_modes")
    if not modes or set(modes) - _MODES:
        raise _failure("wrapper mode is invalid")
    if wrapper.get("operation") == "execute-light" and modes != ("native-light",):
        raise _failure("execute-light wrapper must be native-light only")
    _strings(wrapper.get("allowed_phases"), "allowed_phases")
    if wrapper.get("claim_policy") not in {"forbidden", "optional", "required"}:
        raise _failure("wrapper claim policy is invalid")
    command = _strings(wrapper.get("command"), "command")
    if not command or command[0] != ".agent-workflow/bin/agent-stack":
        raise _failure("wrapper command does not use the project launcher")
    _token(wrapper.get("runtime_entry_id"), "runtime_entry_id")
    return MappingProxyType(dict(wrapper))


def validate_platform_adapter(
    document: Mapping[str, object],
) -> VerifiedPlatformAdapterContract:
    """Validate one exact, version-bound platform adapter contract."""

    if set(document) != _FIELDS:
        raise _failure(
            "platform adapter fields are not closed",
            missing=sorted(_FIELDS - set(document)),
            unknown=sorted(set(document) - _FIELDS),
        )
    if document.get("schema_id") != "agent-workflow.platform-adapter" or document.get(
        "schema_version"
    ) != 1:
        raise _failure("platform adapter schema is unsupported")
    try:
        platform = StablePlatformID(cast(str, document.get("platform")))
    except (TypeError, ValueError) as error:
        raise _failure("platform ID is not supported") from error
    adapter_id = _token(document.get("adapter_id"), "adapter_id")
    if adapter_id != platform.value:
        raise _failure("adapter ID differs from platform")
    version = _token(document.get("adapter_version"), "adapter_version")
    if _SEMVER.fullmatch(version) is None:
        raise _failure("adapter version is invalid")
    harness_versions = _strings(document.get("tested_harness_versions"), "tested_harness_versions")
    if not harness_versions:
        raise _failure("adapter has no tested harness version")
    suite = _mapping(document.get("capability_probe_suite"), "capability_probe_suite")
    if set(suite) != {"probe_suite_id", "probe_suite_version", "capability_ids"}:
        raise _failure("capability probe suite fields are not closed")
    capabilities = _strings(suite.get("capability_ids"), "capability_ids", sorted_values=True)
    if set(capabilities) != _CAPABILITIES:
        raise _failure("capability probe suite is not the closed v0.1 set")
    if suite.get("probe_suite_version") != 1:
        raise _failure("capability probe suite version is unsupported")
    _token(suite.get("probe_suite_id"), "probe_suite_id")
    approvals = _mapping(document.get("approval_verifiers"), "approval_verifiers")
    if set(approvals) != {"task_creation"}:
        raise _failure("approval verifier branches are not closed")
    task_approval = _mapping(approvals.get("task_creation"), "task_creation")
    if set(task_approval) != {
        "verifier_id",
        "verifier_version",
        "actor_source",
        "receipt_source",
    } or task_approval.get("actor_source") != "direct-human":
        raise _failure("task approval verifier is invalid")
    for field in ("verifier_id", "verifier_version", "receipt_source"):
        _token(task_approval.get(field), field)
    projections = tuple(_render_projection(raw) for raw in _array(document.get("render_projections"), "render_projections"))
    wrappers = tuple(_wrapper(raw) for raw in _array(document.get("wrapper_entries"), "wrapper_entries"))
    blocked = _strings(document.get("blocked_bypass_entries"), "blocked_bypass_entries")
    trellis = _mapping(document.get("trellis_adapter_contract"), "trellis_adapter_contract")
    if set(trellis) != {
        "active_root",
        "archive_root",
        "integration_relative_path",
        "precommit_side_effects",
    } or trellis.get("precommit_side_effects") != "disabled":
        raise _failure("Trellis adapter contract is invalid")
    for field in ("active_root", "archive_root", "integration_relative_path"):
        try:
            normalize_path(_token(trellis.get(field), field))
        except CoreFailure as error:
            raise _failure("Trellis adapter path is invalid", field=field) from error
    return VerifiedPlatformAdapterContract(
        platform,
        adapter_id,
        version,
        harness_versions,
        _token(document.get("native_light_entry_id"), "native_light_entry_id"),
        _strings(document.get("caller_context_fields"), "caller_context_fields"),
        MappingProxyType(dict(suite)),
        MappingProxyType(dict(approvals)),
        projections,
        wrappers,
        blocked,
        MappingProxyType(dict(trellis)),
        _token(document.get("golden_contract_id"), "golden_contract_id"),
    )
