"""Runtime-surface registry, digest graph, and full-coverage witness."""

from __future__ import annotations

import hashlib
import heapq
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from .canonical import CANONICAL_NULL, canonical_json_bytes, digest, normalize_mode, normalize_path
from .errors import CoreFailure


_REGISTRY_FIELDS = {"schema_id", "schema_version", "surfaces"}
_SURFACE_FIELDS = {
    "surface_id",
    "surface_kind",
    "descriptor_version",
    "digest_recipe_id",
    "owned_unit_ids",
    "references",
    "contract_change_class",
}
_INVENTORY_FIELDS = {"schema_id", "schema_version", "units"}
_UNIT_FIELDS = {
    "unit_id",
    "unit_kind",
    "distribution_scope",
    "normalized_path",
    "owning_surface_id",
    "leaf_recipe_id",
    "runtime_visible",
}
_EVIDENCE_FIELDS = {
    "unit_id",
    "byte_hash",
    "mode",
    "contract_digest",
    "distributions",
}
_UNIT_ID = re.compile(r"^[a-z][a-z0-9-]*:[a-z0-9][a-z0-9._:/-]*$")
_SURFACE_SUFFIX = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_TASK_LOADABLE_KINDS = {
    "trellis-runtime",
    "router",
    "platform-adapter",
    "hook",
    "agent",
    "skill",
    "runtime-entry",
}
_EXPECTED_DISTRIBUTIONS = {
    "runtime-package": ("git-checkout", "sdist", "wheel"),
    "rendered-project": ("rendered-project",),
}


@dataclass(frozen=True)
class SurfaceDescriptor:
    surface_id: str
    surface_kind: str
    descriptor_version: int
    digest_recipe_id: str
    owned_unit_ids: tuple[str, ...]
    references: tuple[str, ...]
    contract_change_class: str


@dataclass(frozen=True)
class RuntimeUnitDescriptor:
    unit_id: str
    unit_kind: str
    distribution_scope: str
    normalized_path: str
    owning_surface_id: str
    leaf_recipe_id: str


@dataclass(frozen=True)
class VerifiedSurfaceRegistry:
    surfaces: Mapping[str, SurfaceDescriptor]
    units: Mapping[str, RuntimeUnitDescriptor]
    topological_surface_ids: tuple[str, ...]
    registry_digest: str


@dataclass(frozen=True)
class UnitEvidence:
    unit_id: str
    byte_hash: str
    mode: str
    contract_digest: str
    distributions: tuple[str, ...]
    leaf_digest: str


@dataclass(frozen=True)
class SurfaceCoverageProof:
    covered_unit_ids: tuple[str, ...]
    surface_ids: tuple[str, ...]
    registry_digest: str
    proof_digest: str


def _graph_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_SURFACE_GRAPH_INVALID", message, details=details)


def _coverage_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_SURFACE_COVERAGE_INVALID", message, details=details)


