from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agent_stack.core.api import SchemaCatalog, canonical_json_bytes
from agent_stack.release.compatibility import (
    CompatibilityResult,
    LocalStateContract,
    RuntimeJournalReference,
)
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.scanner import NormativeTaskScanner
from agent_stack.runtime.workspace import migrate_workspace
from tests.integration.runtime.test_workspace_register import (
    PROJECT_ID,
    _caller,
    _manifest,
    _project,
)
from tests.unit.runtime.test_scanner import (
    TASK_ID,
    discovery_schemas,
    layout_document,
    verified_layout,
    write_integration,
)


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_ID = "44444444-4444-4444-8444-444444444444"
SOURCE_WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_RELEASE = "a" * 64
TARGET_RELEASE = "c" * 64
SOURCE_MANIFEST_DIGEST = "b" * 64
TARGET_MANIFEST_DIGEST = "d" * 64


def _release_contract(manifest: dict[str, object], layout) -> LocalStateContract:
    local = manifest["local_state_contract"]
    assert isinstance(local, dict)
    return LocalStateContract(
        contract_digest=str(local["contract_digest"]),
        trellis_task_layout_digest=layout.layout_digest,
        schema_versions={
            "manifest": 1,
            "workflow_lock": 1,
            "integration": 1,
            "task_transaction": 1,
            "workspace": int(local["workspace_schema"]),
            "approval_replay": int(local["approval_replay_schema"]),
            "task_outbox": int(local["task_outbox_schema"]),
        },
    )


def _target_manifest(layout) -> dict[str, object]:
    contract = {
        "release_id": TARGET_RELEASE,
        "release_version": "0.2.0",
        "workspace_schema": 1,
        "approval_replay_schema": 1,
        "task_outbox_schema": 1,
        "trellis_task_layout_digest": layout.layout_digest,
    }
    contract["contract_digest"] = hashlib.sha256(canonical_json_bytes(contract)).hexdigest()
    return {
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "generation": 2,
        "pack_version": "0.2.0",
        "release_id": TARGET_RELEASE,
        "release_manifest_digest": TARGET_MANIFEST_DIGEST,
        "local_state_contract": contract,
    }


def _edge(
    source_contract: LocalStateContract,
    target_contract: LocalStateContract,
) -> CompatibilityResult:
    edge = {
        "local_state_contracts": {
            "from": source_contract.contract_digest,
            "to": target_contract.contract_digest,
        },
        "trellis_task_layouts": {
            "from": source_contract.trellis_task_layout_digest,
            "to": target_contract.trellis_task_layout_digest,
        },
        "schema_transitions": {
            field: {
                "from": source_contract.schema_versions[field],
                "to": target_contract.schema_versions[field],
            }
            for field in source_contract.schema_versions
        },
        "migrations": [
            {"migration_id": "local-state-v1", "migration_digest": "f" * 64}
        ],
    }
    return CompatibilityResult(
        relationship="migration-required",
        edge_owner="target",
        edge=edge,
        target_local_state_contract_digest=target_contract.contract_digest,
        target_trellis_task_layout_digest=target_contract.trellis_task_layout_digest,
    )


def _registered_project(tmp_path: Path, *, source_layout=None):
    from agent_stack.runtime.workspace import register_workspace

    project = _project(tmp_path)
    layout = source_layout or verified_layout()
    manifest = _manifest(layout)
    register_workspace(
        project,
        manifest,
        _caller(tmp_path),
        trellis_task_layout=layout,
        bootstrap_lock_root=tmp_path / "bootstrap-locks",
        transaction_id="11111111-1111-4111-8111-111111111111",
        workspace_instance_id=SOURCE_WORKSPACE_ID,
        recovery_runtime=RuntimeJournalReference(
            "committed", SOURCE_RELEASE, SOURCE_MANIFEST_DIGEST
        ),
    )
    return project, manifest, layout


def _migration_inputs(tmp_path: Path, *, source_layout=None, target_layout=None):
    project, source_manifest, source = _registered_project(
        tmp_path, source_layout=source_layout
    )
    target = target_layout or source
    target_manifest = _target_manifest(target)
    source_contract = _release_contract(source_manifest, source)
    target_contract = _release_contract(target_manifest, target)
    schemas = discovery_schemas()
    scanner = NormativeTaskScanner(project)
    snapshot = scanner(source, target, schemas, schemas)
    return {
        "project": project,
        "source_manifest": source_manifest,
        "target_manifest": target_manifest,
        "source_layout": source,
        "target_layout": target,
        "source_contract": source_contract,
        "target_contract": target_contract,
        "schemas": schemas,
        "scanner": scanner,
        "snapshot": snapshot,
        "edge": _edge(source_contract, target_contract),
    }


