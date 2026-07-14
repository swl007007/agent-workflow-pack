from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.core.errors import CoreFailure
from agent_stack.core.schema_catalog import SchemaCatalog
from agent_stack.core.surfaces import (
    compute_surface_digests,
    prove_surface_coverage,
    validate_surface_registry,
)


ROOT = Path(__file__).resolve().parents[3]


def _surface(
    surface_id: str,
    kind: str,
    units: list[str],
    references: list[str],
) -> dict[str, object]:
    return {
        "surface_id": surface_id,
        "surface_kind": kind,
        "descriptor_version": 1,
        "digest_recipe_id": "surface-content-v1",
        "owned_unit_ids": units,
        "references": references,
        "contract_change_class": "runtime-visible",
    }


def _unit(unit_id: str, owner: str, path: str, scope: str) -> dict[str, object]:
    return {
        "unit_id": unit_id,
        "unit_kind": unit_id.split(":", 1)[0],
        "distribution_scope": scope,
        "normalized_path": path,
        "owning_surface_id": owner,
        "leaf_recipe_id": "bytes-mode-contract-v1",
        "runtime_visible": True,
    }


def _registry(*surfaces: dict[str, object]) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.runtime-surface-registry",
        "schema_version": 1,
        "surfaces": list(surfaces),
    }


def _inventory(*units: dict[str, object]) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.runtime-unit-inventory",
        "schema_version": 1,
        "units": list(units),
    }


def _valid_contract() -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    registry = _registry(
        _surface("surface-registry", "surface-registry", ["schema:surface-registry"], []),
        _surface(
            "runtime-control-plane",
            "runtime-control-plane",
            ["module:runtime-control"],
            ["surface-registry"],
        ),
        _surface("skill:tdd", "skill", ["render-unit:tdd"], ["runtime-control-plane"]),
    )
    inventory = _inventory(
        _unit(
            "schema:surface-registry",
            "surface-registry",
            "schemas/core/runtime-surface-registry.v1.json",
            "runtime-package",
        ),
        _unit(
            "module:runtime-control",
            "runtime-control-plane",
            "src/agent_stack/runtime/control.py",
            "runtime-package",
        ),
        _unit("render-unit:tdd", "skill:tdd", ".agents/skills/tdd/SKILL.md", "rendered-project"),
    )
    evidence = [
        {
            "unit_id": "schema:surface-registry",
            "byte_hash": "a" * 64,
            "mode": "0644",
            "contract_digest": "b" * 64,
            "distributions": ["git-checkout", "sdist", "wheel"],
        },
        {
            "unit_id": "module:runtime-control",
            "byte_hash": "c" * 64,
            "mode": "0644",
            "contract_digest": "d" * 64,
            "distributions": ["git-checkout", "sdist", "wheel"],
        },
        {
            "unit_id": "render-unit:tdd",
            "byte_hash": "e" * 64,
            "mode": "0644",
            "contract_digest": "f" * 64,
            "distributions": ["rendered-project"],
        },
    ]
    return registry, inventory, evidence


def test_valid_registry_computes_stable_topological_surface_digests() -> None:
    registry, inventory, evidence = _valid_contract()
    verified = validate_surface_registry(registry, inventory)

    digests = compute_surface_digests(verified, evidence)

    assert tuple(digests) == ("surface-registry", "runtime-control-plane", "skill:tdd")
    assert all(len(value) == 64 for value in digests.values())
    proof = prove_surface_coverage(verified, evidence)
    assert proof.covered_unit_ids == (
        "module:runtime-control",
        "render-unit:tdd",
        "schema:surface-registry",
    )
    assert len(proof.proof_digest) == 64


@pytest.mark.parametrize(
    "mutator,error_code",
    [
        (lambda registry, inventory: registry["surfaces"].pop(0), "AWP_SURFACE_GRAPH_INVALID"),
        (
            lambda registry, inventory: registry["surfaces"].append(
                _surface("unknown:thing", "unknown", [], [])
            ),
            "AWP_SURFACE_GRAPH_INVALID",
        ),
        (
            lambda registry, inventory: registry["surfaces"][2]["references"].append("missing"),
            "AWP_SURFACE_GRAPH_INVALID",
        ),
        (
            lambda registry, inventory: registry["surfaces"][0]["references"].append("skill:tdd"),
            "AWP_SURFACE_GRAPH_INVALID",
        ),
        (
            lambda registry, inventory: inventory["units"][2].update(
                {"owning_surface_id": "runtime-control-plane"}
            ),
            "AWP_SURFACE_COVERAGE_INVALID",
        ),
    ],
)
def test_invalid_reserved_ids_mandatory_members_graph_or_owner_fail(
    mutator, error_code: str
) -> None:
    registry, inventory, _ = _valid_contract()
    mutator(registry, inventory)

    with pytest.raises(CoreFailure, match=error_code):
        validate_surface_registry(registry, inventory)


def test_omitted_leaf_fields_and_distribution_mismatch_fail_coverage() -> None:
    registry, inventory, evidence = _valid_contract()
    verified = validate_surface_registry(registry, inventory)
    evidence[0].pop("mode")
    with pytest.raises(CoreFailure, match="AWP_SURFACE_COVERAGE_INVALID"):
        compute_surface_digests(verified, evidence)

    _, _, evidence = _valid_contract()
    evidence[0]["distributions"] = ["wheel"]
    with pytest.raises(CoreFailure, match="AWP_SURFACE_COVERAGE_INVALID"):
        prove_surface_coverage(verified, evidence)


def test_registry_source_rejects_computed_roots() -> None:
    registry, inventory, _ = _valid_contract()
    registry["surface_registry_digest"] = "a" * 64

    with pytest.raises(CoreFailure, match="AWP_SURFACE_GRAPH_INVALID"):
        validate_surface_registry(registry, inventory)


def test_surface_schemas_are_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    registry, inventory, _ = _valid_contract()
    for schema_id in (
        "agent-workflow.runtime-surface-registry",
        "agent-workflow.runtime-unit-inventory",
        "agent-workflow.surface-coverage-proof",
    ):
        assert catalog.supported_versions(schema_id) == (1,)
    catalog.load_and_validate(registry)
    catalog.load_and_validate(inventory)
