from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from agent_stack.core.api import (
    TaskSnapshotAndFindings,
    VerifiedDiscoverySchemas,
    VerifiedTrellisTaskLayout,
    canonical_json_bytes,
)
from agent_stack.reconcile.api import plan_reconcile
from agent_stack.reconcile.models import StagedRenderTree
from tests.unit.reconcile.test_ownership import staged, state
from tests.unit.reconcile.test_plan import (
    empty_task_state,
    ir_for,
    manifest_for,
    observed_for,
)


class RecordingScanner:
    def __init__(self, results: list[TaskSnapshotAndFindings]) -> None:
        self.results = results
        self.calls: list[tuple[object, object, object, object]] = []

    def __call__(self, source_layout, target_layout, source_schemas, target_schemas):
        self.calls.append((source_layout, target_layout, source_schemas, target_schemas))
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]


def scanner_inputs() -> tuple[
    VerifiedTrellisTaskLayout,
    VerifiedTrellisTaskLayout,
    VerifiedDiscoverySchemas,
    VerifiedDiscoverySchemas,
]:
    layout = VerifiedTrellisTaskLayout(
        adapter_id="trellis-v0.1",
        adapter_version="1.0.0",
        runtime_namespace=".trellis",
        active_root=".trellis/tasks",
        archive_root=".trellis/tasks/archive",
        metadata_contracts=(),
        task_transaction_root=".agent-workflow/task-transactions",
        normalized={},
        layout_digest="5" * 64,
    )
    schemas = VerifiedDiscoverySchemas("6" * 64, {})
    return layout, layout, schemas, schemas


def make_apply_case(root: Path, *, after: bytes = b"after\n"):
    control = root / ".agent-workflow"
    control.mkdir(parents=True)
    target = root / "generated/config.txt"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"before\n")
    os.chmod(target, 0o644)
    record = staged("generated/config.txt", after, definition_id="config")
    manifest = manifest_for(record)
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_path = control / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    os.chmod(manifest_path, 0o644)
    observed = observed_for(record, "sync")
    observed["manifest_digest"] = hashlib.sha256(manifest_bytes).hexdigest()
    observed["files"] = {
        record.path: {"state": state(record.path, b"before\n"), "content": "before\n"}
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
        "project_root": str(root),
        "source_layout": source_layout,
        "target_layout": target_layout,
        "source_schemas": source_schemas,
        "target_schemas": target_schemas,
    }
    return envelope, task_state, approval


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
