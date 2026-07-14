from __future__ import annotations

import dataclasses

import pytest

from agent_stack.core.api import digest
from agent_stack.core.surfaces import compute_surface_digests, validate_surface_registry
from agent_stack.route.calculator import RouteCalculationInputs, calculate_route
from agent_stack.route.errors import RouteFailure
from agent_stack.route.surfaces import (
    VerifiedRuntimeSurfaceRegistry,
    derive_task_surface_closure,
)
from tests.unit.route.test_calculator import authorities, intent


def _surface(surface_id: str, references: list[str]) -> dict[str, object]:
    exact = {
        "runtime-control-plane": "runtime-control-plane",
        "surface-registry": "surface-registry",
        "trellis-runtime": "trellis-runtime",
    }
    kind = exact.get(surface_id, surface_id.split(":", 1)[0])
    slug = surface_id.replace(":", "-")
    return {
        "surface_id": surface_id,
        "surface_kind": kind,
        "descriptor_version": 1,
        "digest_recipe_id": "surface-content-v1",
        "owned_unit_ids": [f"module:{slug}"],
        "references": references,
        "contract_change_class": "runtime-visible",
    }


def verified_registry() -> VerifiedRuntimeSurfaceRegistry:
    surface_documents = [
        _surface("surface-registry", []),
        _surface("runtime-control-plane", ["surface-registry"]),
        _surface("hook:shared:task", ["runtime-control-plane"]),
        _surface("skill:tdd", ["hook:shared:task", "runtime-control-plane"]),
        _surface("skill:evidence", ["runtime-control-plane"]),
        _surface("agent:trellis:runtime", ["runtime-control-plane", "skill:tdd"]),
        _surface("trellis-runtime", ["agent:trellis:runtime", "runtime-control-plane"]),
        _surface("runtime-entry:trellis-implement", ["trellis-runtime"]),
        _surface(
            "router:heavy-development-router",
            ["runtime-control-plane", "skill:evidence"],
        ),
        _surface(
            "runtime-entry:heavy-development-router",
            ["router:heavy-development-router", "trellis-runtime"],
        ),
        _surface("platform-adapter:codex", ["runtime-control-plane"]),
        _surface("platform-adapter:opencode", ["runtime-control-plane"]),
        _surface("platform-adapter:claude-code", ["runtime-control-plane"]),
    ]
    registry_document = {
        "schema_id": "agent-workflow.runtime-surface-registry",
        "schema_version": 1,
        "surfaces": surface_documents,
    }
    inventory = {
        "schema_id": "agent-workflow.runtime-unit-inventory",
        "schema_version": 1,
        "units": [
            {
                "unit_id": surface["owned_unit_ids"][0],
                "unit_kind": "module",
                "distribution_scope": "runtime-package",
                "normalized_path": f"src/runtime/{surface['surface_id'].replace(':', '/')}.py",
                "owning_surface_id": surface["surface_id"],
                "leaf_recipe_id": "bytes-mode-contract-v1",
                "runtime_visible": True,
            }
            for surface in surface_documents
        ],
    }
    verified = validate_surface_registry(registry_document, inventory)
    evidence = [
        {
            "unit_id": unit_id,
            "byte_hash": f"{index + 1:064x}",
            "mode": "0644",
            "contract_digest": f"{index + 101:064x}",
            "distributions": ["git-checkout", "sdist", "wheel"],
        }
        for index, unit_id in enumerate(sorted(verified.units))
    ]
    return VerifiedRuntimeSurfaceRegistry(
        registry=verified,
        surface_digests=compute_surface_digests(verified, evidence),
    )


def ids(closure: tuple[object, ...]) -> tuple[str, ...]:
    return tuple(record["surface_id"] for record in closure)  # type: ignore[index]


def test_trellis_and_heavy_closures_include_exact_transitive_surfaces() -> None:
    registry = verified_registry()

    trellis = derive_task_surface_closure(
        "trellis-native", "codex", "trellis-implement", registry
    )
    heavy = derive_task_surface_closure(
        "speckit-superpowers", "codex", "heavy-development-router", registry
    )

    assert ids(trellis) == tuple(sorted(ids(trellis)))
    assert {
        "platform-adapter:codex",
        "runtime-control-plane",
        "surface-registry",
        "trellis-runtime",
        "runtime-entry:trellis-implement",
        "agent:trellis:runtime",
        "skill:tdd",
        "hook:shared:task",
    } == set(ids(trellis))
    assert "router:heavy-development-router" not in ids(trellis)
    assert "skill:evidence" not in ids(trellis)
    assert {
        "router:heavy-development-router",
        "runtime-entry:heavy-development-router",
        "skill:evidence",
    } < set(ids(heavy))
    assert all(set(record) == {"surface_id", "surface_digest"} for record in heavy)


def test_platform_and_skill_closures_are_exact_not_wildcarded() -> None:
    registry = verified_registry()
    codex = derive_task_surface_closure(
        "trellis-native", "codex", "trellis-implement", registry
    )
    opencode = derive_task_surface_closure(
        "trellis-native", "opencode", "trellis-implement", registry
    )

    assert "platform-adapter:codex" in ids(codex)
    assert "platform-adapter:opencode" not in ids(codex)
    assert "platform-adapter:opencode" in ids(opencode)
    assert "platform-adapter:codex" not in ids(opencode)
    with pytest.raises(RouteFailure, match="AWP_ROUTE_SURFACE_CLOSURE_INVALID"):
        derive_task_surface_closure("trellis-native", "*", "trellis-implement", registry)


def test_calculator_and_admission_recomputation_use_identical_surface_digest() -> None:
    registry = verified_registry()
    closure = derive_task_surface_closure(
        "trellis-native", "codex", "trellis-implement", registry
    )
    auth = dataclasses.replace(
        authorities(),
        task_surface_closures={
            "trellis-native": closure,
            "speckit-superpowers": derive_task_surface_closure(
                "speckit-superpowers",
                "codex",
                "heavy-development-router",
                registry,
            ),
        },
    )

    decision = calculate_route(
        "create-integrated-task",
        RouteCalculationInputs(
            intent=intent(requested_mode="trellis-native"),
            requested_task_ref=".trellis/tasks/example",
        ),
        auth,
    )

    assert decision["task_contract_surfaces"] == [dict(record) for record in closure]
    assert decision["task_contract_surfaces_digest"] == digest(
        "agent-workflow.task-surfaces.v1", closure
    )


@pytest.mark.parametrize(
    ("route", "entry_owner"),
    [
        ("native-light", "sol-native"),
        ("trellis-native", "heavy-development-router"),
        ("speckit-superpowers", "trellis-implement"),
    ],
)
def test_illegal_route_or_owner_root_fails_closed(route: str, entry_owner: str) -> None:
    with pytest.raises(RouteFailure, match="AWP_ROUTE_SURFACE_CLOSURE_INVALID"):
        derive_task_surface_closure(route, "codex", entry_owner, verified_registry())
