from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from agent_stack.core.api import (
    VerifiedDiscoverySchemas,
    evaluate_workspace_state_quiescence,
    validate_trellis_layout,
)
from agent_stack.core.canonical import canonical_json_bytes, digest
from agent_stack.runtime.scanner import NormativeTaskScanner


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "runtime" / "trellis_layouts"
TASK_ID = "5f477c7f-a1dc-4a16-8f75-39f153170222"
SECOND_TASK_ID = "6ea415f2-3823-4a36-9d25-cf00b82f1f70"


def layout_document() -> dict[str, object]:
    return json.loads((FIXTURES / "layout.json").read_text(encoding="utf-8"))


def verified_layout(document: dict[str, object] | None = None):
    return validate_trellis_layout(document or layout_document(), source_roots=("src",))


def discovery_schemas() -> VerifiedDiscoverySchemas:
    normalized = json.loads(
        (FIXTURES / "discovery-schemas.json").read_text(encoding="utf-8")
    )
    return VerifiedDiscoverySchemas(
        hashlib.sha256(canonical_json_bytes(normalized)).hexdigest(), normalized
    )


def integration_document(
    *,
    task_id: str = TASK_ID,
    task_ref: str = ".trellis/tasks/example",
    status: str = "active",
    revision: int = 2,
    mode: str = "trellis-native",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": mode,
        "workflow_contract": {
            "version": 1,
            "profile_digest_at_admission": "1" * 64,
            "lock_digest_at_admission": "2" * 64,
            "artifact_bundle_digest_at_admission": "3" * 64,
            "policy_digest_at_admission": "4" * 64,
            "adapter_id": "codex",
            "adapter_version_at_admission": "1.0.0",
            "route_contract_version": 1,
            "task_contract_surfaces": [
                {"surface_id": "adapter:codex", "surface_digest": "5" * 64},
                {"surface_id": "runtime-control-plane", "surface_digest": "6" * 64},
            ],
        },
        "lifecycle": {"status": status, "state_revision": revision},
        "admission": {"task_id": task_id, "task_ref": task_ref},
    }


def write_integration(
    root: Path,
    relative: str,
    *,
    task_id: str = TASK_ID,
    status: str = "active",
    task_ref: str | None = None,
) -> Path:
    task = root / relative
    task.mkdir(parents=True)
    document = integration_document(
        task_id=task_id,
        task_ref=task_ref or relative,
        status=status,
    )
    path = task / "integration.yaml"
    path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    os.chmod(path, 0o640)
    return path


def scan(root: Path, source=None, target=None):
    source_layout = source or verified_layout()
    target_layout = target or source_layout
    schemas = discovery_schemas()
    return NormativeTaskScanner(root)(source_layout, target_layout, schemas, schemas)


def finding_kinds(result) -> list[str]:
    return [str(item["kind"]) for item in result.findings["findings"]]


def test_empty_missing_roots_are_canonical_quiescent(tmp_path: Path) -> None:
    result = scan(tmp_path)

    assert result.snapshot["tasks"] == []
    assert result.snapshot["metadata"] == []
    assert result.snapshot["task_journals"] == []
    assert result.snapshot["finding_ids"] == []
    assert result.task_quiescence_digest == result.snapshot["task_quiescence_digest"]
    state = evaluate_workspace_state_quiescence(result.snapshot, result.findings)
    assert state.task_quiescence == "quiescent"


def test_recognizes_task_and_recomputes_contract_digest(tmp_path: Path) -> None:
    integration = write_integration(tmp_path, ".trellis/tasks/example")

    result = scan(tmp_path)

    assert finding_kinds(result) == ["non-archived-task"]
    task = result.snapshot["tasks"][0]
    document = json.loads(integration.read_text(encoding="utf-8"))
    assert task["task_id"] == TASK_ID
    assert task["current_path"] == ".trellis/tasks/example"
    assert task["source_role"] == "active"
    assert task["target_role"] == "active"
    assert task["integration_mode"] == "0640"
    assert task["task_contract_surfaces"] == document["workflow_contract"][
        "task_contract_surfaces"
    ]
    assert task["task_contract_digest"] == digest(
        "agent-workflow.task-contract.v1", document["workflow_contract"]
    )


def test_source_target_union_reports_one_sided_task_state(tmp_path: Path) -> None:
    write_integration(
        tmp_path,
        ".trellis/tasks/archive/old",
        task_id=TASK_ID,
        status="archived",
        task_ref=".trellis/tasks/old",
    )
    write_integration(
        tmp_path,
        ".trellis/work-items/new",
        task_id=SECOND_TASK_ID,
        status="active",
        task_ref=".trellis/work-items/new",
    )
    target_document = layout_document()
    target_document["active_root"] = ".trellis/work-items"
    target_document["archive_root"] = ".trellis/work-items/archive"
    target = verified_layout(target_document)

    result = scan(tmp_path, verified_layout(), target)

    tasks = {task["task_id"]: task for task in result.snapshot["tasks"]}
    assert tasks[TASK_ID]["source_role"] == "archive"
    assert tasks[TASK_ID]["target_role"] == "absent"
    assert tasks[SECOND_TASK_ID]["source_role"] == "absent"
    assert tasks[SECOND_TASK_ID]["target_role"] == "active"
    assert finding_kinds(result).count("layout-state-stranded") == 2
    assert "non-archived-task" in finding_kinds(result)


