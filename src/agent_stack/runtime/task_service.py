"""Recoverable task admission, mutation, and archive state machines."""

from __future__ import annotations

import base64
import copy
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from agent_stack.core.api import CANONICAL_NULL, canonical_json_bytes, digest, normalize_mode, normalize_path
from agent_stack.core.errors import CoreFailure
from agent_stack.reconcile.cas import compare_and_swap, observe_file_state
from agent_stack.reconcile.locks import acquire_runtime_state_gate
from agent_stack.reconcile.models import FileState

from .errors import RuntimeFailure
from .integration import VerifiedIntegration, validate_integration
from .outbox import enqueue_effect
from .ports import RouteVerifierPorts
from .replay import consume_proof, proof_key, reserve_proof
from .task_journal import (
    advance_task_journal,
    create_task_journal,
    read_task_journal,
    unfinished_task_journals,
)


def _crash_at(point: str) -> None:
    """Test seam; production code never selects a crash point."""


@dataclass(frozen=True)
class TaskFile:
    path: str
    content: bytes
    mode: str


@dataclass(frozen=True)
class MetadataMutation:
    original: FileState
    candidate: FileState
    original_bytes: bytes | None
    candidate_bytes: bytes | None


@dataclass(frozen=True)
class OutboxEffect:
    effect_kind: str
    handler_id: str
    handler_version: str
    payload: object


@dataclass(frozen=True)
class TaskAdmissionRequest:
    project_root: Path
    project_id: str
    workspace_instance_id: str
    transaction_id: str
    decision: Mapping[str, object]
    approval_proof: Mapping[str, object]
    current_authorities: Mapping[str, object]
    capability: Mapping[str, object]
    runtime_context: Mapping[str, object]
    workflow_contract: Mapping[str, object]
    mode_state: Mapping[str, object]
    task_files: tuple[TaskFile, ...]
    metadata_mutations: tuple[MetadataMutation, ...]
    admitted_at: datetime
    route_ports: RouteVerifierPorts
    outbox_effects: tuple[OutboxEffect, ...] = ()
    recovery_runtime: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskClaimRequest:
    project_root: Path
    task_ref: str
    task_id: str
    expected_revision: int
    claim_id: str
    executor: str
    actor: str
    claimed_at: datetime


@dataclass(frozen=True)
class TaskReleaseRequest:
    project_root: Path
    task_ref: str
    task_id: str
    expected_revision: int
    claim_id: str
    actor: str
    released_at: datetime


@dataclass(frozen=True)
class TaskTransitionRequest:
    project_root: Path
    task_ref: str
    task_id: str
    expected_revision: int
    transition_id: str
    target_lifecycle_status: str
    target_phase: str | None
    completion_flags: Mapping[str, bool] | None
    changed_at: datetime


@dataclass(frozen=True)
class TaskArchiveRequest:
    project_root: Path
    transaction_id: str
    task_ref: str
    task_id: str
    expected_revision: int
    archive_root: str
    metadata_mutations: tuple[MetadataMutation, ...]
    archived_at: datetime
    outbox_effects: tuple[OutboxEffect, ...] = ()


@dataclass(frozen=True)
class TaskMutationResult:
    transaction_id: str
    task_id: str
    task_ref: str
    lifecycle_status: str
    state_revision: int
    mode: str
    phase: str | None
    executor_claim: Mapping[str, object] | None
    outcome: str = "committed"


