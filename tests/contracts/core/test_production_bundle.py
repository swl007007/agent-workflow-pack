from __future__ import annotations

from pathlib import Path

from agent_stack._vendor import yaml
from agent_stack.reconcile.production_bundle import load_production_bundle
from agent_stack.runtime.scanner import NormativeTaskScanner


ROOT = Path(__file__).resolve().parents[3]


REQUIRED_PRODUCTION_INPUTS = (
    "profiles/default.yaml",
    "catalog/workflow-components.yaml",
    "catalog/workflow.lock",
    "catalog/runtime-surfaces.yaml",
    "catalog/runtime-units.yaml",
    "catalog/route-policy.yaml",
    "catalog/router-contract.yaml",
    "catalog/trellis-task-layout.json",
    "catalog/trellis-discovery-schemas.json",
    "templates/platforms/codex/AGENTS.md.tmpl",
    "templates/platforms/codex/SKILL.md.tmpl",
    "templates/platforms/codex/codex-wrapper.tmpl",
    "artifact-definitions/platforms/codex-agents.yaml",
    "artifact-definitions/platforms/codex-skill.yaml",
    "artifact-definitions/platforms/codex-wrapper.yaml",
    "artifact-definitions/platforms/project-gitignore.yaml",
    "templates/control/runtime-control.json.tmpl",
    "templates/control/gitignore-block.tmpl",
)


def test_production_bundle_contains_every_closed_resolver_and_render_input() -> None:
    for relative in REQUIRED_PRODUCTION_INPUTS:
        path = ROOT / relative
        assert path.is_file(), relative
        assert path.read_bytes(), relative


def test_codex_artifact_definitions_each_bind_one_exact_template_source() -> None:
    expected = {
        "codex-agents": ("templates/platforms/codex/AGENTS.md.tmpl", "AGENTS.md"),
        "codex-skill": (
            "templates/platforms/codex/SKILL.md.tmpl",
            ".agents/skills/agent-workflow/SKILL.md",
        ),
        "codex-wrapper": (
            "templates/platforms/codex/codex-wrapper.tmpl",
            ".agent-workflow/bin/codex-wrapper",
        ),
    }
    actual: dict[str, tuple[str, str]] = {}
    for path in sorted((ROOT / "artifact-definitions/platforms").glob("codex-*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[no-untyped-call]
        assert isinstance(document, dict)
        targets = document["targets"]
        assert isinstance(targets, list) and len(targets) == 1
        actual[str(document["id"])] = (str(document["source"]), str(targets[0]["path"]))

    assert actual == expected


def test_production_bundle_validates_closed_schemas_references_and_actual_evidence() -> None:
    bundle = load_production_bundle(ROOT)

    assert bundle.profile["id"] == "default"
    assert bundle.catalog["schema_id"] == "agent-workflow.catalog"
    assert bundle.workflow_lock["components"]
    assert len(bundle.artifact_definitions) == 4
    assert {row["unit_id"] for row in bundle.runtime_unit_evidence} == {
        row["unit_id"] for row in bundle.runtime_unit_inventory["units"]
    }
    assert all(row["byte_hash"] != "0" * 64 for row in bundle.runtime_unit_evidence)
    assert bundle.trellis_layout.layout_digest
    assert bundle.discovery_schemas.schema_bundle_digest
    assert bundle.route_policy["default_route"] == "native-light"
    assert bundle.router_contract["router_id"] == "heavy-development-router"
    assert bundle.trust_policy["policy_id"] == "github-immutable-release-v1"


def test_packaged_trellis_contract_drives_the_real_scanner(tmp_path: Path) -> None:
    bundle = load_production_bundle(ROOT)

    result = NormativeTaskScanner(tmp_path)(
        bundle.trellis_layout,
        bundle.trellis_layout,
        bundle.discovery_schemas,
        bundle.discovery_schemas,
    )

    assert result.snapshot["tasks"] == []
    assert result.snapshot["metadata"] == []
    assert result.snapshot["task_journals"] == []
    assert result.findings["findings"] == []