def _migrate(inputs: dict[str, object], **overrides: object):
    arguments = {
        "project_root": inputs["project"],
        "source_contract": inputs["source_contract"],
        "target_contract": inputs["target_contract"],
        "compatibility": inputs["edge"],
        "snapshot": inputs["snapshot"],
        "target_manifest": inputs["target_manifest"],
        "source_layout": inputs["source_layout"],
        "target_layout": inputs["target_layout"],
        "source_schemas": inputs["schemas"],
        "target_schemas": inputs["schemas"],
        "scanner": inputs["scanner"],
        "transaction_id": MIGRATION_ID,
        "recovery_runtime": RuntimeJournalReference(
            "committed", TARGET_RELEASE, TARGET_MANIFEST_DIGEST
        ),
    }
    arguments.update(overrides)
    return migrate_workspace(**arguments)


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_workspace_migration_commits_local_state_only_and_binds_evaluators(
    tmp_path: Path,
) -> None:
    inputs = _migration_inputs(tmp_path)
    project = inputs["project"]
    assert isinstance(project, Path)
    manifest_before = canonical_json_bytes(inputs["target_manifest"])

    result = _migrate(inputs)

    workspace = _read(project / ".agent-workflow/local/workspace.json")
    replay = _read(project / ".agent-workflow/local/approval-replay.json")
    journal = _read(
        project / f".agent-workflow/local/workspace-transactions/{MIGRATION_ID}.json"
    )
    header = journal["immutable_header"]
    assert isinstance(header, dict)
    assert result.committed is True
    assert workspace["local_state_release_id"] == TARGET_RELEASE
    assert workspace["local_state_release_manifest_digest"] == TARGET_MANIFEST_DIGEST
    assert workspace["workspace_instance_id"] == SOURCE_WORKSPACE_ID
    assert replay["workspace_instance_id"] == SOURCE_WORKSPACE_ID
    assert journal["phase"] == "complete"
    assert header["task_quiescence_digest"] == inputs["snapshot"].task_quiescence_digest
    assert header["workspace_state_evaluation"]["task_quiescence"] == "quiescent"
    assert header["task_gate_evaluation"]["blockers"] == []
    assert header["workspace_diagnostic"]["command_admission"] == {
        "command": "workspace-migrate",
        "allowed": True,
        "blocker": None,
    }
    assert canonical_json_bytes(inputs["target_manifest"]) == manifest_before
    assert not (project / ".trellis").exists()
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.load_and_validate(journal) == journal


@pytest.mark.parametrize(
    ("relationship", "relationship_evidence", "expected"),
    [
        ("ahead", "verified", "AWP_WORKSPACE_CONTRACT_AHEAD"),
        ("diverged", "verified", "AWP_WORKSPACE_CONTRACT_DIVERGED"),
        ("missing", "missing", "AWP_WORKSPACE_SOURCE_METADATA_REQUIRED"),
        ("migration-required", "invalid", "AWP_SOURCE_RELEASE_VERIFICATION_FAILED"),
    ],
)
def test_non_migratable_relationships_fail_before_local_mutation(
    tmp_path: Path,
    relationship: str,
    relationship_evidence: str,
    expected: str,
) -> None:
    inputs = _migration_inputs(tmp_path)
    edge = inputs["edge"]
    assert isinstance(edge, CompatibilityResult)
    inputs["edge"] = CompatibilityResult(relationship, edge_owner=edge.edge_owner, edge=edge.edge)
    project = inputs["project"]
    assert isinstance(project, Path)
    before = (project / ".agent-workflow/local/workspace.json").read_bytes()

    with pytest.raises(RuntimeFailure) as captured:
        _migrate(inputs, relationship_evidence=relationship_evidence)
    assert captured.value.code == expected
    assert (project / ".agent-workflow/local/workspace.json").read_bytes() == before
    assert not (
        project / f".agent-workflow/local/workspace-transactions/{MIGRATION_ID}.json"
    ).exists()


