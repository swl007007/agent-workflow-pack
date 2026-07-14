from __future__ import annotations

from pathlib import Path

from agent_stack.core.api import SchemaCatalog, digest


ROOT = Path(__file__).resolve().parents[3]


def _journal(phase: str = "planned") -> dict[str, object]:
    immutable_header = {
        "transaction_id": "11111111-1111-4111-8111-111111111111",
        "operation": "sync",
        "project_id": "22222222-2222-4222-8222-222222222222",
        "workspace_instance_id": "33333333-3333-4333-8333-333333333333",
        "plan_core_digest": "a" * 64,
        "task_quiescence_digest": "b" * 64,
        "baseline_manifest_digest": "c" * 64,
        "candidate_manifest_generation": 2,
        "recovery_runtime": {
            "runtime_role": "committed",
            "release_id": "d" * 64,
            "release_manifest_digest": "e" * 64,
        },
    }
    return {
        "schema_id": "agent-workflow.lifecycle-transaction",
        "schema_version": 1,
        "immutable_header": immutable_header,
        "journal_binding_digest": digest(
            "agent-workflow.lifecycle-transaction.v1", immutable_header
        ),
        "task_quiescence_snapshot": {},
        "plan_digest": "f" * 64,
        "candidate_manifest_digest": "1" * 64,
        "candidate_manifest": {},
        "phase": phase,
        "file_records": [],
        "created_directories": [],
        "diagnostics": [],
        "rollback_state": {},
    }


def test_journal_schema_separates_immutable_header_from_mutable_phase() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    first = catalog.load_and_validate(_journal("planned"))
    second = catalog.load_and_validate(_journal("files_applied"))
    assert first["immutable_header"] == second["immutable_header"]
    assert first["journal_binding_digest"] == second["journal_binding_digest"]
    assert first["phase"] != second["phase"]


def test_lifecycle_journal_model_rejects_binding_drift() -> None:
    from agent_stack.reconcile.errors import RendererFailure
    from agent_stack.reconcile.models import LifecycleJournal

    document = _journal()
    document["journal_binding_digest"] = "0" * 64
    try:
        LifecycleJournal.from_document(document)
    except RendererFailure as error:
        assert error.code == "AWP_RECONCILE_RECOVERY_REQUIRED"
    else:
        raise AssertionError("journal binding drift was accepted")
