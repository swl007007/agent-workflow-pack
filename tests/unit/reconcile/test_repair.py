from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from agent_stack.core.api import CandidateImpact
from agent_stack.core.impact import AuthorityChange, SurfaceChange
from agent_stack.reconcile.models import StagedRenderTree
from agent_stack.reconcile.repair import (
    stage_restorative_repair,
    validate_repair_selection,
)
from tests.unit.reconcile.test_ownership import staged
from tests.unit.reconcile.test_plan import ir_for


SURFACE = "runtime-entry:config"
EXPECTED = "4" * 64


def impact(
    *,
    after: str = EXPECTED,
    observed: str = "canonical-null",
    authorities=(),
) -> CandidateImpact:
    return CandidateImpact(
        "runtime-visible",
        authorities,
        (SurfaceChange(SURFACE, "repair", EXPECTED, observed, after),),
        False,
        "8" * 64,
    )


def test_valid_repair_preserves_contract_registry_and_task_pins() -> None:
    changes = validate_repair_selection(
        impact(),
        selected_surface_ids=[SURFACE],
        pinned_surface_digests={SURFACE: EXPECTED},
        registry_graph_before_digest="7" * 64,
        registry_graph_after_digest="7" * 64,
    )

    assert changes[0].contract_before_digest == changes[0].after_digest == EXPECTED
    assert changes[0].observed_before_digest == "canonical-null"


@pytest.mark.parametrize(
    "invalid_impact",
    [
        impact(after="5" * 64),
        impact(observed=EXPECTED),
        impact(
            authorities=(AuthorityChange("profile", "1" * 64, "2" * 64),)
        ),
    ],
)
def test_repair_to_different_contract_or_without_real_drift_is_rejected(
    invalid_impact: CandidateImpact,
) -> None:
    with pytest.raises(Exception, match="AWP_OWNERSHIP_CONFLICT"):
        validate_repair_selection(
            invalid_impact,
            selected_surface_ids=[SURFACE],
            pinned_surface_digests={SURFACE: EXPECTED},
            registry_graph_before_digest="7" * 64,
            registry_graph_after_digest="7" * 64,
        )


def test_repair_rejects_registry_or_task_pin_change() -> None:
    with pytest.raises(Exception, match="AWP_OWNERSHIP_CONFLICT"):
        validate_repair_selection(
            impact(),
            selected_surface_ids=[SURFACE],
            pinned_surface_digests={SURFACE: "6" * 64},
            registry_graph_before_digest="7" * 64,
            registry_graph_after_digest="7" * 64,
        )
    with pytest.raises(Exception, match="AWP_OWNERSHIP_CONFLICT"):
        validate_repair_selection(
            impact(),
            selected_surface_ids=[SURFACE],
            pinned_surface_digests={},
            registry_graph_before_digest="7" * 64,
            registry_graph_after_digest="9" * 64,
        )


def test_stage_repair_selects_only_frozen_after_surfaces() -> None:
    record = staged("generated/config.txt", b"before\n", definition_id="config")
    ir = replace(
        ir_for("repair", record),
        candidate_impact=impact(),
        surface_digests=MappingProxyType({SURFACE: EXPECTED}),
    )

    selected = stage_restorative_repair(ir, StagedRenderTree((record,), "a" * 64))

    assert selected.files == (record,)


def test_stage_repair_rejects_unselected_or_wrong_contract_surface() -> None:
    record = staged("generated/config.txt", b"before\n", definition_id="config")
    wrong = replace(record, surface_id="skill:unrelated")
    ir = replace(
        ir_for("repair", record),
        candidate_impact=impact(),
        surface_digests=MappingProxyType({SURFACE: EXPECTED}),
    )

    with pytest.raises(Exception, match="AWP_OWNERSHIP_CONFLICT"):
        stage_restorative_repair(ir, StagedRenderTree((wrong,), "a" * 64))
