from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.core.canonical import CANONICAL_NULL
from agent_stack.core.errors import CoreFailure
from agent_stack.core.impact import compute_candidate_impact
from agent_stack.core.schema_catalog import SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]
AUTHORITIES = (
    "release-identity",
    "profile",
    "workflow-lock",
    "artifact-bundle",
    "route-policy",
    "router-contract",
    "surface-registry",
    "trellis-layout",
)


def _authorities(seed: str = "a") -> dict[str, str]:
    return {authority: seed * 64 for authority in AUTHORITIES}


def _current(**surfaces: str) -> dict[str, object]:
    return {
        "authority_digests": _authorities("a"),
        "surface_digests": surfaces,
        "registry_graph_digest": "b" * 64,
    }


def _observed(**surfaces: str) -> dict[str, object]:
    return {"surface_digests": surfaces, "unclassified_runtime_units": []}


def _candidate(operation: str = "sync", **surfaces: str) -> dict[str, object]:
    return {
        "operation": operation,
        "authority_digests": _authorities("a"),
        "surface_digests": surfaces,
        "registry_graph_digest": "b" * 64,
        "repair_surface_ids": [],
    }


def test_no_change_produces_none_impact() -> None:
    current = _current(**{"skill:tdd": "c" * 64})
    impact = compute_candidate_impact(
        current,
        _observed(**{"skill:tdd": "c" * 64}),
        _candidate(**{"skill:tdd": "c" * 64}),
    )

    assert impact.impact_kind == "none"
    assert impact.authority_changes == ()
    assert impact.surface_changes == ()
    assert impact.contract_changing is False


def test_authority_change_and_surface_add_remove_are_normalized() -> None:
    current = _current(
        **{"platform-adapter:codex": "c" * 64, "skill:old": "d" * 64}
    )
    candidate = _candidate(
        "upgrade", **{"platform-adapter:codex": "e" * 64, "skill:new": "f" * 64}
    )
    candidate["authority_digests"] = _authorities("a")
    candidate["authority_digests"]["release-identity"] = "9" * 64  # type: ignore[index]

    impact = compute_candidate_impact(
        current,
        _observed(
            **{"platform-adapter:codex": "c" * 64, "skill:old": "d" * 64}
        ),
        candidate,
    )

    assert [change.authority_id for change in impact.authority_changes] == ["release-identity"]
    assert [change.surface_id for change in impact.surface_changes] == [
        "platform-adapter:codex",
        "skill:new",
        "skill:old",
    ]
    assert impact.surface_changes[1].contract_before_digest == CANONICAL_NULL
    assert impact.surface_changes[2].after_digest == CANONICAL_NULL
    assert impact.contract_changing is True


def test_restorative_repair_keeps_the_pinned_contract() -> None:
    current = _current(**{"platform-adapter:codex": "c" * 64})
    candidate = _candidate("repair", **{"platform-adapter:codex": "c" * 64})
    candidate["repair_surface_ids"] = ["platform-adapter:codex"]

    impact = compute_candidate_impact(
        current,
        _observed(**{"platform-adapter:codex": CANONICAL_NULL}),
        candidate,
    )

    assert len(impact.surface_changes) == 1
    repair = impact.surface_changes[0]
    assert repair.change_kind == "repair"
    assert repair.contract_before_digest == repair.after_digest == "c" * 64
    assert repair.observed_before_digest == CANONICAL_NULL
    assert impact.contract_changing is False


@pytest.mark.parametrize("case", ["unexplained-drift", "repair-changes-contract", "unclassified"])
def test_incomplete_or_inconsistent_impact_evidence_fails(case: str) -> None:
    current = _current(**{"skill:tdd": "c" * 64})
    observed = _observed(**{"skill:tdd": "d" * 64})
    candidate = _candidate(**{"skill:tdd": "c" * 64})
    if case == "repair-changes-contract":
        candidate = _candidate("repair", **{"skill:tdd": "e" * 64})
        candidate["repair_surface_ids"] = ["skill:tdd"]
    elif case == "unclassified":
        observed = _observed(**{"skill:tdd": "c" * 64})
        observed["unclassified_runtime_units"] = ["src/unknown.py"]

    with pytest.raises(
        CoreFailure,
        match="AWP_SURFACE_COVERAGE_INVALID" if case == "unclassified" else "AWP_CANDIDATE_IMPACT_INVALID",
    ):
        compute_candidate_impact(current, observed, candidate)


def test_upgrade_must_change_release_identity() -> None:
    with pytest.raises(CoreFailure, match="AWP_CANDIDATE_IMPACT_INVALID"):
        compute_candidate_impact(_current(), _observed(), _candidate("upgrade"))


def test_candidate_impact_schema_is_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.supported_versions("agent-workflow.candidate-impact") == (1,)
    document = {
        "schema_id": "agent-workflow.candidate-impact",
        "schema_version": 1,
        "impact_kind": "none",
        "authority_changes": [],
        "surface_changes": [],
        "candidate_impact_digest": "a" * 64,
    }
    catalog.load_and_validate(document)
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**document, "unknown": True})
