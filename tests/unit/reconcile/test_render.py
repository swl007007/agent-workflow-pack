from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import MappingProxyType

import pytest

from agent_stack.core.api import CandidateImpact, DesiredStateIR
from agent_stack.providers.api import ProviderExecutionResult
from agent_stack.providers.archive import content_root_digest
from agent_stack.reconcile.api import render
from agent_stack.reconcile.errors import RendererFailure
from agent_stack.reconcile.staging import materialize_staged_tree


def make_ir(
    render_units: list[dict[str, object]],
    artifact_definitions: list[dict[str, object]],
    *,
    release_id: str = "a" * 64,
    release_manifest_digest: str = "b" * 64,
) -> DesiredStateIR:
    impact = CandidateImpact("none", (), (), False, "c" * 64)
    return DesiredStateIR(
        operation="sync",
        release_contract=MappingProxyType(
            {
                "release_id": release_id,
                "release_manifest_digest": release_manifest_digest,
            }
        ),
        resolved_profile=MappingProxyType({"profile_id": "default"}),
        authority_digests=MappingProxyType({"profile": "d" * 64}),
        workflow_lock_projection=MappingProxyType({}),
        selected_platforms=(),
        capability_results=(),
        catalog_closure=(),
        reference_closure=(),
        route_policy=MappingProxyType({}),
        entry_ownership=(),
        discoverable_leaf_ids=(),
        runtime_catalog_entry_ids=(),
        trellis_task_layout=MappingProxyType({}),
        surface_registry=MappingProxyType({}),
        surface_digests=MappingProxyType({}),
        coverage_result=MappingProxyType({}),
        render_units=tuple(MappingProxyType(item) for item in render_units),
        artifact_definitions=tuple(
            MappingProxyType(item) for item in artifact_definitions
        ),
        candidate_impact=impact,
        workspace_state_evaluation=MappingProxyType({}),
        task_gate_evaluation=MappingProxyType({}),
        diagnostics=(),
        desired_state_ir_digest="e" * 64,
    )


def provider_result(root: Path) -> ProviderExecutionResult:
    return ProviderExecutionResult.without_approval(
        provider_plan_digest="1" * 64,
        attempt_id="11111111-1111-4111-8111-111111111111",
        terminal_state="succeeded",
        containment_evidence_digest="2" * 64,
        result_category="validated",
        candidate_output_root_digest=content_root_digest(root),
        candidate_output_path=str(root),
        diagnostics_digest="3" * 64,
        provenance_records=(),
    )


def render_unit(
    source_path: str,
    source_bytes: bytes,
    target_path: str,
    candidate_bytes: bytes,
    *,
    definition_id: str,
    surface_id: str,
    ownership: str = "managed",
    merge_strategy: str = "whole-file",
    mode_policy: str = "exact",
    mode: str = "0644",
) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.render-unit",
        "schema_version": 1,
        "unit_id": f"unit:{definition_id}",
        "definition_id": definition_id,
        "source": {
            "source_id": source_path,
            "source_digest": hashlib.sha256(source_bytes).hexdigest(),
        },
        "target": {
            "path": target_path,
            "ownership": ownership,
            "merge_strategy": merge_strategy,
            "mode_policy": mode_policy,
            "mode": mode,
        },
        "surface_id": surface_id,
        "validator_ids": ["utf8-text-v1", "newline-v1"],
        "candidate_leaf_digest": hashlib.sha256(candidate_bytes).hexdigest(),
    }


def artifact(definition_id: str, source_path: str, target_path: str) -> dict[str, object]:
    return {
        "id": definition_id,
        "source": source_path,
        "targets": [
            {
                "path": target_path,
                "ownership": "managed",
                "merge_strategy": "whole-file",
                "mode_policy": "exact",
                "mode": "0644",
                "markers": None,
            }
        ],
        "forbidden_paths": [],
        "validators": [
            {"id": "utf8-text-v1", "version": 1},
            {"id": "newline-v1", "version": 1},
        ],
    }


def test_render_orders_paths_normalizes_newlines_and_applies_fixed_substitutions(
    tmp_path: Path,
) -> None:
    provider_root = tmp_path / "provider"
    (provider_root / "templates").mkdir(parents=True)
    first_source = b"release={{release_id}}\r\nprofile={{profile_digest}}\r\n"
    second_source = b"plain\r\n"
    (provider_root / "templates/first.txt").write_bytes(first_source)
    (provider_root / "templates/second.txt").write_bytes(second_source)
    os.chmod(provider_root / "templates/first.txt", 0o644)
    os.chmod(provider_root / "templates/second.txt", 0o644)
    first_candidate = f"release={'a' * 64}\nprofile={'d' * 64}\n".encode()
    second_candidate = b"plain\n"
    units = [
        render_unit(
            "templates/second.txt",
            second_source,
            "z/second.txt",
            second_candidate,
            definition_id="second",
            surface_id="skill:second",
        ),
        render_unit(
            "templates/first.txt",
            first_source,
            "a/first.txt",
            first_candidate,
            definition_id="first",
            surface_id="adapter:first",
        ),
    ]
    definitions = [
        artifact("second", "templates/second.txt", "z/second.txt"),
        artifact("first", "templates/first.txt", "a/first.txt"),
    ]

    tree = render(make_ir(units, definitions), [provider_result(provider_root)])

    assert [record.path for record in tree.files] == ["a/first.txt", "z/second.txt"]
    assert tree.files[0].candidate_bytes == first_candidate
    assert tree.files[0].candidate_mode == "0644"
    assert tree.files[1].candidate_bytes == second_candidate


