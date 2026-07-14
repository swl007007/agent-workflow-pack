from __future__ import annotations

import copy

import pytest
from hypothesis import given, strategies as st

from agent_stack.route.calculator import RouteCalculationInputs, calculate_route
from agent_stack.route.errors import RouteFailure
from agent_stack.route.verifier import verify_route_decision
from tests.unit.route.test_calculator import authorities, intent


@given(st.sampled_from(["profile_digest", "lock_digest", "manifest_digest", "entry_owner"]))
def test_any_authority_field_mutation_breaks_decision_replay(field: str) -> None:
    auth = authorities()
    decision = calculate_route(
        "execute-light", RouteCalculationInputs(intent=intent()), auth
    )
    changed = copy.deepcopy(dict(decision))
    changed[field] = "f" * 64 if field.endswith("digest") else "other-owner"

    with pytest.raises(RouteFailure):
        verify_route_decision(changed, auth, "execute-light")


def test_reasons_participate_in_digest_but_cannot_change_policy_result() -> None:
    auth = authorities()
    decision = calculate_route(
        "execute-light", RouteCalculationInputs(intent=intent()), auth
    )
    changed = copy.deepcopy(dict(decision))
    changed["reasons"] = ["looks-heavy"]

    with pytest.raises(RouteFailure, match="AWP_ROUTE_DECISION_INVALID"):
        verify_route_decision(changed, auth, "execute-light")
