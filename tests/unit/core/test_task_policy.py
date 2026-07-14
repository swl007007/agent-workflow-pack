from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from agent_stack.core.canonical import CANONICAL_NULL, digest
from agent_stack.core.diagnostics import build_workspace_diagnostic
from agent_stack.core.errors import CoreFailure
from agent_stack.core.impact import CandidateImpact, compute_candidate_impact
from agent_stack.core.schema_catalog import SchemaCatalog
from agent_stack.core.task_policy import (
    evaluate_task_gate,
    evaluate_workspace_state_quiescence,
)


ROOT = Path(__file__).resolve().parents[3]
TASK_ID = "11111111-1111-4111-8111-111111111111"
SECOND_TASK_ID = "22222222-2222-4222-8222-222222222222"


def _task(
    *,
    task_id: str = TASK_ID,
    mode: str = "trellis-native",
    status: str = "active",
    surface_id: str = "skill:tdd",
    surface_digest: str = "c" * 64,
) -> dict[str, object]:
    return {
        "task_id": task_id,
        "admission_task_ref": f"task-{task_id[:8]}",
        "current_path": f".trellis/tasks/task-{task_id[:8]}",
        "source_role": "active",
        "target_role": "active",
        "integration_byte_hash": "a" * 64,
        "integration_mode": "0644",
        "integration_schema_id": "agent-workflow.task-integration",
        "integration_schema_version": 1,
        "lifecycle_status": status,
        "revision": 3,
        "mode": mode,
        "task_contract_digest": "b" * 64,
        "task_contract_surfaces": [
            {"surface_id": surface_id, "surface_digest": surface_digest}
        ],
    }


def _non_archived_finding(task: Mapping[str, object], finding_id: str) -> dict[str, object]:
    return {
        "kind": "non-archived-task",
        "finding_id": finding_id,
        "task_id": task["task_id"],
        "current_path": task["current_path"],
        "lifecycle_status": task["lifecycle_status"],
        "mode": task["mode"],
        "pinned_surfaces": task["task_contract_surfaces"],
    }


def _unfinished_finding(finding_id: str = "f-journal") -> dict[str, object]:
    return {
        "kind": "unfinished-task-transaction",
        "finding_id": finding_id,
        "journal_path": ".agent-workflow/task-transactions/tx-1.json",
        "task_id": TASK_ID,
        "task_ref": "task-11111111",
        "operation": "admit",
        "phase": "metadata_applied",
    }


def _ambiguous_finding(finding_id: str = "f-ambiguous") -> dict[str, object]:
    return {
        "kind": "layout-ambiguous",
        "finding_id": finding_id,
        "normalized_path": ".trellis/tasks",
        "evidence_class": "unsupported-parser",
        "parser_id": "legacy-index-v1",
        "parser_version": 1,
        "evidence_schema_id": "agent-workflow.legacy-index",
        "evidence_schema_version": 1,
    }


def _stranded_finding(finding_id: str = "f-stranded") -> dict[str, object]:
    return {
        "kind": "layout-state-stranded",
        "finding_id": finding_id,
        "normalized_path": ".trellis/tasks/archive/legacy",
        "semantic_role": "archive",
        "source_visibility": "recognized",
        "target_visibility": "unrecognized",
    }


def _snapshot(
    findings: Sequence[Mapping[str, object]] = (),
    tasks: Sequence[Mapping[str, object]] = (),
) -> tuple[dict[str, object], dict[str, object]]:
    journals = []
    for finding in findings:
        if finding["kind"] == "unfinished-task-transaction":
            journals.append(
                {
                    "journal_path": finding["journal_path"],
                    "byte_hash": "d" * 64,
                    "mode": "0644",
                    "schema_id": "agent-workflow.task-transaction",
                    "schema_version": 1,
                    "operation": finding["operation"],
                    "phase": finding["phase"],
                    "task_id": finding["task_id"],
                    "task_ref": finding["task_ref"],
                    "terminal": False,
                }
            )
    projection: dict[str, object] = {
        "schema_id": "agent-workflow.task-quiescence-snapshot",
        "schema_version": 1,
        "source_layout_digest": "1" * 64,
        "target_layout_digest": "2" * 64,
        "source_schema_bundle_digest": "3" * 64,
        "target_schema_bundle_digest": "4" * 64,
        "tasks": list(tasks),
        "metadata": [],
        "task_journals": journals,
        "finding_ids": sorted(str(finding["finding_id"]) for finding in findings),
    }
    projection["task_quiescence_digest"] = digest(
        "agent-workflow.task-quiescence.v1", projection
    )
    findings_document = {
        "schema_id": "agent-workflow.task-findings",
        "schema_version": 1,
        "findings": list(findings),
    }
    return projection, findings_document


