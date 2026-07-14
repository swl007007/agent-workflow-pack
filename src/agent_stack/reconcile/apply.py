"""Manifest-last lifecycle apply with injected task-quiescence scanner port."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from agent_stack.core.api import (
    SavedPlanEnvelope,
    TaskSnapshotAndFindings,
    VerifiedDiscoverySchemas,
    VerifiedTrellisTaskLayout,
    canonical_json_bytes,
    validate_saved_plan_envelope,
)

from .cas import compare_and_swap
from .errors import RendererFailure
from .journal import advance_journal, build_lifecycle_journal, write_journal
from .locks import acquire_bootstrap_lock, acquire_project_locks
from .maintenance import (
    build_maintenance_marker,
    remove_maintenance,
    write_maintenance,
)
from .manifest import apply_candidate_manifest
from .models import FileState
from .plan import render_candidate_manifest
from .ports import TaskQuiescenceScannerPort
from .probes import run_write_probe
from .local_state import build_first_init_local_state


def _crash_at(point: str) -> None:
    """Test seam; production code never selects a crash point."""


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "apply context object is invalid",
            details={"field": field},
        )
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "apply context array is invalid",
            details={"field": field},
        )
    return value


def _task_state_document(value: TaskSnapshotAndFindings) -> dict[str, object]:
    return {
        "snapshot": dict(value.snapshot),
        "findings": dict(value.findings),
        "task_quiescence_digest": value.task_quiescence_digest,
    }


def _expected_task_state(envelope: SavedPlanEnvelope) -> dict[str, object]:
    return {
        "snapshot": dict(
            _mapping(
                envelope.plan_core["task_quiescence_snapshot"],
                "task_quiescence_snapshot",
            )
        ),
        "findings": dict(
            _mapping(envelope.plan_core["task_findings"], "task_findings")
        ),
        "task_quiescence_digest": envelope.plan_core["task_quiescence_digest"],
    }


def _scan(
    scanner: TaskQuiescenceScannerPort,
    source_layout: VerifiedTrellisTaskLayout,
    target_layout: VerifiedTrellisTaskLayout,
    source_schemas: VerifiedDiscoverySchemas,
    target_schemas: VerifiedDiscoverySchemas,
) -> TaskSnapshotAndFindings:
    return scanner(source_layout, target_layout, source_schemas, target_schemas)


def _require_same_task_state(
    actual: TaskSnapshotAndFindings, expected: Mapping[str, object]
) -> None:
    if canonical_json_bytes(_task_state_document(actual)) != canonical_json_bytes(expected):
        raise RendererFailure(
            "AWP_TASK_QUIESCENCE_CHANGED",
            "task quiescence evidence changed during reconcile apply",
            details={"latest_task_quiescence_digest": actual.task_quiescence_digest},
        )


def _is_true_noop(envelope: SavedPlanEnvelope) -> bool:
    if envelope.operation != "sync" or envelope.plan_core["candidate_file_states"]:
        return False
    stable_reasons = {
        "already-current",
        "create-once-already-consumed",
        "user-owned-no-write-authority",
        "adopted-drift-is-observed",
    }
    file_preconditions = [
        _mapping(item, "file precondition")
        for item in _sequence(envelope.plan_core["preconditions"], "preconditions")
        if isinstance(item, Mapping) and item.get("kind") == "file"
    ]
    return all(
        _mapping(item.get("ownership_decision"), "ownership decision").get("action")
        == "no-op"
        and _mapping(item.get("ownership_decision"), "ownership decision").get(
            "reason_code"
        )
        in stable_reasons
        for item in file_preconditions
    )


def _file_records(
    envelope: SavedPlanEnvelope,
    candidate_manifest: Mapping[str, object],
    target_layout: VerifiedTrellisTaskLayout,
) -> list[dict[str, object]]:
    candidate_states = {
        str(raw["path"]): FileState.from_document(_mapping(raw, "candidate file state"))
        for raw in _sequence(
            envelope.plan_core["candidate_file_states"], "candidate file states"
        )
        if isinstance(raw, Mapping)
    }
    transaction_id = str(envelope.plan_core["transaction_id"])
    records: list[dict[str, object]] = []
    for raw in _sequence(envelope.plan_core["preconditions"], "preconditions"):
        precondition = _mapping(raw, "precondition")
        if precondition.get("kind") != "file":
            continue
        path = str(precondition.get("path"))
        candidate = candidate_states.get(path)
        if candidate is None:
            continue
        decision = _mapping(precondition.get("ownership_decision"), "ownership decision")
        original = FileState.from_document(
            _mapping(decision.get("observed_file_state"), "observed file state")
        )
        content = precondition.get("candidate_content_utf8")
        if content is not None and not isinstance(content, str):
            raise RendererFailure(
                "AWP_RECONCILE_RECOVERY_REQUIRED", "candidate content is not UTF-8 text"
            )
        records.append(
            {
                "path": path,
                "original_state": original.to_document(),
                "candidate_state": candidate.to_document(),
                "candidate_content_utf8": content,
                "backup_path": (
                    None
                    if not original.exists
                    else f".agent-workflow/transactions/{transaction_id}.data/backups/{len(records):04d}.bin"
                ),
                "backup_byte_hash": None,
                "applied": False,
            }
        )
    if envelope.operation == "init":
        workspace, replay = build_first_init_local_state(
            candidate_manifest,
            target_layout,
            str(envelope.plan_core["candidate_workspace_instance_id"]),
            str(envelope.plan_core["empty_replay_ledger_candidate_digest"]),
        )
        for path, document in (
            (".agent-workflow/local/workspace.json", workspace),
            (".agent-workflow/local/approval-replay.json", replay),
        ):
            payload = canonical_json_bytes(document)
            records.append(
                {
                    "path": path,
                    "original_state": FileState(
                        path,
                        False,
                        "absent",
                        "canonical-null",
                        "canonical-null",
                        True,
                    ).to_document(),
                    "candidate_state": FileState(
                        path,
                        True,
                        "regular",
                        hashlib.sha256(payload).hexdigest(),
                        "0600",
                        True,
                    ).to_document(),
                    "candidate_content_utf8": payload.decode("utf-8"),
                    "backup_path": None,
                    "backup_byte_hash": None,
                    "applied": False,
                }
            )
    return records


def _created_directories(root: Path, records: Sequence[Mapping[str, object]]) -> list[str]:
    created: set[str] = set()
    for record in records:
        candidate = FileState.from_document(
            _mapping(record.get("candidate_state"), "candidate state")
        )
        if not candidate.exists:
            continue
        parent = Path(candidate.path).parent
        chain: list[Path] = []
        while str(parent) != ".":
            chain.append(parent)
            parent = parent.parent
        for relative in reversed(chain):
            absolute = root / relative
            if absolute.is_symlink():
                raise RendererFailure(
                    "AWP_FILE_CAS_MISMATCH", "candidate directory path is a symlink"
                )
            if absolute.exists() and not absolute.is_dir():
                raise RendererFailure(
                    "AWP_FILE_CAS_MISMATCH", "candidate directory path is not a directory"
                )
            if not absolute.exists():
                created.add(relative.as_posix())
    return sorted(created, key=lambda value: (value.count("/"), value))


def _prepare_backups(
    root: Path, records: list[dict[str, object]], created_directories: Sequence[str]
) -> None:
    for relative in created_directories:
        (root / relative).mkdir()
    for record in records:
        original = FileState.from_document(
            _mapping(record["original_state"], "original state")
        )
        backup_value = record["backup_path"]
        if not original.exists or not isinstance(backup_value, str):
            continue
        source = root / original.path
        if source.is_symlink() or not source.is_file():
            raise RendererFailure("AWP_FILE_CAS_MISMATCH", "backup source changed type")
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != original.byte_hash:
            raise RendererFailure("AWP_FILE_CAS_MISMATCH", "backup source bytes changed")
        backup = root / backup_value
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(payload)
        os.chmod(backup, int(original.mode, 8))
        record["backup_byte_hash"] = original.byte_hash


def _apply_file_records(root: Path, records: list[dict[str, object]]) -> None:
    for record in records:
        original = FileState.from_document(
            _mapping(record["original_state"], "original state")
        )
        candidate = FileState.from_document(
            _mapping(record["candidate_state"], "candidate state")
        )
        raw_content = record["candidate_content_utf8"]
        content = None if raw_content is None else str(raw_content).encode("utf-8")
        compare_and_swap(root, original, candidate, content)
        record["applied"] = True
        if candidate.path == ".agent-workflow/local/workspace.json":
            _crash_at("after_workspace")
        elif candidate.path == ".agent-workflow/local/approval-replay.json":
            _crash_at("after_replay")


def _cleanup_transaction_data(root: Path, records: Sequence[Mapping[str, object]]) -> None:
    directories: set[Path] = set()
    for record in records:
        backup_value = record.get("backup_path")
        if not isinstance(backup_value, str):
            continue
        backup = root / backup_value
        if backup.exists():
            if backup.is_symlink() or not backup.is_file():
                raise RendererFailure(
                    "AWP_RECONCILE_RECOVERY_REQUIRED", "backup path changed type"
                )
            backup.unlink()
        directories.add(backup.parent)
        directories.add(backup.parent.parent)
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        if directory.exists():
            directory.rmdir()


@contextmanager
def _apply_locks(
    root: Path, envelope: SavedPlanEnvelope, approval: Mapping[str, object]
) -> Iterator[None]:
    if envelope.operation == "init":
        raw_lock_root = approval.get("bootstrap_lock_root")
        if not isinstance(raw_lock_root, str):
            raise RendererFailure(
                "AWP_RECONCILE_LOCKED", "init apply lacks bootstrap lock root"
            )
        with acquire_bootstrap_lock(root, Path(raw_lock_root)):
            with acquire_project_locks(root):
                yield
    else:
        with acquire_project_locks(root):
            yield


def apply_plan(
    saved_plan: SavedPlanEnvelope,
    approval: Mapping[str, object] | None = None,
    *,
    scanner: TaskQuiescenceScannerPort | None = None,
) -> Mapping[str, object]:
    if approval is None or approval.get("plan_digest") != saved_plan.plan_digest:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "apply approval does not bind the saved plan"
        )
    candidate_manifest = render_candidate_manifest(saved_plan)
    validate_saved_plan_envelope(saved_plan.to_document(), candidate_manifest)
    if _is_true_noop(saved_plan):
        return {
            "schema_id": "agent-workflow.reconcile-result",
            "schema_version": 1,
            "transaction_id": saved_plan.plan_core["transaction_id"],
            "committed": False,
            "no_op": True,
        }
    if scanner is None:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "production scanner port is not bound"
        )
    raw_root = approval.get("project_root")
    if not isinstance(raw_root, str):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "apply context lacks project root"
        )
    root = Path(raw_root)
    source_layout = approval.get("source_layout")
    target_layout = approval.get("target_layout")
    source_schemas = approval.get("source_schemas")
    target_schemas = approval.get("target_schemas")
    if not isinstance(source_layout, VerifiedTrellisTaskLayout) or not isinstance(
        target_layout, VerifiedTrellisTaskLayout
    ):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "apply context lacks verified layouts"
        )
    if not isinstance(source_schemas, VerifiedDiscoverySchemas) or not isinstance(
        target_schemas, VerifiedDiscoverySchemas
    ):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "apply context lacks verified schemas"
        )
    expected_task_state = _expected_task_state(saved_plan)

    with _apply_locks(root, saved_plan, approval):
        initial = _scan(
            scanner, source_layout, target_layout, source_schemas, target_schemas
        )
        _require_same_task_state(initial, expected_task_state)
        records = _file_records(saved_plan, candidate_manifest, target_layout)
        created_directories = _created_directories(root, records)
        journal = build_lifecycle_journal(
            saved_plan,
            candidate_manifest,
            file_records=records,
            created_directories=created_directories,
        )
        write_journal(root, journal)
        _crash_at("planned")

        journal = advance_journal(journal, "probing")
        write_journal(root, journal)
        _crash_at("probing")
        run_write_probe(root, probe_id=str(saved_plan.plan_core["transaction_id"]))

        _prepare_backups(root, records, created_directories)
        journal = advance_journal(journal, "prepared", file_records=records)
        write_journal(root, journal)
        marker = build_maintenance_marker(saved_plan)
        write_maintenance(root, marker)
        _crash_at("prepared")

        journal = advance_journal(journal, "applying", file_records=records)
        write_journal(root, journal)
        _crash_at("applying")
        _apply_file_records(root, records)
        journal = advance_journal(journal, "files_applied", file_records=records)
        write_journal(root, journal)
        _crash_at("files_applied")

        final = _scan(
            scanner, source_layout, target_layout, source_schemas, target_schemas
        )
        _require_same_task_state(final, expected_task_state)
        _crash_at("before_manifest")
        apply_candidate_manifest(root, saved_plan)
        _crash_at("after_manifest")

        journal = advance_journal(journal, "manifest_committed", file_records=records)
        write_journal(root, journal)
        _crash_at("manifest_committed")
        journal = advance_journal(journal, "cleanup_pending", file_records=records)
        write_journal(root, journal)
        _crash_at("cleanup_pending")

        remove_maintenance(root, marker)
        _cleanup_transaction_data(root, records)
        journal = advance_journal(journal, "complete", file_records=records)
        write_journal(root, journal)
        return {
            "schema_id": "agent-workflow.reconcile-result",
            "schema_version": 1,
            "transaction_id": saved_plan.plan_core["transaction_id"],
            "committed": True,
            "no_op": False,
        }