def _string_set(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _graph_failure(f"{label} must be a string array")
    normalized = tuple(sorted(set(value)))
    if len(normalized) != len(value):
        raise _graph_failure(f"{label} contains duplicates")
    return normalized


def _surface_kind(surface_id: str) -> str | None:
    exact = {
        "runtime-control-plane": "runtime-control-plane",
        "surface-registry": "surface-registry",
        "trellis-runtime": "trellis-runtime",
        "trellis-layout": "trellis-layout",
        "route-policy": "route-policy",
    }
    if surface_id in exact:
        return exact[surface_id]
    prefixes = {
        "router": 2,
        "platform-adapter": 2,
        "hook": 3,
        "agent": 3,
        "skill": 2,
        "runtime-entry": 2,
    }
    parts = surface_id.split(":")
    expected_parts = prefixes.get(parts[0])
    if expected_parts is None or len(parts) != expected_parts:
        return None
    if not all(_SURFACE_SUFFIX.fullmatch(part) for part in parts[1:]):
        return None
    return parts[0]


def _parse_surfaces(document: Mapping[str, object]) -> dict[str, SurfaceDescriptor]:
    if set(document) != _REGISTRY_FIELDS:
        raise _graph_failure("runtime-surface registry fields are not closed")
    if document.get("schema_id") != "agent-workflow.runtime-surface-registry" or document.get(
        "schema_version"
    ) != 1:
        raise _graph_failure("runtime-surface registry schema identity/version is invalid")
    raw_surfaces = document.get("surfaces")
    if not isinstance(raw_surfaces, list):
        raise _graph_failure("surfaces must be an array")
    surfaces: dict[str, SurfaceDescriptor] = {}
    for raw in raw_surfaces:
        if not isinstance(raw, Mapping) or set(raw) != _SURFACE_FIELDS:
            raise _graph_failure("surface descriptor fields are not closed")
        surface_id = raw.get("surface_id")
        surface_kind = raw.get("surface_kind")
        if not isinstance(surface_id, str) or not isinstance(surface_kind, str):
            raise _graph_failure("surface identity and kind must be strings")
        expected_kind = _surface_kind(surface_id)
        if expected_kind is None or surface_kind != expected_kind:
            raise _graph_failure(
                "surface id is outside the reserved namespace or disagrees with kind",
                surface_id=surface_id,
            )
        if surface_id in surfaces:
            raise _graph_failure("duplicate surface id", surface_id=surface_id)
        if raw.get("descriptor_version") != 1:
            raise _graph_failure("surface descriptor version is unsupported", surface_id=surface_id)
        if raw.get("digest_recipe_id") != "surface-content-v1":
            raise _graph_failure("surface digest recipe is unsupported", surface_id=surface_id)
        if raw.get("contract_change_class") != "runtime-visible":
            raise _graph_failure("surface contract change class must be runtime-visible")
        owned_units = _string_set(raw.get("owned_unit_ids"), "owned_unit_ids")
        references = _string_set(raw.get("references"), "references")
        if not owned_units:
            raise _coverage_failure("every surface must own at least one runtime unit", surface_id=surface_id)
        surfaces[surface_id] = SurfaceDescriptor(
            surface_id=surface_id,
            surface_kind=surface_kind,
            descriptor_version=1,
            digest_recipe_id="surface-content-v1",
            owned_unit_ids=owned_units,
            references=references,
            contract_change_class="runtime-visible",
        )
    for mandatory in ("runtime-control-plane", "surface-registry"):
        if mandatory not in surfaces:
            raise _graph_failure("mandatory runtime meta-surface is missing", surface_id=mandatory)
    return surfaces


def _parse_units(document: Mapping[str, object]) -> dict[str, RuntimeUnitDescriptor]:
    if set(document) != _INVENTORY_FIELDS:
        raise _coverage_failure("runtime-unit inventory fields are not closed")
    if document.get("schema_id") != "agent-workflow.runtime-unit-inventory" or document.get(
        "schema_version"
    ) != 1:
        raise _coverage_failure("runtime-unit inventory schema identity/version is invalid")
    raw_units = document.get("units")
    if not isinstance(raw_units, list):
        raise _coverage_failure("runtime units must be an array")
    units: dict[str, RuntimeUnitDescriptor] = {}
    paths: dict[str, str] = {}
    for raw in raw_units:
        if not isinstance(raw, Mapping) or set(raw) != _UNIT_FIELDS:
            raise _coverage_failure("runtime-unit descriptor fields are not closed")
        unit_id = raw.get("unit_id")
        unit_kind = raw.get("unit_kind")
        owner = raw.get("owning_surface_id")
        scope = raw.get("distribution_scope")
        path_value = raw.get("normalized_path")
        if not isinstance(unit_id, str) or not _UNIT_ID.fullmatch(unit_id):
            raise _coverage_failure("runtime unit id is invalid", unit_id=unit_id)
        if not isinstance(unit_kind, str) or unit_id.split(":", 1)[0] != unit_kind:
            raise _coverage_failure("runtime unit kind disagrees with id", unit_id=unit_id)
        if not isinstance(owner, str):
            raise _coverage_failure("runtime unit owner must be a surface id", unit_id=unit_id)
        if scope not in _EXPECTED_DISTRIBUTIONS:
            raise _coverage_failure("runtime unit distribution scope is invalid", unit_id=unit_id)
        if not isinstance(path_value, str):
            raise _coverage_failure("runtime unit path must be a string", unit_id=unit_id)
        path = normalize_path(path_value)
        if raw.get("leaf_recipe_id") != "bytes-mode-contract-v1":
            raise _coverage_failure("runtime unit leaf recipe is unsupported", unit_id=unit_id)
        if raw.get("runtime_visible") is not True:
            raise _coverage_failure("inventory may contain only runtime-visible units", unit_id=unit_id)
        if unit_id in units:
            raise _coverage_failure("duplicate runtime unit id", unit_id=unit_id)
        path_key = path.casefold()
        if path_key in paths:
            raise _coverage_failure(
                "runtime unit paths collide after normalization",
                path=path,
                first_unit=paths[path_key],
                second_unit=unit_id,
            )
        paths[path_key] = unit_id
        units[unit_id] = RuntimeUnitDescriptor(
            unit_id=unit_id,
            unit_kind=unit_kind,
            distribution_scope=scope,
            normalized_path=path,
            owning_surface_id=owner,
            leaf_recipe_id="bytes-mode-contract-v1",
        )
    return units


def _topological_order(surfaces: Mapping[str, SurfaceDescriptor]) -> tuple[str, ...]:
    consumers: dict[str, set[str]] = {surface_id: set() for surface_id in surfaces}
    indegree = {surface_id: 0 for surface_id in surfaces}
    for surface_id, surface in surfaces.items():
        for reference in surface.references:
            if reference not in surfaces:
                raise _graph_failure(
                    "surface reference is dangling", surface_id=surface_id, reference=reference
                )
            if reference == surface_id:
                raise _graph_failure("surface may not reference itself", surface_id=surface_id)
            if surface_id not in consumers[reference]:
                consumers[reference].add(surface_id)
                indegree[surface_id] += 1
    ready = [surface_id for surface_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        surface_id = heapq.heappop(ready)
        ordered.append(surface_id)
        for consumer in sorted(consumers[surface_id]):
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                heapq.heappush(ready, consumer)
    if len(ordered) != len(surfaces):
        raise _graph_failure(
            "surface reference graph is cyclic",
            surfaces=sorted(surface_id for surface_id, count in indegree.items() if count > 0),
        )
    return tuple(ordered)


def _transitive_references(
    surface_id: str, surfaces: Mapping[str, SurfaceDescriptor]
) -> set[str]:
    visited: set[str] = set()
    pending = list(surfaces[surface_id].references)
    while pending:
        reference = pending.pop()
        if reference in visited:
            continue
        visited.add(reference)
        pending.extend(surfaces[reference].references)
    return visited


def validate_surface_registry(
    registry_document: Mapping[str, object], inventory_document: Mapping[str, object]
) -> VerifiedSurfaceRegistry:
    """Validate the closed ownership graph without accepting computed roots."""

    surfaces = _parse_surfaces(registry_document)
    units = _parse_units(inventory_document)
    ordered = _topological_order(surfaces)

    claimed_owners: dict[str, str] = {}
    for surface_id, surface in surfaces.items():
        for unit_id in surface.owned_unit_ids:
            if unit_id in claimed_owners:
                raise _coverage_failure(
                    "runtime unit is multiply owned",
                    unit_id=unit_id,
                    first_owner=claimed_owners[unit_id],
                    second_owner=surface_id,
                )
            claimed_owners[unit_id] = surface_id
    if set(claimed_owners) != set(units):
        raise _coverage_failure(
            "surface ownership and unit inventory differ",
            unowned=sorted(set(units) - set(claimed_owners)),
            unknown=sorted(set(claimed_owners) - set(units)),
        )
    for unit_id, unit in units.items():
        if unit.owning_surface_id not in surfaces:
            raise _coverage_failure("runtime unit owner does not exist", unit_id=unit_id)
        if claimed_owners[unit_id] != unit.owning_surface_id:
            raise _coverage_failure(
                "runtime unit owner disagrees with surface descriptor", unit_id=unit_id
            )

    for surface_id, surface in surfaces.items():
        if surface.surface_kind in _TASK_LOADABLE_KINDS:
            references = _transitive_references(surface_id, surfaces)
            missing = {"runtime-control-plane", "surface-registry"} - references
            if missing:
                raise _coverage_failure(
                    "task-loadable surface omits mandatory transitive runtime surfaces",
                    surface_id=surface_id,
                    missing=sorted(missing),
                )

    registry_projection = {
        "schema_id": "agent-workflow.runtime-surface-registry",
        "schema_version": 1,
        "surfaces": [
            {
                "surface_id": surface.surface_id,
                "surface_kind": surface.surface_kind,
                "descriptor_version": surface.descriptor_version,
                "digest_recipe_id": surface.digest_recipe_id,
                "owned_unit_ids": list(surface.owned_unit_ids),
                "references": list(surface.references),
                "contract_change_class": surface.contract_change_class,
            }
            for surface in (surfaces[surface_id] for surface_id in sorted(surfaces))
        ],
        "inventory": [
            {
                "unit_id": unit.unit_id,
                "unit_kind": unit.unit_kind,
                "distribution_scope": unit.distribution_scope,
                "normalized_path": unit.normalized_path,
                "owning_surface_id": unit.owning_surface_id,
                "leaf_recipe_id": unit.leaf_recipe_id,
            }
            for unit in (units[unit_id] for unit_id in sorted(units))
        ],
    }
    registry_digest = digest("agent-workflow.surface-registry.v1", registry_projection)
    return VerifiedSurfaceRegistry(
        surfaces=MappingProxyType({key: surfaces[key] for key in sorted(surfaces)}),
        units=MappingProxyType({key: units[key] for key in sorted(units)}),
        topological_surface_ids=ordered,
        registry_digest=registry_digest,
    )


def _parse_evidence(
    registry: VerifiedSurfaceRegistry, evidence: Sequence[Mapping[str, object]]
) -> Mapping[str, UnitEvidence]:
    parsed: dict[str, UnitEvidence] = {}
    for raw in evidence:
        if set(raw) != _EVIDENCE_FIELDS:
            raise _coverage_failure("runtime unit evidence fields are not closed")
        unit_id = raw.get("unit_id")
        if not isinstance(unit_id, str) or unit_id not in registry.units:
            raise _coverage_failure("runtime unit evidence identity is unknown", unit_id=unit_id)
        if unit_id in parsed:
            raise _coverage_failure("duplicate runtime unit evidence", unit_id=unit_id)
        byte_hash = raw.get("byte_hash")
        contract_digest = raw.get("contract_digest")
        if not isinstance(byte_hash, str) or not _SHA256.fullmatch(byte_hash):
            raise _coverage_failure("runtime unit byte hash is missing or invalid", unit_id=unit_id)
        if not isinstance(contract_digest, str) or not (
            _SHA256.fullmatch(contract_digest) or contract_digest == CANONICAL_NULL
        ):
            raise _coverage_failure(
                "runtime unit contract digest is missing or invalid", unit_id=unit_id
            )
        mode_value = raw.get("mode")
        if not isinstance(mode_value, (str, int)) or isinstance(mode_value, bool):
            raise _coverage_failure("runtime unit mode is missing or invalid", unit_id=unit_id)
        mode = normalize_mode(mode_value)
        distributions_value = raw.get("distributions")
        if not isinstance(distributions_value, list) or not all(
            isinstance(item, str) for item in distributions_value
        ):
            raise _coverage_failure("runtime unit distributions must be a string array")
        distributions = tuple(sorted(set(distributions_value)))
        if len(distributions) != len(distributions_value):
            raise _coverage_failure("runtime unit distributions contain duplicates", unit_id=unit_id)
        expected = _EXPECTED_DISTRIBUTIONS[registry.units[unit_id].distribution_scope]
        if distributions != expected:
            raise _coverage_failure(
                "runtime unit distribution ownership is not equivalent",
                unit_id=unit_id,
                expected=list(expected),
                observed=list(distributions),
            )
        leaf_projection = {
            "unit_id": unit_id,
            "leaf_recipe_id": registry.units[unit_id].leaf_recipe_id,
            "byte_hash": byte_hash,
            "mode": mode,
            "contract_digest": contract_digest,
        }
        leaf_digest = hashlib.sha256(canonical_json_bytes(leaf_projection)).hexdigest()
        parsed[unit_id] = UnitEvidence(
            unit_id=unit_id,
            byte_hash=byte_hash,
            mode=mode,
            contract_digest=contract_digest,
            distributions=distributions,
            leaf_digest=leaf_digest,
        )
    if set(parsed) != set(registry.units):
        raise _coverage_failure(
            "runtime unit evidence is incomplete",
            missing=sorted(set(registry.units) - set(parsed)),
            unknown=sorted(set(parsed) - set(registry.units)),
        )
    return MappingProxyType(parsed)


def _compute_digests(
    registry: VerifiedSurfaceRegistry, evidence: Mapping[str, UnitEvidence]
) -> dict[str, str]:
    surface_digests: dict[str, str] = {}
    for surface_id in registry.topological_surface_ids:
        surface = registry.surfaces[surface_id]
        projection = {
            "surface_id": surface.surface_id,
            "surface_kind": surface.surface_kind,
            "descriptor_version": surface.descriptor_version,
            "digest_recipe_id": surface.digest_recipe_id,
            "owned_units": [
                {"unit_id": unit_id, "leaf_digest": evidence[unit_id].leaf_digest}
                for unit_id in surface.owned_unit_ids
            ],
            "references": [
                {"surface_id": reference, "surface_digest": surface_digests[reference]}
                for reference in surface.references
            ],
        }
        surface_digests[surface_id] = digest("agent-workflow.runtime-surface.v1", projection)
    return surface_digests


def compute_surface_digests(
    registry: VerifiedSurfaceRegistry, evidence: Sequence[Mapping[str, object]]
) -> Mapping[str, str]:
    """Compute task-pinnable surface roots in stable topological order."""

    parsed_evidence = _parse_evidence(registry, evidence)
    return MappingProxyType(_compute_digests(registry, parsed_evidence))


def prove_surface_coverage(
    registry: VerifiedSurfaceRegistry, evidence: Sequence[Mapping[str, object]]
) -> SurfaceCoverageProof:
    """Produce a release-neutral witness over actual units and ownership."""

    parsed_evidence = _parse_evidence(registry, evidence)
    surface_digests = _compute_digests(registry, parsed_evidence)
    projection = {
        "registry_digest": registry.registry_digest,
        "units": [
            {
                "unit_id": unit_id,
                "normalized_path": registry.units[unit_id].normalized_path,
                "owning_surface_id": registry.units[unit_id].owning_surface_id,
                "leaf_digest": parsed_evidence[unit_id].leaf_digest,
                "distributions": list(parsed_evidence[unit_id].distributions),
            }
            for unit_id in sorted(registry.units)
        ],
        "surfaces": [
            {"surface_id": surface_id, "surface_digest": surface_digests[surface_id]}
            for surface_id in registry.topological_surface_ids
        ],
        "graph_valid": True,
    }
    proof_digest = digest("agent-workflow.surface-coverage.v1", projection)
    return SurfaceCoverageProof(
        covered_unit_ids=tuple(sorted(registry.units)),
        surface_ids=registry.topological_surface_ids,
        registry_digest=registry.registry_digest,
        proof_digest=proof_digest,
    )