def test_missing_integration_unknown_entry_and_aliases_remain_visible(tmp_path: Path) -> None:
    active = tmp_path / ".trellis/tasks"
    (active / "missing").mkdir(parents=True)
    (active / "rogue.txt").write_text("visible", encoding="utf-8")
    write_integration(tmp_path, ".trellis/tasks/Task", task_id=TASK_ID)
    write_integration(tmp_path, ".trellis/tasks/task", task_id=SECOND_TASK_ID)

    result = scan(tmp_path)

    kinds = finding_kinds(result)
    assert "layout-ambiguous" in kinds
    assert "unknown-entry" in kinds
    assert "collision" in kinds


def test_metadata_parsers_classifiers_and_journal_phase_table(tmp_path: Path) -> None:
    active = tmp_path / ".trellis/active.json"
    active.parent.mkdir(parents=True)
    active.write_text(
        json.dumps(
            {
                "schema_id": "trellis.active-pointer",
                "schema_version": 1,
                "task_ref": ".trellis/tasks/example",
            }
        ),
        encoding="utf-8",
    )
    session_id = "7bf2518a-96cb-4857-9fce-70d724f13653"
    sessions = tmp_path / ".trellis/sessions"
    sessions.mkdir()
    (sessions / f"{session_id}.json").write_text(
        json.dumps(
            {
                "schema_id": "trellis.session-journal",
                "schema_version": 1,
                "task_ref": ".trellis/tasks/example",
            }
        ),
        encoding="utf-8",
    )
    journals = tmp_path / ".agent-workflow/task-transactions"
    journals.mkdir(parents=True)
    unfinished_id = "2383ca7d-23d0-4f3c-b3bb-cba9439302fc"
    complete_id = "b5652e12-68d4-4901-b62a-324974e681d4"
    for transaction_id, phase in ((unfinished_id, "planned"), (complete_id, "complete")):
        (journals / f"{transaction_id}.json").write_text(
            json.dumps(
                {
                    "schema_id": "agent-workflow.task-transaction",
                    "schema_version": 1,
                    "operation": "admit",
                    "phase": phase,
                    "task_id": TASK_ID,
                    "task_ref": ".trellis/tasks/example",
                }
            ),
            encoding="utf-8",
        )

    result = scan(tmp_path)

    metadata = {item["path"]: item for item in result.snapshot["metadata"]}
    assert metadata[".trellis/active.json"]["classification"] == "nonempty"
    assert metadata[".trellis/active.json"]["parsed_task_refs"] == [
        ".trellis/tasks/example"
    ]
    assert len(result.snapshot["task_journals"]) == 2
    assert sum(not item["terminal"] for item in result.snapshot["task_journals"]) == 1
    assert finding_kinds(result) == ["unfinished-task-transaction"]


def test_duplicate_task_uuid_and_journal_disagreement_are_conflicts(tmp_path: Path) -> None:
    write_integration(tmp_path, ".trellis/tasks/one", task_id=TASK_ID)
    write_integration(tmp_path, ".trellis/tasks/two", task_id=TASK_ID)
    journals = tmp_path / ".agent-workflow/task-transactions"
    journals.mkdir(parents=True)
    transaction_id = str(uuid.uuid4())
    (journals / f"{transaction_id}.json").write_text(
        json.dumps(
            {
                "schema_id": "agent-workflow.task-transaction",
                "schema_version": 1,
                "operation": "claim",
                "phase": "planned",
                "task_id": TASK_ID,
                "task_ref": ".trellis/tasks/different",
            }
        ),
        encoding="utf-8",
    )

    result = scan(tmp_path)

    conflicts = [
        item for item in result.findings["findings"] if item["kind"] == "interpretation-conflict"
    ]
    assert conflicts
    assert {field for item in conflicts for field in item["conflicting_fields"]} >= {
        "task_id",
        "task_ref",
    }


def test_invalid_schema_symlink_wrong_type_and_oversize_are_ambiguous(tmp_path: Path) -> None:
    active = tmp_path / ".trellis/tasks"
    active.mkdir(parents=True)
    bad = active / "bad"
    bad.mkdir()
    (bad / "integration.yaml").write_text("schema_version: 99\n", encoding="utf-8")
    linked = active / "linked"
    linked.mkdir()
    (linked / "integration.yaml").symlink_to(bad / "integration.yaml")
    wrong = tmp_path / ".trellis/sessions"
    wrong.write_text("not a directory", encoding="utf-8")
    layout = layout_document()
    layout["task_discovery"]["max_integration_bytes"] = 8

    result = scan(tmp_path, verified_layout(layout), verified_layout(layout))

    assert finding_kinds(result).count("layout-ambiguous") >= 3


def test_snapshot_and_findings_are_stably_sorted(tmp_path: Path) -> None:
    write_integration(tmp_path, ".trellis/tasks/zeta", task_id=SECOND_TASK_ID)
    write_integration(tmp_path, ".trellis/tasks/alpha", task_id=TASK_ID)

    first = scan(tmp_path)
    second = scan(tmp_path)

    assert canonical_json_bytes(first.snapshot) == canonical_json_bytes(second.snapshot)
    assert canonical_json_bytes(first.findings) == canonical_json_bytes(second.findings)
    assert first.snapshot["finding_ids"] == sorted(first.snapshot["finding_ids"])
    assert [task["current_path"] for task in first.snapshot["tasks"]] == sorted(
        task["current_path"] for task in first.snapshot["tasks"]
    )
