from __future__ import annotations

from pathlib import Path
import hashlib
import os

import pytest

import agent_stack.reconcile.apply as apply_module
from agent_stack.core.api import canonical_json_bytes
from agent_stack.reconcile.api import apply_plan, recover_transaction
from agent_stack.reconcile.errors import RendererFailure
from agent_stack.reconcile.api import plan_reconcile
from agent_stack.reconcile.models import StagedRenderTree
from tests.integration.reconcile.apply_helpers import (
    RecordingScanner,
    make_apply_case,
    read_json,
    scanner_inputs,
)
from tests.unit.reconcile.test_ownership import staged, state
from tests.unit.reconcile.test_plan import empty_task_state, ir_for, manifest_for, observed_for


class InjectedTermination(BaseException):
    pass


def interrupt_apply(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    killpoint: str,
):
    envelope, task_state, approval = make_apply_case(root)

    def terminate(point: str) -> None:
        if point == killpoint:
            raise InjectedTermination(point)

    monkeypatch.setattr(apply_module, "_crash_at", terminate)
    with pytest.raises(InjectedTermination):
        apply_plan(
            envelope,
            approval,
            scanner=RecordingScanner([task_state, task_state]),
        )
    return envelope, task_state, approval


@pytest.mark.parametrize(
    "killpoint",
    ["planned", "probing", "prepared", "applying", "files_applied", "before_manifest"],
)
def test_precommit_transactions_can_explicitly_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    killpoint: str,
) -> None:
    envelope, task_state, approval = interrupt_apply(tmp_path, monkeypatch, killpoint)

    result = recover_transaction(
        str(envelope.plan_core["transaction_id"]),
        "rollback",
        root=tmp_path,
        scanner=RecordingScanner([task_state]),
        scanner_context=approval,
    )

    assert result["rolled_back"] is True
    assert (tmp_path / "generated/config.txt").read_bytes() == b"before\n"
    manifest = read_json(tmp_path / ".agent-workflow/manifest.json")
    assert manifest["last_transaction_binding_digest"] != envelope.journal_binding_digest
    assert not (tmp_path / ".agent-workflow/maintenance.json").exists()


@pytest.mark.parametrize(
    "killpoint",
    ["planned", "probing", "prepared", "applying", "files_applied", "before_manifest"],
)
def test_precommit_transactions_can_explicitly_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    killpoint: str,
) -> None:
    envelope, task_state, approval = interrupt_apply(tmp_path, monkeypatch, killpoint)

    result = recover_transaction(
        str(envelope.plan_core["transaction_id"]),
        "resume",
        root=tmp_path,
        scanner=RecordingScanner([task_state, task_state]),
        scanner_context=approval,
    )

    assert result["committed"] is True
    assert (tmp_path / "generated/config.txt").read_bytes() == b"after\n"
    manifest = read_json(tmp_path / ".agent-workflow/manifest.json")
    assert manifest["last_transaction_binding_digest"] == envelope.journal_binding_digest


@pytest.mark.parametrize("killpoint", ["after_manifest", "manifest_committed", "cleanup_pending"])
def test_committed_transaction_allows_cleanup_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    killpoint: str,
) -> None:
    envelope, task_state, approval = interrupt_apply(tmp_path, monkeypatch, killpoint)

    with pytest.raises(RendererFailure, match="AWP_RECONCILE_RECOVERY_REQUIRED"):
        recover_transaction(
            str(envelope.plan_core["transaction_id"]),
            "rollback",
            root=tmp_path,
            scanner=RecordingScanner([task_state]),
            scanner_context=approval,
        )
    result = recover_transaction(
        str(envelope.plan_core["transaction_id"]),
        "resume",
        root=tmp_path,
        scanner=RecordingScanner([task_state]),
        scanner_context=approval,
    )

    assert result["committed"] is True
    journal = read_json(
        tmp_path / f".agent-workflow/transactions/{envelope.plan_core['transaction_id']}.json"
    )
    assert journal["phase"] == "complete"
    assert not (tmp_path / ".agent-workflow/maintenance.json").exists()


def test_orphan_marker_never_authorizes_guessed_recovery(tmp_path: Path) -> None:
    control = tmp_path / ".agent-workflow"
    control.mkdir()
    (control / "maintenance.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RendererFailure, match="AWP_RECONCILE_RECOVERY_REQUIRED"):
        recover_transaction(
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "rollback",
            root=tmp_path,
        )


def test_rollback_removes_only_recorded_empty_created_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = tmp_path / ".agent-workflow"
    control.mkdir()
    record = staged(
        "generated/nested/config.txt", b"created\n", definition_id="config"
    )
    manifest = manifest_for(record)
    manifest["files"] = []
    manifest_bytes = canonical_json_bytes(manifest)
    (control / "manifest.json").write_bytes(manifest_bytes)
    os.chmod(control / "manifest.json", 0o644)
    observed = observed_for(record, "sync")
    observed["manifest_digest"] = hashlib.sha256(manifest_bytes).hexdigest()
    observed["files"] = {
        record.path: {"state": state(record.path, None), "content": None}
    }
    task_state = empty_task_state()
    envelope = plan_reconcile(
        ir_for("sync", record),
        StagedRenderTree((record,), "a" * 64),
        manifest,
        observed,
        task_state,
    )
    source_layout, target_layout, source_schemas, target_schemas = scanner_inputs()
    approval = {
        "plan_digest": envelope.plan_digest,
        "project_root": str(tmp_path),
        "source_layout": source_layout,
        "target_layout": target_layout,
        "source_schemas": source_schemas,
        "target_schemas": target_schemas,
    }

    def terminate(point: str) -> None:
        if point == "files_applied":
            raise InjectedTermination(point)

    monkeypatch.setattr(apply_module, "_crash_at", terminate)
    with pytest.raises(InjectedTermination):
        apply_plan(
            envelope,
            approval,
            scanner=RecordingScanner([task_state, task_state]),
        )
    recover_transaction(
        str(envelope.plan_core["transaction_id"]),
        "rollback",
        root=tmp_path,
        scanner=RecordingScanner([task_state]),
        scanner_context=approval,
    )

    assert not (tmp_path / "generated").exists()
