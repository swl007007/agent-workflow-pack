"""Pure deterministic projection of one selected platform adapter."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import DesiredStateIR, digest, normalize_mode, normalize_path
from agent_stack.core.errors import CoreFailure

from .adapter_contract import VerifiedPlatformAdapterContract
from .errors import RouteFailure


_UNIT_FIELDS = {
    "schema_id",
    "schema_version",
    "unit_id",
    "definition_id",
    "source",
    "target",
    "surface_id",
    "validator_ids",
    "candidate_leaf_digest",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GATED_ENTRY_IDS = {
    "router:heavy-development-router",
    "runtime-entry:trellis-native",
    "skill:claude-mem-compactor",
    "skill:sdd-superpower-micro-plan",
    "skill:speckit-evidence-pack",
}


def _failure(message: str, **details: object) -> RouteFailure:
    return RouteFailure("AWP_ADAPTER_PROJECTION_INVALID", message, details=details)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("adapter projection object is invalid", field=field)
    return cast(Mapping[str, object], value)


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _failure("adapter projection string array is invalid", field=field)
    if not all(isinstance(item, str) and item for item in value):
        raise _failure("adapter projection string array is invalid", field=field)
    result = tuple(cast(Sequence[str], value))
    if len(result) != len(set(result)):
        raise _failure("adapter projection string array contains duplicates", field=field)
    return result


def _unit_index(ir: DesiredStateIR) -> dict[str, Mapping[str, object]]:
    units: dict[str, Mapping[str, object]] = {}
    for raw in ir.render_units:
        if set(raw) != _UNIT_FIELDS or raw.get("schema_id") != "agent-workflow.render-unit" or raw.get(
            "schema_version"
        ) != 1:
            raise _failure("IR render-unit fields are not closed")
        unit_id = raw.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id:
            raise _failure("IR render-unit identity is invalid")
        if unit_id in units:
            raise _failure("IR render-unit identity repeats", unit_id=unit_id)
        units[unit_id] = raw
    return units


def _definition_index(ir: DesiredStateIR) -> dict[str, Mapping[str, object]]:
    definitions: dict[str, Mapping[str, object]] = {}
    for raw in ir.artifact_definitions:
        definition_id = raw.get("id")
        if not isinstance(definition_id, str) or not definition_id or definition_id in definitions:
            raise _failure("IR artifact definition identity is invalid")
        definitions[definition_id] = raw
    return definitions


def _definition_target(
    definition: Mapping[str, object], path: str
) -> Mapping[str, object]:
    raw_targets = definition.get("targets")
    if not isinstance(raw_targets, Sequence) or isinstance(raw_targets, (str, bytes)):
        raise _failure("IR artifact targets are invalid")
    matches = [
        raw
        for raw in raw_targets
        if isinstance(raw, Mapping) and raw.get("path") == path
    ]
    if len(matches) != 1:
        raise _failure("IR render target lacks one artifact owner", path=path)
    return cast(Mapping[str, object], matches[0])


def _validate_target(
    target: Mapping[str, object],
    definition_target: Mapping[str, object],
    adapter_projection: Mapping[str, object],
) -> None:
    try:
        path = normalize_path(cast(str, target.get("path")))
    except (CoreFailure, TypeError) as error:
        raise _failure("IR render target path is invalid") from error
    if path != adapter_projection.get("target_path"):
        raise _failure("adapter target path differs from IR", path=path)
    adapter_ownership = adapter_projection.get("ownership")
    if adapter_ownership == "pack-managed":
        expected = {
            "ownership": "managed",
            "merge_strategy": "whole-file",
            "mode_policy": "exact",
        }
        if set(target) != {"path", *expected, "mode"}:
            raise _failure("managed IR target fields are not closed", path=path)
        if normalize_mode(cast(str, target.get("mode"))) != adapter_projection.get("mode"):
            raise _failure("adapter target mode differs from IR", path=path)
    elif adapter_ownership == "overlay-managed":
        expected = {
            "ownership": "overlay-managed",
            "merge_strategy": "marked-block",
            "mode_policy": "preserve",
        }
        if set(target) != {"path", *expected, "markers"}:
            raise _failure("overlay IR target fields are not closed", path=path)
        markers = _mapping(target.get("markers"), "target.markers")
        if set(markers) != {"begin", "end"}:
            raise _failure("overlay IR marker fields are not closed", path=path)
    else:
        raise _failure("adapter target ownership is unsupported")
    if any(target.get(field) != value for field, value in expected.items()):
        raise _failure("adapter ownership policy differs from IR", path=path)
    for field, value in target.items():
        if definition_target.get(field) != value:
            raise _failure("IR target differs from artifact definition", path=path, field=field)


def _project_unit(
    raw: Mapping[str, object],
    adapter_projection: Mapping[str, object],
    definition: Mapping[str, object],
    discoverable: bool,
) -> Mapping[str, object]:
    source = _mapping(raw.get("source"), "source")
    target = _mapping(raw.get("target"), "target")
    if set(source) != {"source_id", "source_digest"}:
        raise _failure("IR render source fields are not closed")
    if source.get("source_id") != definition.get("source"):
        raise _failure("IR render source differs from artifact definition")
    source_digest = source.get("source_digest")
    candidate_digest = raw.get("candidate_leaf_digest")
    if (
        not isinstance(source_digest, str)
        or _SHA256.fullmatch(source_digest) is None
        or not isinstance(candidate_digest, str)
        or _SHA256.fullmatch(candidate_digest) is None
    ):
        raise _failure("IR render digest is invalid")
    path = normalize_path(cast(str, target.get("path")))
    _validate_target(target, _definition_target(definition, path), adapter_projection)
    if raw.get("surface_id") != adapter_projection.get("owning_surface_id"):
        raise _failure("adapter surface owner differs from IR")
    validator_ids = _strings(raw.get("validator_ids"), "validator_ids")
    if validator_ids != _strings(
        adapter_projection.get("validator_ids"), "adapter.validator_ids"
    ):
        raise _failure("adapter validators differ from IR")
    return MappingProxyType(
        {
            "schema_id": raw["schema_id"],
            "schema_version": raw["schema_version"],
            "unit_id": raw["unit_id"],
            "definition_id": raw["definition_id"],
            "source": MappingProxyType(dict(source)),
            "target": MappingProxyType(dict(target)),
            "surface_id": raw["surface_id"],
            "validator_ids": validator_ids,
            "candidate_leaf_digest": candidate_digest,
            "discoverable": discoverable,
        }
    )


def _validate_exposure(ir: DesiredStateIR) -> None:
    discoverable = set(_strings(ir.discoverable_leaf_ids, "discoverable_leaf_ids"))
    references = set(_strings(ir.reference_closure, "reference_closure"))
    leaked = sorted((discoverable | references) & _GATED_ENTRY_IDS)
    if leaked:
        raise _failure("route-gated entry leaked into discoverable/reference closure", entries=leaked)
    disabled_raw = ir.resolved_profile.get("skills_disable", ())
    disabled = set(_strings(disabled_raw, "resolved_profile.skills_disable"))
    overlap = sorted(disabled & (discoverable | references))
    if overlap:
        raise _failure("disabled entry entered discoverable/reference closure", entries=overlap)


def project_platform_adapter(
    ir: DesiredStateIR,
    adapter: VerifiedPlatformAdapterContract,
) -> Mapping[str, object]:
    """Select only adapter-declared units already present in the verified IR."""

    if not isinstance(ir, DesiredStateIR) or not isinstance(
        adapter, VerifiedPlatformAdapterContract
    ):
        raise _failure("verified IR and platform adapter are required")
    if adapter.platform.value not in ir.selected_platforms:
        raise _failure("platform adapter is not selected by the IR")
    _validate_exposure(ir)
    units = _unit_index(ir)
    definitions = _definition_index(ir)
    adapter_units = {
        cast(str, projection["unit_id"]) for projection in adapter.render_projections
    }
    if len(adapter_units) != len(adapter.render_projections):
        raise _failure("adapter render-unit identities repeat")
    owned_in_ir = {
        unit_id
        for unit_id, raw in units.items()
        if raw.get("surface_id") == f"platform-adapter:{adapter.platform.value}"
    }
    if owned_in_ir != adapter_units:
        raise _failure(
            "adapter and IR unit inventories differ",
            missing=sorted(adapter_units - owned_in_ir),
            undeclared=sorted(owned_in_ir - adapter_units),
        )

    discoverable_ids = set(ir.discoverable_leaf_ids)
    projected_units: list[Mapping[str, object]] = []
    for adapter_projection in adapter.render_projections:
        unit_id = cast(str, adapter_projection["unit_id"])
        raw = units[unit_id]
        definition_id = raw.get("definition_id")
        if not isinstance(definition_id, str) or definition_id not in definitions:
            raise _failure("adapter unit references an unknown artifact definition")
        expected_discoverable = bool(adapter_projection["discoverable"])
        if (unit_id in discoverable_ids) != expected_discoverable:
            raise _failure("adapter discoverability differs from IR", unit_id=unit_id)
        projected_units.append(
            _project_unit(
                raw,
                adapter_projection,
                definitions[definition_id],
                expected_discoverable,
            )
        )

    projection: dict[str, object] = {
        "schema_id": "agent-workflow.platform-adapter-projection",
        "schema_version": 1,
        "platform": adapter.platform.value,
        "adapter_id": adapter.adapter_id,
        "adapter_version": adapter.adapter_version,
        "units": tuple(projected_units),
        "wrappers": tuple(MappingProxyType(dict(item)) for item in adapter.wrapper_entries),
        "blocked_bypass_entries": adapter.blocked_bypass_entries,
    }
    projection["projection_digest"] = digest(
        "agent-workflow.platform-adapter-projection.v1", projection
    )
    return MappingProxyType(projection)
