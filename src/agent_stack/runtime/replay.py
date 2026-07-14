"""Monotonic approval-proof replay ledger transitions."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from agent_stack.core.api import CANONICAL_NULL, canonical_json_bytes
from agent_stack.reconcile.cas import compare_and_swap, observe_file_state
from agent_stack.reconcile.models import FileState

from .errors import RuntimeFailure


_REPLAY_PATH = ".agent-workflow/local/approval-replay.json"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReplayEntry:
    """One immutable proof binding with a monotonic delivery state."""

    proof_key: str
    bound_transaction_id: str
    state: str
    validated_at: str
    proof_expires_at: str
    consumed_at: str | None


def _failure(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure("AWP_APPROVAL_REPLAY_BLOCKED", message, details=details)


def _canonical_uuid(value: str, field: str) -> str:
    try:
        parsed = str(uuid.UUID(value))
    except (AttributeError, ValueError) as error:
        raise _failure("approval replay UUID is invalid", field=field) from error
    if parsed != value:
        raise _failure("approval replay UUID is not canonical", field=field)
    return value


def _sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise _failure("approval replay digest is invalid", field=field)
    return value


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise _failure("approval replay time is not timezone aware", field=field)
    return value.astimezone(UTC)


def _format(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise _failure("approval replay timestamp is invalid", field=field)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise _failure("approval replay timestamp is invalid", field=field) from error
    return parsed.astimezone(UTC)


def proof_key(
    approval_id: str,
    approval_challenge: str,
    route_decision_digest: str,
    workspace_instance_id: str,
) -> str:
    """Compute the transaction-independent proof identity."""

    projection = {
        "approval_id": _canonical_uuid(approval_id, "approval_id"),
        "approval_challenge": _sha256(approval_challenge, "approval_challenge"),
        "route_decision_digest": _sha256(route_decision_digest, "route_decision_digest"),
        "workspace_instance_id": _canonical_uuid(
            workspace_instance_id, "workspace_instance_id"
        ),
    }
    return hashlib.sha256(canonical_json_bytes(projection)).hexdigest()


def _load(root: Path, project_id: str | None = None, workspace_id: str | None = None) -> tuple[
    dict[str, object], FileState
]:
    state = observe_file_state(root, _REPLAY_PATH)
    path = root / _REPLAY_PATH
    if not state.exists or state.file_type != "regular" or state.mode != "0600":
        raise _failure("registered approval replay ledger is missing or has invalid metadata")
    try:
        payload = path.read_bytes()
        parsed = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _failure("registered approval replay ledger is corrupt") from error
    if not isinstance(parsed, dict) or canonical_json_bytes(parsed) != payload:
        raise _failure("registered approval replay ledger is not canonical")
    if set(parsed) != {
        "schema_id",
        "schema_version",
        "project_id",
        "workspace_instance_id",
        "entries",
    }:
        raise _failure("approval replay ledger fields are not closed")
    if parsed.get("schema_id") != "agent-workflow.approval-replay" or parsed.get(
        "schema_version"
    ) != 1:
        raise _failure("approval replay ledger schema is unsupported")
    actual_project = _canonical_uuid(cast(str, parsed.get("project_id")), "project_id")
    actual_workspace = _canonical_uuid(
        cast(str, parsed.get("workspace_instance_id")), "workspace_instance_id"
    )
    if project_id is not None and actual_project != _canonical_uuid(project_id, "project_id"):
        raise _failure("approval replay project identity differs")
    if workspace_id is not None and actual_workspace != _canonical_uuid(
        workspace_id, "workspace_instance_id"
    ):
        raise _failure("approval replay workspace identity differs")
    entries = parsed.get("entries")
    if not isinstance(entries, dict) or not all(isinstance(key, str) for key in entries):
        raise _failure("approval replay entries are invalid")
    for key, raw in entries.items():
        _sha256(key, "proof_key")
        _entry(key, raw)
    return cast(dict[str, object], parsed), state


def _entry(key: str, raw: object) -> ReplayEntry:
    if not isinstance(raw, Mapping) or set(raw) != {
        "bound_transaction_id",
        "state",
        "validated_at",
        "proof_expires_at",
        "consumed_at",
    }:
        raise _failure("approval replay entry is invalid", proof_key=key)
    transaction_id = _canonical_uuid(
        cast(str, raw.get("bound_transaction_id")), "bound_transaction_id"
    )
    state = raw.get("state")
    if state not in {"reserved", "consumed"}:
        raise _failure("approval replay state is invalid", proof_key=key)
    validated = _parse(raw.get("validated_at"), "validated_at")
    expires = _parse(raw.get("proof_expires_at"), "proof_expires_at")
    consumed_value = raw.get("consumed_at")
    consumed: str | None = None
    if state == "reserved":
        if consumed_value is not None:
            raise _failure("reserved replay entry has consumed_at", proof_key=key)
    else:
        consumed_time = _parse(consumed_value, "consumed_at")
        consumed = _format(consumed_time)
    if expires < validated:
        raise _failure("approval proof expires before validation", proof_key=key)
    return ReplayEntry(
        key,
        transaction_id,
        cast(str, state),
        _format(validated),
        _format(expires),
        consumed,
    )


def _candidate(state: FileState, document: Mapping[str, object]) -> tuple[FileState, bytes]:
    payload = canonical_json_bytes(document)
    return (
        FileState(
            state.path,
            True,
            "regular",
            hashlib.sha256(payload).hexdigest(),
            "0600",
            True,
            CANONICAL_NULL,
        ),
        payload,
    )


def _store(root: Path, before: FileState, document: Mapping[str, object]) -> None:
    candidate, payload = _candidate(before, document)
    try:
        compare_and_swap(root, before, candidate, payload)
    except ValueError as error:
        raise _failure("approval replay ledger changed during CAS") from error


def reserve_proof(
    root: Path,
    *,
    project_id: str,
    workspace_instance_id: str,
    approval_id: str,
    approval_challenge: str,
    route_decision_digest: str,
    transaction_id: str,
    validated_at: datetime,
    proof_expires_at: datetime,
    now: datetime,
    recovery: bool = False,
) -> ReplayEntry:
    """CAS-create or idempotently validate one transaction-bound reservation."""

    transaction = _canonical_uuid(transaction_id, "transaction_id")
    validated = _utc(validated_at, "validated_at")
    expires = _utc(proof_expires_at, "proof_expires_at")
    current_time = _utc(now, "now")
    if expires < validated:
        raise _failure("approval proof expires before successful validation")
    key = proof_key(
        approval_id, approval_challenge, route_decision_digest, workspace_instance_id
    )
    document, before = _load(root, project_id, workspace_instance_id)
    entries = cast(dict[str, object], document["entries"])
    existing = entries.get(key)
    if existing is not None:
        entry = _entry(key, existing)
        expected = ReplayEntry(
            key,
            transaction,
            "reserved",
            _format(validated),
            _format(expires),
            None,
        )
        if entry != expected:
            raise _failure("approval proof is rebound or already consumed", proof_key=key)
        return entry
    if not recovery and (current_time < validated or current_time > expires):
        raise _failure("approval proof is expired or not yet valid", proof_key=key)
    entry = ReplayEntry(
        key,
        transaction,
        "reserved",
        _format(validated),
        _format(expires),
        None,
    )
    entries[key] = {
        "bound_transaction_id": transaction,
        "state": "reserved",
        "validated_at": entry.validated_at,
        "proof_expires_at": entry.proof_expires_at,
        "consumed_at": None,
    }
    _store(root, before, document)
    return entry


def consume_proof(
    root: Path,
    *,
    proof_key: str,
    transaction_id: str,
    consumed_at: datetime,
) -> ReplayEntry:
    """CAS-transition one same-transaction reservation to a permanent tombstone."""

    key = _sha256(proof_key, "proof_key")
    transaction = _canonical_uuid(transaction_id, "transaction_id")
    consumed = _utc(consumed_at, "consumed_at")
    document, before = _load(root)
    entries = cast(dict[str, object], document["entries"])
    raw = entries.get(key)
    if raw is None:
        raise _failure("approval proof has no reserved state", proof_key=key)
    entry = _entry(key, raw)
    if entry.bound_transaction_id != transaction:
        raise _failure("approval proof belongs to another transaction", proof_key=key)
    if entry.state == "consumed":
        return entry
    candidate = ReplayEntry(
        key,
        transaction,
        "consumed",
        entry.validated_at,
        entry.proof_expires_at,
        _format(consumed),
    )
    entries[key] = {
        "bound_transaction_id": transaction,
        "state": "consumed",
        "validated_at": entry.validated_at,
        "proof_expires_at": entry.proof_expires_at,
        "consumed_at": candidate.consumed_at,
    }
    _store(root, before, document)
    return candidate
