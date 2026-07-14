from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from agent_stack.core.api import CandidateImpact, canonical_json_bytes
from agent_stack.core.impact import SurfaceChange
from agent_stack.reconcile.api import apply_plan, plan_reconcile
from agent_stack.reconcile.models import StagedRenderTree
from agent_stack.reconcile.repair import validate_repair_selection
from tests.integration.reconcile.apply_helpers import (
    RecordingScanner,
    scanner_inputs,
)
from tests.unit.reconcile.test_ownership import staged, state
from tests.unit.reconcile.test_plan import (
    empty_task_state,
    ir_for,
    manifest_for,
    observed_for,
)


def test_restorative_repair_uses_observed_drift_as_cas_preimage(tmp_path: Path) -> None:
    control = tmp_path / ".agent-workflow"
    control.mkdir()
    target = tmp_path / "generated/config.txt"
    target.parent.mkdir()
    target.write_bytes(b"drifted\n")
    os.chmod(target, 0o600)
    record = staged("generated/config.txt", b"before\n", definition_id="config")
    expected_surface = "4" * 64
    repair_impact = CandidateImpact(
        "runtime-visible",
        (),
        (
            SurfaceChange(
                record.surface_id,
                "repair",
                expected_surface,
                "canonical-null",
                expected_surface,
            ),
        ),
        False,
        "8" * 64,
    )
    ir = replace(
        ir_for("repair", record),
        candidate_impact=repair_impact,
        surface_digests=MappingProxyType({record.surface_id: expected_surface}),
    )
    manifest = manifest_for(record)
    manifest_bytes = canonical_json_bytes(manifest)
    (control / "manifest.json").write_bytes(manifest_bytes)
    os.chmod(control / "manifest.json", 0o644)
    observed = observed_for(record, "repair")
    observed["manifest_digest"] = hashlib.sha256(manifest_bytes).hexdigest()
    observed["files"] = {
        record.path: {
            "state": state(record.path, b"drifted\n", mode="0600"),
            "content": "drifted\n",
        }
    }
    task_state = empty_task_state()
    validate_repair_selection(
        repair_impact,
        selected_surface_ids=[record.surface_id],
        pinned_surface_digests={},
        registry_graph_before_digest="7" * 64,
        registry_graph_after_digest="7" * 64,
    )
    envelope = plan_reconcile(
        ir,
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

    result = apply_plan(
        envelope,
        approval,
        scanner=RecordingScanner([task_state, task_state]),
    )

    assert result["committed"] is True
    assert target.read_bytes() == b"before\n"
    assert target.stat().st_mode & 0o777 == 0o644
