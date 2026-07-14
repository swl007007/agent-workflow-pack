from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agent_stack._vendor import fastjsonschema
from agent_stack.route.adapter_contract import (
    StablePlatformID,
    validate_platform_adapter,
)
from agent_stack.route.errors import RouteFailure


ROOT = Path(__file__).resolve().parents[3]


def adapter_document(platform: str = "codex") -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.platform-adapter",
        "schema_version": 1,
        "platform": platform,
        "adapter_id": platform,
        "adapter_version": "1.0.0",
        "tested_harness_versions": ["1.2.3"],
        "native_light_entry_id": "sol-native",
        "caller_context_fields": ["user_home", "codex_home", "harness.executable"],
        "capability_probe_suite": {
            "probe_suite_id": f"{platform}-capability-probes",
            "probe_suite_version": 1,
            "capability_ids": [
                "direct_human_confirmation",
                "explicit_runtime_load",
                "maintenance_gate",
                "native_light_binding",
                "project_instructions",
                "project_skills",
                "provider_exception_approval",
                "route_gated_catalog",
                "task_admission_gate",
                "task_archive_gate",
            ],
        },
        "approval_verifiers": {
            "task_creation": {
                "verifier_id": "platform-approval-verifier",
                "verifier_version": "1.0.0",
                "actor_source": "direct-human",
                "receipt_source": "enforced-confirmation",
            }
        },
        "render_projections": [
            {
                "unit_id": "instruction:codex-agents",
                "target_path": "AGENTS.md",
                "ownership": "overlay-managed",
                "merge_strategy": "managed-block",
                "mode": "0644",
                "owning_surface_id": "platform-adapter:codex",
                "template_id": "codex-agents-v1",
                "validator_ids": ["utf8-text-v1"],
                "discoverable": True,
            }
        ],
        "wrapper_entries": [
            {
                "operation": "integrated-runtime-load",
                "runtime_entry_id": "trellis-implement",
                "allowed_modes": ["trellis-native"],
                "allowed_phases": [],
                "claim_policy": "forbidden",
                "command": [".agent-workflow/bin/agent-stack", "task", "runtime", "load"],
            }
        ],
        "blocked_bypass_entries": ["/speckit.implement", "trellis-implement-direct"],
        "trellis_adapter_contract": {
            "active_root": ".trellis/tasks",
            "archive_root": ".trellis/tasks/archive",
            "integration_relative_path": "integration.yaml",
            "precommit_side_effects": "disabled",
        },
        "golden_contract_id": f"{platform}-v1",
    }


def test_platform_ids_and_closed_adapter_contract_validate() -> None:
    assert tuple(item.value for item in StablePlatformID) == (
        "claude-code",
        "codex",
        "opencode",
    )
    for platform in StablePlatformID:
        document = adapter_document(platform.value)
        verified = validate_platform_adapter(document)
        assert verified.platform is platform
        assert verified.adapter_id == platform.value
        assert verified.wrapper_entries[0]["operation"] == "integrated-runtime-load"


def test_unknown_routes_signals_capabilities_and_task_mutation_fields_are_rejected() -> None:
    unknown_capability = adapter_document()
    suite = unknown_capability["capability_probe_suite"]
    assert isinstance(suite, dict)
    suite["capability_ids"].append("model-invented-capability")

    task_mutation = adapter_document()
    projection = task_mutation["render_projections"]
    assert isinstance(projection, list)
    assert isinstance(projection[0], dict)
    projection[0]["task_id"] = "forbidden"

    unknown_route = adapter_document()
    wrapper = unknown_route["wrapper_entries"]
    assert isinstance(wrapper, list)
    assert isinstance(wrapper[0], dict)
    wrapper[0]["allowed_modes"] = ["model-heavy"]

    unknown_signal = adapter_document()
    unknown_signal["signals"] = ["free-form"]

    for document in (unknown_capability, task_mutation, unknown_route, unknown_signal):
        with pytest.raises(RouteFailure, match="AWP_ADAPTER_CONTRACT_INVALID"):
            validate_platform_adapter(document)


def test_all_route_owned_schemas_are_registered_and_closed() -> None:
    for name in (
        "platform-adapter.v1.json",
        "platform-adapter-projection.v1.json",
        "approval-verification-result.v1.json",
        "adapter-golden-contract.v1.json",
        "route-failure.v1.json",
    ):
        schema = json.loads((ROOT / "schemas/route" / name).read_text(encoding="utf-8"))
        validator = fastjsonschema.compile(schema)
        if name == "platform-adapter.v1.json":
            document = adapter_document()
            assert validator(copy.deepcopy(document)) == document

    projection_schema = json.loads(
        (ROOT / "schemas/route/platform-adapter-projection.v1.json").read_text()
    )
    projection = {
        "schema_id": "agent-workflow.platform-adapter-projection",
        "schema_version": 1,
        "platform": "codex",
        "adapter_id": "codex",
        "adapter_version": "1.0.0",
        "units": [],
        "wrappers": [],
        "blocked_bypass_entries": [],
        "projection_digest": "a" * 64,
    }
    fastjsonschema.compile(projection_schema)(projection)
    with pytest.raises(Exception):
        fastjsonschema.compile(projection_schema)({**projection, "task_id": "forbidden"})
