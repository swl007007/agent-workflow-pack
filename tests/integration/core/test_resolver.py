from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_stack.core import api
from agent_stack.core.errors import CoreFailure
from agent_stack.core.resolver import ResolverInputs, resolve
from agent_stack.core.schema_catalog import SchemaCatalog
from tests.unit.core.test_catalog import _catalog, _entry, _manifest
from tests.unit.core.test_profile import _profile
from tests.unit.core.test_surfaces import _valid_contract
from tests.unit.core.test_task_policy import _snapshot


ROOT = Path(__file__).resolve().parents[3]


def _workflow_lock() -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.workflow-lock",
        "schema_version": 1,
        "components": [
            {
                "id": "skill:tdd",
                "version": "1.0.0",
                "source_sha256": "a" * 64,
                "content_digest": "b" * 64,
                "provider_id": "builtin",
                "acquisition_id": "builtin:tdd",
            }
        ],
    }


def _inputs() -> ResolverInputs:
    registry, inventory, evidence = _valid_contract()
    layout = json.loads(
        (ROOT / "tests/fixtures/core/trellis_layouts/valid.json").read_text(encoding="utf-8")
    )
    task_snapshot, task_findings = _snapshot()
    return ResolverInputs(
        operation="init",
        release_contract={
            "release_id": "1" * 64,
            "release_manifest_digest": "2" * 64,
            "release_trust_policy_id": "github-immutable-release-v1",
            "release_trust_policy_digest": "3" * 64,
            "version": "0.1.0",
        },
        profile_sources=(
            _profile(
                "base",
                skills={"enable": ["skill:tdd"], "disable": []},
                default_platforms=["codex"],
            ),
        ),
        selected_profile_id="base",
        catalog_document=_catalog(
            _entry("skill:tdd"), _entry("platform:codex", mandatory=True)
        ),
        workflow_lock_document=_workflow_lock(),
        capability_manifests=(_manifest(),),
        artifact_definition_documents=(),
        trellis_layout_document=layout,
        surface_registry_document=registry,
        runtime_unit_inventory_document=inventory,
        runtime_unit_evidence=tuple(evidence),
        route_policy_document={"policy_id": "default", "policy_version": 1},
        router_contract_document={"router_id": "heavy-development-router", "version": 1},
        entry_ownership=(),
        render_units=(),
        current_contract={
            "authority_digests": {},
            "surface_digests": {},
            "registry_graph_digest": "canonical-null",
        },
        observed_state={"surface_digests": {}, "unclassified_runtime_units": []},
        repair_surface_ids=(),
        diagnostics=(),
        task_snapshot=task_snapshot,
        task_findings=task_findings,
    )


def test_resolver_composes_validated_modules_into_stable_ir() -> None:
    first = resolve(_inputs())
    second = resolve(_inputs())

    assert first.desired_state_ir_digest == second.desired_state_ir_digest
    assert first.operation == "init"
    assert first.release_contract["version"] == "0.1.0"
    assert first.release_contract["release_trust_policy_id"] == (
        "github-immutable-release-v1"
    )
    assert first.selected_platforms == ("codex",)
    assert first.catalog_closure == ("platform:codex", "skill:tdd")
    assert first.candidate_impact.impact_kind == "runtime-visible"
    assert tuple(first.surface_digests) == (
        "surface-registry",
        "runtime-control-plane",
        "skill:tdd",
    )


def test_resolver_preserves_normative_validation_order() -> None:
    inputs = _inputs()
    bad_lock = dict(inputs.workflow_lock_document)
    bad_lock["schema_version"] = 2
    bad_profile = dict(inputs.profile_sources[0])
    bad_profile["schema_version"] = 2
    invalid = ResolverInputs(
        **{
            **inputs.__dict__,
            "workflow_lock_document": bad_lock,
            "profile_sources": (bad_profile,),
        }
    )

    with pytest.raises(CoreFailure, match="AWP_CATALOG_CLOSURE_BLOCKED"):
        resolve(invalid)


def test_desired_state_ir_schema_and_public_api_are_frozen() -> None:
    ir = resolve(_inputs())
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.supported_versions("agent-workflow.desired-state-ir") == (1,)
    catalog.load_and_validate(ir.to_document())

    assert api.CORE_INTERFACE_VERSION == 1
    assert api.resolve is resolve
    assert "compute_candidate_impact" in api.__all__
    assert "render_saved_plan" not in api.__all__
