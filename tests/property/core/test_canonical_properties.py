from __future__ import annotations

import unicodedata

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.core.canonical import (
    canonical_json_bytes,
    digest,
    normalize_mode,
    normalize_path,
    normalize_string_set,
)


@given(st.dictionaries(st.text(min_size=1), st.integers(), max_size=20))
def test_mapping_insertion_order_never_changes_canonical_bytes(value: dict[str, int]) -> None:
    reversed_items = dict(reversed(list(value.items())))

    assert canonical_json_bytes(value) == canonical_json_bytes(reversed_items)


@given(st.lists(st.text(min_size=1), max_size=30))
def test_string_set_normalization_is_sorted_unique_and_idempotent(values: list[str]) -> None:
    normalized = normalize_string_set(values)

    assert normalized == tuple(sorted(set(normalized), key=lambda item: item.encode("utf-16-be")))
    assert normalize_string_set(normalized) == normalized


@given(st.integers(min_value=0, max_value=0o177777))
def test_mode_normalization_is_idempotent(value: int) -> None:
    normalized = normalize_mode(value)

    assert normalize_mode(normalized) == normalized


@given(st.lists(st.sampled_from(["alpha", "beta", "café", "δ"]), min_size=1, max_size=8))
def test_normalized_repository_paths_are_idempotent(segments: list[str]) -> None:
    path = "/".join(segments)

    assert normalize_path(normalize_path(path)) == unicodedata.normalize("NFC", path)


@given(st.text())
def test_nfc_equivalent_strings_have_the_same_digest(value: str) -> None:
    normalized = unicodedata.normalize("NFC", value)

    assert digest("agent-workflow.property.v1", value) == digest(
        "agent-workflow.property.v1", normalized
    )
