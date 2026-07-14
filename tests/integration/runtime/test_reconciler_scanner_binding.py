from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

from agent_stack.core.api import canonical_json_bytes
from agent_stack.reconcile import apply as apply_module
from agent_stack.reconcile.api import apply_plan, plan_reconcile
from agent_stack.reconcile.errors import RendererFailure
from agent_stack.reconcile.models import StagedRenderTree
from agent_stack.reconcile.ports import TaskQuiescenceScannerPort
from agent_stack.runtime.scanner import NormativeTaskScanner
from tests.integration.reconcile.apply_helpers import read_json
from tests.unit.reconcile.test_ownership import staged, state
from tests.unit.reconcile.test_plan import ir_for, manifest_for, observed_for
from tests.unit.runtime.test_scanner import (
    discovery_schemas,
    verified_layout,
    write_integration,
)


def _case(root: Path, scanner: NormativeTaskScanner):
    control = root / ".agent-workflow"
    control.mkdir(parents=True)
    target = root / "generated/config.txt"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"before\n")
    record = staged("generated/config.txt", b"after\n", definition_id="config")
    manifest = manifest_for(record)
    manifest_bytes = canonical_json_bytes(manifest)
    (control / "manifest.json").write_bytes(manifest_bytes)
    observed = observed_for(record, "sync")
    observed["manifest_digest"] = hashlib.sha256(manifest_bytes).hexdigest()
    observed["files"] = {
        record.path: {"state": state(record.path, b"before\n"), "content": "before\n"}
    }
    layout = verified_layout()
    schemas = discovery_schemas()
    task_state = scanner(layout, layout, schemas, schemas)
    envelope = plan_reconcile(
        ir_for("sync", record),
        StagedRenderTree((record,), "a" * 64),
        manifest,
        observed,
        task_state,
    )
    approval = {
        "plan_digest": envelope.plan_digest,
        "project_root": str(root),
        "source_layout": layout,
        "target_layout": layout,
        "source_schemas": schemas,
        "target_schemas": schemas,
    }
    return envelope, approval


def test_normative_scanner_exactly_satisfies_renderer_port(tmp_path: Path) -> None:
    signature = inspect.signature(NormativeTaskScanner.__call__)
    assert tuple(signature.parameters) == (
        "self",
        "source_layout",
        "target_layout",
        "source_schemas",
        "target_schemas",
    )
    scanner: TaskQuiescenceScannerPort = NormativeTaskScanner(tmp_path)
    envelope, approval = _case(tmp_path, scanner)

    result = apply_plan(envelope, approval, scanner=scanner)

    assert result["committed"] is True
    assert read_json(tmp_path / ".agent-workflow/manifest.json")["generation"] == 3


def test_real_scanner_detects_commit_time_task_state_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = NormativeTaskScanner(tmp_path)
    envelope, approval = _case(tmp_path, scanner)

    def mutate_at(point: str) -> None:
        if point == "files_applied":
            write_integration(tmp_path, ".trellis/tasks/raced")

    monkeypatch.setattr(apply_module, "_crash_at", mutate_at)

    with pytest.raises(RendererFailure) as captured:
        apply_plan(envelope, approval, scanner=scanner)
    assert captured.value.code == "AWP_TASK_QUIESCENCE_CHANGED"


def test_renderer_calls_real_scanner_only_while_project_locks_are_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanner = NormativeTaskScanner(tmp_path)
    envelope, approval = _case(tmp_path, scanner)
    lock_state = {"held": False}
    original_locks = apply_module.acquire_project_locks
    original_call = NormativeTaskScanner.__call__

    def checked_call(self, *args, **kwargs):
        assert lock_state["held"] is True
        return original_call(self, *args, **kwargs)

    def checked_locks(root):
        context = original_locks(root)

        class CheckedContext:
            def __enter__(self):
                value = context.__enter__()
                lock_state["held"] = True
                return value

            def __exit__(self, *exc):
                lock_state["held"] = False
                return context.__exit__(*exc)

        return CheckedContext()

    monkeypatch.setattr(NormativeTaskScanner, "__call__", checked_call)
    monkeypatch.setattr(apply_module, "acquire_project_locks", checked_locks)

    apply_plan(envelope, approval, scanner=scanner)
