from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent_stack.core.artifact_policy import (
    validate_task_journal_name,
    validate_task_segment,
    validate_trellis_layout,
)
from agent_stack.core.errors import CoreFailure


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "core" / "trellis_layouts"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_layout_is_normalized_and_digest_stable() -> None:
    first = validate_trellis_layout(_fixture("valid.json"), artifact_targets=("AGENTS.md",))
    second = validate_trellis_layout(_fixture("valid.json"), artifact_targets=("AGENTS.md",))

    assert first == second
    assert first.active_root == ".trellis/tasks"
    assert first.archive_root == ".trellis/tasks/archive"
    assert len(first.layout_digest) == 64


def test_layout_roots_must_be_strictly_nested_and_partitioned() -> None:
    layout = _fixture("valid.json")
    layout["active_root"] = ".trellis"
    with pytest.raises(CoreFailure, match="AWP_ARTIFACT_POLICY_INVALID"):
        validate_trellis_layout(layout)

    layout = _fixture("valid.json")
    layout["archive_root"] = ".trellis/archive"
    with pytest.raises(CoreFailure, match="AWP_ARTIFACT_POLICY_INVALID"):
        validate_trellis_layout(layout)


def test_metadata_cannot_overlap_source_artifact_or_control_plane_paths() -> None:
    with pytest.raises(CoreFailure, match="AWP_PROTECTED_PATH_VIOLATION"):
        validate_trellis_layout(_fixture("metadata-collision.json"), source_roots=("src",))

    layout = _fixture("valid.json")
    layout["metadata_contracts"][0]["path"] = "AGENTS.md"  # type: ignore[index]
    with pytest.raises(CoreFailure, match="AWP_PROTECTED_PATH_VIOLATION"):
        validate_trellis_layout(layout, artifact_targets=("AGENTS.md",))

    layout = _fixture("valid.json")
    layout["metadata_contracts"][0]["path"] = ".agent-workflow/manifest.json"  # type: ignore[index]
    with pytest.raises(CoreFailure, match="AWP_PROTECTED_PATH_VIOLATION"):
        validate_trellis_layout(layout)


def test_bounded_metadata_contract_is_finite_and_closed() -> None:
    layout = _fixture("valid.json")
    bounded = layout["metadata_contracts"][1]  # type: ignore[index]
    bounded["max_depth"] = 2  # type: ignore[index]
    with pytest.raises(CoreFailure, match="AWP_ARTIFACT_POLICY_INVALID"):
        validate_trellis_layout(layout)

    layout = _fixture("valid.json")
    bounded = layout["metadata_contracts"][1]  # type: ignore[index]
    bounded["glob"] = "**/*.json"  # type: ignore[index]
    with pytest.raises(CoreFailure, match="AWP_ARTIFACT_POLICY_INVALID"):
        validate_trellis_layout(layout)


@given(st.from_regex(r"[A-Za-z0-9_-]{1,40}", fullmatch=True))
def test_safe_nfc_segment_accepts_bounded_plain_segments(segment: str) -> None:
    assert validate_task_segment(segment) == segment


@pytest.mark.parametrize(
    "segment", [".", "..", " task", "task ", "task.", "a/b", "a\\b", "a\0b", "a\n"]
)
def test_safe_nfc_segment_rejects_aliases_and_controls(segment: str) -> None:
    with pytest.raises(CoreFailure, match="AWP_ARTIFACT_POLICY_INVALID"):
        validate_task_segment(segment)


def test_uuid_json_journal_grammar_is_exact() -> None:
    journal_id = uuid.UUID("c7c2dd65-7073-5e38-8004-fe6b9b4af8f5")
    assert validate_task_journal_name(f"{journal_id}.json") == str(journal_id)
    for invalid in (f"{str(journal_id).upper()}.json", f"{journal_id}.yaml", "latest.json"):
        with pytest.raises(CoreFailure, match="AWP_ARTIFACT_POLICY_INVALID"):
            validate_task_journal_name(invalid)
