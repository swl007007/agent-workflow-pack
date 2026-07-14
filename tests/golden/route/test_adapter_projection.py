from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import pytest

from agent_stack._vendor import yaml
from agent_stack.core.api import CandidateImpact, DesiredStateIR
from agent_stack.route.projection import project_platform_adapter
from agent_stack.route.platforms.claude_code import load_claude_code_contract
from agent_stack.route.platforms.codex import load_codex_contract
from agent_stack.route.platforms.opencode import load_opencode_contract


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).with_name("fixtures")


def _artifact_projection(platform: str) -> dict[str, object]:
    document = yaml.safe_load(
        (ROOT / "artifact-definitions/platforms" / f"{platform}.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(document, dict)
    return {
        "id": document["id"],
        "source": document["source"],
        "targets": [
            {
                **target,
                "mode": target.get("mode"),
                "markers": target.get("markers"),
            }
            for target in document["targets"]
        ],
        "forbidden_paths": document["forbidden_paths"],
        "validators": document["validators"],
    }


def _render_units(binding) -> list[dict[str, object]]:
    definition = _artifact_projection(binding.adapter.platform.value)
    targets = {target["path"]: target for target in definition["targets"]}
    units = []
    for projection in binding.adapter.render_projections:
        target = dict(targets[projection["target_path"]])
        target.pop("markers") if target["markers"] is None else None
        target.pop("mode") if target["mode"] is None else None
        unit_id = projection["unit_id"]
        units.append(
            {
                "schema_id": "agent-workflow.render-unit",
                "schema_version": 1,
                "unit_id": unit_id,
                "definition_id": definition["id"],
                "source": {
                    "source_id": definition["source"],
                    "source_digest": hashlib.sha256(
                        f"source:{unit_id}".encode()
                    ).hexdigest(),
                },
                "target": target,
                "surface_id": projection["owning_surface_id"],
                "validator_ids": list(projection["validator_ids"]),
                "candidate_leaf_digest": hashlib.sha256(
                    f"candidate:{unit_id}".encode()
                ).hexdigest(),
            }
        )
    return units


def make_ir(binding) -> DesiredStateIR:
    units = _render_units(binding)
    discoverable = tuple(
        sorted(
            projection["unit_id"]
            for projection in binding.adapter.render_projections
            if projection["discoverable"]
        )
    )
    impact = CandidateImpact("none", (), (), False, "c" * 64)
    return DesiredStateIR(
        operation="sync",
        release_contract=MappingProxyType(
            {"release_id": "a" * 64, "release_manifest_digest": "b" * 64}
        ),
        resolved_profile=MappingProxyType(
            {"profile_id": "default", "skills_disable": []}
        ),
        authority_digests=MappingProxyType({"profile": "d" * 64}),
        workflow_lock_projection=MappingProxyType({}),
        selected_platforms=(binding.adapter.platform.value,),
        capability_results=(),
        catalog_closure=discoverable,
        reference_closure=(),
        route_policy=MappingProxyType({}),
        entry_ownership=(),
        discoverable_leaf_ids=discoverable,
        runtime_catalog_entry_ids=tuple(
            sorted(unit["unit_id"] for unit in units)
        ),
        trellis_task_layout=MappingProxyType({}),
        surface_registry=MappingProxyType({}),
        surface_digests=MappingProxyType({}),
        coverage_result=MappingProxyType({}),
        render_units=tuple(MappingProxyType(unit) for unit in units),
        artifact_definitions=(MappingProxyType(_artifact_projection(binding.adapter.platform.value)),),
        candidate_impact=impact,
        workspace_state_evaluation=MappingProxyType({}),
        task_gate_evaluation=MappingProxyType({}),
        diagnostics=(),
        desired_state_ir_digest="e" * 64,
    )


@pytest.mark.parametrize(
    ("platform", "loader"),
    [
        ("claude-code", load_claude_code_contract),
        ("codex", load_codex_contract),
        ("opencode", load_opencode_contract),
    ],
)
def test_three_platform_projections_match_exact_golden_contracts(platform, loader) -> None:
    binding = loader(ROOT)
    ir = make_ir(binding)

    projection = project_platform_adapter(ir, binding.adapter)
    repeated = project_platform_adapter(ir, binding.adapter)

    assert projection == repeated
    summary = {
        "platform": projection["platform"],
        "paths": [unit["target"]["path"] for unit in projection["units"]],
        "modes": [unit["target"].get("mode", "preserve") for unit in projection["units"]],
        "candidate_leaf_digests": [
            unit["candidate_leaf_digest"] for unit in projection["units"]
        ],
        "discoverable": [
            unit["unit_id"] for unit in projection["units"] if unit["discoverable"]
        ],
        "wrapper_entries": [
            wrapper["runtime_entry_id"] for wrapper in projection["wrappers"]
        ],
        "blocked_bypass_entries": list(projection["blocked_bypass_entries"]),
    }
    expected = json.loads((FIXTURES / f"{platform}.json").read_text(encoding="utf-8"))
    assert summary == expected


def test_distribution_identity_does_not_change_logical_projection() -> None:
    binding = load_codex_contract(ROOT)
    first = make_ir(binding)
    second = dataclasses.replace(
        first,
        release_contract=MappingProxyType(
            {"release_id": "9" * 64, "release_manifest_digest": "8" * 64}
        ),
        desired_state_ir_digest="7" * 64,
    )

    assert project_platform_adapter(first, binding.adapter) == project_platform_adapter(
        second, binding.adapter
    )
