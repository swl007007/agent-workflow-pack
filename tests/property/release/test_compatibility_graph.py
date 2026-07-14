from __future__ import annotations

from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.release.compatibility import classify_compatibility
from tests.unit.release.test_compatibility import (
    bundle,
    edge,
    local_contract,
    release,
)


@given(
    source_minor=st.integers(min_value=0, max_value=99),
    target_minor=st.integers(min_value=0, max_value=99),
)
def test_versions_never_imply_an_unlisted_edge(
    source_minor: int, target_minor: int
) -> None:
    source = release(f"1.{source_minor}.0", bundle_seed=1)
    target = release(f"1.{target_minor}.0", bundle_seed=2)
    source = replace(source, compatibility=bundle(source))
    target = replace(target, compatibility=bundle(target))

    result = classify_compatibility(source, target, local_contract())

    if source.identity.release_id == target.identity.release_id:
        assert result.relationship == "equal"
    else:
        assert result.relationship == "diverged"


@given(reverse_owner=st.booleans())
def test_exact_reverse_edge_is_ahead_independent_of_version_order(
    reverse_owner: bool,
) -> None:
    source = release("0.1.0", bundle_seed=1)
    target = release("9.9.9", bundle_seed=2)
    reverse = edge(target, source)
    if reverse_owner:
        source = replace(source, compatibility=bundle(source, reverse))
        target = replace(target, compatibility=bundle(target))
    else:
        source = replace(source, compatibility=bundle(source))
        target = replace(target, compatibility=bundle(target, reverse))

    assert classify_compatibility(source, target, local_contract()).relationship == "ahead"
