from __future__ import annotations

import dataclasses
from types import MappingProxyType

import pytest

from agent_stack.route.adapter_contract import VerifiedPlatformAdapterContract
from agent_stack.route.errors import RouteFailure
from agent_stack.route.platforms.codex import load_codex_contract
from agent_stack.route.projection import project_platform_adapter
from tests.golden.route.test_adapter_projection import ROOT, make_ir


def test_adapter_cannot_add_ir_absent_or_undeclared_owned_unit() -> None:
    binding = load_codex_contract(ROOT)
    ir = make_ir(binding)
    missing = dataclasses.replace(ir, render_units=ir.render_units[:-1])
    extra_unit = {
        **dict(ir.render_units[0]),
        "unit_id": "command:codex-undeclared",
        "candidate_leaf_digest": "0" * 64,
    }
    extra = dataclasses.replace(
        ir,
        render_units=(*ir.render_units, MappingProxyType(extra_unit)),
    )

    for candidate in (missing, extra):
        with pytest.raises(RouteFailure, match="AWP_ADAPTER_PROJECTION_INVALID"):
            project_platform_adapter(candidate, binding.adapter)


def test_disabled_or_gated_nodes_cannot_enter_discoverable_or_reference_closure() -> None:
    binding = load_codex_contract(ROOT)
    ir = make_ir(binding)
    gated_discoverable = dataclasses.replace(
        ir,
        discoverable_leaf_ids=(*ir.discoverable_leaf_ids, "router:heavy-development-router"),
    )
    gated_reference = dataclasses.replace(
        ir,
        reference_closure=("skill:sdd-superpower-micro-plan",),
    )
    disabled = dataclasses.replace(
        ir,
        resolved_profile=MappingProxyType(
            {
                "profile_id": "default",
                "skills_disable": [ir.discoverable_leaf_ids[0]],
            }
        ),
    )

    for candidate in (gated_discoverable, gated_reference, disabled):
        with pytest.raises(RouteFailure, match="AWP_ADAPTER_PROJECTION_INVALID"):
            project_platform_adapter(candidate, binding.adapter)


def test_projection_metadata_must_match_ir_path_surface_validator_and_discoverability() -> None:
    binding = load_codex_contract(ROOT)
    ir = make_ir(binding)
    first = dict(binding.adapter.render_projections[0])
    variants = []
    for field, value in (
        ("target_path", "other.md"),
        ("owning_surface_id", "platform-adapter:opencode"),
        ("validator_ids", ["other-v1"]),
        ("discoverable", False),
    ):
        changed = {**first, field: value}
        variants.append(
            VerifiedPlatformAdapterContract(
                **{
                    **binding.adapter.__dict__,
                    "render_projections": (
                        MappingProxyType(changed),
                        *binding.adapter.render_projections[1:],
                    ),
                }
            )
        )

    for adapter in variants:
        with pytest.raises(RouteFailure, match="AWP_ADAPTER_PROJECTION_INVALID"):
            project_platform_adapter(ir, adapter)
