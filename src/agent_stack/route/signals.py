"""Stable signal normalization and one compiled route policy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_stack._vendor import yaml
from agent_stack.core.api import canonical_json_bytes, digest

from .errors import RouteFailure


@dataclass(frozen=True)
class CompoundRule:
    rule_id: str
    all_signals: tuple[str, ...]


@dataclass(frozen=True)
class CompiledRoutePolicy:
    policy_version: int
    default_route: str
    hard_signals: tuple[str, ...]
    compound_rules: tuple[CompoundRule, ...]
    known_signals: frozenset[str]
    policy_digest: str


@dataclass(frozen=True)
class PolicyResult:
    route: str
    matched_rule_ids: tuple[str, ...]
    signals: tuple[str, ...]
    reasons: tuple[str, ...]


def _failure(message: str, **details: object) -> RouteFailure:
    return RouteFailure("AWP_ROUTE_SIGNAL_INVALID", message, details=details)


def _string_array(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise _failure("compiled policy string array is invalid", field=field)
    result = tuple(value)
    if len(result) != len(set(result)):
        raise _failure("compiled policy string array contains duplicates", field=field)
    return result


def load_compiled_policy(path: Path) -> CompiledRoutePolicy:
    """Load the sole declarative route policy and reject executable/unknown structure."""

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[no-untyped-call]
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise _failure("compiled route policy cannot be loaded") from error
    expected = {
        "schema_id",
        "schema_version",
        "policy_version",
        "default_route",
        "hard_signals",
        "compound_rules",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise _failure("compiled route policy fields are not closed")
    if document.get("schema_id") != "agent-workflow.route-policy" or document.get(
        "schema_version"
    ) != 1 or document.get("policy_version") != 1:
        raise _failure("compiled route policy version is unsupported")
    if document.get("default_route") != "native-light":
        raise _failure("compiled route policy default is invalid")
    hard = _string_array(document.get("hard_signals"), "hard_signals")
    if hard != tuple(sorted(hard)):
        raise _failure("hard signal list is not sorted")
    raw_compounds = document.get("compound_rules")
    if not isinstance(raw_compounds, list):
        raise _failure("compound rules are invalid")
    compounds: list[CompoundRule] = []
    for raw in raw_compounds:
        if not isinstance(raw, dict) or set(raw) != {"rule_id", "all"}:
            raise _failure("compound rule fields are not closed")
        rule_id = raw.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.startswith("compound:"):
            raise _failure("compound rule ID is invalid")
        all_signals = _string_array(raw.get("all"), "compound.all")
        if len(all_signals) < 2 or all_signals != tuple(sorted(all_signals)):
            raise _failure("compound signal set is invalid")
        compounds.append(CompoundRule(rule_id, all_signals))
    if tuple(rule.rule_id for rule in compounds) != tuple(
        sorted(rule.rule_id for rule in compounds)
    ):
        raise _failure("compound rules are not sorted")
    known = frozenset(hard).union(
        signal for rule in compounds for signal in rule.all_signals
    )
    return CompiledRoutePolicy(
        1,
        "native-light",
        hard,
        tuple(compounds),
        frozenset(known),
        digest("agent-workflow.route-policy.v1", document),
    )


def normalize_signals(
    signals: Sequence[str], policy: CompiledRoutePolicy
) -> tuple[str, ...]:
    """Validate supplied stable IDs and return their unique canonical order."""

    if isinstance(signals, (str, bytes, bytearray)) or not all(
        isinstance(signal, str) and signal for signal in signals
    ):
        raise _failure("signal set is not a string sequence")
    if len(signals) != len(set(signals)):
        raise _failure("signal set contains duplicate IDs")
    unknown = set(signals) - policy.known_signals
    if unknown:
        raise _failure("signal set contains unknown IDs", signals=sorted(unknown))
    return tuple(sorted(signals))


def evaluate_compiled_policy(
    signals: Sequence[str],
    explicit_modes: Sequence[str],
    policy: CompiledRoutePolicy,
) -> PolicyResult:
    """Evaluate explicit selection then the stable heavy boundary deterministically."""

    normalized = normalize_signals(signals, policy)
    if isinstance(explicit_modes, (str, bytes, bytearray)) or not all(
        isinstance(mode, str) for mode in explicit_modes
    ):
        raise _failure("explicit mode set is invalid")
    if len(explicit_modes) != len(set(explicit_modes)):
        raise _failure("explicit mode set contains duplicates")
    if set(explicit_modes) - {"trellis-native", "speckit-superpowers"}:
        raise _failure("explicit mode set contains an unknown route")
    if len(explicit_modes) > 1:
        raise _failure("conflicting explicit modes are forbidden")

    matched = [f"hard:{signal}" for signal in normalized if signal in policy.hard_signals]
    supplied = set(normalized)
    matched.extend(
        rule.rule_id for rule in policy.compound_rules if set(rule.all_signals) <= supplied
    )
    ordered = tuple(sorted(matched))
    if explicit_modes:
        route = explicit_modes[0]
    elif ordered:
        route = "speckit-superpowers"
    else:
        route = policy.default_route
    return PolicyResult(
        route,
        ordered,
        normalized,
        tuple(f"matched:{rule_id}" for rule_id in ordered),
    )


def policy_bytes(policy: CompiledRoutePolicy) -> bytes:
    """Return a stable evidence projection for diagnostics/tests."""

    return canonical_json_bytes(
        {
            "policy_version": policy.policy_version,
            "default_route": policy.default_route,
            "hard_signals": list(policy.hard_signals),
            "compound_rules": [
                {"rule_id": rule.rule_id, "all": list(rule.all_signals)}
                for rule in policy.compound_rules
            ],
        }
    )
