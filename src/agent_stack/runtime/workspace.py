"""Clone-local workspace registration and recovery transactions."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import (
    CANONICAL_NULL,
    SchemaCatalog,
    VerifiedTrellisTaskLayout,
    canonical_json_bytes,
)
from agent_stack.reconcile.cas import compare_and_swap, observe_file_state
from agent_stack.reconcile.locks import acquire_bootstrap_lock, acquire_project_locks
from agent_stack.reconcile.models import FileState
from agent_stack.release.compatibility import RuntimeJournalReference

from .caller_context import VerifiedCallerContext
from .errors import RuntimeFailure


MANAGED_IGNORE_BLOCK = """# BEGIN AGENT-WORKFLOW-PACK EPHEMERAL
.agent-workflow/local/
.agent-workflow/task-transactions/
.agent-workflow/transactions/
.agent-workflow/reconcile.lock
.agent-workflow/runtime-state.lock
.agent-workflow/maintenance.json
# END AGENT-WORKFLOW-PACK EPHEMERAL
"""
_WORKSPACE_PATH = ".agent-workflow/local/workspace.json"
_REPLAY_PATH = ".agent-workflow/local/approval-replay.json"
_TRANSACTION_ROOT = ".agent-workflow/local/workspace-transactions"
_PHASES = {
    "planned": 0,
    "workspace_written": 1,
    "registration_committed": 2,
    "cleanup_pending": 3,
    "complete": 4,
}
_CONTRACT_FIELDS = {
    "release_id",
    "release_version",
    "workspace_schema",
    "approval_replay_schema",
    "task_outbox_schema",
    "trellis_task_layout_digest",
    "contract_digest",
}


def _crash_at(point: str) -> None:
    """Test seam; production code never selects a crash point."""


def _registration_failure(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure("AWP_WORKSPACE_REGISTRATION_REQUIRED", message, details=details)


def _recovery_failure(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure(
        "AWP_WORKSPACE_REGISTRATION_RECOVERY_REQUIRED", message, details=details
    )


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _registration_failure("workspace authority object is invalid", field=field)
    return value


def _canonical_uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise _registration_failure("workspace identity is invalid", field=field)
    try:
        parsed = str(uuid.UUID(value))
    except ValueError as error:
        raise _registration_failure("workspace identity is invalid", field=field) from error
    if parsed != value:
        raise _registration_failure("workspace identity is not canonical", field=field)
    return value


def _sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _registration_failure("workspace digest is invalid", field=field)
    return value


def _local_contract(manifest: Mapping[str, object]) -> Mapping[str, object]:
    contract = _mapping(manifest.get("local_state_contract"), "local_state_contract")
    if set(contract) != _CONTRACT_FIELDS:
        raise _registration_failure("local-state contract fields are not closed")
    projection = dict(contract)
    claimed = projection.pop("contract_digest", None)
    actual = hashlib.sha256(canonical_json_bytes(projection)).hexdigest()
    if claimed != actual:
        raise _registration_failure("local-state contract digest is stale")
    if any(
        not isinstance(contract.get(field), int)
        or isinstance(contract.get(field), bool)
        or cast(int, contract[field]) != 1
        for field in ("workspace_schema", "approval_replay_schema", "task_outbox_schema")
    ):
        raise _registration_failure("local-state schema version is unsupported")
    _sha256(contract.get("release_id"), "local_state_contract.release_id")
    _sha256(
        contract.get("trellis_task_layout_digest"),
        "local_state_contract.trellis_task_layout_digest",
    )
    _sha256(contract.get("contract_digest"), "local_state_contract.contract_digest")
    release_version = contract.get("release_version")
    if not isinstance(release_version, str) or not release_version:
        raise _registration_failure("local-state release version is invalid")
    return contract


def _validate_manifest(
    manifest: Mapping[str, object], layout: VerifiedTrellisTaskLayout
) -> tuple[str, Mapping[str, object]]:
    if manifest.get("schema_version") != 1:
        raise _registration_failure("committed Manifest schema is unsupported")
    project_id = _canonical_uuid(manifest.get("project_id"), "project_id")
    contract = _local_contract(manifest)
    if (
        manifest.get("release_id") != contract.get("release_id")
        or manifest.get("pack_version") != contract.get("release_version")
        or contract.get("trellis_task_layout_digest") != layout.layout_digest
    ):
        raise _registration_failure("Manifest local-state contract is inconsistent")
    _sha256(manifest.get("release_manifest_digest"), "release_manifest_digest")
    return project_id, contract


def _workspace_document(
    manifest: Mapping[str, object],
    layout: VerifiedTrellisTaskLayout,
    project_id: str,
    workspace_instance_id: str,
    contract: Mapping[str, object],
) -> dict[str, object]:
    normalized_layout = {"layout_digest": layout.layout_digest, **dict(layout.normalized)}
    return {
        "schema_id": "agent-workflow.workspace-local",
        "schema_version": 1,
        "project_id": project_id,
        "workspace_instance_id": workspace_instance_id,
        "local_state_release_id": contract["release_id"],
        "local_state_release_version": contract["release_version"],
        "local_state_release_manifest_digest": manifest["release_manifest_digest"],
        "local_state_contract_digest": contract["contract_digest"],
        "trellis_task_layout": normalized_layout,
        "local_state_schemas": {
            "workspace": contract["workspace_schema"],
            "approval_replay": contract["approval_replay_schema"],
            "task_outbox": contract["task_outbox_schema"],
        },
    }


def _replay_document(project_id: str, workspace_instance_id: str) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.approval-replay",
        "schema_version": 1,
        "project_id": project_id,
        "workspace_instance_id": workspace_instance_id,
        "entries": {},
    }


def _absent(path: str) -> FileState:
    return FileState(path, False, "absent", CANONICAL_NULL, CANONICAL_NULL, True)


def _candidate(path: str, payload: bytes) -> FileState:
    return FileState(path, True, "regular", hashlib.sha256(payload).hexdigest(), "0600", True)


def _atomic_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(canonical_json_bytes(document))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _transaction_path(root: Path, transaction_id: str) -> Path:
    return root / _TRANSACTION_ROOT / f"{transaction_id}.json"


def _journal_document(
    transaction_id: str,
    project_id: str,
    workspace_instance_id: str,
    workspace: Mapping[str, object],
    replay: Mapping[str, object],
    recovery_runtime: RuntimeJournalReference,
) -> dict[str, object]:
    workspace_bytes = canonical_json_bytes(workspace)
    replay_bytes = canonical_json_bytes(replay)
    return {
        "schema_id": "agent-workflow.workspace-registration-transaction",
        "schema_version": 1,
        "transaction_id": transaction_id,
        "operation": "workspace-register",
        "project_id": project_id,
        "workspace_instance_id": workspace_instance_id,
        "original_state": {"workspace": "absent", "approval_replay": "absent"},
        "workspace_candidate": dict(workspace),
        "workspace_candidate_digest": hashlib.sha256(workspace_bytes).hexdigest(),
        "replay_candidate": dict(replay),
        "replay_candidate_digest": hashlib.sha256(replay_bytes).hexdigest(),
        "recovery_runtime": recovery_runtime.to_document(),
        "phase": "planned",
        "rollback_state": {},
    }


def _load_json(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise _recovery_failure("workspace registration journal is unavailable")
    try:
        parsed = SchemaCatalog.parse_json(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise _recovery_failure("workspace registration journal is invalid") from error
    if not isinstance(parsed, dict) or canonical_json_bytes(parsed) != path.read_bytes():
        raise _recovery_failure("workspace registration journal is not canonical JSON")
    return cast(dict[str, object], parsed)


def _validate_journal(document: Mapping[str, object]) -> None:
    required = {
        "schema_id",
        "schema_version",
        "transaction_id",
        "operation",
        "project_id",
        "workspace_instance_id",
        "original_state",
        "workspace_candidate",
        "workspace_candidate_digest",
        "replay_candidate",
        "replay_candidate_digest",
        "recovery_runtime",
        "phase",
        "rollback_state",
    }
    if set(document) != required:
        raise _recovery_failure("workspace registration journal fields are not closed")
    if (
        document.get("schema_id") != "agent-workflow.workspace-registration-transaction"
        or document.get("schema_version") != 1
        or document.get("operation") != "workspace-register"
        or document.get("phase") not in _PHASES
        or document.get("original_state")
        != {"workspace": "absent", "approval_replay": "absent"}
    ):
        raise _recovery_failure("workspace registration journal contract is invalid")
    _canonical_uuid(document.get("transaction_id"), "transaction_id")
    _canonical_uuid(document.get("project_id"), "project_id")
    _canonical_uuid(document.get("workspace_instance_id"), "workspace_instance_id")
    for name in ("workspace", "replay"):
        candidate = _mapping(document.get(f"{name}_candidate"), f"{name}_candidate")
        expected = hashlib.sha256(canonical_json_bytes(candidate)).hexdigest()
        if document.get(f"{name}_candidate_digest") != expected:
            raise _recovery_failure("workspace registration candidate digest changed")


def _write_journal(root: Path, document: Mapping[str, object]) -> Path:
    _validate_journal(document)
    transaction_id = str(document["transaction_id"])
    path = _transaction_path(root, transaction_id)
    if path.exists() or path.is_symlink():
        existing = _load_json(path)
        _validate_journal(existing)
        immutable = set(document) - {"phase", "rollback_state"}
        if any(existing[field] != document[field] for field in immutable):
            raise _recovery_failure("workspace registration immutable evidence changed")
        if _PHASES[str(document["phase"])] < _PHASES[str(existing["phase"])]:
            raise _recovery_failure("workspace registration phase regressed")
    _atomic_json(path, document)
    return path


def _advance(
    root: Path,
    document: Mapping[str, object],
    phase: str,
    *,
    rollback_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    changed = dict(document)
    changed["phase"] = phase
    if rollback_state is not None:
        changed["rollback_state"] = dict(rollback_state)
    _write_journal(root, changed)
    return changed


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )


def _validate_ignore_and_tracking(root: Path) -> None:
    ignore = root / ".gitignore"
    if ignore.is_symlink() or not ignore.is_file():
        raise _registration_failure("managed ignore marker is unavailable")
    text = ignore.read_text(encoding="utf-8")
    if MANAGED_IGNORE_BLOCK not in text:
        raise _registration_failure("managed ignore marker is invalid")
    for relative in (_WORKSPACE_PATH, _REPLAY_PATH, f"{_TRANSACTION_ROOT}/probe.json"):
        ignored = _git(root, "check-ignore", "-q", "--no-index", "--", relative)
        if ignored.returncode != 0:
            raise _registration_failure("workspace local state is not ignored", path=relative)
    for relative in (_WORKSPACE_PATH, _REPLAY_PATH):
        tracked = _git(root, "ls-files", "--error-unmatch", "--", relative)
        if tracked.returncode == 0:
            raise _registration_failure("workspace local state is tracked", path=relative)


def _unfinished_external_state(root: Path, own_transaction_id: str) -> str | None:
    maintenance = root / ".agent-workflow/maintenance.json"
    if maintenance.exists() or maintenance.is_symlink():
        return ".agent-workflow/maintenance.json"
    roots = (
        root / ".agent-workflow/transactions",
        root / ".agent-workflow/task-transactions",
        root / _TRANSACTION_ROOT,
    )
    for directory in roots:
        if directory.is_symlink():
            return directory.relative_to(root).as_posix()
        if not directory.exists():
            continue
        if not directory.is_dir():
            return directory.relative_to(root).as_posix()
        for path in sorted(directory.glob("*.json")):
            if path == _transaction_path(root, own_transaction_id):
                continue
            try:
                parsed = SchemaCatalog.parse_json(path.read_text(encoding="utf-8"))
            except Exception:
                return path.relative_to(root).as_posix()
            if not isinstance(parsed, Mapping) or parsed.get("phase") != "complete":
                return path.relative_to(root).as_posix()
    return None


def _candidate_relation(root: Path, path: str, payload: bytes) -> str:
    observed = observe_file_state(root, path)
    absent = _absent(path)
    candidate = _candidate(path, payload)
    if observed.to_document() == absent.to_document():
        return "absent"
    if observed.to_document() == candidate.to_document():
        return "candidate"
    return "third"


@dataclass(frozen=True)
class WorkspaceRegistrationResult:
    committed: bool
    workspace: Mapping[str, object]
    replay: Mapping[str, object]
    journal_path: Path


def _finish_registration(
    root: Path, journal: Mapping[str, object]
) -> WorkspaceRegistrationResult:
    workspace = _mapping(journal["workspace_candidate"], "workspace_candidate")
    replay = _mapping(journal["replay_candidate"], "replay_candidate")
    workspace_bytes = canonical_json_bytes(workspace)
    replay_bytes = canonical_json_bytes(replay)
    transaction_id = str(journal["transaction_id"])

    workspace_relation = _candidate_relation(root, _WORKSPACE_PATH, workspace_bytes)
    replay_relation = _candidate_relation(root, _REPLAY_PATH, replay_bytes)
    phase = str(journal["phase"])
    if "third" in {workspace_relation, replay_relation} or (
        replay_relation == "candidate" and workspace_relation != "candidate"
    ):
        raise _recovery_failure("workspace registration encountered an external third state")
    if _PHASES[phase] >= _PHASES["registration_committed"] and not (
        workspace_relation == replay_relation == "candidate"
    ):
        raise _recovery_failure(
            "committed workspace registration pair is missing or inconsistent"
        )
    if workspace_relation == "absent":
        _crash_at("before_workspace")
        compare_and_swap(
            root,
            _absent(_WORKSPACE_PATH),
            _candidate(_WORKSPACE_PATH, workspace_bytes),
            workspace_bytes,
        )
        _crash_at("after_workspace")
    if _PHASES[phase] < _PHASES["workspace_written"]:
        journal = _advance(root, journal, "workspace_written")
        phase = "workspace_written"
        _crash_at("workspace_written")
    if replay_relation == "absent":
        _crash_at("before_replay")
        compare_and_swap(
            root,
            _absent(_REPLAY_PATH),
            _candidate(_REPLAY_PATH, replay_bytes),
            replay_bytes,
        )
        _crash_at("after_replay")
    if _PHASES[phase] < _PHASES["registration_committed"]:
        journal = _advance(root, journal, "registration_committed")
        phase = "registration_committed"
        _crash_at("registration_committed")
    if _PHASES[phase] < _PHASES["cleanup_pending"]:
        journal = _advance(root, journal, "cleanup_pending")
        phase = "cleanup_pending"
        _crash_at("cleanup_pending")
    if _PHASES[phase] < _PHASES["complete"]:
        _advance(root, journal, "complete")
    return WorkspaceRegistrationResult(
        True,
        MappingProxyType(dict(workspace)),
        MappingProxyType(dict(replay)),
        _transaction_path(root, transaction_id),
    )


def register_workspace(
    project_root: Path,
    manifest: Mapping[str, object],
    caller_context: VerifiedCallerContext,
    *,
    trellis_task_layout: VerifiedTrellisTaskLayout,
    bootstrap_lock_root: Path,
    transaction_id: str,
    workspace_instance_id: str,
    recovery_runtime: RuntimeJournalReference,
) -> WorkspaceRegistrationResult:
    """Create the clone-local workspace/replay pair with replay rename as commit."""

    if not isinstance(caller_context, VerifiedCallerContext):
        raise _registration_failure("workspace registration caller context is unverified")
    transaction_id = _canonical_uuid(transaction_id, "transaction_id")
    workspace_instance_id = _canonical_uuid(
        workspace_instance_id, "workspace_instance_id"
    )
    project_id, contract = _validate_manifest(manifest, trellis_task_layout)
    workspace = _workspace_document(
        manifest,
        trellis_task_layout,
        project_id,
        workspace_instance_id,
        contract,
    )
    replay = _replay_document(project_id, workspace_instance_id)
    journal = _journal_document(
        transaction_id,
        project_id,
        workspace_instance_id,
        workspace,
        replay,
        recovery_runtime,
    )
    with acquire_bootstrap_lock(project_root, bootstrap_lock_root):
        with acquire_project_locks(project_root):
            _validate_ignore_and_tracking(project_root)
            own_path = _transaction_path(project_root, transaction_id)
            if own_path.exists() or own_path.is_symlink():
                existing = _load_json(own_path)
                _validate_journal(existing)
                if existing.get("phase") != "complete":
                    raise _recovery_failure(
                        "workspace registration transaction requires recovery"
                    )
            external = _unfinished_external_state(project_root, transaction_id)
            if external is not None:
                raise _recovery_failure(
                    "unrelated maintenance or transaction blocks registration",
                    path=external,
                )
            if (
                _candidate_relation(project_root, _WORKSPACE_PATH, canonical_json_bytes(workspace))
                != "absent"
                or _candidate_relation(project_root, _REPLAY_PATH, canonical_json_bytes(replay))
                != "absent"
                or own_path.exists()
            ):
                raise _registration_failure("workspace is not a fresh unregistered clone")
            journal_path = _write_journal(project_root, journal)
            _crash_at("planned")
            result = _finish_registration(project_root, journal)
            return WorkspaceRegistrationResult(
                result.committed, result.workspace, result.replay, journal_path
            )


def recover_workspace_registration(
    project_root: Path,
    transaction_id: str,
    *,
    action: str,
    bootstrap_lock_root: Path,
) -> WorkspaceRegistrationResult:
    """Explicitly resume or roll back one exact registration transaction."""

    transaction_id = _canonical_uuid(transaction_id, "transaction_id")
    if action not in {"resume", "rollback"}:
        raise _recovery_failure("workspace registration recovery action is invalid")
    with acquire_bootstrap_lock(project_root, bootstrap_lock_root):
        with acquire_project_locks(project_root):
            _validate_ignore_and_tracking(project_root)
            path = _transaction_path(project_root, transaction_id)
            journal = _load_json(path)
            _validate_journal(journal)
            workspace = _mapping(journal["workspace_candidate"], "workspace_candidate")
            replay = _mapping(journal["replay_candidate"], "replay_candidate")
            workspace_bytes = canonical_json_bytes(workspace)
            replay_bytes = canonical_json_bytes(replay)
            workspace_relation = _candidate_relation(
                project_root, _WORKSPACE_PATH, workspace_bytes
            )
            replay_relation = _candidate_relation(project_root, _REPLAY_PATH, replay_bytes)
            if "third" in {workspace_relation, replay_relation} or (
                replay_relation == "candidate" and workspace_relation != "candidate"
            ):
                raise _recovery_failure(
                    "workspace registration recovery found an external third state"
                )
            committed = workspace_relation == replay_relation == "candidate"
            if action == "rollback":
                if committed:
                    raise _recovery_failure(
                        "committed workspace registration cannot be rolled back"
                    )
                if workspace_relation == "candidate":
                    compare_and_swap(
                        project_root,
                        _candidate(_WORKSPACE_PATH, workspace_bytes),
                        _absent(_WORKSPACE_PATH),
                        None,
                    )
                changed = _advance(
                    project_root,
                    journal,
                    "cleanup_pending",
                    rollback_state={"action": "rollback", "workspace_removed": True},
                )
                _advance(project_root, changed, "complete")
                return WorkspaceRegistrationResult(
                    False,
                    MappingProxyType(dict(workspace)),
                    MappingProxyType(dict(replay)),
                    path,
                )
            return _finish_registration(project_root, journal)


def validate_workspace_pair(
    project_root: Path, manifest: Mapping[str, object]
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    """Validate an already committed workspace/replay pair without recreating it."""

    try:
        workspace = _load_json(project_root / _WORKSPACE_PATH)
        replay = _load_json(project_root / _REPLAY_PATH)
    except RuntimeFailure as error:
        raise _registration_failure("committed workspace pair is unavailable") from error
    if (
        workspace.get("schema_id") != "agent-workflow.workspace-local"
        or workspace.get("schema_version") != 1
        or replay.get("schema_id") != "agent-workflow.approval-replay"
        or replay.get("schema_version") != 1
        or workspace.get("project_id") != manifest.get("project_id")
        or replay.get("project_id") != workspace.get("project_id")
        or replay.get("workspace_instance_id") != workspace.get("workspace_instance_id")
        or not isinstance(replay.get("entries"), Mapping)
    ):
        raise _registration_failure("committed workspace pair identity is inconsistent")
    return MappingProxyType(workspace), MappingProxyType(replay)
