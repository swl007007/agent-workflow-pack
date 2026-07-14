"""Explicit pre-commit resume/rollback and post-commit forward cleanup."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from agent_stack.core.api import (
    CANONICAL_NULL,
    VerifiedDiscoverySchemas,
    VerifiedTrellisTaskLayout,
    canonical_json_bytes,
)

from .apply import _cleanup_transaction_data, _prepare_backups
from .cas import compare_and_swap, observe_file_state
from .errors import RendererFailure
from .journal import advance_journal, load_journal, transaction_path, write_journal
from .locks import acquire_bootstrap_lock, acquire_project_locks
from .maintenance import maintenance_path, remove_maintenance, write_maintenance
from .models import FileState
from .ports import TaskQuiescenceScannerPort
from .probes import run_write_probe


_PRECOMMIT_PHASES = {"planned", "probing", "prepared", "applying", "files_applied"}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "recovery evidence object is invalid",
            details={"field": field},
        )
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "recovery evidence array is invalid",
            details={"field": field},
        )
    return value


def _marker(journal: Mapping[str, object]) -> dict[str, object]:
    header = _mapping(journal["immutable_header"], "immutable header")
    return {
        "schema_id": "agent-workflow.maintenance-marker",
        "schema_version": 1,
        "transaction_id": header["transaction_id"],
        "journal_binding_digest": journal["journal_binding_digest"],
        "plan_digest": journal["plan_digest"],
        "task_quiescence_digest": header["task_quiescence_digest"],
        "candidate_manifest_generation": header["candidate_manifest_generation"],
    }


def _manifest_committed(root: Path, journal: Mapping[str, object]) -> bool:
    path = root / ".agent-workflow" / "manifest.json"
    if path.is_symlink():
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "Manifest path became a symlink"
        )
    if not path.is_file():
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "Manifest is invalid during recovery"
        ) from error
    if not isinstance(manifest, Mapping):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "Manifest is not an object"
        )
    header = _mapping(journal["immutable_header"], "immutable header")
    return (
        manifest.get("generation") == header.get("candidate_manifest_generation")
        and manifest.get("last_transaction_id") == header.get("transaction_id")
        and manifest.get("last_transaction_binding_digest")
        == journal.get("journal_binding_digest")
    )


def _physical_projection(state: FileState) -> tuple[object, ...]:
    return (
        state.path,
        state.exists,
        state.file_type,
        state.byte_hash,
        state.mode,
        state.non_symlink,
    )


def _current_matches(root: Path, expected: FileState) -> bool:
    try:
        current = observe_file_state(root, expected.path)
    except RendererFailure:
        return False
    return _physical_projection(current) == _physical_projection(expected)


def _candidate_content(record: Mapping[str, object]) -> bytes | None:
    raw = record.get("candidate_content_utf8")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "journal candidate content is invalid"
        )
    return raw.encode("utf-8")


def _backup_content(root: Path, record: Mapping[str, object], original: FileState) -> bytes | None:
    if not original.exists:
        return None
    raw_path = record.get("backup_path")
    if not isinstance(raw_path, str):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "journal backup path is missing"
        )
    backup = root / raw_path
    if backup.is_symlink() or not backup.is_file():
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "journal backup is unavailable"
        )
    payload = backup.read_bytes()
    if __import__("hashlib").sha256(payload).hexdigest() != original.byte_hash:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "journal backup bytes changed"
        )
    return payload


def _rollback_files(root: Path, records: list[dict[str, object]]) -> None:
    for record in reversed(records):
        original = FileState.from_document(
            _mapping(record["original_state"], "original state")
        )
        candidate = FileState.from_document(
            _mapping(record["candidate_state"], "candidate state")
        )
        if _current_matches(root, original):
            record["applied"] = False
            continue
        if not _current_matches(root, candidate):
            raise RendererFailure(
                "AWP_ROLLBACK_CONFLICT",
                "current state is neither original nor candidate",
                details={"path": original.path},
            )
        compare_and_swap(
            root,
            candidate,
            original,
            _backup_content(root, record, original),
        )
        record["applied"] = False


def _resume_files(root: Path, records: list[dict[str, object]]) -> None:
    for record in records:
        original = FileState.from_document(
            _mapping(record["original_state"], "original state")
        )
        candidate = FileState.from_document(
            _mapping(record["candidate_state"], "candidate state")
        )
        if _current_matches(root, candidate):
            record["applied"] = True
            continue
        if not _current_matches(root, original):
            raise RendererFailure(
                "AWP_FILE_CAS_MISMATCH",
                "resume current state is neither original nor candidate",
                details={"path": original.path},
            )
        compare_and_swap(root, original, candidate, _candidate_content(record))
        record["applied"] = True


def _cleanup_created_directories(root: Path, directories: Sequence[object]) -> None:
    normalized = sorted((str(item) for item in directories), key=lambda item: item.count("/"), reverse=True)
    for relative in normalized:
        path = root / relative
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_dir() or any(path.iterdir()):
            raise RendererFailure(
                "AWP_ROLLBACK_CONFLICT",
                "transaction-created directory changed or is not empty",
                details={"path": relative},
            )
        path.rmdir()


def _remove_marker_if_present(root: Path, marker: Mapping[str, object]) -> None:
    path = maintenance_path(root)
    if path.exists() or path.is_symlink():
        remove_maintenance(root, marker)


def _ensure_marker(
    root: Path, journal: Mapping[str, object], *, allow_create: bool
) -> dict[str, object]:
    marker = _marker(journal)
    path = maintenance_path(root)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != canonical_json_bytes(marker):
            raise RendererFailure(
                "AWP_MAINTENANCE_CORRUPT", "maintenance marker binding changed"
            )
        return marker
    if not allow_create:
        raise RendererFailure(
            "AWP_MAINTENANCE_CORRUPT", "maintenance marker is missing after apply began"
        )
    write_maintenance(root, marker)
    return marker


def _scanner_inputs(
    context: Mapping[str, object] | None,
) -> tuple[
    VerifiedTrellisTaskLayout,
    VerifiedTrellisTaskLayout,
    VerifiedDiscoverySchemas,
    VerifiedDiscoverySchemas,
]:
    if context is None:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "resume lacks scanner context"
        )
    source_layout = context.get("source_layout")
    target_layout = context.get("target_layout")
    source_schemas = context.get("source_schemas")
    target_schemas = context.get("target_schemas")
    if not isinstance(source_layout, VerifiedTrellisTaskLayout) or not isinstance(
        target_layout, VerifiedTrellisTaskLayout
    ):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "resume lacks verified layouts"
        )
    if not isinstance(source_schemas, VerifiedDiscoverySchemas) or not isinstance(
        target_schemas, VerifiedDiscoverySchemas
    ):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "resume lacks verified schemas"
        )
    return source_layout, target_layout, source_schemas, target_schemas


def _require_recovery_scan(
    scanner: TaskQuiescenceScannerPort | None,
    context: Mapping[str, object] | None,
    journal: Mapping[str, object],
) -> None:
    if scanner is None:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "resume scanner port is not bound"
        )
    source_layout, target_layout, source_schemas, target_schemas = _scanner_inputs(context)
    actual = scanner(source_layout, target_layout, source_schemas, target_schemas)
    expected = _mapping(journal["task_quiescence_snapshot"], "task snapshot")
    actual_document = {
        "snapshot": dict(actual.snapshot),
        "findings": dict(actual.findings),
        "task_quiescence_digest": actual.task_quiescence_digest,
    }
    if canonical_json_bytes(actual_document) != canonical_json_bytes(expected):
        raise RendererFailure(
            "AWP_TASK_QUIESCENCE_CHANGED", "task evidence changed during resume"
        )


def _apply_manifest_from_journal(root: Path, journal: Mapping[str, object]) -> None:
    header = _mapping(journal["immutable_header"], "immutable header")
    operation = str(header["operation"])
    expected = (
        FileState(
            ".agent-workflow/manifest.json",
            False,
            "absent",
            CANONICAL_NULL,
            CANONICAL_NULL,
            True,
        )
        if operation == "init"
        else FileState(
            ".agent-workflow/manifest.json",
            True,
            "regular",
            str(header["baseline_manifest_digest"]),
            "0644",
            True,
        )
    )
    candidate = FileState(
        ".agent-workflow/manifest.json",
        True,
        "regular",
        str(journal["candidate_manifest_digest"]),
        "0644",
        True,
    )
    compare_and_swap(
        root,
        expected,
        candidate,
        canonical_json_bytes(_mapping(journal["candidate_manifest"], "candidate Manifest")),
    )


@contextmanager
def _recovery_locks(
    root: Path,
    journal: Mapping[str, object],
    context: Mapping[str, object] | None,
) -> Iterator[None]:
    header = _mapping(journal["immutable_header"], "immutable header")
    if header.get("operation") == "init":
        if context is None or not isinstance(context.get("bootstrap_lock_root"), str):
            raise RendererFailure(
                "AWP_RECONCILE_LOCKED", "init recovery lacks bootstrap lock root"
            )
        with acquire_bootstrap_lock(root, Path(str(context["bootstrap_lock_root"]))):
            with acquire_project_locks(root):
                yield
    else:
        with acquire_project_locks(root):
            yield


def _cleanup_committed(
    root: Path, journal: dict[str, object], records: list[dict[str, object]]
) -> dict[str, object]:
    marker = _marker(journal)
    if journal["phase"] not in {"cleanup_pending", "complete"}:
        journal = advance_journal(journal, "manifest_committed", file_records=records)
        write_journal(root, journal)
        journal = advance_journal(journal, "cleanup_pending", file_records=records)
        write_journal(root, journal)
    _remove_marker_if_present(root, marker)
    _cleanup_transaction_data(root, records)
    if journal["phase"] != "complete":
        journal = advance_journal(journal, "complete", file_records=records)
        write_journal(root, journal)
    return journal


def recover_transaction(
    transaction_id: str,
    action: str,
    *,
    root: Path | None = None,
    scanner: TaskQuiescenceScannerPort | None = None,
    scanner_context: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    if action not in {"resume", "rollback"}:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "recovery action must be explicit"
        )
    project_root = Path.cwd() if root is None else root
    journal = load_journal(transaction_path(project_root, transaction_id))
    records = [
        dict(_mapping(item, "file record"))
        for item in _sequence(journal["file_records"], "file records")
    ]
    with _recovery_locks(project_root, journal, scanner_context):
        committed = _manifest_committed(project_root, journal)
        if committed:
            if action == "rollback":
                raise RendererFailure(
                    "AWP_RECONCILE_RECOVERY_REQUIRED",
                    "committed transaction cannot be rolled back",
                )
            _cleanup_committed(project_root, journal, records)
            return {
                "schema_id": "agent-workflow.reconcile-recovery-result",
                "schema_version": 1,
                "transaction_id": transaction_id,
                "committed": True,
                "rolled_back": False,
            }
        phase = str(journal["phase"])
        if phase not in _PRECOMMIT_PHASES:
            raise RendererFailure(
                "AWP_RECONCILE_RECOVERY_REQUIRED",
                "journal claims post-commit without a matching Manifest",
            )
        if action == "rollback":
            _rollback_files(project_root, records)
            _cleanup_created_directories(
                project_root,
                _sequence(journal["created_directories"], "created directories"),
            )
            _remove_marker_if_present(project_root, _marker(journal))
            _cleanup_transaction_data(project_root, records)
            journal = advance_journal(
                journal,
                "complete",
                file_records=records,
                rollback_state={"status": "rolled-back"},
            )
            write_journal(project_root, journal)
            return {
                "schema_id": "agent-workflow.reconcile-recovery-result",
                "schema_version": 1,
                "transaction_id": transaction_id,
                "committed": False,
                "rolled_back": True,
            }

        if phase in {"planned", "probing"}:
            journal = advance_journal(journal, "probing", file_records=records)
            write_journal(project_root, journal)
            run_write_probe(project_root, probe_id=transaction_id)
            _prepare_backups(
                project_root,
                records,
                [
                    str(item)
                    for item in _sequence(
                        journal["created_directories"], "created directories"
                    )
                ],
            )
            journal = advance_journal(journal, "prepared", file_records=records)
            write_journal(project_root, journal)
            phase = "prepared"
        marker = _ensure_marker(
            project_root,
            journal,
            allow_create=phase == "prepared",
        )
        if phase == "prepared":
            journal = advance_journal(journal, "applying", file_records=records)
            write_journal(project_root, journal)
        _resume_files(project_root, records)
        journal = advance_journal(journal, "files_applied", file_records=records)
        write_journal(project_root, journal)
        _require_recovery_scan(scanner, scanner_context, journal)
        _apply_manifest_from_journal(project_root, journal)
        journal = advance_journal(journal, "manifest_committed", file_records=records)
        write_journal(project_root, journal)
        journal = advance_journal(journal, "cleanup_pending", file_records=records)
        write_journal(project_root, journal)
        _remove_marker_if_present(project_root, marker)
        _cleanup_transaction_data(project_root, records)
        journal = advance_journal(journal, "complete", file_records=records)
        write_journal(project_root, journal)
        return {
            "schema_id": "agent-workflow.reconcile-recovery-result",
            "schema_version": 1,
            "transaction_id": transaction_id,
            "committed": True,
            "rolled_back": False,
        }
