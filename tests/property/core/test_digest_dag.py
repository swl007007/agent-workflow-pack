from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.core.saved_plan import (
    compute_journal_binding_digest,
    compute_plan_core_digest,
)
from tests.unit.core.test_saved_plan import _plan_core


@given(st.text(min_size=1, max_size=24))
def test_plan_core_changes_flow_forward_without_a_reverse_digest_edge(pack_version: str) -> None:
    original = _plan_core("sync")
    changed = _plan_core("sync")
    changed["pack_version"] = pack_version

    original_core_digest = compute_plan_core_digest(original)
    changed_core_digest = compute_plan_core_digest(changed)
    original_header = {
        "transaction_id": original["transaction_id"],
        "operation": "sync",
        "project_id": original["project_id"],
        "workspace_instance_id": original["workspace_instance_id"],
        "plan_core_digest": original_core_digest,
        "baseline_manifest_digest": original["manifest_digest"],
        "candidate_manifest_generation": original["candidate_manifest_generation"],
        "task_quiescence_digest": original["task_quiescence_digest"],
        "recovery_runtime": original["recovery_runtime"],
    }
    changed_header = {**original_header, "plan_core_digest": changed_core_digest}

    if pack_version != original["pack_version"]:
        assert original_core_digest != changed_core_digest
        assert compute_journal_binding_digest(original_header) != compute_journal_binding_digest(
            changed_header
        )
