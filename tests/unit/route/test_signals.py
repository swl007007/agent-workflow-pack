from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack._vendor import yaml
from agent_stack.route.errors import RouteFailure
from agent_stack.route.signals import (
    evaluate_compiled_policy,
    load_compiled_policy,
    normalize_signals,
)


ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / "catalog/route-policy.yaml"
LEGACY = Path(__file__).resolve().parents[2] / "fixtures/route/legacy-trigger-map.yaml"


def test_every_hard_and_compound_rule_has_stable_heavy_behavior() -> None:
    policy = load_compiled_policy(POLICY)
    for signal in policy.hard_signals:
        result = evaluate_compiled_policy((signal,), (), policy)
        assert result.route == "speckit-superpowers"
        assert result.matched_rule_ids == (f"hard:{signal}",)

    for compound in policy.compound_rules:
        result = evaluate_compiled_policy(compound.all_signals, (), policy)
        assert result.route == "speckit-superpowers"
        assert compound.rule_id in result.matched_rule_ids


def test_unknown_duplicate_and_conflicting_explicit_modes_fail_closed() -> None:
    policy = load_compiled_policy(POLICY)
    with pytest.raises(RouteFailure, match="AWP_ROUTE_SIGNAL_INVALID"):
        normalize_signals(("unknown-signal",), policy)
    with pytest.raises(RouteFailure, match="duplicate"):
        normalize_signals(("public_contract_change", "public_contract_change"), policy)
    with pytest.raises(RouteFailure, match="conflicting explicit modes"):
        evaluate_compiled_policy(
            (), ("trellis-native", "speckit-superpowers"), policy
        )


def test_explicit_integrated_selection_and_native_light_default_are_disjoint() -> None:
    policy = load_compiled_policy(POLICY)

    assert evaluate_compiled_policy((), (), policy).route == "native-light"
    assert evaluate_compiled_policy((), ("trellis-native",), policy).route == "trellis-native"
    assert (
        evaluate_compiled_policy((), ("speckit-superpowers",), policy).route
        == "speckit-superpowers"
    )
    assert (
        evaluate_compiled_policy(("multi_module",), (), policy).route == "native-light"
    )


def test_rule_order_and_reasons_are_stable_but_reasons_do_not_select_route() -> None:
    policy = load_compiled_policy(POLICY)
    signals = (
        "public_contract_change",
        "architecture_or_subsystem_change",
        "contract_surface",
        "multi_module",
    )

    first = evaluate_compiled_policy(signals, (), policy)
    second = evaluate_compiled_policy(tuple(reversed(signals)), (), policy)

    assert first == second
    assert first.matched_rule_ids == tuple(sorted(first.matched_rule_ids))
    assert all(reason.startswith("matched:") for reason in first.reasons)


def test_legacy_trigger_map_preserves_the_effective_heavy_boundary() -> None:
    policy = load_compiled_policy(POLICY)
    fixture = yaml.safe_load(LEGACY.read_text(encoding="utf-8"))

    for case in fixture["cases"]:
        result = evaluate_compiled_policy(tuple(case["signals"]), (), policy)
        assert result.route == case["route"], case["legacy_trigger"]
