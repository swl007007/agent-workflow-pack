from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

import pytest

from agent_stack.route.capabilities import PlatformProbeInputs, measure_capability_manifest
from agent_stack.route.errors import RouteFailure
from agent_stack.route.platforms.claude_code import load_claude_code_contract
from agent_stack.route.platforms.codex import load_codex_contract
from agent_stack.route.platforms.opencode import load_opencode_contract
from agent_stack.runtime.caller_context import VerifiedCallerContext


ROOT = Path(__file__).resolve().parents[3]


class Probe:
    def __init__(
        self,
        *,
        unsupported: set[str] | None = None,
        instruction_only: set[str] | None = None,
        mutable: set[str] | None = None,
        bypass_open: set[str] | None = None,
    ) -> None:
        self.unsupported = unsupported or set()
        self.instruction_only = instruction_only or set()
        self.mutable = mutable or set()
        self.bypass_open = bypass_open or set()
        self.calls: list[str] = []

    def __call__(
        self, probe_id: str, capability_id: str, context: VerifiedCallerContext
    ) -> Mapping[str, object]:
        self.calls.append(probe_id)
        return {
            "probe_id": probe_id,
            "capability_id": capability_id,
            "read_only": capability_id not in self.mutable,
            "supported": capability_id not in self.unsupported,
            "instruction_present": capability_id in self.instruction_only,
            "enforcement_verified": capability_id
            not in self.unsupported | self.instruction_only,
            "bypass_closed": capability_id not in self.bypass_open,
            "integration_evidence_id": f"{context.platform}:{capability_id}:v1",
        }


def caller_context(platform: str) -> VerifiedCallerContext:
    caller_platform = "claude" if platform == "claude-code" else platform
    return VerifiedCallerContext(
        platform=caller_platform,
        user_home=Path("/home/user"),
        config_roots=MappingProxyType({f"{caller_platform}_home": Path("/home/user/config")}),
        harness_executable=Path(f"/usr/bin/{caller_platform}"),
        harness_version_probe_id=f"{platform}-version-v1",
        tty=MappingProxyType(
            {
                "direct_confirmation_capable": True,
                "stdin": True,
                "stdout": True,
                "stderr": True,
            }
        ),
    )


def test_three_locked_contracts_have_exact_versions_entries_and_gates() -> None:
    bindings = (
        load_claude_code_contract(ROOT),
        load_codex_contract(ROOT),
        load_opencode_contract(ROOT),
    )

    assert [binding.adapter.platform.value for binding in bindings] == [
        "claude-code",
        "codex",
        "opencode",
    ]
    for binding in bindings:
        assert binding.default_platform is True
        assert binding.adapter.tested_harness_versions == (binding.harness_version,)
        assert binding.adapter.native_light_entry_id
        assert binding.adapter.wrapper_entries
        assert binding.adapter.blocked_bypass_entries
        assert binding.adapter.trellis_adapter_contract["active_root"] == ".trellis/tasks"
        verifier = binding.adapter.approval_verifiers["task_creation"]
        assert verifier["actor_source"] == "direct-human"
        assert set(binding.probes) == set(binding.minimum_capabilities)


def test_measurement_populates_only_read_only_version_bound_evidence() -> None:
    binding = load_codex_contract(ROOT)
    probe = Probe()

    manifest = measure_capability_manifest(
        PlatformProbeInputs(
            binding=binding,
            caller_context=caller_context("codex"),
            observed_harness_version=binding.harness_version,
            probe=probe,
            enforce_minimums=True,
        )
    )

    assert manifest["platform"] == "codex"
    assert manifest["harness_version"] == binding.harness_version
    assert set(manifest["capabilities"].values()) == {"enforced"}
    assert len(manifest["evidence_digest"]) == 64
    assert probe.calls == [binding.probes[key] for key in sorted(binding.probes)]


def test_unknown_is_unsupported_and_instruction_only_never_claims_enforced() -> None:
    binding = load_codex_contract(ROOT)
    manifest = measure_capability_manifest(
        PlatformProbeInputs(
            binding=binding,
            caller_context=caller_context("codex"),
            observed_harness_version=binding.harness_version,
            probe=Probe(
                unsupported={"project_skills"},
                instruction_only={"direct_human_confirmation"},
            ),
            enforce_minimums=False,
        )
    )

    assert manifest["capabilities"]["project_skills"] == "unsupported"
    assert manifest["capabilities"]["direct_human_confirmation"] == "instruction-only"
    with pytest.raises(RouteFailure, match="AWP_ADAPTER_CAPABILITY_UNVERIFIED"):
        measure_capability_manifest(
            PlatformProbeInputs(
                binding=binding,
                caller_context=caller_context("codex"),
                observed_harness_version=binding.harness_version,
                probe=Probe(unsupported={"project_skills"}),
                enforce_minimums=True,
            )
        )


def test_mutating_probe_open_bypass_or_wrong_harness_fails_closed() -> None:
    binding = load_codex_contract(ROOT)
    for probe in (
        Probe(mutable={"project_instructions"}),
        Probe(bypass_open={"task_admission_gate"}),
    ):
        with pytest.raises(RouteFailure):
            measure_capability_manifest(
                PlatformProbeInputs(
                    binding=binding,
                    caller_context=caller_context("codex"),
                    observed_harness_version=binding.harness_version,
                    probe=probe,
                    enforce_minimums=True,
                )
            )

    with pytest.raises(RouteFailure, match="AWP_ADAPTER_CAPABILITY_UNVERIFIED"):
        measure_capability_manifest(
            PlatformProbeInputs(
                binding=binding,
                caller_context=caller_context("codex"),
                observed_harness_version="99.0.0",
                probe=Probe(),
                enforce_minimums=True,
            )
        )


def test_caller_platform_and_version_probe_identity_are_bound() -> None:
    binding = load_codex_contract(ROOT)
    wrong_platform = caller_context("opencode")
    wrong_probe = VerifiedCallerContext(
        **{
            **caller_context("codex").__dict__,
            "harness_version_probe_id": "other-version-probe",
        }
    )

    for context in (wrong_platform, wrong_probe):
        with pytest.raises(RouteFailure, match="AWP_ADAPTER_CAPABILITY_UNVERIFIED"):
            measure_capability_manifest(
                PlatformProbeInputs(
                    binding=binding,
                    caller_context=context,
                    observed_harness_version=binding.harness_version,
                    probe=Probe(),
                    enforce_minimums=True,
                )
            )

