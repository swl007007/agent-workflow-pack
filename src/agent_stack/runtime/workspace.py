"""Clone-local workspace registration and recovery transactions."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import (
    CANONICAL_NULL,
    CandidateImpact,
    SchemaCatalog,
    TaskSnapshotAndFindings,
    VerifiedDiscoverySchemas,
    VerifiedTrellisTaskLayout,
    build_workspace_diagnostic,
    canonical_json_bytes,
    digest,
    evaluate_task_gate,
    evaluate_workspace_state_quiescence,
)
from agent_stack.core.impact import AuthorityChange
from agent_stack.reconcile.cas import compare_and_swap, observe_file_state
from agent_stack.reconcile.locks import acquire_bootstrap_lock, acquire_project_locks
from agent_stack.reconcile.models import FileState
from agent_stack.reconcile.ports import TaskQuiescenceScannerPort
from agent_stack.release.compatibility import (
    CompatibilityResult,
    LocalStateContract,
    RuntimeJournalReference,
)

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
_MIGRATION_PHASES = {
    "planned": 0,
    "local_candidates_applied": 1,
    "workspace_committed": 2,
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


def build_first_init_local_state(
    manifest: Mapping[str, object],
    layout: VerifiedTrellisTaskLayout,
    workspace_instance_id: str,
    expected_replay_digest: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """Build the two local-state candidates committed by first init."""
    project_id, contract = _validate_manifest(manifest, layout)
    normalized_workspace_id = _canonical_uuid(
        workspace_instance_id, "workspace_instance_id"
    )
    expected_digest = _sha256(expected_replay_digest, "expected_replay_digest")
    workspace = _workspace_document(
        manifest,
        layout,
        project_id,
        normalized_workspace_id,
        contract,
    )
    replay = _replay_document(project_id, normalized_workspace_id)
    if hashlib.sha256(canonical_json_bytes(replay)).hexdigest() != expected_digest:
        raise _registration_failure("empty replay candidate digest changed")
    return workspace, replay


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


LocalStateMigration = Callable[[str, Mapping[str, object]], Mapping[str, object]]


@dataclass(frozen=True)
class WorkspaceMigrationResult:
    committed: bool
    workspace: Mapping[str, object]
    replay: Mapping[str, object]
    journal_path: Path


def _migration_failure(code: str, message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure(code, message, details=details)


def _migration_recovery_failure(message: str, **details: object) -> RuntimeFailure:
    return _migration_failure(
        "AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED", message, **details
    )


def _migration_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _migration_recovery_failure(
            "workspace migration object is invalid", field=field
        )
    return value


def _migration_array(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _migration_recovery_failure(
            "workspace migration array is invalid", field=field
        )
    return value


def _load_local_document(root: Path, relative: str) -> dict[str, object]:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise _migration_recovery_failure(
            "workspace local-state file is unavailable", path=relative
        )
    try:
        payload = path.read_bytes()
        parsed = SchemaCatalog.parse_json(payload.decode("utf-8"))
    except Exception as error:
        raise _migration_recovery_failure(
            "workspace local-state file is invalid", path=relative
        ) from error
    if not isinstance(parsed, dict) or canonical_json_bytes(parsed) != payload:
        raise _migration_recovery_failure(
            "workspace local-state file is not canonical JSON", path=relative
        )
    return cast(dict[str, object], parsed)


def _workspace_source_contract(
    workspace: Mapping[str, object], source_contract: LocalStateContract
) -> None:
    schemas = _migration_mapping(workspace.get("local_state_schemas"), "local schemas")
    expected_versions = {
        "workspace": source_contract.schema_versions["workspace"],
        "approval_replay": source_contract.schema_versions["approval_replay"],
        "task_outbox": source_contract.schema_versions["task_outbox"],
    }
    if (
        workspace.get("local_state_contract_digest") != source_contract.contract_digest
        or schemas != expected_versions
    ):
        raise _migration_recovery_failure(
            "workspace source local-state contract does not match verified evidence"
        )


def _target_contract_matches_manifest(
    manifest: Mapping[str, object],
    target_layout: VerifiedTrellisTaskLayout,
    target_contract: LocalStateContract,
) -> tuple[str, Mapping[str, object]]:
    try:
        project_id, manifest_contract = _validate_manifest(manifest, target_layout)
    except RuntimeFailure as error:
        raise _migration_recovery_failure(
            "target Manifest local-state contract is invalid"
        ) from error
    versions = {
        "workspace": target_contract.schema_versions["workspace"],
        "approval_replay": target_contract.schema_versions["approval_replay"],
        "task_outbox": target_contract.schema_versions["task_outbox"],
    }
    if (
        manifest_contract.get("contract_digest") != target_contract.contract_digest
        or manifest_contract.get("trellis_task_layout_digest")
        != target_contract.trellis_task_layout_digest
        or any(manifest_contract.get(f"{name}_schema") != value for name, value in versions.items())
    ):
        raise _migration_recovery_failure(
            "target Manifest and verified local-state contract disagree"
        )
    return project_id, manifest_contract


def _validate_compatibility_result(
    compatibility: CompatibilityResult,
    source_contract: LocalStateContract,
    target_contract: LocalStateContract,
    *,
    relationship_evidence: str,
    discovery_evidence: str,
) -> Mapping[str, object]:
    if relationship_evidence == "invalid":
        raise _migration_failure(
            "AWP_SOURCE_RELEASE_VERIFICATION_FAILED",
            "source release relationship evidence is invalid",
        )
    if relationship_evidence == "missing" or compatibility.relationship == "missing":
        raise _migration_failure(
            "AWP_WORKSPACE_SOURCE_METADATA_REQUIRED",
            "source release relationship evidence is unavailable",
        )
    if compatibility.relationship == "ahead":
        raise _migration_failure(
            "AWP_WORKSPACE_CONTRACT_AHEAD",
            "workspace local-state contract is ahead of the checked-out target",
        )
    if compatibility.relationship == "diverged":
        raise _migration_failure(
            "AWP_WORKSPACE_CONTRACT_DIVERGED",
            "workspace and target local-state contracts have no directed edge",
        )
    if compatibility.relationship != "migration-required":
        raise _migration_failure(
            "AWP_WORKSPACE_MIGRATION_REQUIRED",
            "workspace migration does not have an exact directed edge",
        )
    if discovery_evidence == "missing":
        raise _migration_failure(
            "AWP_WORKSPACE_SOURCE_METADATA_REQUIRED",
            "source task-discovery evidence is unavailable",
        )
    if discovery_evidence in {"unsupported", "invalid"}:
        raise _migration_failure(
            "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS",
            "source task-discovery evidence cannot be interpreted",
        )
    if relationship_evidence != "verified" or discovery_evidence != "verified":
        raise _migration_recovery_failure("workspace migration evidence state is invalid")
    edge = _migration_mapping(compatibility.edge, "compatibility edge")
    contracts = _migration_mapping(edge.get("local_state_contracts"), "edge contracts")
    layouts = _migration_mapping(edge.get("trellis_task_layouts"), "edge layouts")
    if (
        contracts.get("from") != source_contract.contract_digest
        or contracts.get("to") != target_contract.contract_digest
        or layouts.get("from") != source_contract.trellis_task_layout_digest
        or layouts.get("to") != target_contract.trellis_task_layout_digest
        or compatibility.target_local_state_contract_digest
        != target_contract.contract_digest
        or compatibility.target_trellis_task_layout_digest
        != target_contract.trellis_task_layout_digest
    ):
        raise _migration_recovery_failure(
            "directed compatibility edge does not bind both local contracts"
        )
    transitions = _migration_mapping(edge.get("schema_transitions"), "schema transitions")
    for field, source_version in source_contract.schema_versions.items():
        transition = _migration_mapping(transitions.get(field), f"schema transition {field}")
        if transition != {
            "from": source_version,
            "to": target_contract.schema_versions[field],
        }:
            raise _migration_recovery_failure(
                "schema transition does not bind source and target versions", field=field
            )
    return edge


def _migration_impact(
    source_contract: LocalStateContract, target_contract: LocalStateContract
) -> CandidateImpact:
    authority_changes: tuple[AuthorityChange, ...] = ()
    if (
        source_contract.trellis_task_layout_digest
        != target_contract.trellis_task_layout_digest
    ):
        authority_changes = (
            AuthorityChange(
                "trellis-layout",
                source_contract.trellis_task_layout_digest,
                target_contract.trellis_task_layout_digest,
            ),
        )
    projection = {
        "schema_id": "agent-workflow.candidate-impact",
        "schema_version": 1,
        "impact_kind": "runtime-visible",
        "authority_changes": [change.to_document() for change in authority_changes],
        "surface_changes": [],
    }
    return CandidateImpact(
        "runtime-visible",
        authority_changes,
        (),
        True,
        digest("agent-workflow.candidate-impact.v1", projection),
    )


def _task_state_document(value: TaskSnapshotAndFindings) -> dict[str, object]:
    return {
        "snapshot": dict(value.snapshot),
        "findings": dict(value.findings),
        "task_quiescence_digest": value.task_quiescence_digest,
    }


def _require_same_migration_snapshot(
    actual: TaskSnapshotAndFindings, expected: TaskSnapshotAndFindings
) -> None:
    if canonical_json_bytes(_task_state_document(actual)) == canonical_json_bytes(
        _task_state_document(expected)
    ):
        return
    latest_gate = evaluate_task_gate(
        "workspace-migrate",
        CandidateImpact("runtime-visible", (), (), True, "0" * 64),
        actual.snapshot,
        actual.findings,
    )
    raise _migration_failure(
        "AWP_TASK_QUIESCENCE_CHANGED",
        "task quiescence evidence changed during workspace migration",
        latest_task_quiescence_digest=actual.task_quiescence_digest,
        secondary_diagnostics=sorted({blocker.code for blocker in latest_gate.blockers}),
    )


def _workspace_state_document(value: object) -> dict[str, object]:
    return {
        "evaluator_id": getattr(value, "evaluator_id"),
        "evaluator_version": getattr(value, "evaluator_version"),
        "task_quiescence": getattr(value, "task_quiescence"),
        "evidence_kinds": list(getattr(value, "evidence_kinds")),
    }


def _task_gate_document(value: object) -> dict[str, object]:
    blockers = []
    for blocker in getattr(value, "blockers"):
        blockers.append(
            {
                "code": blocker.code,
                "finding_id": blocker.finding_id,
                "task_id": blocker.task_id,
                "path": blocker.path,
                "surface_id": blocker.surface_id,
                "authority_id": blocker.authority_id,
            }
        )
    return {
        "evaluator_id": getattr(value, "evaluator_id"),
        "evaluator_version": getattr(value, "evaluator_version"),
        "operation": getattr(value, "operation"),
        "blockers": blockers,
        "primary_evaluator_blocker": getattr(value, "primary_evaluator_blocker"),
    }


def _migrate_document(
    path: str,
    document: Mapping[str, object],
    edge: Mapping[str, object],
    migration_functions: Mapping[str, LocalStateMigration],
) -> dict[str, object]:
    candidate: Mapping[str, object] = document
    for raw in _migration_array(edge.get("migrations"), "edge migrations"):
        migration = _migration_mapping(raw, "edge migration")
        migration_id = migration.get("migration_id")
        if not isinstance(migration_id, str):
            raise _migration_recovery_failure("edge migration id is invalid")
        function = migration_functions.get(migration_id)
        if function is None:
            continue
        migrated = function(path, candidate)
        candidate = _migration_mapping(migrated, "local-state migration result")
    return dict(candidate)


def _migration_file_record(
    root: Path,
    path: str,
    kind: str,
    preimage_document: Mapping[str, object],
    candidate_document: Mapping[str, object],
) -> dict[str, object]:
    observed = observe_file_state(root, path)
    if not observed.exists or observed.file_type != "regular" or observed.mode == CANONICAL_NULL:
        raise _migration_recovery_failure(
            "workspace local-state preimage is not a regular file", path=path
        )
    preimage_bytes = canonical_json_bytes(preimage_document)
    if observed.byte_hash != hashlib.sha256(preimage_bytes).hexdigest():
        raise _migration_recovery_failure(
            "workspace local-state preimage bytes changed", path=path
        )
    candidate_bytes = canonical_json_bytes(candidate_document)
    candidate_state = FileState(
        path,
        True,
        "regular",
        hashlib.sha256(candidate_bytes).hexdigest(),
        observed.mode,
        True,
    )
    return {
        "path": path,
        "kind": kind,
        "preimage_state": observed.to_document(),
        "candidate_state": candidate_state.to_document(),
        "preimage_document": dict(preimage_document),
        "candidate_document": dict(candidate_document),
    }


def _outbox_documents(root: Path) -> list[tuple[str, dict[str, object]]]:
    relative_root = ".agent-workflow/local/task-outbox"
    directory = root / relative_root
    if directory.is_symlink():
        raise _migration_recovery_failure("task outbox root is a symlink")
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise _migration_recovery_failure("task outbox root is not a directory")
    result: list[tuple[str, dict[str, object]]] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise _migration_recovery_failure(
                "task outbox contains an unexpected entry",
                path=path.relative_to(root).as_posix(),
            )
        relative = path.relative_to(root).as_posix()
        result.append((relative, _load_local_document(root, relative)))
    return result


def _build_migration_records(
    root: Path,
    workspace: Mapping[str, object],
    replay: Mapping[str, object],
    target_workspace: Mapping[str, object],
    edge: Mapping[str, object],
    migration_functions: Mapping[str, LocalStateMigration],
) -> list[dict[str, object]]:
    migrated_replay = _migrate_document(_REPLAY_PATH, replay, edge, migration_functions)
    records = [
        _migration_file_record(
            root, _REPLAY_PATH, "approval-replay", replay, migrated_replay
        )
    ]
    for path, document in _outbox_documents(root):
        migrated = _migrate_document(path, document, edge, migration_functions)
        records.append(
            _migration_file_record(root, path, "task-outbox", document, migrated)
        )
    records.append(
        _migration_file_record(
            root, _WORKSPACE_PATH, "workspace", workspace, target_workspace
        )
    )
    return records


def _migration_journal_document(
    *,
    transaction_id: str,
    project_id: str,
    workspace_instance_id: str,
    source_contract: LocalStateContract,
    target_contract: LocalStateContract,
    edge: Mapping[str, object],
    target_manifest: Mapping[str, object],
    source_layout: VerifiedTrellisTaskLayout,
    target_layout: VerifiedTrellisTaskLayout,
    source_schemas: VerifiedDiscoverySchemas,
    target_schemas: VerifiedDiscoverySchemas,
    snapshot: TaskSnapshotAndFindings,
    workspace_state: object,
    task_gate: object,
    diagnostic: object,
    records: Sequence[Mapping[str, object]],
    recovery_runtime: RuntimeJournalReference,
) -> dict[str, object]:
    header = {
        "transaction_id": transaction_id,
        "operation": "workspace-migrate",
        "project_id": project_id,
        "workspace_instance_id": workspace_instance_id,
        "source_contract": source_contract.to_document(),
        "target_contract": target_contract.to_document(),
        "compatibility_edge": dict(edge),
        "target_manifest_identity": {
            "release_id": target_manifest["release_id"],
            "release_version": target_manifest["pack_version"],
            "release_manifest_digest": target_manifest["release_manifest_digest"],
            "generation": target_manifest["generation"],
        },
        "source_layout": {
            "layout_digest": source_layout.layout_digest,
            **dict(source_layout.normalized),
        },
        "target_layout": {
            "layout_digest": target_layout.layout_digest,
            **dict(target_layout.normalized),
        },
        "source_schemas": {
            "schema_bundle_digest": source_schemas.schema_bundle_digest,
            "normalized": dict(source_schemas.normalized),
        },
        "target_schemas": {
            "schema_bundle_digest": target_schemas.schema_bundle_digest,
            "normalized": dict(target_schemas.normalized),
        },
        "task_snapshot": dict(snapshot.snapshot),
        "task_findings": dict(snapshot.findings),
        "task_quiescence_digest": snapshot.task_quiescence_digest,
        "workspace_state_evaluation": _workspace_state_document(workspace_state),
        "task_gate_evaluation": _task_gate_document(task_gate),
        "workspace_diagnostic": getattr(diagnostic, "to_document")(),
        "file_records": [dict(record) for record in records],
        "recovery_runtime": recovery_runtime.to_document(),
    }
    return {
        "schema_id": "agent-workflow.workspace-migration-transaction",
        "schema_version": 1,
        "immutable_header": header,
        "journal_binding_digest": digest(
            "agent-workflow.workspace-migration-binding.v1", header
        ),
        "phase": "planned",
        "rollback_state": {},
    }


def _load_migration_journal(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise _migration_recovery_failure("workspace migration journal is unavailable")
    try:
        payload = path.read_bytes()
        parsed = SchemaCatalog.parse_json(payload.decode("utf-8"))
    except Exception as error:
        raise _migration_recovery_failure("workspace migration journal is invalid") from error
    if not isinstance(parsed, dict) or canonical_json_bytes(parsed) != payload:
        raise _migration_recovery_failure(
            "workspace migration journal is not canonical JSON"
        )
    document = cast(dict[str, object], parsed)
    _validate_migration_journal(document)
    return document


def _validate_migration_journal(document: Mapping[str, object]) -> None:
    if set(document) != {
        "schema_id",
        "schema_version",
        "immutable_header",
        "journal_binding_digest",
        "phase",
        "rollback_state",
    }:
        raise _migration_recovery_failure(
            "workspace migration journal fields are not closed"
        )
    header = _migration_mapping(document.get("immutable_header"), "immutable header")
    required_header = {
        "transaction_id",
        "operation",
        "project_id",
        "workspace_instance_id",
        "source_contract",
        "target_contract",
        "compatibility_edge",
        "target_manifest_identity",
        "source_layout",
        "target_layout",
        "source_schemas",
        "target_schemas",
        "task_snapshot",
        "task_findings",
        "task_quiescence_digest",
        "workspace_state_evaluation",
        "task_gate_evaluation",
        "workspace_diagnostic",
        "file_records",
        "recovery_runtime",
    }
    if (
        set(header) != required_header
        or document.get("schema_id")
        != "agent-workflow.workspace-migration-transaction"
        or document.get("schema_version") != 1
        or header.get("operation") != "workspace-migrate"
        or document.get("phase") not in _MIGRATION_PHASES
        or document.get("journal_binding_digest")
        != digest("agent-workflow.workspace-migration-binding.v1", header)
    ):
        raise _migration_recovery_failure(
            "workspace migration journal contract is invalid"
        )
    _canonical_uuid(header.get("transaction_id"), "transaction_id")
    _canonical_uuid(header.get("project_id"), "project_id")
    _canonical_uuid(header.get("workspace_instance_id"), "workspace_instance_id")
    records = _migration_array(header.get("file_records"), "file records")
    paths: list[str] = []
    for raw in records:
        record = _migration_mapping(raw, "file record")
        if set(record) != {
            "path",
            "kind",
            "preimage_state",
            "candidate_state",
            "preimage_document",
            "candidate_document",
        }:
            raise _migration_recovery_failure("workspace migration file record is invalid")
        path = record.get("path")
        if not isinstance(path, str):
            raise _migration_recovery_failure("workspace migration path is invalid")
        paths.append(path)
        if record.get("kind") not in {"approval-replay", "task-outbox", "workspace"}:
            raise _migration_recovery_failure("workspace migration file kind is invalid")
        preimage = FileState.from_document(
            _migration_mapping(record.get("preimage_state"), "preimage state")
        )
        candidate = FileState.from_document(
            _migration_mapping(record.get("candidate_state"), "candidate state")
        )
        if preimage.path != path or candidate.path != path:
            raise _migration_recovery_failure("workspace migration file path changed")
        for side, state in (
            ("preimage", preimage),
            ("candidate", candidate),
        ):
            document_value = _migration_mapping(
                record.get(f"{side}_document"), f"{side} document"
            )
            if state.byte_hash != hashlib.sha256(
                canonical_json_bytes(document_value)
            ).hexdigest():
                raise _migration_recovery_failure(
                    "workspace migration file document digest changed", path=path
                )
    if len(paths) != len(set(paths)) or paths[-1:] != [_WORKSPACE_PATH]:
        raise _migration_recovery_failure(
            "workspace migration records are duplicated or commit point is not last"
        )
    if any(
        path != _REPLAY_PATH
        and path != _WORKSPACE_PATH
        and not path.startswith(".agent-workflow/local/task-outbox/")
        for path in paths
    ):
        raise _migration_recovery_failure(
            "workspace migration record exceeds local-state authority"
        )


def _write_migration_journal(root: Path, document: Mapping[str, object]) -> Path:
    _validate_migration_journal(document)
    header = _migration_mapping(document["immutable_header"], "immutable header")
    path = _transaction_path(root, str(header["transaction_id"]))
    if path.exists() or path.is_symlink():
        existing = _load_migration_journal(path)
        if existing["immutable_header"] != document["immutable_header"] or existing[
            "journal_binding_digest"
        ] != document["journal_binding_digest"]:
            raise _migration_recovery_failure(
                "workspace migration immutable evidence changed"
            )
        if _MIGRATION_PHASES[str(document["phase"])] < _MIGRATION_PHASES[
            str(existing["phase"])
        ]:
            raise _migration_recovery_failure("workspace migration phase regressed")
    _atomic_json(path, document)
    return path


def _advance_migration(
    root: Path,
    journal: Mapping[str, object],
    phase: str,
    *,
    rollback_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    changed = dict(journal)
    changed["phase"] = phase
    if rollback_state is not None:
        changed["rollback_state"] = dict(rollback_state)
    _write_migration_journal(root, changed)
    return changed


def _record_states(record: Mapping[str, object]) -> tuple[FileState, FileState, bytes, bytes]:
    preimage = FileState.from_document(
        _migration_mapping(record["preimage_state"], "preimage state")
    )
    candidate = FileState.from_document(
        _migration_mapping(record["candidate_state"], "candidate state")
    )
    preimage_bytes = canonical_json_bytes(
        _migration_mapping(record["preimage_document"], "preimage document")
    )
    candidate_bytes = canonical_json_bytes(
        _migration_mapping(record["candidate_document"], "candidate document")
    )
    return preimage, candidate, preimage_bytes, candidate_bytes


def _record_relation(root: Path, record: Mapping[str, object]) -> str:
    preimage, candidate, _, _ = _record_states(record)
    observed = observe_file_state(root, preimage.path)
    if observed.to_document() == candidate.to_document():
        return "candidate"
    if observed.to_document() == preimage.to_document():
        return "preimage"
    return "third"


def _snapshot_from_header(header: Mapping[str, object]) -> TaskSnapshotAndFindings:
    return TaskSnapshotAndFindings(
        snapshot=_migration_mapping(header["task_snapshot"], "task snapshot"),
        findings=_migration_mapping(header["task_findings"], "task findings"),
        task_quiescence_digest=str(header["task_quiescence_digest"]),
    )


def _validate_recovery_scanner_context(
    header: Mapping[str, object],
    source_layout: VerifiedTrellisTaskLayout,
    target_layout: VerifiedTrellisTaskLayout,
    source_schemas: VerifiedDiscoverySchemas,
    target_schemas: VerifiedDiscoverySchemas,
) -> None:
    recorded_source_layout = _migration_mapping(header["source_layout"], "source layout")
    recorded_target_layout = _migration_mapping(header["target_layout"], "target layout")
    recorded_source_schemas = _migration_mapping(header["source_schemas"], "source schemas")
    recorded_target_schemas = _migration_mapping(header["target_schemas"], "target schemas")
    if (
        recorded_source_layout.get("layout_digest") != source_layout.layout_digest
        or recorded_target_layout.get("layout_digest") != target_layout.layout_digest
        or recorded_source_schemas.get("schema_bundle_digest")
        != source_schemas.schema_bundle_digest
        or recorded_target_schemas.get("schema_bundle_digest")
        != target_schemas.schema_bundle_digest
        or recorded_source_layout
        != {"layout_digest": source_layout.layout_digest, **dict(source_layout.normalized)}
        or recorded_target_layout
        != {"layout_digest": target_layout.layout_digest, **dict(target_layout.normalized)}
        or recorded_source_schemas.get("normalized") != source_schemas.normalized
        or recorded_target_schemas.get("normalized") != target_schemas.normalized
    ):
        raise _migration_recovery_failure(
            "workspace migration recovery scanner context changed"
        )


def _finish_workspace_migration(
    root: Path,
    journal: Mapping[str, object],
    *,
    source_layout: VerifiedTrellisTaskLayout,
    target_layout: VerifiedTrellisTaskLayout,
    source_schemas: VerifiedDiscoverySchemas,
    target_schemas: VerifiedDiscoverySchemas,
    scanner: TaskQuiescenceScannerPort,
    fresh: bool,
) -> WorkspaceMigrationResult:
    header = _migration_mapping(journal["immutable_header"], "immutable header")
    records = [
        _migration_mapping(record, "file record")
        for record in _migration_array(header["file_records"], "file records")
    ]
    local_records = records[:-1]
    workspace_record = records[-1]
    phase = str(journal["phase"])
    relations = {str(record["path"]): _record_relation(root, record) for record in records}
    if "third" in relations.values():
        raise _migration_recovery_failure(
            "workspace migration encountered an external third state"
        )
    workspace_relation = relations[_WORKSPACE_PATH]
    committed = workspace_relation == "candidate"
    if committed and any(relations[str(record["path"])] != "candidate" for record in local_records):
        raise _migration_recovery_failure(
            "committed workspace migration has incomplete local candidates"
        )
    if _MIGRATION_PHASES[phase] >= _MIGRATION_PHASES["workspace_committed"] and not committed:
        raise _migration_recovery_failure("committed workspace migration is missing")
    if not committed:
        for record in local_records:
            path = str(record["path"])
            preimage, candidate, _, candidate_bytes = _record_states(record)
            if fresh or relations[path] == "preimage":
                point = (
                    "replay_candidate"
                    if record["kind"] == "approval-replay"
                    else "outbox_candidate"
                )
                _crash_at(f"before_{point}")
                compare_and_swap(root, preimage, candidate, candidate_bytes)
                _crash_at(f"after_{point}")
        if _MIGRATION_PHASES[phase] < _MIGRATION_PHASES["local_candidates_applied"]:
            journal = _advance_migration(root, journal, "local_candidates_applied")
            phase = "local_candidates_applied"
            _crash_at("local_candidates_applied")
        expected = _snapshot_from_header(header)
        latest = scanner(
            source_layout, target_layout, source_schemas, target_schemas
        )
        _require_same_migration_snapshot(latest, expected)
        preimage, candidate, _, candidate_bytes = _record_states(workspace_record)
        _crash_at("before_workspace_candidate")
        compare_and_swap(root, preimage, candidate, candidate_bytes)
        _crash_at("after_workspace_candidate")
        journal = _advance_migration(root, journal, "workspace_committed")
        phase = "workspace_committed"
        _crash_at("workspace_committed")
    if _MIGRATION_PHASES[phase] < _MIGRATION_PHASES["cleanup_pending"]:
        journal = _advance_migration(root, journal, "cleanup_pending")
        phase = "cleanup_pending"
        _crash_at("migration_cleanup_pending")
    if _MIGRATION_PHASES[phase] < _MIGRATION_PHASES["complete"]:
        journal = _advance_migration(root, journal, "complete")
    workspace = _migration_mapping(
        workspace_record["candidate_document"], "workspace candidate"
    )
    replay_record = next(record for record in records if record["kind"] == "approval-replay")
    replay = _migration_mapping(replay_record["candidate_document"], "replay candidate")
    return WorkspaceMigrationResult(
        True,
        MappingProxyType(dict(workspace)),
        MappingProxyType(dict(replay)),
        _transaction_path(root, str(header["transaction_id"])),
    )


def migrate_workspace(
    project_root: Path,
    source_contract: LocalStateContract,
    target_contract: LocalStateContract,
    compatibility: CompatibilityResult,
    snapshot: TaskSnapshotAndFindings,
    *,
    target_manifest: Mapping[str, object],
    source_layout: VerifiedTrellisTaskLayout,
    target_layout: VerifiedTrellisTaskLayout,
    source_schemas: VerifiedDiscoverySchemas,
    target_schemas: VerifiedDiscoverySchemas,
    scanner: TaskQuiescenceScannerPort,
    transaction_id: str,
    recovery_runtime: RuntimeJournalReference,
    relationship_evidence: str = "verified",
    discovery_evidence: str = "verified",
    migration_functions: Mapping[str, LocalStateMigration] | None = None,
) -> WorkspaceMigrationResult:
    """Migrate ignored clone-local state with workspace.json as the commit point."""

    if not isinstance(source_contract, LocalStateContract) or not isinstance(
        target_contract, LocalStateContract
    ):
        raise _migration_recovery_failure("workspace migration contracts are unverified")
    if not isinstance(compatibility, CompatibilityResult):
        raise _migration_recovery_failure("workspace compatibility result is unverified")
    if not isinstance(snapshot, TaskSnapshotAndFindings):
        raise _migration_recovery_failure("workspace task snapshot is unverified")
    transaction_id = _canonical_uuid(transaction_id, "transaction_id")
    edge = _validate_compatibility_result(
        compatibility,
        source_contract,
        target_contract,
        relationship_evidence=relationship_evidence,
        discovery_evidence=discovery_evidence,
    )
    migration_functions = migration_functions or {}
    with acquire_project_locks(project_root):
        workspace = _load_local_document(project_root, _WORKSPACE_PATH)
        replay = _load_local_document(project_root, _REPLAY_PATH)
        if (
            workspace.get("schema_id") != "agent-workflow.workspace-local"
            or replay.get("schema_id") != "agent-workflow.approval-replay"
            or replay.get("project_id") != workspace.get("project_id")
            or replay.get("workspace_instance_id") != workspace.get("workspace_instance_id")
            or not isinstance(replay.get("entries"), Mapping)
        ):
            raise _migration_recovery_failure(
                "workspace/replay source pair is invalid and cannot be reset"
            )
        _workspace_source_contract(workspace, source_contract)
        source_snapshot = {
            "layout_digest": source_layout.layout_digest,
            **dict(source_layout.normalized),
        }
        if workspace.get("trellis_task_layout") != source_snapshot:
            raise _migration_recovery_failure(
                "workspace source Trellis layout snapshot changed"
            )
        project_id, target_manifest_contract = _target_contract_matches_manifest(
            target_manifest, target_layout, target_contract
        )
        if workspace.get("project_id") != project_id:
            raise _migration_recovery_failure("target Manifest project identity changed")
        own_path = _transaction_path(project_root, transaction_id)
        if own_path.exists() or own_path.is_symlink():
            existing = _load_migration_journal(own_path)
            if existing.get("phase") != "complete":
                raise _migration_recovery_failure(
                    "workspace migration transaction requires explicit recovery"
                )
            raise _migration_recovery_failure("workspace migration transaction id is reused")
        external = _unfinished_external_state(project_root, transaction_id)
        current = scanner(
            source_layout, target_layout, source_schemas, target_schemas
        )
        _require_same_migration_snapshot(current, snapshot)
        workspace_state = evaluate_workspace_state_quiescence(
            snapshot.snapshot, snapshot.findings
        )
        task_gate = evaluate_task_gate(
            "workspace-migrate",
            _migration_impact(source_contract, target_contract),
            snapshot.snapshot,
            snapshot.findings,
        )
        diagnostic = build_workspace_diagnostic(
            command="workspace-migrate",
            relationship="migration-required",
            relationship_evidence="verified",
            discovery_evidence="verified",
            workspace_task_state=workspace_state,
            task_gate_result=task_gate,
        )
        if task_gate.primary_evaluator_blocker is not None:
            raise _migration_failure(
                task_gate.primary_evaluator_blocker,
                "workspace task-state gate blocks local-state migration",
                secondary_diagnostics=[
                    blocker.code for blocker in task_gate.blockers[1:]
                ],
            )
        if not diagnostic.command_admission.allowed:
            raise _migration_recovery_failure(
                "workspace diagnostic did not admit the migration command"
            )
        if external is not None:
            raise _migration_recovery_failure(
                "unrelated maintenance or transaction blocks workspace migration",
                path=external,
            )
        target_workspace = _workspace_document(
            target_manifest,
            target_layout,
            project_id,
            str(workspace["workspace_instance_id"]),
            target_manifest_contract,
        )
        records = _build_migration_records(
            project_root,
            workspace,
            replay,
            target_workspace,
            edge,
            migration_functions,
        )
        journal = _migration_journal_document(
            transaction_id=transaction_id,
            project_id=project_id,
            workspace_instance_id=str(workspace["workspace_instance_id"]),
            source_contract=source_contract,
            target_contract=target_contract,
            edge=edge,
            target_manifest=target_manifest,
            source_layout=source_layout,
            target_layout=target_layout,
            source_schemas=source_schemas,
            target_schemas=target_schemas,
            snapshot=snapshot,
            workspace_state=workspace_state,
            task_gate=task_gate,
            diagnostic=diagnostic,
            records=records,
            recovery_runtime=recovery_runtime,
        )
        journal_path = _write_migration_journal(project_root, journal)
        _crash_at("migration_planned")
        result = _finish_workspace_migration(
            project_root,
            journal,
            source_layout=source_layout,
            target_layout=target_layout,
            source_schemas=source_schemas,
            target_schemas=target_schemas,
            scanner=scanner,
            fresh=True,
        )
        return WorkspaceMigrationResult(
            result.committed, result.workspace, result.replay, journal_path
        )


def recover_workspace_migration(
    project_root: Path,
    transaction_id: str,
    *,
    action: str,
    source_layout: VerifiedTrellisTaskLayout,
    target_layout: VerifiedTrellisTaskLayout,
    source_schemas: VerifiedDiscoverySchemas,
    target_schemas: VerifiedDiscoverySchemas,
    scanner: TaskQuiescenceScannerPort,
) -> WorkspaceMigrationResult:
    """Explicitly resume or roll back one exact clone-local migration."""

    transaction_id = _canonical_uuid(transaction_id, "transaction_id")
    if action not in {"resume", "rollback"}:
        raise _migration_recovery_failure("workspace migration recovery action is invalid")
    with acquire_project_locks(project_root):
        path = _transaction_path(project_root, transaction_id)
        journal = _load_migration_journal(path)
        header = _migration_mapping(journal["immutable_header"], "immutable header")
        _validate_recovery_scanner_context(
            header,
            source_layout,
            target_layout,
            source_schemas,
            target_schemas,
        )
        records = [
            _migration_mapping(record, "file record")
            for record in _migration_array(header["file_records"], "file records")
        ]
        workspace_record = records[-1]
        workspace_relation = _record_relation(project_root, workspace_record)
        if action == "rollback":
            if workspace_relation == "candidate":
                raise _migration_recovery_failure(
                    "committed workspace migration cannot be rolled back"
                )
            if workspace_relation == "third":
                raise _migration_recovery_failure(
                    "workspace migration rollback found an external third state"
                )
            restored: list[str] = []
            for record in reversed(records[:-1]):
                relation = _record_relation(project_root, record)
                if relation == "third":
                    raise _migration_recovery_failure(
                        "workspace migration rollback found an external third state",
                        path=record["path"],
                    )
                preimage, candidate, preimage_bytes, _ = _record_states(record)
                if relation == "candidate" and candidate.to_document() != preimage.to_document():
                    compare_and_swap(
                        project_root, candidate, preimage, preimage_bytes
                    )
                restored.append(str(record["path"]))
            changed = _advance_migration(
                project_root,
                journal,
                "cleanup_pending",
                rollback_state={"action": "rollback", "restored_paths": sorted(restored)},
            )
            _advance_migration(project_root, changed, "complete")
            workspace = _migration_mapping(
                workspace_record["preimage_document"], "workspace preimage"
            )
            replay_record = next(
                record for record in records if record["kind"] == "approval-replay"
            )
            replay = _migration_mapping(
                replay_record["preimage_document"], "replay preimage"
            )
            return WorkspaceMigrationResult(
                False,
                MappingProxyType(dict(workspace)),
                MappingProxyType(dict(replay)),
                path,
            )
        return _finish_workspace_migration(
            project_root,
            journal,
            source_layout=source_layout,
            target_layout=target_layout,
            source_schemas=source_schemas,
            target_schemas=target_schemas,
            scanner=scanner,
            fresh=False,
        )