def _failure(code: str, message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure(code, message, details=details)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise _failure("AWP_TASK_TRANSITION_INVALID", "task timestamp is not timezone aware")
    return value.astimezone(UTC)


def _format(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _parse_time(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _failure("AWP_TASK_TRANSITION_INVALID", "task timestamp is invalid", field=field_name)
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(UTC)
    except ValueError as error:
        raise _failure(
            "AWP_TASK_TRANSITION_INVALID", "task timestamp is invalid", field=field_name
        ) from error


def _uuid(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise _failure("AWP_TASK_TRANSITION_INVALID", "task UUID is invalid", field=field_name)
    try:
        canonical = str(uuid.UUID(value))
    except ValueError as error:
        raise _failure("AWP_TASK_TRANSITION_INVALID", "task UUID is invalid", field=field_name) from error
    if canonical != value:
        raise _failure(
            "AWP_TASK_TRANSITION_INVALID", "task UUID is not canonical", field=field_name
        )
    return value


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("AWP_TASK_TRANSITION_INVALID", "task object is invalid", field=field_name)
    return cast(Mapping[str, object], value)


def _task_ref(value: str) -> str:
    try:
        return normalize_path(value)
    except CoreFailure as error:
        raise _failure("AWP_TASK_REF_CONFLICT", "task ref is invalid", task_ref=value) from error


def _task_lock_path(root: Path, task_ref: str) -> Path:
    token = hashlib.sha256(task_ref.encode("utf-8")).hexdigest()
    return root / ".agent-workflow/local/task-locks" / f"{token}.lock"


@contextmanager
def _task_lock(root: Path, task_ref: str) -> Iterator[None]:
    path = _task_lock_path(root, task_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise _failure("AWP_TASK_STATE_STALE", "task lock root is a symlink")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _maintenance_clear(root: Path) -> None:
    marker = root / ".agent-workflow/maintenance.json"
    if marker.exists() or marker.is_symlink():
        raise _failure("AWP_TASK_STATE_STALE", "maintenance blocks task mutation")


def _no_other_transaction(root: Path, current: str | None = None) -> None:
    for journal in unfinished_task_journals(root):
        if journal["transaction_id"] != current:
            raise _failure(
                "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED",
                "another unfinished task transaction blocks mutation",
                transaction_id=journal["transaction_id"],
            )


def _integration_paths(root: Path) -> Iterator[Path]:
    trellis = root / ".trellis/tasks"
    if not trellis.exists():
        return
    if trellis.is_symlink() or not trellis.is_dir():
        raise _failure("AWP_TASK_STATE_STALE", "Trellis task root has invalid type")
    for path in sorted(trellis.rglob("integration.yaml")):
        if path.is_symlink() or not path.is_file():
            raise _failure("AWP_TASK_STATE_STALE", "integration path has invalid type")
        yield path


def _read_integration_path(path: Path) -> tuple[dict[str, object], VerifiedIntegration, bytes]:
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _failure("AWP_TASK_STATE_STALE", "integration file is corrupt") from error
    if not isinstance(document, dict) or canonical_json_bytes(document) != payload:
        raise _failure("AWP_TASK_STATE_STALE", "integration file is not canonical")
    return document, validate_integration(document), payload


def _assert_identity_available(root: Path, task_id: str, task_ref: str) -> None:
    target = root / task_ref
    if target.exists() or target.is_symlink():
        raise _failure("AWP_TASK_REF_CONFLICT", "requested task ref already exists")
    for path in _integration_paths(root):
        _, verified, _ = _read_integration_path(path)
        if verified.task_id == task_id:
            raise _failure("AWP_TASK_ID_CONFLICT", "task ID already exists")
    for journal in unfinished_task_journals(root):
        if journal["task_id"] == task_id:
            raise _failure("AWP_TASK_ID_CONFLICT", "task ID appears in unfinished journal")
        if journal["task_ref"] == task_ref:
            raise _failure("AWP_TASK_REF_CONFLICT", "task ref appears in unfinished journal")


def _file_document(task_file: TaskFile) -> dict[str, object]:
    path = normalize_path(task_file.path)
    if path == "integration.yaml" or path.startswith("integration.yaml/"):
        raise _failure("AWP_TASK_TRANSITION_INVALID", "task shell cannot supply integration.yaml")
    mode = normalize_mode(task_file.mode)
    return {
        "path": path,
        "mode": mode,
        "content_base64": base64.b64encode(task_file.content).decode("ascii"),
        "byte_hash": hashlib.sha256(task_file.content).hexdigest(),
    }


def _mutation_document(mutation: MetadataMutation) -> dict[str, object]:
    if mutation.original.path != mutation.candidate.path:
        raise _failure("AWP_TASK_TRANSITION_INVALID", "metadata mutation changes path")
    return {
        "original": mutation.original.to_document(),
        "candidate": mutation.candidate.to_document(),
        "original_base64": (
            None
            if mutation.original_bytes is None
            else base64.b64encode(mutation.original_bytes).decode("ascii")
        ),
        "candidate_base64": (
            None
            if mutation.candidate_bytes is None
            else base64.b64encode(mutation.candidate_bytes).decode("ascii")
        ),
    }


def _decode(value: object) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _failure("AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "journal bytes are invalid")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise _failure(
            "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "journal bytes are invalid"
        ) from error


def _candidate_tree_digest(files: Sequence[Mapping[str, object]]) -> str:
    projection = [
        {"path": item["path"], "mode": item["mode"], "byte_hash": item["byte_hash"]}
        for item in files
    ]
    return digest("agent-workflow.task-tree.v1", projection)


def _verify_admission(request: TaskAdmissionRequest) -> tuple[Mapping[str, object], Mapping[str, object]]:
    verified_decision = request.route_ports.decision(
        request.decision, request.current_authorities, "task-admit"
    )
    if not isinstance(verified_decision, Mapping):
        raise _failure("AWP_TASK_TRANSITION_INVALID", "Route verifier returned invalid value")
    if verified_decision.get("operation") != "create-integrated-task" or verified_decision.get(
        "route"
    ) not in {"trellis-native", "speckit-superpowers"}:
        raise _failure("AWP_TASK_TRANSITION_INVALID", "Route verifier returned wrong branch")
    verified_approval = request.route_ports.approval(
        request.approval_proof,
        verified_decision,
        request.capability,
        request.runtime_context,
    )
    if not isinstance(verified_approval, Mapping) or verified_approval.get(
        "schema_id"
    ) != "agent-workflow.approval-verification-result":
        raise _failure("AWP_TASK_TRANSITION_INVALID", "approval verifier returned invalid value")
    if verified_approval.get("approval_id") != request.approval_proof.get("approval_id"):
        raise _failure("AWP_TASK_TRANSITION_INVALID", "approval verifier changed approval identity")
    return verified_decision, verified_approval


def _build_integrations(
    request: TaskAdmissionRequest,
    verified_decision: Mapping[str, object],
    verified_approval: Mapping[str, object],
    files: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    task_id = _uuid(verified_decision.get("requested_task_id"), "requested_task_id")
    task_ref = _task_ref(cast(str, verified_decision.get("requested_task_ref")))
    mode = cast(str, verified_decision.get("route"))
    surfaces = request.workflow_contract.get("task_contract_surfaces")
    if verified_decision.get("task_contract_surfaces_digest") != digest(
        "agent-workflow.task-surfaces.v1", surfaces
    ):
        raise _failure("AWP_TASK_SURFACE_MISMATCH", "task surface closure differs from Decision")
    proof = request.approval_proof
    for field_name, expected in (
        ("task_id", task_id),
        ("task_ref", task_ref),
        ("workspace_instance_id", request.workspace_instance_id),
        ("route_decision_digest", verified_decision.get("decision_digest")),
        ("approval_challenge", verified_decision.get("approval_challenge")),
    ):
        if proof.get(field_name) != expected:
            raise _failure("AWP_TASK_TRANSITION_INVALID", "approval proof binding differs", field=field_name)
    common: dict[str, object] = {
        "schema_version": 1,
        "mode": mode,
        "workflow_contract": copy.deepcopy(dict(request.workflow_contract)),
        "lifecycle": {
            "status": "admitting",
            "state_revision": 1,
            "admitted_at": None,
            "archived_at": None,
            "blocked_reason": None,
            "last_transition": {},
        },
        "admission": {
            "operation": "create-integrated-task",
            "task_id": task_id,
            "task_ref": task_ref,
            "intent_id": verified_decision.get("intent_id"),
            "intent_digest": verified_decision.get("intent_digest"),
            "task_transaction_id": request.transaction_id,
            "candidate_tree_digest": _candidate_tree_digest(files),
            "workspace_instance_id_at_admission": request.workspace_instance_id,
            "route_decision_id": verified_decision.get("decision_id"),
            "route_decision_digest": verified_decision.get("decision_digest"),
            "approval_id": proof.get("approval_id"),
            "approval_challenge": proof.get("approval_challenge"),
            "approval_proof_digest": digest("agent-workflow.approval-proof.v1", proof),
            "approval_verifier_id": verified_approval.get("verifier_id"),
            "approval_verifier_version": verified_approval.get("verifier_version"),
            "approved_by": verified_approval.get("actor_id"),
            "approval_mechanism": verified_approval.get("mechanism"),
            "approved_at": verified_approval.get("validated_at"),
        },
    }
    branch = "trellis_native" if mode == "trellis-native" else "speckit_superpowers"
    common[branch] = copy.deepcopy(dict(request.mode_state))
    validate_integration(common)
    active = copy.deepcopy(common)
    lifecycle = cast(dict[str, object], active["lifecycle"])
    lifecycle.update(
        status="active",
        state_revision=2,
        admitted_at=_format(request.admitted_at),
        last_transition={"operation": "task-admit", "transaction_id": request.transaction_id},
    )
    validate_integration(active)
    return common, active


def _proof_projection(
    request: TaskAdmissionRequest,
    verified_decision: Mapping[str, object],
    verified_approval: Mapping[str, object],
) -> dict[str, object]:
    return {
        "approval_id": request.approval_proof["approval_id"],
        "approval_challenge": verified_decision["approval_challenge"],
        "route_decision_digest": verified_decision["decision_digest"],
        "validated_at": verified_approval["validated_at"],
        "proof_expires_at": verified_approval["proof_expires_at"],
        "proof_key": proof_key(
            cast(str, request.approval_proof["approval_id"]),
            cast(str, verified_decision["approval_challenge"]),
            cast(str, verified_decision["decision_digest"]),
            request.workspace_instance_id,
        ),
    }


def _effect_document(effect: OutboxEffect) -> dict[str, object]:
    return {
        "effect_kind": effect.effect_kind,
        "handler_id": effect.handler_id,
        "handler_version": effect.handler_version,
        "payload": effect.payload,
    }


def _admission_header(
    request: TaskAdmissionRequest,
    decision: Mapping[str, object],
    approval: Mapping[str, object],
    files: Sequence[Mapping[str, object]],
    admitting: Mapping[str, object],
    active: Mapping[str, object],
) -> dict[str, object]:
    return {
        "operation": "admit",
        "task_id": decision["requested_task_id"],
        "task_ref": decision["requested_task_ref"],
        "project_id": request.project_id,
        "workspace_instance_id": request.workspace_instance_id,
        "decision": dict(request.decision),
        "verified_decision": dict(decision),
        "approval_proof": dict(request.approval_proof),
        "verified_approval": dict(approval),
        "proof": _proof_projection(request, decision, approval),
        "task_files": list(files),
        "metadata_mutations": [_mutation_document(item) for item in request.metadata_mutations],
        "admitting_integration": dict(admitting),
        "active_integration": dict(active),
        "outbox_effects": [_effect_document(item) for item in request.outbox_effects],
        "admitted_at": _format(request.admitted_at),
        "recovery_runtime": dict(request.recovery_runtime),
    }


def _write_new_file(path: Path, payload: bytes, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise _failure("AWP_TASK_STATE_STALE", "task staging file already exists", path=str(path))
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, int(mode, 8))
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _stage_from_header(root: Path, transaction_id: str, header: Mapping[str, object]) -> None:
    staging = root / ".agent-workflow/local/task-staging" / transaction_id / "task"
    if staging.exists():
        return
    staging.mkdir(parents=True)
    files = cast(Sequence[Mapping[str, object]], header["task_files"])
    for item in files:
        payload = _decode(item.get("content_base64"))
        assert payload is not None
        if hashlib.sha256(payload).hexdigest() != item.get("byte_hash"):
            raise _failure("AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "task file bytes differ")
        _write_new_file(staging / cast(str, item["path"]), payload, cast(str, item["mode"]))
    _write_new_file(
        staging / "integration.yaml",
        canonical_json_bytes(header["admitting_integration"]),
        "0640",
    )


def _move_staged_task(root: Path, transaction_id: str, task_ref: str) -> None:
    staging = root / ".agent-workflow/local/task-staging" / transaction_id / "task"
    target = root / task_ref
    if target.exists():
        return
    if not staging.is_dir() or staging.is_symlink():
        raise _failure("AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "task staging tree is missing")
    target.parent.mkdir(parents=True, exist_ok=True)
    if staging.stat().st_dev != target.parent.stat().st_dev:
        raise _failure("AWP_TASK_STATE_STALE", "task move is cross-device")
    os.replace(staging, target)


def _metadata_from_header(header: Mapping[str, object]) -> tuple[MetadataMutation, ...]:
    result: list[MetadataMutation] = []
    for raw in cast(Sequence[Mapping[str, object]], header["metadata_mutations"]):
        result.append(
            MetadataMutation(
                FileState.from_document(_mapping(raw["original"], "original")),
                FileState.from_document(_mapping(raw["candidate"], "candidate")),
                _decode(raw.get("original_base64")),
                _decode(raw.get("candidate_base64")),
            )
        )
    return tuple(result)


def _apply_metadata(root: Path, mutations: Sequence[MetadataMutation]) -> None:
    for mutation in mutations:
        current = observe_file_state(root, mutation.original.path)
        if current.to_document() == mutation.candidate.to_document():
            continue
        compare_and_swap(root, mutation.original, mutation.candidate, mutation.candidate_bytes)


def _restore_metadata(root: Path, mutations: Sequence[MetadataMutation]) -> None:
    for mutation in reversed(mutations):
        current = observe_file_state(root, mutation.candidate.path)
        if current.to_document() == mutation.original.to_document():
            continue
        compare_and_swap(root, mutation.candidate, mutation.original, mutation.original_bytes)


def _integration_state(root: Path, task_ref: str, payload: bytes) -> FileState:
    return FileState(
        f"{task_ref}/integration.yaml",
        True,
        "regular",
        hashlib.sha256(payload).hexdigest(),
        "0640",
        True,
        CANONICAL_NULL,
    )


def _cas_integration(root: Path, task_ref: str, before: Mapping[str, object], after: Mapping[str, object]) -> None:
    before_bytes = canonical_json_bytes(before)
    after_bytes = canonical_json_bytes(after)
    expected = _integration_state(root, task_ref, before_bytes)
    candidate = _integration_state(root, task_ref, after_bytes)
    current = observe_file_state(root, expected.path)
    if current.to_document() == candidate.to_document():
        return
    compare_and_swap(root, expected, candidate, after_bytes)


def _enqueue_header_effects(
    root: Path, header: Mapping[str, object], transaction_id: str, operation: str
) -> None:
    for raw in cast(Sequence[Mapping[str, object]], header.get("outbox_effects", [])):
        enqueue_effect(
            root,
            operation=operation,
            task_id=cast(str, header["task_id"]),
            transaction_id=transaction_id,
            effect_kind=cast(str, raw["effect_kind"]),
            handler_id=cast(str, raw["handler_id"]),
            handler_version=cast(str, raw["handler_version"]),
            payload=raw.get("payload"),
            created_at=_parse_time(header.get("admitted_at") or header.get("archived_at"), "effect time"),
        )


def _result(transaction_id: str, task_ref: str, document: Mapping[str, object], *, outcome: str = "committed") -> TaskMutationResult:
    verified = validate_integration(document)
    return TaskMutationResult(
        transaction_id,
        verified.task_id,
        task_ref,
        verified.lifecycle_status,
        verified.state_revision,
        verified.mode,
        verified.phase,
        verified.executor_claim,
        outcome,
    )


def admit_task(request: TaskAdmissionRequest) -> TaskMutationResult:
    """Create one integrated task with metadata-complete admission commit."""

    task_id = _uuid(request.decision.get("requested_task_id"), "requested_task_id")
    task_ref = _task_ref(cast(str, request.decision.get("requested_task_ref")))
    _uuid(request.transaction_id, "transaction_id")
    with acquire_runtime_state_gate(request.project_root):
        with _task_lock(request.project_root, task_ref):
            _maintenance_clear(request.project_root)
            _no_other_transaction(request.project_root)
            _assert_identity_available(request.project_root, task_id, task_ref)
            verified_decision, verified_approval = _verify_admission(request)
            files = tuple(_file_document(item) for item in request.task_files)
            if len({item["path"] for item in files}) != len(files):
                raise _failure("AWP_TASK_TRANSITION_INVALID", "task shell contains duplicate paths")
            admitting, active = _build_integrations(
                request, verified_decision, verified_approval, files
            )
            header = _admission_header(
                request, verified_decision, verified_approval, files, admitting, active
            )
            journal = create_task_journal(
                request.project_root,
                transaction_id=request.transaction_id,
                operation="admit",
                task_id=task_id,
                task_ref=task_ref,
                immutable_header=header,
            )
            _crash_at("after_planned")
            return _resume_admission(request.project_root, journal, recovery=False)


def _reserve_from_header(root: Path, transaction_id: str, header: Mapping[str, object], *, recovery: bool) -> None:
    proof = _mapping(header["proof"], "proof")
    reserve_proof(
        root,
        project_id=cast(str, header["project_id"]),
        workspace_instance_id=cast(str, header["workspace_instance_id"]),
        approval_id=cast(str, proof["approval_id"]),
        approval_challenge=cast(str, proof["approval_challenge"]),
        route_decision_digest=cast(str, proof["route_decision_digest"]),
        transaction_id=transaction_id,
        validated_at=_parse_time(proof["validated_at"], "validated_at"),
        proof_expires_at=_parse_time(proof["proof_expires_at"], "proof_expires_at"),
        now=_parse_time(header["admitted_at"], "admitted_at"),
        recovery=recovery,
    )


def _consume_from_header(root: Path, transaction_id: str, header: Mapping[str, object]) -> None:
    proof = _mapping(header["proof"], "proof")
    consume_proof(
        root,
        proof_key=cast(str, proof["proof_key"]),
        transaction_id=transaction_id,
        consumed_at=_parse_time(header["admitted_at"], "admitted_at"),
    )


def _resume_admission(
    root: Path, journal: Mapping[str, object], *, recovery: bool
) -> TaskMutationResult:
    transaction_id = cast(str, journal["transaction_id"])
    task_ref = cast(str, journal["task_ref"])
    header = _mapping(journal["immutable_header"], "immutable_header")
    phase = cast(str, journal["phase"])
    current = dict(journal)
    if phase == "planned":
        _reserve_from_header(root, transaction_id, header, recovery=recovery)
        _crash_at("after_reserved")
        _stage_from_header(root, transaction_id, header)
        current = advance_task_journal(root, current, "staged")
        _crash_at("after_staged")
        phase = "staged"
    if phase == "staged":
        _move_staged_task(root, transaction_id, task_ref)
        current = advance_task_journal(root, current, "task_moved")
        _crash_at("after_task_moved")
        phase = "task_moved"
    if phase == "task_moved":
        _apply_metadata(root, _metadata_from_header(header))
        current = advance_task_journal(root, current, "metadata_applied")
        _crash_at("after_metadata_applied")
        phase = "metadata_applied"
    if phase == "metadata_applied":
        _cas_integration(
            root,
            task_ref,
            _mapping(header["admitting_integration"], "admitting"),
            _mapping(header["active_integration"], "active"),
        )
        current = advance_task_journal(root, current, "admission_committed")
        _crash_at("after_admission_committed")
        phase = "admission_committed"
    if phase == "admission_committed":
        current = advance_task_journal(root, current, "cleanup_pending")
        phase = "cleanup_pending"
    if phase == "cleanup_pending":
        _consume_from_header(root, transaction_id, header)
        _enqueue_header_effects(root, header, transaction_id, "task-admit")
        staging_root = root / ".agent-workflow/local/task-staging" / transaction_id
        if staging_root.exists():
            shutil.rmtree(staging_root)
        current = advance_task_journal(root, current, "complete", outcome="committed")
    return _result(
        transaction_id,
        task_ref,
        _mapping(header["active_integration"], "active"),
    )


def _load_task(root: Path, task_ref: str, task_id: str, expected_revision: int) -> tuple[dict[str, object], VerifiedIntegration, bytes]:
    normalized = _task_ref(task_ref)
    path = root / normalized / "integration.yaml"
    document, verified, payload = _read_integration_path(path)
    if verified.task_id != _uuid(task_id, "task_id"):
        raise _failure("AWP_TASK_ID_CONFLICT", "task ID differs from integration")
    if verified.state_revision != expected_revision:
        raise _failure("AWP_TASK_STATE_STALE", "task revision changed")
    return document, verified, payload


def _single_file_mutation(
    root: Path,
    task_ref: str,
    operation: str,
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> TaskMutationResult:
    transaction_id = str(uuid.uuid4())
    verified = validate_integration(before)
    header = {
        "operation": operation,
        "task_id": verified.task_id,
        "task_ref": task_ref,
        "before_integration": dict(before),
        "after_integration": dict(after),
    }
    journal = create_task_journal(
        root,
        transaction_id=transaction_id,
        operation=operation,
        task_id=verified.task_id,
        task_ref=task_ref,
        immutable_header=header,
    )
    _cas_integration(root, task_ref, before, after)
    journal = advance_task_journal(root, journal, "integration_committed")
    journal = advance_task_journal(root, journal, "cleanup_pending")
    advance_task_journal(root, journal, "complete", outcome="committed")
    return _result(transaction_id, task_ref, after)


def claim_task(request: TaskClaimRequest) -> TaskMutationResult:
    task_ref = _task_ref(request.task_ref)
    with acquire_runtime_state_gate(request.project_root):
        with _task_lock(request.project_root, task_ref):
            _maintenance_clear(request.project_root)
            _no_other_transaction(request.project_root)
            before, verified, _ = _load_task(
                request.project_root, task_ref, request.task_id, request.expected_revision
            )
            if verified.mode != "speckit-superpowers" or verified.phase != "implementing":
                raise _failure("AWP_TASK_TRANSITION_INVALID", "claim requires heavy implementing phase")
            if verified.executor_claim is not None:
                raise _failure("AWP_TASK_STATE_STALE", "task already has an executor claim")
            after = copy.deepcopy(before)
            lifecycle = cast(dict[str, object], after["lifecycle"])
            lifecycle["state_revision"] = verified.state_revision + 1
            lifecycle["last_transition"] = {"operation": "claim", "claim_id": request.claim_id}
            heavy = cast(dict[str, object], after["speckit_superpowers"])
            heavy["executor_claim"] = {
                "claim_id": _uuid(request.claim_id, "claim_id"),
                "executor": request.executor,
                "actor": request.actor,
                "claimed_at": _format(request.claimed_at),
                "base_revision": request.expected_revision,
            }
            validate_integration(after)
            return _single_file_mutation(request.project_root, task_ref, "claim", before, after)


def release_task(request: TaskReleaseRequest) -> TaskMutationResult:
    task_ref = _task_ref(request.task_ref)
    with acquire_runtime_state_gate(request.project_root):
        with _task_lock(request.project_root, task_ref):
            _maintenance_clear(request.project_root)
            _no_other_transaction(request.project_root)
            before, verified, _ = _load_task(
                request.project_root, task_ref, request.task_id, request.expected_revision
            )
            claim = verified.executor_claim
            if claim is None or claim.get("claim_id") != request.claim_id or claim.get(
                "actor"
            ) != request.actor:
                raise _failure("AWP_TASK_TRANSITION_INVALID", "release claim identity differs")
            after = copy.deepcopy(before)
            lifecycle = cast(dict[str, object], after["lifecycle"])
            lifecycle["state_revision"] = verified.state_revision + 1
            lifecycle["last_transition"] = {"operation": "release", "claim_id": request.claim_id}
            heavy = cast(dict[str, object], after["speckit_superpowers"])
            heavy["executor_claim"] = None
            validate_integration(after)
            return _single_file_mutation(request.project_root, task_ref, "release", before, after)


def transition_task(request: TaskTransitionRequest) -> TaskMutationResult:
    task_ref = _task_ref(request.task_ref)
    allowed = {
        "active": {"active", "blocked", "completed"},
        "blocked": {"active", "blocked", "completed"},
        "completed": {"completed"},
    }
    with acquire_runtime_state_gate(request.project_root):
        with _task_lock(request.project_root, task_ref):
            _maintenance_clear(request.project_root)
            _no_other_transaction(request.project_root)
            before, verified, _ = _load_task(
                request.project_root, task_ref, request.task_id, request.expected_revision
            )
            if request.target_lifecycle_status not in allowed.get(verified.lifecycle_status, set()):
                raise _failure("AWP_TASK_TRANSITION_INVALID", "lifecycle transition is illegal")
            if verified.mode == "trellis-native" and request.target_phase is not None:
                raise _failure("AWP_TASK_TRANSITION_INVALID", "Trellis-native has no heavy phase")
            if (
                verified.mode == "speckit-superpowers"
                and verified.executor_claim is not None
                and request.target_phase != "implementing"
            ):
                raise _failure("AWP_TASK_TRANSITION_INVALID", "unresolved executor claim blocks phase exit")
            after = copy.deepcopy(before)
            lifecycle = cast(dict[str, object], after["lifecycle"])
            lifecycle.update(
                status=request.target_lifecycle_status,
                state_revision=verified.state_revision + 1,
                blocked_reason=(
                    request.transition_id
                    if request.target_lifecycle_status == "blocked"
                    else None
                ),
                last_transition={
                    "operation": "transition",
                    "transition_id": request.transition_id,
                    "changed_at": _format(request.changed_at),
                },
            )
            if verified.mode == "speckit-superpowers":
                heavy = cast(dict[str, object], after["speckit_superpowers"])
                if request.target_phase is not None:
                    heavy["phase"] = request.target_phase
                if request.completion_flags is not None:
                    heavy["completion_flags"] = dict(request.completion_flags)
                if request.target_lifecycle_status == "completed" and not all(
                    cast(Mapping[str, object], heavy["completion_flags"]).values()
                ):
                    raise _failure(
                        "AWP_TASK_TRANSITION_INVALID", "heavy completion flags are incomplete"
                    )
            validate_integration(after)
            return _single_file_mutation(
                request.project_root, task_ref, "transition", before, after
            )


def derive_archive_ref(archive_root: str, task_id: str, admission_ref: str) -> str:
    """Derive a collision-free archive ref from immutable task identity and label."""

    root = _task_ref(archive_root)
    canonical_id = _uuid(task_id, "task_id")
    label = Path(_task_ref(admission_ref)).name
    return normalize_path(f"{root}/{label}--{canonical_id}")


def _archive_integrations(
    before: Mapping[str, object], transaction_id: str, archived_at: datetime
) -> tuple[dict[str, object], dict[str, object]]:
    verified = validate_integration(before)
    marking = copy.deepcopy(dict(before))
    lifecycle = cast(dict[str, object], marking["lifecycle"])
    lifecycle.update(
        status="archiving",
        state_revision=verified.state_revision + 1,
        last_transition={"operation": "task-archive", "transaction_id": transaction_id},
    )
    validate_integration(marking)
    archived = copy.deepcopy(marking)
    archived_lifecycle = cast(dict[str, object], archived["lifecycle"])
    archived_lifecycle.update(
        status="archived",
        state_revision=verified.state_revision + 2,
        archived_at=_format(archived_at),
    )
    validate_integration(archived)
    return marking, archived


def archive_task(request: TaskArchiveRequest) -> TaskMutationResult:
    task_ref = _task_ref(request.task_ref)
    _uuid(request.transaction_id, "transaction_id")
    with acquire_runtime_state_gate(request.project_root):
        with _task_lock(request.project_root, task_ref):
            _maintenance_clear(request.project_root)
            _no_other_transaction(request.project_root)
            before, verified, _ = _load_task(
                request.project_root, task_ref, request.task_id, request.expected_revision
            )
            if verified.lifecycle_status != "completed" or verified.executor_claim is not None:
                raise _failure("AWP_TASK_ARCHIVE_BLOCKED", "task is not completed and claim-free")
            if verified.mode == "speckit-superpowers":
                heavy = _mapping(before["speckit_superpowers"], "speckit_superpowers")
                flags = _mapping(heavy["completion_flags"], "completion_flags")
                if not flags or not all(flags.values()):
                    raise _failure("AWP_TASK_ARCHIVE_BLOCKED", "completion flags are incomplete")
            destination = derive_archive_ref(request.archive_root, request.task_id, verified.task_ref)
            if (request.project_root / destination).exists():
                raise _failure("AWP_TASK_ARCHIVE_BLOCKED", "archive destination already exists")
            marking, archived = _archive_integrations(
                before, request.transaction_id, request.archived_at
            )
            header = {
                "operation": "archive",
                "task_id": verified.task_id,
                "task_ref": task_ref,
                "archive_ref": destination,
                "before_integration": before,
                "archiving_integration": marking,
                "archived_integration": archived,
                "metadata_mutations": [_mutation_document(item) for item in request.metadata_mutations],
                "outbox_effects": [_effect_document(item) for item in request.outbox_effects],
                "archived_at": _format(request.archived_at),
            }
            journal = create_task_journal(
                request.project_root,
                transaction_id=request.transaction_id,
                operation="archive",
                task_id=verified.task_id,
                task_ref=task_ref,
                immutable_header=header,
            )
            _crash_at("after_archive_planned")
            return _resume_archive(request.project_root, journal)


def _resume_archive(root: Path, journal: Mapping[str, object]) -> TaskMutationResult:
    transaction_id = cast(str, journal["transaction_id"])
    header = _mapping(journal["immutable_header"], "immutable_header")
    source = cast(str, header["task_ref"])
    destination = cast(str, header["archive_ref"])
    phase = cast(str, journal["phase"])
    current = dict(journal)
    if phase == "planned":
        _cas_integration(
            root,
            source,
            _mapping(header["before_integration"], "before"),
            _mapping(header["archiving_integration"], "archiving"),
        )
        current = advance_task_journal(root, current, "state_marked")
        _crash_at("after_archive_state_marked")
        phase = "state_marked"
    if phase == "state_marked":
        source_path = root / source
        destination_path = root / destination
        if not destination_path.exists():
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            if source_path.stat().st_dev != destination_path.parent.stat().st_dev:
                raise _failure("AWP_TASK_ARCHIVE_BLOCKED", "archive move is cross-device")
            os.replace(source_path, destination_path)
        current = advance_task_journal(root, current, "task_moved")
        _crash_at("after_archive_task_moved")
        phase = "task_moved"
    if phase == "task_moved":
        _apply_metadata(root, _metadata_from_header(header))
        current = advance_task_journal(root, current, "metadata_applied")
        _crash_at("after_archive_metadata_applied")
        phase = "metadata_applied"
    if phase == "metadata_applied":
        _cas_integration(
            root,
            destination,
            _mapping(header["archiving_integration"], "archiving"),
            _mapping(header["archived_integration"], "archived"),
        )
        current = advance_task_journal(root, current, "archive_committed")
        _crash_at("after_archive_committed")
        phase = "archive_committed"
    if phase == "archive_committed":
        current = advance_task_journal(root, current, "cleanup_pending")
        phase = "cleanup_pending"
    if phase == "cleanup_pending":
        _enqueue_header_effects(root, header, transaction_id, "task-archive")
        advance_task_journal(root, current, "complete", outcome="committed")
    return _result(
        transaction_id,
        destination,
        _mapping(header["archived_integration"], "archived"),
    )


def recover_task_transaction_internal(
    root: Path, transaction_id: str, action: str
) -> TaskMutationResult:
    journal = read_task_journal(root, transaction_id)
    operation = cast(str, journal["operation"])
    task_ref = cast(str, journal["task_ref"])
    with acquire_runtime_state_gate(root):
        with _task_lock(root, task_ref):
            _maintenance_clear(root)
            _no_other_transaction(root, transaction_id)
            if action == "resume":
                if operation == "admit":
                    return _resume_admission(root, journal, recovery=True)
                if operation == "archive":
                    return _resume_archive(root, journal)
                raise _failure(
                    "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED",
                    "single-file mutation recovery is cleanup-only",
                )
            if action != "rollback":
                raise _failure("AWP_TASK_TRANSITION_INVALID", "recovery action is invalid")
            if operation == "admit":
                return _rollback_admission(root, journal)
            if operation == "archive":
                return _rollback_archive(root, journal)
            raise _failure(
                "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED",
                "committed single-file mutation cannot roll back",
            )


def _remove_task_tree(root: Path, task_ref: str) -> None:
    path = root / task_ref
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise _failure("AWP_TASK_STATE_STALE", "task tree has invalid type")
        shutil.rmtree(path)


def _rollback_admission(root: Path, journal: Mapping[str, object]) -> TaskMutationResult:
    if journal["phase"] in {"admission_committed", "cleanup_pending", "complete"}:
        raise _failure(
            "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "committed admission cannot roll back"
        )
    transaction_id = cast(str, journal["transaction_id"])
    task_ref = cast(str, journal["task_ref"])
    header = _mapping(journal["immutable_header"], "immutable_header")
    phase = cast(str, journal["phase"])
    if phase in {"metadata_applied"}:
        _restore_metadata(root, _metadata_from_header(header))
    if phase in {"task_moved", "metadata_applied"}:
        _remove_task_tree(root, task_ref)
    staging = root / ".agent-workflow/local/task-staging" / transaction_id
    if staging.exists():
        shutil.rmtree(staging)
    _reserve_from_header(root, transaction_id, header, recovery=True)
    _consume_from_header(root, transaction_id, header)
    complete = advance_task_journal(root, journal, "complete", outcome="rolled-back")
    admitting = _mapping(header["admitting_integration"], "admitting")
    result = _result(transaction_id, task_ref, admitting, outcome="rolled-back")
    return TaskMutationResult(
        result.transaction_id,
        result.task_id,
        result.task_ref,
        result.lifecycle_status,
        result.state_revision,
        result.mode,
        result.phase,
        result.executor_claim,
        cast(str, complete["outcome"]),
    )


def _rollback_archive(root: Path, journal: Mapping[str, object]) -> TaskMutationResult:
    if journal["phase"] in {"archive_committed", "cleanup_pending", "complete"}:
        raise _failure("AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "committed archive cannot roll back")
    header = _mapping(journal["immutable_header"], "immutable_header")
    source = cast(str, header["task_ref"])
    destination = cast(str, header["archive_ref"])
    phase = cast(str, journal["phase"])
    if phase == "metadata_applied":
        _restore_metadata(root, _metadata_from_header(header))
    if phase in {"task_moved", "metadata_applied"}:
        if (root / source).exists():
            raise _failure("AWP_TASK_STATE_STALE", "archive source unexpectedly exists")
        os.replace(root / destination, root / source)
    if phase in {"state_marked", "task_moved", "metadata_applied"}:
        _cas_integration(
            root,
            source,
            _mapping(header["archiving_integration"], "archiving"),
            _mapping(header["before_integration"], "before"),
        )
    advance_task_journal(root, journal, "complete", outcome="rolled-back")
    return _result(
        cast(str, journal["transaction_id"]),
        source,
        _mapping(header["before_integration"], "before"),
        outcome="rolled-back",
    )
