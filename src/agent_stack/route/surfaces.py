"""Exact integrated-task runtime surface closure."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from agent_stack.core.surfaces import SurfaceDescriptor, VerifiedSurfaceRegistry

from .adapter_contract import StablePlatformID
from .errors import RouteFailure


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OWNER = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_TASK_LOADABLE_KINDS = {
    "trellis-runtime",
    "router",
    "platform-adapter",
    "hook",
    "agent",
    "skill",
    "runtime-entry",
}


@dataclass(frozen=True)
class VerifiedRuntimeSurfaceRegistry:
    """Core-verified graph plus the corresponding current surface roots."""

    registry: VerifiedSurfaceRegistry
    surface_digests: Mapping[str, str]


def _failure(message: str, **details: object) -> RouteFailure:
    return RouteFailure("AWP_ROUTE_SURFACE_CLOSURE_INVALID", message, details=details)


def _transitive(
    start: str, surfaces: Mapping[str, SurfaceDescriptor]
) -> set[str]:
    visited: set[str] = set()
    pending = list(surfaces[start].references)
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        if current not in surfaces:
            raise _failure("surface reference is dangling", surface_id=start, reference=current)
        visited.add(current)
        pending.extend(surfaces[current].references)
    return visited


def _validate_registry(runtime: VerifiedRuntimeSurfaceRegistry) -> None:
    if not isinstance(runtime, VerifiedRuntimeSurfaceRegistry) or not isinstance(
        runtime.registry, VerifiedSurfaceRegistry
    ):
        raise _failure("verified runtime surface registry is required")
    registry = runtime.registry
    surfaces = registry.surfaces
    units = registry.units
    order = registry.topological_surface_ids
    if len(order) != len(set(order)) or set(order) != set(surfaces):
        raise _failure("surface topological inventory is inconsistent")
    positions = {surface_id: index for index, surface_id in enumerate(order)}
    claimed_units: dict[str, str] = {}
    for key, surface in surfaces.items():
        if key != surface.surface_id:
            raise _failure("surface descriptor identity differs from registry key", surface_id=key)
        if (
            surface.descriptor_version != 1
            or surface.digest_recipe_id != "surface-content-v1"
            or surface.contract_change_class != "runtime-visible"
        ):
            raise _failure("surface descriptor contract is unsupported", surface_id=key)
        if not surface.owned_unit_ids or len(surface.owned_unit_ids) != len(
            set(surface.owned_unit_ids)
        ):
            raise _failure("surface unit ownership is empty or duplicated", surface_id=key)
        for unit_id in surface.owned_unit_ids:
            if unit_id in claimed_units:
                raise _failure("runtime unit is multiply owned", unit_id=unit_id)
            claimed_units[unit_id] = key
        if len(surface.references) != len(set(surface.references)):
            raise _failure("surface references contain duplicates", surface_id=key)
        for reference in surface.references:
            if reference not in surfaces:
                raise _failure("surface reference is dangling", surface_id=key, reference=reference)
            if reference == key or positions[reference] >= positions[key]:
                raise _failure("surface reference graph is cyclic or topologically invalid")
    if set(claimed_units) != set(units):
        raise _failure("surface ownership and runtime unit inventory differ")
    for unit_id, unit in units.items():
        if claimed_units.get(unit_id) != unit.owning_surface_id:
            raise _failure("runtime unit owner differs from surface descriptor", unit_id=unit_id)
    for mandatory in ("runtime-control-plane", "surface-registry"):
        if mandatory not in surfaces:
            raise _failure("mandatory runtime meta-surface is missing", surface_id=mandatory)
    for surface_id, surface in surfaces.items():
        if surface.surface_kind in _TASK_LOADABLE_KINDS:
            missing = {"runtime-control-plane", "surface-registry"} - _transitive(
                surface_id, surfaces
            )
            if missing:
                raise _failure(
                    "task-loadable surface omits mandatory meta-surfaces",
                    surface_id=surface_id,
                    missing=sorted(missing),
                )
    if set(runtime.surface_digests) != set(surfaces):
        raise _failure("surface digest inventory differs from registry")
    if any(
        not isinstance(value, str) or _SHA256.fullmatch(value) is None
        for value in runtime.surface_digests.values()
    ):
        raise _failure("surface digest is missing or invalid")


def _roots(route: str, platform: str, entry_owner: str, registry: VerifiedSurfaceRegistry) -> set[str]:
    if route not in {"trellis-native", "speckit-superpowers"}:
        raise _failure("task surface closure requires an integrated route")
    try:
        stable_platform = StablePlatformID(platform)
    except ValueError as error:
        raise _failure("task surface platform is unsupported") from error
    if _OWNER.fullmatch(entry_owner) is None:
        raise _failure("task surface entry owner is invalid")
    adapter = f"platform-adapter:{stable_platform.value}"
    entry = f"runtime-entry:{entry_owner}"
    roots = {adapter, "trellis-runtime", entry}
    router = f"router:{entry_owner}"
    if route == "trellis-native" and router in registry.surfaces:
        raise _failure("Trellis-native entry owner is a heavy router")
    if route == "speckit-superpowers":
        if router not in registry.surfaces:
            raise _failure("heavy entry owner has no router surface")
        roots.add(router)
    missing = sorted(roots - set(registry.surfaces))
    if missing:
        raise _failure("task surface root is unknown", missing=missing)
    return roots


def derive_task_surface_closure(
    route: str,
    platform: str,
    entry_owner: str,
    registry: VerifiedRuntimeSurfaceRegistry,
) -> tuple[Mapping[str, object], ...]:
    """Return the sorted exact closure selected only from verified registry data."""

    _validate_registry(registry)
    roots = _roots(route, platform, entry_owner, registry.registry)
    selected = set(roots)
    pending = list(roots)
    while pending:
        surface_id = pending.pop()
        for reference in registry.registry.surfaces[surface_id].references:
            if reference not in selected:
                selected.add(reference)
                pending.append(reference)
    if {"runtime-control-plane", "surface-registry"} - selected:
        raise _failure("task surface closure omits mandatory meta-surfaces")
    return tuple(
        MappingProxyType(
            {
                "surface_id": surface_id,
                "surface_digest": registry.surface_digests[surface_id],
            }
        )
        for surface_id in sorted(selected)
    )
