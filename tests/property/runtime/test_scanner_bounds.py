from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.runtime.scanner import NormativeTaskScanner
from tests.unit.runtime.test_scanner import (
    discovery_schemas,
    finding_kinds,
    layout_document,
    verified_layout,
    write_integration,
)


@given(segment=st.sampled_from([".", "..", " task", "task ", "task.", "a\\b", "bad\nname"]))
def test_invalid_task_segments_never_disappear(segment: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        active = root / ".trellis/tasks"
        active.mkdir(parents=True)
        candidate = active / segment
        try:
            candidate.mkdir()
        except (FileExistsError, OSError):
            return

        result = NormativeTaskScanner(root)(
            verified_layout(), verified_layout(), discovery_schemas(), discovery_schemas()
        )

        assert finding_kinds(result)


def test_task_and_root_count_limits_fail_closed_without_quiescent_truncation(
    tmp_path: Path,
) -> None:
    write_integration(tmp_path, ".trellis/tasks/one", task_id="5f477c7f-a1dc-4a16-8f75-39f153170222")
    write_integration(tmp_path, ".trellis/tasks/two", task_id="6ea415f2-3823-4a36-9d25-cf00b82f1f70")
    document = layout_document()
    document["task_discovery"]["max_tasks"] = 1
    document["task_discovery"]["max_root_entries"] = 1
    layout = verified_layout(document)

    result = NormativeTaskScanner(tmp_path)(layout, layout, discovery_schemas(), discovery_schemas())

    limits = [item for item in result.findings["findings"] if item["kind"] == "scan-limit"]
    assert {item["limit_kind"] for item in limits} >= {"max_tasks", "max_root_entries"}


def test_bounded_metadata_depth_match_and_byte_limits_are_findings(tmp_path: Path) -> None:
    sessions = tmp_path / ".trellis/sessions"
    sessions.mkdir(parents=True)
    (sessions / "nested").mkdir()
    (sessions / "nested" / "hidden.json").write_text("{}", encoding="utf-8")
    for index in range(2):
        name = f"00000000-0000-4000-8000-{index:012d}.json"
        (sessions / name).write_text("{" + "x" * 64 + "}", encoding="utf-8")
    document = layout_document()
    bounded = document["metadata_contracts"][1]
    bounded["max_matches"] = 1
    bounded["max_bytes"] = 8
    layout = verified_layout(document)

    result = NormativeTaskScanner(tmp_path)(layout, layout, discovery_schemas(), discovery_schemas())

    kinds = finding_kinds(result)
    assert "scan-limit" in kinds
    assert "unknown-entry" in kinds
    assert "layout-ambiguous" in kinds
