"""Pure SavedPlan construction over staged ownership evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from agent_stack.core.api import (
    DesiredStateIR,
    SavedPlanEnvelope,
    TaskSnapshotAndFindings,
    compute_candidate_manifest_digest,
    compute_journal_binding_digest,
    compute_plan_core_digest,
    compute_plan_digest,
    evaluate_task_gate,
    evaluate_workspace_state_quiescence,
)

from .errors import RendererFailure
from .models import StagedRenderTree
from .ownership import OwnershipPlan, plan_ownership


def _failure(code: str, message: str, **details: object) -> RendererFailure:
    return RendererFailure(code, message, details=details)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("AWP_OWNERSHIP_CONFLICT", "plan input object is invalid", field=field)
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _failure("AWP_OWNERSHIP_CONFLICT", "plan input array is invalid", field=field)
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "plan input string is invalid", field=field)
    return value


def _workspace_evaluation(ir: DesiredStateIR, task_state: TaskSnapshotAndFindings) -> Mapping[str, object]:
    evaluated = evaluate_workspace_state_quiescence(task_state.snapshot, task_state.findings)
    document: Mapping[str, object] = MappingProxyType(
        {
            "evaluator_id": evaluated.evaluator_id,
            "evaluator_version": evaluated.evaluator_version,
            "task_quiescence": evaluated.task_quiescence,
            "blockers": list(evaluated.evidence_kinds),
        }
    )
    if dict(document) != dict(ir.workspace_state_evaluation):
        raise _failure(
            "AWP_TASK_QUIESCENCE_CHANGED",
            "Resolver workspace-state evaluation differs from planning evidence",
        )
    return document


def _task_gate_evaluation(ir: DesiredStateIR, task_state: TaskSnapshotAndFindings) -> Mapping[str, object]:
    evaluated = evaluate_task_gate(
        ir.operation,
        ir.candidate_impact,
        task_state.snapshot,
        task_state.findings,
    )
    blockers = [
        {
            "code": blocker.code,
            "finding_id": blocker.finding_id,
            "task_id": blocker.task_id,
            "path": blocker.path,
            "surface_id": blocker.surface_id,
            "authority_id": blocker.authority_id,
        }
        for blocker in evaluated.blockers
    ]
    document: Mapping[str, object] = MappingProxyType(
        {
            "evaluator_id": evaluated.evaluator_id,
            "evaluator_version": evaluated.evaluator_version,
            "blockers": blockers,
            "primary_evaluator_blocker": evaluated.primary_evaluator_blocker,
        }
    )
    supplied = ir.task_gate_evaluation
    supplied_blockers = supplied.get("blockers")
    if supplied_blockers:
        first = _mapping(_sequence(supplied_blockers, "task gate blockers")[0], "task blocker")
        code = _string(first.get("code"), "task blocker code")
        raise _failure(code, "task gate blocks reconcile planning")
    if dict(document) != dict(supplied):
        raise _failure(
            "AWP_TASK_QUIESCENCE_CHANGED",
            "Resolver task-gate evaluation differs from planning evidence",
        )
    return document


def _authority_precondition(ir: DesiredStateIR) -> Mapping[str, object]:
    profile_id = ir.resolved_profile.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "resolved profile identity is missing")
    return MappingProxyType(
        {
            "kind": "manifest-authority",
            "profile": profile_id,
            "platforms": list(ir.selected_platforms),
        }
    )


def _file_preconditions(ownership: OwnershipPlan) -> list[Mapping[str, object]]:
    manifest_by_path = {
        str(record["path"]): record for record in ownership.manifest_file_records
    }
    result: list[Mapping[str, object]] = []
    for decision in ownership.decisions:
        path = str(decision["path"])
        candidate = ownership.candidate_contents.get(path)
        result.append(
            MappingProxyType(
                {
                    "kind": "file",
                    "path": path,
                    "ownership_decision": dict(decision),
                    "candidate_manifest_record": (
                        None
                        if path not in manifest_by_path
                        else dict(manifest_by_path[path])
                    ),
                    "candidate_content_utf8": (
                        None if candidate is None else candidate.decode("utf-8")
                    ),
                }
            )
        )
    return result


def _release(ir: DesiredStateIR) -> dict[str, str]:
    return {
        "release_id": _string(ir.release_contract.get("release_id"), "release_id"),
        "release_manifest_digest": _string(
            ir.release_contract.get("release_manifest_digest"),
            "release_manifest_digest",
        ),
    }


def _common_plan_core(
    ir: DesiredStateIR,
    ownership: OwnershipPlan,
    observed: Mapping[str, object],
    task_state: TaskSnapshotAndFindings,
) -> dict[str, object]:
    snapshot = task_state.snapshot
    preconditions = [_authority_precondition(ir), *_file_preconditions(ownership)]
    return {
        "operation": ir.operation,
        "transaction_id": _string(observed.get("transaction_id"), "transaction_id"),
        "candidate_release": _release(ir),
        "release_trust_policy_id": _string(
            ir.release_contract.get("release_trust_policy_id"),
            "release_trust_policy_id",
        ),
        "release_trust_policy_digest": _string(
            ir.release_contract.get("release_trust_policy_digest"),
            "release_trust_policy_digest",
        ),
        "profile_digest": _string(ir.authority_digests.get("profile"), "profile_digest"),
        "lock_digest": _string(ir.authority_digests.get("workflow-lock"), "lock_digest"),
        "artifact_bundle_digest": _string(
            ir.authority_digests.get("artifact-bundle"), "artifact_bundle_digest"
        ),
        "pack_version": _string(ir.release_contract.get("version"), "pack_version"),
        "source_trellis_task_layout_digest": _string(
            snapshot.get("source_layout_digest"), "source layout digest"
        ),
        "target_trellis_task_layout_digest": _string(
            snapshot.get("target_layout_digest"), "target layout digest"
        ),
        "source_schema_bundle_digest": _string(
            snapshot.get("source_schema_bundle_digest"), "source schema bundle digest"
        ),
        "target_schema_bundle_digest": _string(
            snapshot.get("target_schema_bundle_digest"), "target schema bundle digest"
        ),
        "task_quiescence_snapshot": dict(task_state.snapshot),
        "task_findings": dict(task_state.findings),
        "task_quiescence_digest": task_state.task_quiescence_digest,
        "candidate_impact": ir.candidate_impact.to_document(),
        "workspace_state_evaluation": dict(_workspace_evaluation(ir, task_state)),
        "task_gate_evaluation": dict(_task_gate_evaluation(ir, task_state)),
        "preconditions": [dict(item) for item in preconditions],
        "candidate_file_states": [
            state.to_document() for state in ownership.candidate_file_states
        ],
        "candidate_local_state_contract": dict(
            _mapping(
                observed.get("candidate_local_state_contract"),
                "candidate_local_state_contract",
            )
        ),
        "provider_approval_bindings": [
            dict(_mapping(item, "provider approval binding"))
            for item in _sequence(
                observed.get("provider_approval_bindings"),
                "provider_approval_bindings",
            )
        ],
        "recovery_runtime": dict(
            _mapping(observed.get("recovery_runtime"), "recovery_runtime")
        ),
        "candidate_manifest_generation": 1,
    }


def _manifest_files(plan_core: Mapping[str, object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for raw in _sequence(plan_core.get("preconditions"), "preconditions"):
        precondition = _mapping(raw, "precondition")
        if precondition.get("kind") != "file":
            continue
        raw_record = precondition.get("candidate_manifest_record")
        if raw_record is not None:
            records.append(dict(_mapping(raw_record, "candidate Manifest record")))
    return sorted(records, key=lambda item: str(item["path"]))


def _manifest_authority(plan_core: Mapping[str, object]) -> Mapping[str, object]:
    matches = [
        _mapping(item, "authority precondition")
        for item in _sequence(plan_core.get("preconditions"), "preconditions")
        if isinstance(item, Mapping) and item.get("kind") == "manifest-authority"
    ]
    if len(matches) != 1:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "plan lacks one Manifest authority projection")
    return matches[0]


def render_candidate_manifest(envelope: SavedPlanEnvelope) -> dict[str, object]:
    """Reconstruct the candidate Manifest from the forward-only plan envelope."""

    core = envelope.plan_core
    authority = _manifest_authority(core)
    candidate_release = _mapping(core.get("candidate_release"), "candidate release")
    operation = str(core.get("operation"))
    project_id = core.get("candidate_project_id" if operation == "init" else "project_id")
    previous_digest = "absent" if operation == "init" else core.get("manifest_digest")
    return {
        "schema_version": 1,
        "project_id": project_id,
        "generation": core.get("candidate_manifest_generation"),
        "pack_version": core.get("pack_version"),
        "release_id": candidate_release.get("release_id"),
        "release_manifest_digest": candidate_release.get("release_manifest_digest"),
        "release_trust_policy_id": core.get("release_trust_policy_id"),
        "release_trust_policy_digest": core.get("release_trust_policy_digest"),
        "profile": authority.get("profile"),
        "profile_digest": core.get("profile_digest"),
        "lock_digest": core.get("lock_digest"),
        "artifact_bundle_digest": core.get("artifact_bundle_digest"),
        "local_state_contract": dict(
            _mapping(core.get("candidate_local_state_contract"), "local state contract")
        ),
        "platforms": list(_sequence(authority.get("platforms"), "platforms")),
        "last_transaction_id": core.get("transaction_id"),
        "last_transaction_binding_digest": envelope.journal_binding_digest,
        "previous_manifest_digest": previous_digest,
        "files": _manifest_files(core),
    }


def plan_reconcile(
    ir: DesiredStateIR,
    staged: StagedRenderTree,
    manifest: Mapping[str, object] | None,
    observed: Mapping[str, object],
    task_snapshot: TaskSnapshotAndFindings,
) -> SavedPlanEnvelope:
    manifest_files: Sequence[Mapping[str, object]] = ()
    if manifest is not None:
        manifest_files = tuple(
            _mapping(item, "Manifest file")
            for item in _sequence(manifest.get("files"), "Manifest files")
        )
    observed_files = _mapping(observed.get("files"), "observed files")
    ownership = plan_ownership(
        staged,
        ir.artifact_definitions,
        manifest_files,
        observed_files,
        operation=ir.operation,
    )
    plan_core = _common_plan_core(ir, ownership, observed, task_snapshot)

    if ir.operation == "init":
        if manifest is not None:
            raise _failure("AWP_OWNERSHIP_CONFLICT", "init requires Manifest absence")
        plan_core.update(
            {
                "project_id_precondition": "absent",
                "candidate_project_id": _string(
                    observed.get("candidate_project_id"), "candidate_project_id"
                ),
                "workspace_instance_precondition": "absent",
                "candidate_workspace_instance_id": _string(
                    observed.get("candidate_workspace_instance_id"),
                    "candidate_workspace_instance_id",
                ),
                "manifest_precondition": "absent",
                "approval_replay_precondition": "absent",
                "empty_replay_ledger_candidate_digest": _string(
                    observed.get("empty_replay_ledger_candidate_digest"),
                    "empty_replay_ledger_candidate_digest",
                ),
                "target_path_digest": _string(
                    observed.get("target_path_digest"), "target_path_digest"
                ),
            }
        )
    else:
        if manifest is None:
            raise _failure("AWP_OWNERSHIP_CONFLICT", "existing operation requires Manifest")
        generation = manifest.get("generation")
        if not isinstance(generation, int) or isinstance(generation, bool):
            raise _failure("AWP_OWNERSHIP_CONFLICT", "Manifest generation is invalid")
        plan_core["candidate_manifest_generation"] = generation + 1
        plan_core.update(
            {
                "project_id": _string(manifest.get("project_id"), "project_id"),
                "workspace_instance_id": _string(
                    observed.get("workspace_instance_id"), "workspace_instance_id"
                ),
                "manifest_generation": generation,
                "manifest_digest": _string(
                    observed.get("manifest_digest"), "manifest_digest"
                ),
                "installed_release": {
                    "release_id": _string(manifest.get("release_id"), "installed release_id"),
                    "release_manifest_digest": _string(
                        manifest.get("release_manifest_digest"),
                        "installed release_manifest_digest",
                    ),
                },
            }
        )
        if ir.operation == "repair":
            repair_ids = [
                change.surface_id
                for change in ir.candidate_impact.surface_changes
                if change.change_kind == "repair"
            ]
            plan_core["repair_surface_ids"] = repair_ids
        if ir.operation == "upgrade":
            plan_core["compatibility_identity"] = _string(
                observed.get("compatibility_identity"), "compatibility_identity"
            )

    plan_core_digest = compute_plan_core_digest(plan_core)
    immutable_header: dict[str, object] = {
        "transaction_id": plan_core["transaction_id"],
        "operation": ir.operation,
        "plan_core_digest": plan_core_digest,
        "baseline_manifest_digest": (
            "absent" if ir.operation == "init" else plan_core["manifest_digest"]
        ),
        "candidate_manifest_generation": plan_core["candidate_manifest_generation"],
        "task_quiescence_digest": plan_core["task_quiescence_digest"],
        "recovery_runtime": plan_core["recovery_runtime"],
    }
    if ir.operation == "init":
        immutable_header.update(
            {
                "candidate_project_id": plan_core["candidate_project_id"],
                "candidate_workspace_instance_id": plan_core[
                    "candidate_workspace_instance_id"
                ],
            }
        )
    else:
        immutable_header.update(
            {
                "project_id": plan_core["project_id"],
                "workspace_instance_id": plan_core["workspace_instance_id"],
            }
        )
    journal_binding_digest = compute_journal_binding_digest(immutable_header)

    provisional = SavedPlanEnvelope(
        operation=ir.operation,
        plan_core=MappingProxyType(plan_core),
        plan_core_digest=plan_core_digest,
        immutable_header=MappingProxyType(immutable_header),
        journal_binding_digest=journal_binding_digest,
        candidate_manifest_digest="0" * 64,
        candidate_manifest_file_state=MappingProxyType({}),
        plan_digest="0" * 64,
    )
    candidate_manifest = render_candidate_manifest(provisional)
    candidate_manifest_digest = compute_candidate_manifest_digest(candidate_manifest)
    manifest_file_state: Mapping[str, object] = MappingProxyType(
        {
            "path": ".agent-workflow/manifest.json",
            "byte_hash": candidate_manifest_digest,
            "mode": "0644",
            "file_type": "regular",
            "non_symlink": True,
        }
    )
    projection = {
        "schema_id": "agent-workflow.saved-plan",
        "schema_version": 1,
        "operation": ir.operation,
        "plan_core": plan_core,
        "plan_core_digest": plan_core_digest,
        "immutable_header": immutable_header,
        "journal_binding_digest": journal_binding_digest,
        "candidate_manifest_digest": candidate_manifest_digest,
        "candidate_manifest_file_state": dict(manifest_file_state),
    }
    return SavedPlanEnvelope(
        operation=ir.operation,
        plan_core=MappingProxyType(plan_core),
        plan_core_digest=plan_core_digest,
        immutable_header=MappingProxyType(immutable_header),
        journal_binding_digest=journal_binding_digest,
        candidate_manifest_digest=candidate_manifest_digest,
        candidate_manifest_file_state=manifest_file_state,
        plan_digest=compute_plan_digest(projection),
    )
