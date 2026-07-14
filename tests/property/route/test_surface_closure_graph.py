from __future__ import annotations

import dataclasses
from types import MappingProxyType

import pytest

from agent_stack.core.surfaces import SurfaceDescriptor, VerifiedSurfaceRegistry
from agent_stack.route.errors import RouteFailure
from agent_stack.route.surfaces import (
    VerifiedRuntimeSurfaceRegistry,
    derive_task_surface_closure,
)
from tests.unit.route.test_surface_closure import ids, verified_registry


def _replace_surface(
    runtime: VerifiedRuntimeSurfaceRegistry,
    surface_id: str,
    *,
    references: tuple[str, ...],
) -> VerifiedRuntimeSurfaceRegistry:
    surfaces = dict(runtime.registry.surfaces)
    original = surfaces[surface_id]
    surfaces[surface_id] = dataclasses.replace(original, references=references)
    registry = dataclasses.replace(
        runtime.registry,
        surfaces=MappingProxyType(surfaces),
    )
    return dataclasses.replace(runtime, registry=registry)


def test_dangling_cycle_duplicate_topology_and_digest_mismatch_fail_closed() -> None:
    valid = verified_registry()
    dangling = _replace_surface(
        valid, "runtime-entry:trellis-implement", references=("missing",)
    )
    cycle = _replace_surface(
        valid, "runtime-control-plane", references=("surface-registry", "skill:tdd")
    )
    duplicate_topology_registry = dataclasses.replace(
        valid.registry,
        topological_surface_ids=(
            *valid.registry.topological_surface_ids,
            valid.registry.topological_surface_ids[-1],
        ),
    )
    duplicate_topology = dataclasses.replace(valid, registry=duplicate_topology_registry)
    missing_digest = dataclasses.replace(
        valid,
        surface_digests=MappingProxyType(
            {
                key: value
                for key, value in valid.surface_digests.items()
                if key != "skill:tdd"
            }
        ),
    )

    for candidate in (dangling, cycle, duplicate_topology, missing_digest):
        with pytest.raises(RouteFailure, match="AWP_ROUTE_SURFACE_CLOSURE_INVALID"):
            derive_task_surface_closure(
                "trellis-native", "codex", "trellis-implement", candidate
            )


def test_mapping_order_cannot_change_sorted_closure() -> None:
    valid = verified_registry()
    reversed_surfaces = MappingProxyType(
        dict(reversed(tuple(valid.registry.surfaces.items())))
    )
    reordered_registry = VerifiedSurfaceRegistry(
        surfaces=reversed_surfaces,
        units=valid.registry.units,
        topological_surface_ids=valid.registry.topological_surface_ids,
        registry_digest=valid.registry.registry_digest,
    )
    reordered = dataclasses.replace(valid, registry=reordered_registry)

    first = derive_task_surface_closure(
        "speckit-superpowers", "codex", "heavy-development-router", valid
    )
    second = derive_task_surface_closure(
        "speckit-superpowers", "codex", "heavy-development-router", reordered
    )

    assert ids(first) == ids(second)
    assert first == second


def test_surface_descriptor_identity_must_match_registry_key() -> None:
    valid = verified_registry()
    surfaces = dict(valid.registry.surfaces)
    original = surfaces["skill:tdd"]
    surfaces["skill:tdd"] = SurfaceDescriptor(
        surface_id="skill:other",
        surface_kind=original.surface_kind,
        descriptor_version=original.descriptor_version,
        digest_recipe_id=original.digest_recipe_id,
        owned_unit_ids=original.owned_unit_ids,
        references=original.references,
        contract_change_class=original.contract_change_class,
    )
    malformed = dataclasses.replace(
        valid,
        registry=dataclasses.replace(
            valid.registry,
            surfaces=MappingProxyType(surfaces),
        ),
    )

    with pytest.raises(RouteFailure, match="AWP_ROUTE_SURFACE_CLOSURE_INVALID"):
        derive_task_surface_closure(
            "trellis-native", "codex", "trellis-implement", malformed
        )
