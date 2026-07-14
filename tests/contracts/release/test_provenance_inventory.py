from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.provenance import load_frozen_provenance, validate_provenance_inventory


ROOT = Path(__file__).resolve().parents[3]


def test_frozen_inventory_covers_exact_vendors_and_projected_units() -> None:
    inventory = load_frozen_provenance(ROOT)
    document = inventory.to_document()
    components = {item["component_id"]: item for item in document["components"]}

    assert set(components) == {
        "first-party:agent-workflow-pack",
        "vendor:fastjsonschema",
        "vendor:pyyaml",
    }
    assert components["vendor:pyyaml"]["version"] == "6.0.2"
    assert components["vendor:pyyaml"]["source"]["sha256"] == (
        "d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e"
    )
    assert components["vendor:fastjsonschema"]["version"] == "2.21.1"
    assert components["vendor:fastjsonschema"]["source"]["sha256"] == (
        "794d4f0a58f848961ba16af7b9c85a3e88cd360df008c59aac6fc5ae9323b5d4"
    )
    for component_id in ("vendor:pyyaml", "vendor:fastjsonschema"):
        component = components[component_id]
        assert component["install"]["target_root"].startswith("src/agent_stack/_vendor/")
        assert component["install"]["modification"] == "namespace-relocation-only"
        assert component["modification_notice"]["text"]
        assert component["files"]
        for row in component["files"]:
            path = ROOT / row["installed_path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row["installed_sha256"]

    projected = document["projected_units"]
    assert [item["unit_id"] for item in projected] == sorted(
        {
            "instruction:claude-project",
            "command:claude-agent-stack",
            "hook:claude:runtime-gate",
            "instruction:codex-agents",
            "skill:codex-agent-workflow",
            "command:codex-wrapper",
            "instruction:opencode-project",
            "command:opencode-agent-stack",
            "hook:opencode:runtime-gate",
        }
    )


def test_inventory_contains_no_distribution_container_hash_cycle() -> None:
    document = load_frozen_provenance(ROOT).to_document()

    def keys(value: object) -> list[str]:
        if isinstance(value, dict):
            return [str(key) for key in value for child in [value[key]] for key in [key]] + [
                nested for child in value.values() for nested in keys(child)
            ]
        if isinstance(value, list):
            return [nested for child in value for nested in keys(child)]
        return []

    forbidden = {"wheel_sha256", "sdist_sha256", "container_sha256", "distribution_sha256"}
    assert forbidden.isdisjoint(keys(document))


def test_missing_or_ambiguous_provenance_fails_closed() -> None:
    document = load_frozen_provenance(ROOT).to_document()
    missing = copy.deepcopy(document)
    missing["components"][1]["files"].pop()
    ambiguous = copy.deepcopy(document)
    ambiguous["projected_units"].append(copy.deepcopy(ambiguous["projected_units"][0]))

    with pytest.raises(LifecycleFailure, match="AWP_PROVENANCE_INCOMPLETE"):
        validate_provenance_inventory(missing, ROOT)
    with pytest.raises(LifecycleFailure, match="AWP_PROVENANCE_INCOMPLETE"):
        validate_provenance_inventory(ambiguous, ROOT)


def test_unregistered_vendor_file_is_rejected(tmp_path: Path) -> None:
    for relative in ("vendor", "src/agent_stack/_vendor", "catalog"):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)
    shutil.copy2(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    (tmp_path / "src/agent_stack/_vendor/yaml/unregistered.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    document = json.loads((ROOT / "release/provenance-lock.json").read_text(encoding="utf-8"))

    with pytest.raises(LifecycleFailure, match="unregistered vendor file"):
        validate_provenance_inventory(document, tmp_path)
