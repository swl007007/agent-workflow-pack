from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.core.impact import compute_candidate_impact
from tests.unit.core.test_impact import _candidate, _current, _observed


@given(st.permutations(("skill:a", "skill:b", "platform-adapter:codex")))
def test_surface_input_order_never_changes_normalized_impact(order: list[str]) -> None:
    before = {surface_id: chr(97 + index) * 64 for index, surface_id in enumerate(order)}
    after = dict(before)
    after["skill:b"] = "f" * 64

    impact = compute_candidate_impact(_current(**before), _observed(**before), _candidate(**after))

    assert [change.surface_id for change in impact.surface_changes] == ["skill:b"]
