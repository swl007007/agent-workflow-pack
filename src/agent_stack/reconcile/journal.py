"""Durable lifecycle journal construction and immutable-header-preserving updates."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from agent_stack.core.api import SavedPlanEnvelope, canonical_json_bytes

from .errors import RendererFailure
from .models import LifecycleJournal


_PHASE_ORDER = {
    "planned": 0,
    "probing": 1,
    "prepared": 2,
    "applying": 3,
    "files_applied": 4,
    "manifest_committed": 5,
    "cleanup_pending": 6,
    "complete": 7,
}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "journal evidence object is invalid",
            details={"field": field},
        )
    return value


def build_lifecycle_journal(
    envelope: SavedPlanEnvelope,
    candidate_manifest: Mapping[str, object],
    *,
    file_records: Sequence[Mapping[str, object]],
    created_directories: Sequence[str],
) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.lifecycle-transaction",
        "schema_version": 1,
        "immutable_header": dict(envelope.immutable_header),
        "journal_binding_digest": envelope.journal_binding_digest,
        "task_quiescence_snapshot": {
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
        },
        "plan_digest": envelope.plan_digest,
        "candidate_manifest_digest": envelope.candidate_manifest_digest,
        "candidate_manifest": dict(candidate_manifest),
        "phase": "planned",
        "file_records": [dict(record) for record in file_records],
        "created_directories": list(created_directories),
        "diagnostics": [],
        "rollback_state": {},
    }


def transaction_path(root: Path, transaction_id: str) -> Path:
    return root / ".agent-workflow" / "transactions" / f"{transaction_id}.json"


def _atomic_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_temporary)
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


def load_journal(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "lifecycle journal is unavailable"
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "lifecycle journal is invalid"
        ) from error
    if not isinstance(document, dict):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "lifecycle journal is not an object"
        )
    LifecycleJournal.from_document(document)
    return document


def write_journal(root: Path, document: Mapping[str, object]) -> Path:
    validated = LifecycleJournal.from_document(document)
    transaction_id = str(validated.immutable_header["transaction_id"])
    path = transaction_path(root, transaction_id)
    if path.exists() or path.is_symlink():
        existing = load_journal(path)
        immutable_fields = (
            "immutable_header",
            "journal_binding_digest",
            "task_quiescence_snapshot",
            "plan_digest",
            "candidate_manifest_digest",
            "candidate_manifest",
            "created_directories",
        )
        if any(existing[field] != document[field] for field in immutable_fields):
            raise RendererFailure(
                "AWP_RECONCILE_RECOVERY_REQUIRED",
                "lifecycle journal immutable evidence changed",
            )
        if _PHASE_ORDER[str(document["phase"])] < _PHASE_ORDER[str(existing["phase"])]:
            raise RendererFailure(
                "AWP_RECONCILE_RECOVERY_REQUIRED", "lifecycle journal phase regressed"
            )
    _atomic_json(path, document)
    return path


def advance_journal(
    document: Mapping[str, object],
    phase: str,
    *,
    file_records: Sequence[Mapping[str, object]] | None = None,
    diagnostics: Sequence[Mapping[str, object]] | None = None,
    rollback_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if phase not in _PHASE_ORDER:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "lifecycle phase is invalid"
        )
    changed = dict(document)
    changed["phase"] = phase
    if file_records is not None:
        changed["file_records"] = [dict(record) for record in file_records]
    if diagnostics is not None:
        changed["diagnostics"] = [dict(item) for item in diagnostics]
    if rollback_state is not None:
        changed["rollback_state"] = dict(rollback_state)
    LifecycleJournal.from_document(changed)
    return changed
