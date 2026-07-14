"""Acyclic SavedPlan digest primitives and closed operation validation."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .canonical import canonical_json_bytes, digest, normalize_mode, normalize_path
from .errors import CoreFailure


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_OPERATIONS = frozenset({"init", "sync", "repair", "upgrade"})
_DERIVED_PLAN_FIELDS = frozenset(
    {
        "plan_core_digest",
        "journal_binding_digest",
        "candidate_manifest",
        "candidate_manifest_digest",
        "plan_digest",
    }
)
_COMMON_FIELDS = {
    "operation",
    "transaction_id",
    "candidate_release",
    "release_trust_policy_id",
    "release_trust_policy_digest",
    "profile_digest",
    "lock_digest",
    "artifact_bundle_digest",
    "pack_version",
    "source_trellis_task_layout_digest",
    "target_trellis_task_layout_digest",
    "source_schema_bundle_digest",
    "target_schema_bundle_digest",
    "task_quiescence_snapshot",
    "task_findings",
    "task_quiescence_digest",
    "candidate_impact",
    "workspace_state_evaluation",
    "task_gate_evaluation",
    "preconditions",
    "candidate_file_states",
    "candidate_local_state_contract",
    "provider_approval_bindings",
    "recovery_runtime",
    "candidate_manifest_generation",
}
_INIT_FIELDS = {
    "project_id_precondition",
    "candidate_project_id",
    "workspace_instance_precondition",
    "candidate_workspace_instance_id",
    "manifest_precondition",
    "approval_replay_precondition",
    "empty_replay_ledger_candidate_digest",
    "target_path_digest",
}
_EXISTING_FIELDS = {
    "project_id",
    "workspace_instance_id",
    "manifest_generation",
    "manifest_digest",
    "installed_release",
}
_REPAIR_FIELDS = {"repair_surface_ids"}
_UPGRADE_FIELDS = {"compatibility_identity"}


@dataclass(frozen=True)
class SavedPlanEnvelope:
    operation: str
    plan_core: Mapping[str, object]
    plan_core_digest: str
    immutable_header: Mapping[str, object]
    journal_binding_digest: str
    candidate_manifest_digest: str
    candidate_manifest_file_state: Mapping[str, object]
    plan_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.saved-plan",
            "schema_version": 1,
            "operation": self.operation,
            "plan_core": dict(self.plan_core),
            "plan_core_digest": self.plan_core_digest,
            "immutable_header": dict(self.immutable_header),
            "journal_binding_digest": self.journal_binding_digest,
            "candidate_manifest_digest": self.candidate_manifest_digest,
            "candidate_manifest_file_state": dict(self.candidate_manifest_file_state),
            "plan_digest": self.plan_digest,
        }


def _graph_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_SAVED_PLAN_GRAPH_INVALID", message, details=details)


def _mismatch(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_SAVED_PLAN_MISMATCH", message, exit_code=40, details=details)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _graph_failure(f"{label} must be a string-keyed object")
    return value


def _array(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _graph_failure(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise _graph_failure(f"{label} must be a nonempty string")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise _graph_failure(f"{label} must be lowercase SHA-256")
    return value


def _uuid(value: object, label: str) -> str:
    text = _string(value, label)
    try:
        parsed = str(uuid.UUID(text))
    except ValueError as error:
        raise _graph_failure(f"{label} must be a canonical UUID") from error
    if text != parsed:
        raise _graph_failure(f"{label} must be a canonical UUID")
    return text


def _release(value: object, label: str) -> Mapping[str, object]:
    release = _mapping(value, label)
    if set(release) != {"release_id", "release_manifest_digest"}:
        raise _graph_failure(f"{label} fields are not closed")
    _sha256(release.get("release_id"), f"{label}.release_id")
    _sha256(release.get("release_manifest_digest"), f"{label}.release_manifest_digest")
    return release


def _validate_evaluations(core: Mapping[str, object]) -> None:
    workspace = _mapping(core.get("workspace_state_evaluation"), "workspace state evaluation")
    if set(workspace) != {"evaluator_id", "evaluator_version", "task_quiescence", "blockers"}:
        raise _graph_failure("workspace-state evaluator fields are not closed")
    if workspace.get("evaluator_id") != "agent-workflow.workspace-state-quiescence" or workspace.get(
        "evaluator_version"
    ) != 1:
        raise _graph_failure("workspace-state evaluator identity/version is invalid")
    _array(workspace.get("blockers"), "workspace-state blockers")

    gate = _mapping(core.get("task_gate_evaluation"), "task-gate evaluation")
    if set(gate) != {
        "evaluator_id",
        "evaluator_version",
        "blockers",
        "primary_evaluator_blocker",
    }:
        raise _graph_failure("task-gate evaluator fields are not closed")
    if gate.get("evaluator_id") != "agent-workflow.task-gate" or gate.get(
        "evaluator_version"
    ) != 1:
        raise _graph_failure("task-gate evaluator identity/version is invalid")
    blockers = _array(gate.get("blockers"), "task-gate blockers")
    if blockers or gate.get("primary_evaluator_blocker") is not None:
        raise _graph_failure("approvable saved plan must have an empty command blocker set")


def validate_plan_core(plan_core: Mapping[str, object]) -> None:
    """Validate the closed init/sync/repair/upgrade plan-core union."""

    forbidden = sorted(set(plan_core) & _DERIVED_PLAN_FIELDS)
    if forbidden:
        raise _graph_failure("plan_core contains a forbidden reverse/derived edge", fields=forbidden)
    operation = plan_core.get("operation")
    if operation not in _OPERATIONS:
        raise _graph_failure("plan_core operation is unsupported", operation=operation)
    allowed = set(_COMMON_FIELDS)
    required = set(_COMMON_FIELDS)
    if operation == "init":
        allowed.update(_INIT_FIELDS)
        required.update(_INIT_FIELDS)
    else:
        allowed.update(_EXISTING_FIELDS)
        required.update(_EXISTING_FIELDS)
    if operation == "repair":
        allowed.update(_REPAIR_FIELDS)
        required.update(_REPAIR_FIELDS)
    if operation == "upgrade":
        allowed.update(_UPGRADE_FIELDS)
        required.update(_UPGRADE_FIELDS)
    if set(plan_core) != allowed or not required.issubset(plan_core):
        raise _graph_failure(
            "plan_core fields do not match its operation branch",
            missing=sorted(required - set(plan_core)),
            unexpected=sorted(set(plan_core) - allowed),
        )

    _uuid(plan_core.get("transaction_id"), "transaction_id")
    candidate_release = _release(plan_core.get("candidate_release"), "candidate_release")
    for field in (
        "release_trust_policy_digest",
        "profile_digest",
        "lock_digest",
        "artifact_bundle_digest",
        "source_trellis_task_layout_digest",
        "target_trellis_task_layout_digest",
        "source_schema_bundle_digest",
        "target_schema_bundle_digest",
        "task_quiescence_digest",
    ):
        _sha256(plan_core.get(field), field)
    _string(plan_core.get("release_trust_policy_id"), "release trust policy id")
    _string(plan_core.get("pack_version"), "pack version")
    if not isinstance(plan_core.get("candidate_manifest_generation"), int):
        raise _graph_failure("candidate Manifest generation must be an integer")
    for field in ("preconditions", "candidate_file_states", "provider_approval_bindings"):
        _array(plan_core.get(field), field)
    for field in (
        "task_quiescence_snapshot",
        "task_findings",
        "candidate_impact",
        "candidate_local_state_contract",
        "recovery_runtime",
    ):
        _mapping(plan_core.get(field), field)
    _validate_evaluations(plan_core)

    if operation == "init":
        for field in (
            "project_id_precondition",
            "workspace_instance_precondition",
            "manifest_precondition",
            "approval_replay_precondition",
        ):
            if plan_core.get(field) != "absent":
                raise _graph_failure(f"init {field} must be absent")
        _uuid(plan_core.get("candidate_project_id"), "candidate_project_id")
        _uuid(
            plan_core.get("candidate_workspace_instance_id"),
            "candidate_workspace_instance_id",
        )
        _sha256(
            plan_core.get("empty_replay_ledger_candidate_digest"),
            "empty replay-ledger candidate digest",
        )
        _sha256(plan_core.get("target_path_digest"), "target path digest")
    else:
        _uuid(plan_core.get("project_id"), "project_id")
        _uuid(plan_core.get("workspace_instance_id"), "workspace_instance_id")
        if not isinstance(plan_core.get("manifest_generation"), int):
            raise _graph_failure("Manifest generation must be an integer")
        _sha256(plan_core.get("manifest_digest"), "Manifest digest")
        installed_release = _release(plan_core.get("installed_release"), "installed_release")
        if operation in {"sync", "repair"} and installed_release != candidate_release:
            raise _graph_failure(f"{operation} must preserve release identity")
        if operation == "upgrade" and installed_release == candidate_release:
            raise _graph_failure("upgrade must change release identity")
    if operation == "repair":
        selected = _array(plan_core.get("repair_surface_ids"), "repair surface ids")
        if not selected or not all(isinstance(item, str) and item for item in selected):
            raise _graph_failure("repair requires explicit surface ids")
    if operation == "upgrade":
        _sha256(plan_core.get("compatibility_identity"), "compatibility identity")


def compute_plan_core_digest(plan_core: Mapping[str, object]) -> str:
    validate_plan_core(plan_core)
    return digest("agent-workflow.plan-core.v1", plan_core)


def _validate_immutable_header(header: Mapping[str, object]) -> None:
    forbidden = set(header) & {
        "journal_binding_digest",
        "candidate_manifest_digest",
        "plan_digest",
    }
    if forbidden:
        raise _graph_failure("immutable header contains a forbidden reverse edge")
    common = {
        "transaction_id",
        "operation",
        "plan_core_digest",
        "baseline_manifest_digest",
        "candidate_manifest_generation",
        "task_quiescence_digest",
        "recovery_runtime",
    }
    operation = header.get("operation")
    identity = (
        {"candidate_project_id", "candidate_workspace_instance_id"}
        if operation == "init"
        else {"project_id", "workspace_instance_id"}
    )
    if operation not in _OPERATIONS or set(header) != common | identity:
        raise _graph_failure("immutable header fields do not match operation branch")
    _uuid(header.get("transaction_id"), "header transaction_id")
    _sha256(header.get("plan_core_digest"), "header plan_core_digest")
    _sha256(header.get("task_quiescence_digest"), "header task_quiescence_digest")
    if operation == "init":
        if header.get("baseline_manifest_digest") != "absent":
            raise _graph_failure("init immutable header baseline must be absent")
        _uuid(header.get("candidate_project_id"), "header candidate_project_id")
        _uuid(
            header.get("candidate_workspace_instance_id"),
            "header candidate_workspace_instance_id",
        )
    else:
        _sha256(header.get("baseline_manifest_digest"), "header baseline Manifest digest")
        _uuid(header.get("project_id"), "header project_id")
        _uuid(header.get("workspace_instance_id"), "header workspace_instance_id")
    if not isinstance(header.get("candidate_manifest_generation"), int):
        raise _graph_failure("header candidate Manifest generation must be an integer")
    _mapping(header.get("recovery_runtime"), "header recovery_runtime")


def compute_journal_binding_digest(immutable_header: Mapping[str, object]) -> str:
    _validate_immutable_header(immutable_header)
    return digest("agent-workflow.journal-binding.v1", immutable_header)


def compute_candidate_manifest_digest(candidate_manifest: Mapping[str, object]) -> str:
    if set(candidate_manifest) & {"candidate_manifest_digest", "plan_digest"}:
        raise _graph_failure("candidate Manifest contains a forbidden reverse edge")
    return hashlib.sha256(canonical_json_bytes(candidate_manifest)).hexdigest()


def compute_plan_digest(envelope_without_plan_digest: Mapping[str, object]) -> str:
    if "plan_digest" in envelope_without_plan_digest:
        raise _graph_failure("plan digest projection contains itself")
    expected = {
        "schema_id",
        "schema_version",
        "operation",
        "plan_core",
        "plan_core_digest",
        "immutable_header",
        "journal_binding_digest",
        "candidate_manifest_digest",
        "candidate_manifest_file_state",
    }
    if set(envelope_without_plan_digest) != expected:
        raise _graph_failure("plan envelope projection fields are not closed")
    return digest("agent-workflow.saved-plan.v1", envelope_without_plan_digest)


def _validate_manifest_file_state(state: Mapping[str, object], expected_digest: str) -> None:
    expected = {"path", "byte_hash", "mode", "file_type", "non_symlink"}
    if set(state) != expected:
        raise _graph_failure("candidate Manifest file-state fields are not closed")
    try:
        path = normalize_path(_string(state.get("path"), "candidate Manifest path"))
        mode = normalize_mode(state.get("mode"))  # type: ignore[arg-type]
    except CoreFailure as error:
        raise _graph_failure("candidate Manifest file-state is not canonical") from error
    if path != ".agent-workflow/manifest.json" or mode != "0644":
        raise _graph_failure("candidate Manifest path/mode contract is invalid")
    if state.get("file_type") != "regular" or state.get("non_symlink") is not True:
        raise _graph_failure("candidate Manifest must be a non-symlink regular file")
    if state.get("byte_hash") != expected_digest:
        raise _mismatch("candidate Manifest file-state digest is stale")


def validate_saved_plan_envelope(
    document: Mapping[str, object], candidate_manifest: Mapping[str, object]
) -> SavedPlanEnvelope:
    """Recompute every forward digest edge and reject stale/reversed envelopes."""

    expected = {
        "schema_id",
        "schema_version",
        "operation",
        "plan_core",
        "plan_core_digest",
        "immutable_header",
        "journal_binding_digest",
        "candidate_manifest_digest",
        "candidate_manifest_file_state",
        "plan_digest",
    }
    if set(document) != expected:
        raise _mismatch("saved plan envelope fields are not closed")
    if document.get("schema_id") != "agent-workflow.saved-plan" or document.get(
        "schema_version"
    ) != 1:
        raise _mismatch("saved plan schema identity/version is invalid")
    operation = document.get("operation")
    core = _mapping(document.get("plan_core"), "plan_core")
    header = _mapping(document.get("immutable_header"), "immutable_header")
    file_state = _mapping(
        document.get("candidate_manifest_file_state"), "candidate_manifest_file_state"
    )
    try:
        actual_core_digest = compute_plan_core_digest(core)
        actual_journal_digest = compute_journal_binding_digest(header)
        actual_manifest_digest = compute_candidate_manifest_digest(candidate_manifest)
        projection = dict(document)
        claimed_plan_digest = projection.pop("plan_digest")
        actual_plan_digest = compute_plan_digest(projection)
    except CoreFailure as error:
        raise _mismatch(error.message, **dict(error.details)) from error

    if operation != core.get("operation") or operation != header.get("operation"):
        raise _mismatch("operation differs across saved-plan layers")
    if document.get("plan_core_digest") != actual_core_digest or header.get(
        "plan_core_digest"
    ) != actual_core_digest:
        raise _mismatch("plan_core digest binding is stale")
    if document.get("journal_binding_digest") != actual_journal_digest:
        raise _mismatch("journal binding digest is stale")
    if candidate_manifest.get("last_transaction_binding_digest") != actual_journal_digest:
        raise _mismatch("candidate Manifest is not bound to the immutable journal header")
    if document.get("candidate_manifest_digest") != actual_manifest_digest:
        raise _mismatch("candidate Manifest digest is stale")
    _validate_manifest_file_state(file_state, actual_manifest_digest)
    if claimed_plan_digest != actual_plan_digest:
        raise _mismatch("final plan digest is stale")
    return SavedPlanEnvelope(
        operation=str(operation),
        plan_core=core,
        plan_core_digest=actual_core_digest,
        immutable_header=header,
        journal_binding_digest=actual_journal_digest,
        candidate_manifest_digest=actual_manifest_digest,
        candidate_manifest_file_state=file_state,
        plan_digest=actual_plan_digest,
    )
