from __future__ import annotations

from pathlib import Path

from agent_stack.reconcile.journal import build_lifecycle_journal
from agent_stack.reconcile.maintenance import build_maintenance_marker
from agent_stack.reconcile.models import LifecycleJournal
from agent_stack.reconcile.plan import render_candidate_manifest
from tests.integration.reconcile.apply_helpers import make_apply_case


def test_maintenance_binds_immutable_header_not_mutable_journal_phase(
    tmp_path: Path,
) -> None:
    envelope, _, _ = make_apply_case(tmp_path)
    journal = build_lifecycle_journal(
        envelope,
        render_candidate_manifest(envelope),
        file_records=(),
        created_directories=(),
    )
    marker = build_maintenance_marker(envelope)
    changed = {**journal, "phase": "applying", "diagnostics": [{"retry": 1}]}

    LifecycleJournal.from_document(journal)
    LifecycleJournal.from_document(changed)
    assert marker["journal_binding_digest"] == envelope.journal_binding_digest
    assert marker["plan_digest"] == envelope.plan_digest