def test_render_rejects_unverified_provider_root_or_candidate_leaf(tmp_path: Path) -> None:
    provider_root = tmp_path / "provider"
    provider_root.mkdir()
    source = b"hello\n"
    (provider_root / "source.txt").write_bytes(source)
    unit = render_unit(
        "source.txt",
        source,
        "output.txt",
        b"different\n",
        definition_id="output",
        surface_id="runtime-entry:output",
    )
    ir = make_ir([unit], [artifact("output", "source.txt", "output.txt")])

    with pytest.raises(RendererFailure, match="AWP_RENDER_NONDETERMINISTIC"):
        render(ir, [provider_result(provider_root)])

    result = provider_result(provider_root)
    changed_result = ProviderExecutionResult(
        **{**result.__dict__, "candidate_output_root_digest": "f" * 64}
    )
    with pytest.raises(RendererFailure, match="AWP_RENDER_NONDETERMINISTIC"):
        render(ir, [changed_result])


def test_release_substitutions_are_excluded_only_from_launcher_bundle_digest(
    tmp_path: Path,
) -> None:
    provider_root = tmp_path / "provider"
    provider_root.mkdir()
    source = b"#!/bin/sh\nWHEEL_MANIFEST={{release_manifest_digest}}\n"
    (provider_root / "launcher.sh").write_bytes(source)
    first_bytes = f"#!/bin/sh\nWHEEL_MANIFEST={'b' * 64}\n".encode()
    second_bytes = f"#!/bin/sh\nWHEEL_MANIFEST={'9' * 64}\n".encode()
    first_unit = render_unit(
        "launcher.sh",
        source,
        ".agent-workflow/agent-stack",
        first_bytes,
        definition_id="launcher",
        surface_id="launcher:bootstrap",
        mode="0755",
    )
    first_definition = artifact(
        "launcher", "launcher.sh", ".agent-workflow/agent-stack"
    )
    first_definition["targets"][0]["mode"] = "0755"  # type: ignore[index]
    first = render(
        make_ir([first_unit], [first_definition]), [provider_result(provider_root)]
    )
    second_unit = render_unit(
        "launcher.sh",
        source,
        ".agent-workflow/agent-stack",
        second_bytes,
        definition_id="launcher",
        surface_id="launcher:bootstrap",
        mode="0755",
    )
    second = render(
        make_ir(
            [second_unit],
            [first_definition],
            release_manifest_digest="9" * 64,
        ),
        [provider_result(provider_root)],
    )

    assert first.launcher_bundle_digest == second.launcher_bundle_digest
    assert first.content_root_digest != second.content_root_digest
    assert first.distribution_render_digest != second.distribution_render_digest


def test_render_accepts_overlay_block_with_preserved_host_mode(tmp_path: Path) -> None:
    provider_root = tmp_path / "provider"
    provider_root.mkdir()
    source = b"managed=true\n"
    (provider_root / "overlay.txt").write_bytes(source)
    markers = {"begin": "# BEGIN AWP", "end": "# END AWP"}
    unit = render_unit(
        "overlay.txt",
        source,
        "AGENTS.md",
        source,
        definition_id="project-instructions",
        surface_id="platform-adapter:codex",
    )
    unit["target"] = {
        "path": "AGENTS.md",
        "ownership": "overlay-managed",
        "merge_strategy": "marked-block",
        "mode_policy": "preserve",
        "markers": markers,
    }
    definition = artifact("project-instructions", "overlay.txt", "AGENTS.md")
    definition["targets"] = [
        {
            "path": "AGENTS.md",
            "ownership": "overlay-managed",
            "merge_strategy": "marked-block",
            "mode_policy": "preserve",
            "mode": None,
            "markers": markers,
        }
    ]

    tree = render(make_ir([unit], [definition]), [provider_result(provider_root)])

    assert tree.files[0].candidate_bytes == source
    assert tree.files[0].candidate_mode == "canonical-null"


def test_staged_tree_materializes_identically_in_independent_roots(
    tmp_path: Path,
) -> None:
    provider_root = tmp_path / "provider"
    provider_root.mkdir()
    source = b"#!/bin/sh\nexit 0\n"
    (provider_root / "launcher.sh").write_bytes(source)
    unit = render_unit(
        "launcher.sh",
        source,
        ".agent-workflow/agent-stack",
        source,
        definition_id="launcher",
        surface_id="launcher:bootstrap",
        mode="0755",
    )
    definition = artifact(
        "launcher", "launcher.sh", ".agent-workflow/agent-stack"
    )
    definition["targets"][0]["mode"] = "0755"  # type: ignore[index]
    tree = render(make_ir([unit], [definition]), [provider_result(provider_root)])

    first = tmp_path / "stage-first"
    second = tmp_path / "stage-second"
    materialize_staged_tree(tree, first)
    materialize_staged_tree(tree, second)

    relative = Path(".agent-workflow/agent-stack")
    assert (first / relative).read_bytes() == (second / relative).read_bytes() == source
    assert (first / relative).stat().st_mode & 0o777 == 0o755
    assert (second / relative).stat().st_mode & 0o777 == 0o755
