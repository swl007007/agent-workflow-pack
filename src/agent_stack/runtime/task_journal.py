"""Closed task-transaction journal storage and phase transitions."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from agent_stack.core.api import canonical_json_bytes, digest

from .errors import RuntimeFailure


_ROOT = ".agent-workflow/task-transactions"
_PHASES = {
    "admit": {
        "planned": 0,
        "staged": 1,
        "task_moved": 2,
        "metadata_applied": 3,
        "admission_committed": 4,
        "cleanup_pending": 5,
        "complete": 6,
    },
    "claim": {"planned": 0, "integration_committed": 1, "cleanup_pending": 2, "complete": 3},
    "transition": {
        "planned": 0,
        "integration_committed": 1,
        "cleanup_pending": 2,
        "complete": 3,
    },
    "release": {
        "planned": 0,
        "integration_committed": 1,
        "cleanup_pending": 2,
        "complete": 3,
    },
    "archive": {
        "planned": 0,
        "state_marked": 1,
        "task_moved": 2,
        "metadata_applied": 3,
        "archive_committed": 4,
        "cleanup_pending": 5,
        "complete": 6,
    },
}


def _failure(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure("AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", message, details=details)


def journal_path(root: Path, transaction_id: str) -> Path:
    try:
        canonical = str(uuid.UUID(transaction_id))
    except ValueError as error:
        raise _failure("task transaction ID is invalid") from error
    if canonical != transaction_id:
        raise _failure("task transaction ID is not canonical")
    return root / _ROOT / f"{canonical}.json"


def _atomic_json(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise _failure("task transaction root is a symlink")
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


def _validate(document: object, expected_transaction_id: str | None = None) -> dict[str, object]:
    if not isinstance(document, Mapping) or set(document) != {
        "schema_id",
        "schema_version",
        "transaction_id",
        "operation",
        "task_id",
        "task_ref",
        "immutable_header",
        "journal_binding_digest",
        "phase",
        "outcome",
        "diagnostics",
        "rollback_state",
    }:
        raise _failure("task journal fields are not closed")
    if document.get("schema_id") != "agent-workflow.task-transaction" or document.get(
        "schema_version"
    ) != 1:
        raise _failure("task journal schema is unsupported")
    transaction_id = document.get("transaction_id")
    if not isinstance(transaction_id, str):
        raise _failure("task journal transaction ID is invalid")
    journal_path(Path("."), transaction_id)
    if expected_transaction_id is not None and transaction_id != expected_transaction_id:
        raise _failure("task journal path identity differs")
    operation = document.get("operation")
    phase = document.get("phase")
    if not isinstance(operation, str) or operation not in _PHASES:
        raise _failure("task journal operation is invalid")
    if not isinstance(phase, str) or phase not in _PHASES[operation]:
        raise _failure("task journal phase is invalid", operation=operation, phase=phase)
    header = document.get("immutable_header")
    if not isinstance(header, Mapping):
        raise _failure("task journal immutable header is invalid")
    claimed = document.get("journal_binding_digest")
    actual = digest("agent-workflow.task-transaction.v1", header)
    if claimed != actual:
        raise _failure("task journal immutable binding changed")
    if document.get("task_id") != header.get("task_id") or document.get("task_ref") != header.get(
        "task_ref"
    ):
        raise _failure("task journal identity differs from immutable header")
    if not isinstance(document.get("diagnostics"), list) or not isinstance(
        document.get("rollback_state"), Mapping
    ):
        raise _failure("task journal mutable state is invalid")
    outcome = document.get("outcome")
    if outcome not in {None, "committed", "rolled-back"}:
        raise _failure("task journal outcome is invalid")
    if phase == "complete" and outcome is None:
        raise _failure("complete task journal has no outcome")
    return cast(dict[str, object], dict(document))


def create_task_journal(
    root: Path,
    *,
    transaction_id: str,
    operation: str,
    task_id: str,
    task_ref: str,
    immutable_header: Mapping[str, object],
) -> dict[str, object]:
    """Create the planned journal before any task/replay/metadata mutation."""

    path = journal_path(root, transaction_id)
    if path.exists() or path.is_symlink():
        raise _failure("task transaction already exists", transaction_id=transaction_id)
    if operation not in _PHASES:
        raise _failure("task journal operation is invalid")
    document: dict[str, object] = {
        "schema_id": "agent-workflow.task-transaction",
        "schema_version": 1,
        "transaction_id": transaction_id,
        "operation": operation,
        "task_id": task_id,
        "task_ref": task_ref,
        "immutable_header": dict(immutable_header),
        "journal_binding_digest": digest(
            "agent-workflow.task-transaction.v1", immutable_header
        ),
        "phase": "planned",
        "outcome": None,
        "diagnostics": [],
        "rollback_state": {},
    }
    _validate(document, transaction_id)
    _atomic_json(path, document)
    return document


def read_task_journal(root: Path, transaction_id: str) -> dict[str, object]:
    path = journal_path(root, transaction_id)
    if path.is_symlink() or not path.is_file():
        raise _failure("task journal is missing or has invalid type")
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _failure("task journal is corrupt") from error
    if canonical_json_bytes(document) != payload:
        raise _failure("task journal is not canonical")
    return _validate(document, transaction_id)


def advance_task_journal(
    root: Path,
    document: Mapping[str, object],
    phase: str,
    *,
    outcome: str | None = None,
    rollback_state: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Advance one closed phase without changing immutable transaction identity."""

    current = _validate(document)
    operation = cast(str, current["operation"])
    current_phase = cast(str, current["phase"])
    if phase not in _PHASES[operation] or _PHASES[operation][phase] < _PHASES[operation][
        current_phase
    ]:
        raise _failure("task journal phase would move backward")
    candidate = dict(current)
    candidate["phase"] = phase
    if outcome is not None:
        candidate["outcome"] = outcome
    if rollback_state is not None:
        candidate["rollback_state"] = dict(rollback_state)
    candidate = _validate(candidate, cast(str, candidate["transaction_id"]))
    _atomic_json(
        journal_path(root, cast(str, candidate["transaction_id"])), candidate
    )
    return candidate


def unfinished_task_journals(root: Path) -> tuple[dict[str, object], ...]:
    directory = root / _ROOT
    if not directory.exists():
        return ()
    if directory.is_symlink() or not directory.is_dir():
        raise _failure("task transaction root has invalid type")
    journals: list[dict[str, object]] = []
    for path in sorted(directory.iterdir()):
        if path.suffix != ".json":
            raise _failure("task transaction root contains an unknown entry")
        journal = read_task_journal(root, path.stem)
        if journal["phase"] != "complete":
            journals.append(journal)
    return tuple(journals)
