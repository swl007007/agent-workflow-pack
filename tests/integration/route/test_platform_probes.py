from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack._vendor import yaml
from agent_stack.core.api import validate_artifact_definitions
from agent_stack.route.capabilities import PlatformProbeInputs, measure_capability_manifest
from agent_stack.route.errors import RouteFailure
from agent_stack.route.platforms.claude_code import load_claude_code_contract
from agent_stack.route.platforms.codex import load_codex_contract
from agent_stack.route.platforms.opencode import load_opencode_contract
from tests.unit.route.test_capabilities import Probe, caller_context


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "loader",
    [load_claude_code_contract, load_codex_contract, load_opencode_contract],
)
def test_default_platform_probe_contracts_meet_strict_minimums(loader) -> None:
    binding = loader(ROOT)

    manifest = measure_capability_manifest(
        PlatformProbeInputs(
            binding=binding,
            caller_context=caller_context(binding.adapter.platform.value),
            observed_harness_version=binding.harness_version,
            probe=Probe(),
            enforce_minimums=True,
        )
    )

    assert set(manifest["capabilities"]) == set(binding.probes)
    assert all(level == "enforced" for level in manifest["capabilities"].values())


def test_platform_artifact_definitions_are_closed_and_non_overlapping() -> None:
    documents = []
    for name in ("claude-code.yaml", "codex.yaml", "opencode.yaml"):
        value = yaml.safe_load(
            (ROOT / "artifact-definitions/platforms" / name).read_text(encoding="utf-8")
        )
        assert isinstance(value, dict)
        documents.append(value)

    verified = validate_artifact_definitions(documents)

    assert [definition.definition_id for definition in verified] == [
        "platform-claude-code",
        "platform-codex",
        "platform-opencode",
    ]


def test_declared_bypass_failure_prevents_enforced_task_gate() -> None:
    binding = load_opencode_contract(ROOT)
    with pytest.raises(RouteFailure, match="AWP_ADAPTER_BYPASS_DETECTED"):
        measure_capability_manifest(
            PlatformProbeInputs(
                binding=binding,
                caller_context=caller_context("opencode"),
                observed_harness_version=binding.harness_version,
                probe=Probe(bypass_open={"task_admission_gate"}),
                enforce_minimums=True,
            )
        )
