from __future__ import annotations

from copy import deepcopy

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.core.surfaces import compute_surface_digests, validate_surface_registry
from tests.unit.core.test_surfaces import _valid_contract


@given(st.permutations((0, 1, 2)), st.permutations((0, 1, 2)))
def test_registry_and_inventory_input_order_never_changes_surface_roots(
    surface_order: list[int], unit_order: list[int]
) -> None:
    registry, inventory, evidence = _valid_contract()
    shuffled_registry = deepcopy(registry)
    shuffled_inventory = deepcopy(inventory)
    shuffled_registry["surfaces"] = [registry["surfaces"][index] for index in surface_order]
    shuffled_inventory["units"] = [inventory["units"][index] for index in unit_order]

    expected = compute_surface_digests(validate_surface_registry(registry, inventory), evidence)
    actual = compute_surface_digests(
        validate_surface_registry(shuffled_registry, shuffled_inventory), evidence
    )

    assert actual == expected
