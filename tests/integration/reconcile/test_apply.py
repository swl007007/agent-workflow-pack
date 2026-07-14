from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agent_stack.core.api import TaskSnapshotAndFindings
from agent_stack.reconcile.api import apply_plan
from agent_stack.reconcile.errors import RendererFailure
from tests.integration.reconcile.apply_helpers import (
    RecordingScanner,
    make_apply_case,
    read_json,
)


def test_apply_commits_manifest_last_and_scans_twice(tmp_path: Path) -> None:
    envelope, task_state, approval = make_apply_case(tmp_path)
    scanner = RecordingScanner([task_state, task_state])

    result = apply_plan(envelope, approval, scanner=scanner)

    assert result["committed"] is True
    assert (tmp_path / "generated/config.txt").read_bytes() == b"after\n"
    manifest = read_json(tmp_path / ".agent-workflow/manifest.json")
    assert manifest["last_transaction_binding_digest"] == envelope.journal_binding_digest
    assert not (tmp_path / ".agent-workflow/maintenance.json").exists()
    journal = read_json(
        tmp_path / f".agent-workflow/transactions/{envelope.plan_core['transaction_id']}.json"
    )
    assert journal["phase"] == "complete"
    assert len(scanner.calls) == 2


def test_changed_commit_time_snapshot_is_primary_and_precommit_recoverable(
    tmp_path: Path,
) -> None:
    envelope, task_state, approval = make_apply_case(tmp_path)
    changed = TaskSnapshotAndFindings(
        {**task_state.snapshot, "tasks": [{"external": "change"}]},
        task_state.findings,
        "0" * 64,
    )
    scanner = RecordingScanner([task_state, changed])

    with pytest.raises(RendererFailure, match="AWP_TASK_QUIESCENCE_CHANGED"):
        apply_plan(envelope, approval, scanner=scanner)

    old_manifest = read_json(tmp_path / ".agent-workflow/manifest.json")
    assert old_manifest["last_transaction_binding_digest"] != envelope.journal_binding_digest
    assert (tmp_path / ".agent-workflow/maintenance.json").is_file()
    journal = read_json(
        tmp_path / f".agent-workflow/transactions/{envelope.plan_core['transaction_id']}.json"
    )
    assert journal["phase"] == "files_applied"


def test_true_noop_apply_performs_zero_target_writes(tmp_path: Path) -> None:
    envelope, task_state, approval = make_apply_case(tmp_path, after=b"before\n")
    before = {
        path.relative_to(tmp_path): (path.stat().st_mtime_ns, path.read_bytes())
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    result = apply_plan(envelope, approval, scanner=RecordingScanner([task_state]))

    after = {
        path.relative_to(tmp_path): (path.stat().st_mtime_ns, path.read_bytes())
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert result["no_op"] is True
    assert after == before


def test_true_noop_still_revalidates_the_complete_saved_plan(tmp_path: Path) -> None:
    envelope, task_state, approval = make_apply_case(tmp_path, after=b"before\n")
    forged = replace(envelope, candidate_manifest_digest="0" * 64)

    with pytest.raises(Exception, match="AWP_SAVED_PLAN_MISMATCH"):
        apply_plan(forged, approval, scanner=RecordingScanner([task_state]))