def _impact(
    *,
    operation: str = "sync",
    before: Mapping[str, str] | None = None,
    observed: Mapping[str, str] | None = None,
    after: Mapping[str, str] | None = None,
    authority_change: bool = False,
    repair_surface_ids: Sequence[str] = (),
) -> CandidateImpact:
    before = dict(before or {})
    observed = dict(observed if observed is not None else before)
    after = dict(after if after is not None else before)
    authorities = {
        authority_id: "a" * 64
        for authority_id in (
            "release-identity",
            "profile",
            "workflow-lock",
            "artifact-bundle",
            "route-policy",
            "router-contract",
            "surface-registry",
            "trellis-layout",
        )
    }
    candidate_authorities = dict(authorities)
    if authority_change:
        candidate_authorities["release-identity"] = "f" * 64
    return compute_candidate_impact(
        {
            "authority_digests": authorities,
            "surface_digests": before,
            "registry_graph_digest": "e" * 64,
        },
        {"surface_digests": observed, "unclassified_runtime_units": []},
        {
            "operation": operation,
            "authority_digests": candidate_authorities,
            "surface_digests": after,
            "registry_graph_digest": "e" * 64,
            "repair_surface_ids": list(repair_surface_ids),
        },
    )


@pytest.mark.parametrize(
    ("findings", "tasks", "expected"),
    [
        ([], [], "quiescent"),
        ([_ambiguous_finding()], [], "ambiguous"),
        ([_unfinished_finding()], [], "blocked"),
        (
            [_non_archived_finding(_task(), "f-task")],
            [_task()],
            "blocked",
        ),
        ([_stranded_finding()], [], "blocked"),
    ],
)
def test_fixed_workspace_evaluator_uses_only_verified_facts(
    findings: list[dict[str, object]],
    tasks: list[dict[str, object]],
    expected: str,
) -> None:
    snapshot, findings_document = _snapshot(findings, tasks)

    state = evaluate_workspace_state_quiescence(snapshot, findings_document)

    assert state.evaluator_id == "agent-workflow.workspace-state-quiescence"
    assert state.evaluator_version == 1
    assert state.task_quiescence == expected


def test_snapshot_digest_and_finding_identity_are_revalidated() -> None:
    snapshot, findings_document = _snapshot([_ambiguous_finding()])
    snapshot["task_quiescence_digest"] = "0" * 64

    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        evaluate_workspace_state_quiescence(snapshot, findings_document)


def test_workspace_migration_returns_every_blocker_in_policy_order() -> None:
    task = _task(status="completed")
    findings = [
        _stranded_finding(),
        _non_archived_finding(task, "f-task"),
        _unfinished_finding(),
        _ambiguous_finding(),
    ]
    snapshot, findings_document = _snapshot(findings, [task])

    result = evaluate_task_gate(
        "workspace-migrate", _impact(), snapshot, findings_document
    )

    assert [blocker.code for blocker in result.blockers] == [
        "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS",
        "AWP_WORKSPACE_TASK_RECOVERY_BLOCK",
        "AWP_WORKSPACE_ACTIVE_TASK_BLOCK",
        "AWP_WORKSPACE_LAYOUT_STATE_STRANDED",
    ]
    assert result.primary_evaluator_blocker == "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS"


def test_upgrade_blocks_heavy_and_only_affected_native_tasks() -> None:
    heavy = _task(task_id=TASK_ID, mode="speckit-superpowers", surface_id="skill:other")
    affected = _task(task_id=SECOND_TASK_ID, surface_id="skill:tdd")
    unaffected = _task(
        task_id="33333333-3333-4333-8333-333333333333", surface_id="skill:other"
    )
    tasks = [heavy, affected, unaffected]
    findings = [
        _non_archived_finding(task, f"f-{index}") for index, task in enumerate(tasks)
    ]
    snapshot, findings_document = _snapshot(findings, tasks)
    impact = _impact(
        operation="upgrade",
        before={"skill:tdd": "c" * 64, "skill:other": "d" * 64},
        after={"skill:tdd": "f" * 64, "skill:other": "d" * 64},
        authority_change=True,
    )

    result = evaluate_task_gate("upgrade", impact, snapshot, findings_document)

    assert [blocker.task_id for blocker in result.blockers] == [TASK_ID, SECOND_TASK_ID]