def test_unsupported_discovery_and_strict_task_findings_block(tmp_path: Path) -> None:
    unsupported = _migration_inputs(tmp_path / "unsupported")
    with pytest.raises(RuntimeFailure) as captured:
        _migrate(unsupported, discovery_evidence="unsupported")
    assert captured.value.code == "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS"

    active = _migration_inputs(tmp_path / "active")
    project = active["project"]
    assert isinstance(project, Path)
    write_integration(project, ".trellis/tasks/active", task_id=TASK_ID)
    scanner = active["scanner"]
    assert isinstance(scanner, NormativeTaskScanner)
    active["snapshot"] = scanner(
        active["source_layout"],
        active["target_layout"],
        active["schemas"],
        active["schemas"],
    )
    with pytest.raises(RuntimeFailure) as captured:
        _migrate(active)
    assert captured.value.code == "AWP_WORKSPACE_ACTIVE_TASK_BLOCK"

    unfinished = _migration_inputs(tmp_path / "unfinished")
    project = unfinished["project"]
    assert isinstance(project, Path)
    journal_root = project / ".agent-workflow/task-transactions"
    journal_root.mkdir(parents=True)
    transaction_id = "77777777-7777-4777-8777-777777777777"
    (journal_root / f"{transaction_id}.json").write_text(
        json.dumps(
            {
                "schema_id": "agent-workflow.task-transaction",
                "schema_version": 1,
                "operation": "admit",
                "phase": "planned",
                "task_id": TASK_ID,
                "task_ref": ".trellis/tasks/pending",
            }
        ),
        encoding="utf-8",
    )
    scanner = unfinished["scanner"]
    assert isinstance(scanner, NormativeTaskScanner)
    unfinished["snapshot"] = scanner(
        unfinished["source_layout"],
        unfinished["target_layout"],
        unfinished["schemas"],
        unfinished["schemas"],
    )
    with pytest.raises(RuntimeFailure) as captured:
        _migrate(unfinished)
    assert captured.value.code == "AWP_WORKSPACE_TASK_RECOVERY_BLOCK"


def test_source_only_archive_is_stranded_when_target_layout_changes(tmp_path: Path) -> None:
    source = verified_layout()
    target_document = layout_document()
    target_document["active_root"] = ".trellis/work-items"
    target_document["archive_root"] = ".trellis/work-items/archive"
    target = verified_layout(target_document)
    inputs = _migration_inputs(tmp_path, source_layout=source, target_layout=target)
    project = inputs["project"]
    assert isinstance(project, Path)
    write_integration(
        project,
        ".trellis/tasks/archive/old",
        status="archived",
        task_ref=".trellis/tasks/old",
    )
    scanner = inputs["scanner"]
    assert isinstance(scanner, NormativeTaskScanner)
    inputs["snapshot"] = scanner(source, target, inputs["schemas"], inputs["schemas"])

    with pytest.raises(RuntimeFailure) as captured:
        _migrate(inputs)
    assert captured.value.code == "AWP_WORKSPACE_LAYOUT_STATE_STRANDED"


def test_external_task_change_before_workspace_commit_is_unconditional_stale_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_stack.runtime.workspace as workspace_module

    inputs = _migration_inputs(tmp_path)
    project = inputs["project"]
    assert isinstance(project, Path)

    def mutate(point: str) -> None:
        if point == "local_candidates_applied":
            write_integration(project, ".trellis/tasks/raced")

    monkeypatch.setattr(workspace_module, "_crash_at", mutate)

    with pytest.raises(RuntimeFailure) as captured:
        _migrate(inputs)
    assert captured.value.code == "AWP_TASK_QUIESCENCE_CHANGED"
    assert "AWP_WORKSPACE_ACTIVE_TASK_BLOCK" in captured.value.details[
        "secondary_diagnostics"
    ]
    workspace = _read(project / ".agent-workflow/local/workspace.json")
    assert workspace["local_state_release_id"] == SOURCE_RELEASE


def test_invalid_existing_replay_or_outbox_state_is_never_reset_empty(tmp_path: Path) -> None:
    inputs = _migration_inputs(tmp_path)
    project = inputs["project"]
    assert isinstance(project, Path)
    replay = project / ".agent-workflow/local/approval-replay.json"
    replay.write_text('{"corrupt":true}', encoding="utf-8")

    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED"):
        _migrate(inputs)
    assert replay.read_text(encoding="utf-8") == '{"corrupt":true}'

    inputs = _migration_inputs(tmp_path / "outbox")
    project = inputs["project"]
    assert isinstance(project, Path)
    outbox = project / ".agent-workflow/local/task-outbox"
    outbox.mkdir()
    (outbox / "unexpected.txt").write_text("not an item", encoding="utf-8")
    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED"):
        _migrate(inputs)
