"""Production Route/Adapter command handlers."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.cli.production import ProductionCommand

from .signals import evaluate_compiled_policy, load_compiled_policy


def _data_root() -> Path:
    return Path(str(files("agent_stack").joinpath("data")))


def _case(
    case_id: str, signals: tuple[str, ...], explicit_modes: tuple[str, ...] = ()
) -> dict[str, object]:
    policy = load_compiled_policy(_data_root() / "catalog/route-policy.yaml")
    result = evaluate_compiled_policy(signals, explicit_modes, policy)
    return {
        "case_id": case_id,
        "signals": list(result.signals),
        "explicit_modes": list(explicit_modes),
        "route": result.route,
        "matched_rule_ids": list(result.matched_rule_ids),
    }


def run_test_routing(payload: object) -> Mapping[str, object]:
    command = cast(ProductionCommand, payload)
    policy = load_compiled_policy(_data_root() / "catalog/route-policy.yaml")
    cases = [_case("ordinary-change", ())]
    cases.extend(
        _case(f"hard:{signal}", (signal,)) for signal in policy.hard_signals
    )
    cases.extend(
        _case(rule.rule_id, rule.all_signals) for rule in policy.compound_rules
    )
    cases.extend(
        (
            _case("explicit:trellis-native", (), ("trellis-native",)),
            _case(
                "explicit:speckit-superpowers",
                (),
                ("speckit-superpowers",),
            ),
        )
    )
    assert cases[0]["route"] == "native-light"
    assert all(
        case["route"] == "speckit-superpowers"
        for case in cases
        if str(case["case_id"]).startswith(("hard:", "compound:"))
    )
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.test-routing-result",
            "schema_version": 1,
            "repository_root": str(command.repository_root),
            "policy_digest": policy.policy_digest,
            "default_route": policy.default_route,
            "heavy_route": "speckit-superpowers",
            "heavy_orchestrator": "heavy-development-router",
            "superpowers_leaf_capabilities": [
                "debugging",
                "review",
                "test-driven-development",
                "verification",
            ],
            "superpowers_planner_exposed": False,
            "superpowers_executor_exposed": False,
            "cases": cases,
        }
    )


def run_route_decide(payload: object) -> Mapping[str, object]:
    command = cast(ProductionCommand, payload)
    signals = command.invocation.options.get("signals", ())
    explicit_modes = command.invocation.options.get("explicit_modes", ())
    if not isinstance(signals, tuple) or not isinstance(explicit_modes, tuple):
        signals = ()
        explicit_modes = ()
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.route-calculation",
            "schema_version": 1,
            **_case("route-decide", signals, explicit_modes),
        }
    )