def test_pinned_surface_mismatch_fails_closed_before_affected_task_policy() -> None:
    task = _task(surface_digest="9" * 64)
    finding = _non_archived_finding(task, "f-task")
    snapshot, findings_document = _snapshot([finding], [task])
    impact = _impact(
        before={"skill:tdd": "c" * 64}, after={"skill:tdd": "f" * 64}
    )

    result = evaluate_task_gate("sync", impact, snapshot, findings_document)

    assert result.primary_evaluator_blocker == "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS"


def test_restorative_repair_of_a_pinned_surface_is_admitted() -> None:
    task = _task(surface_digest="c" * 64)
    finding = _non_archived_finding(task, "f-task")
    snapshot, findings_document = _snapshot([finding], [task])
    impact = _impact(
        operation="repair",
        before={"skill:tdd": "c" * 64},
        observed={"skill:tdd": CANONICAL_NULL},
        after={"skill:tdd": "c" * 64},
        repair_surface_ids=["skill:tdd"],
    )

    result = evaluate_task_gate("repair", impact, snapshot, findings_document)

    assert result.blockers == ()
    assert result.primary_evaluator_blocker is None


def test_true_no_op_sync_does_not_turn_active_task_facts_into_a_blocker() -> None:
    task = _task()
    finding = _non_archived_finding(task, "f-task")
    snapshot, findings_document = _snapshot([finding], [task])

    result = evaluate_task_gate("sync", _impact(), snapshot, findings_document)

    assert result.blockers == ()


def test_workspace_diagnostic_separates_state_from_command_admission() -> None:
    snapshot, findings_document = _snapshot()
    state = evaluate_workspace_state_quiescence(snapshot, findings_document)
    gate = evaluate_task_gate("workspace-migrate", _impact(), snapshot, findings_document)

    diagnostic = build_workspace_diagnostic(
        command="workspace-migrate",
        relationship="migration-required",
        relationship_evidence="verified",
        discovery_evidence="verified",
        workspace_task_state=state,
        task_gate_result=gate,
    )

    assert diagnostic.workspace_state.primary_state_blocker == "AWP_WORKSPACE_MIGRATION_REQUIRED"
    assert diagnostic.command_admission.allowed is True
    assert diagnostic.command_admission.blocker is None


def test_relationship_evidence_precedence_is_independent_of_discovery() -> None:
    snapshot, findings_document = _snapshot()
    state = evaluate_workspace_state_quiescence(snapshot, findings_document)
    gate = evaluate_task_gate("workspace-migrate", _impact(), snapshot, findings_document)

    ahead = build_workspace_diagnostic(
        command="doctor",
        relationship="ahead",
        relationship_evidence="verified",
        discovery_evidence="unsupported",
        workspace_task_state=state,
        task_gate_result=gate,
    )
    invalid = build_workspace_diagnostic(
        command="doctor",
        relationship="migration-required",
        relationship_evidence="invalid",
        discovery_evidence="verified",
        workspace_task_state=state,
        task_gate_result=gate,
    )

    assert ahead.workspace_state.primary_state_blocker == "AWP_WORKSPACE_CONTRACT_AHEAD"
    assert invalid.workspace_state.relationship == "unknown"
    assert invalid.workspace_state.primary_state_blocker == (
        "AWP_SOURCE_RELEASE_VERIFICATION_FAILED"
    )
    assert invalid.command_admission.allowed is True


def test_task_and_workspace_schemas_are_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.supported_versions("agent-workflow.task-quiescence-snapshot") == (1,)
    assert catalog.supported_versions("agent-workflow.task-findings") == (1,)
    assert catalog.supported_versions("agent-workflow.workspace-diagnostic") == (1,)

    snapshot, findings_document = _snapshot()
    catalog.load_and_validate(snapshot)
    catalog.load_and_validate(findings_document)
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**findings_document, "unknown": True})
