from __future__ import annotations

import math
import uuid

import pytest

from agent_stack.core.canonical import (
    CANONICAL_NULL,
    canonical_json_bytes,
    digest,
    normalize_mode,
    normalize_path,
    normalize_string_set,
    normalize_uuid,
)
from agent_stack.core.errors import CoreFailure


def test_rfc8785_number_vector_uses_ecmascript_formatting() -> None:
    value = [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27, 1e20, 1e-6, 1e-7]

    assert canonical_json_bytes(value) == (
        b"[333333333.3333333,1e+30,4.5,0.002,1e-27,"
        b"100000000000000000000,0.000001,1e-7]"
    )


def test_jcs_sorts_object_keys_by_utf16_code_units() -> None:
    value = {"\U00010000": 1, "\ue000": 2, "a": 3}

    assert canonical_json_bytes(value) == '{"a":3,"𐀀":1,"":2}'.encode()


def test_domain_separation_changes_digest() -> None:
    value = {"x": 1}

    assert digest("agent-workflow.a.v1", value) != digest("agent-workflow.b.v1", value)


def test_nfc_normalization_is_applied_before_digesting() -> None:
    assert digest("agent-workflow.text.v1", {"name": "e\u0301"}) == digest(
        "agent-workflow.text.v1", {"name": "é"}
    )


def test_nfc_key_collision_is_rejected() -> None:
    with pytest.raises(CoreFailure, match="AWP_CANONICALIZATION_INVALID"):
        canonical_json_bytes({"é": 1, "e\u0301": 2})


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(CoreFailure, match="AWP_CANONICALIZATION_INVALID"):
        canonical_json_bytes(value)


def test_repository_paths_are_nfc_and_alias_safe() -> None:
    assert normalize_path("profiles/cafe\u0301.yaml") == "profiles/café.yaml"
    for invalid in ("/absolute", "../escape", "a/./b", "a//b", "a\\b", "C:/drive", "a\0b"):
        with pytest.raises(CoreFailure, match="AWP_CANONICALIZATION_INVALID"):
            normalize_path(invalid)


def test_modes_are_masked_and_rendered_as_four_octal_digits() -> None:
    assert normalize_mode(0o100644) == "0644"
    assert normalize_mode("644") == "0644"
    assert normalize_mode("100755") == "0755"


def test_uuid_and_set_semantics_have_one_normal_form() -> None:
    value = uuid.UUID("C7C2DD65-7073-5E38-8004-FE6B9B4AF8F5")

    assert normalize_uuid(value) == "c7c2dd65-7073-5e38-8004-fe6b9b4af8f5"
    assert normalize_uuid("{C7C2DD65-7073-5E38-8004-FE6B9B4AF8F5}") == str(value)
    assert normalize_string_set(["z", "e\u0301", "é", "a"]) == ("a", "z", "é")


def test_canonical_null_is_a_literal_domain_value() -> None:
    assert CANONICAL_NULL == "canonical-null"
    assert canonical_json_bytes(CANONICAL_NULL) == b'"canonical-null"'
