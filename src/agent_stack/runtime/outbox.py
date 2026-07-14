"""Non-authoritative, idempotent task outbox effects."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import CANONICAL_NULL, canonical_json_bytes, digest
from agent_stack.reconcile.cas import compare_and_swap, observe_file_state
from agent_stack.reconcile.models import FileState

from .errors import RuntimeFailure


_OUTBOX_ROOT = ".agent-workflow/local/task-outbox"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OutboxItem:
    """Immutable effect identity plus current non-authoritative delivery state."""

    effect_id: str
    idempotency_key: str
    delivery_state: str
    attempt_count: int
    document: Mapping[str, object]


def _failure(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure("AWP_TASK_TRANSITION_INVALID", message, details=details)


def _uuid(value: str, field: str) -> str:
    try:
        parsed = str(uuid.UUID(value))
    except (AttributeError, ValueError) as error:
        raise _failure("outbox UUID is invalid", field=field) from error
    if parsed != value:
        raise _failure("outbox UUID is not canonical", field=field)
    return value


def _token(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or any(ord(character) < 0x20 for character in value):
        raise _failure("outbox token is invalid", field=field)
    return value


def _sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise _failure("outbox digest is invalid", field=field)
    return value


def _format(value: datetime, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise _failure("outbox timestamp is not timezone aware", field=field)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _path(root: Path, effect_id: str) -> tuple[str, Path]:
    key = _sha256(effect_id, "effect_id")
    relative = f"{_OUTBOX_ROOT}/{key}.json"
    return relative, root / relative


def _state(relative: str, payload: bytes) -> FileState:
    return FileState(
        relative,
        True,
        "regular",
        hashlib.sha256(payload).hexdigest(),
        "0600",
        True,
        CANONICAL_NULL,
    )


def _absent(relative: str) -> FileState:
    return FileState(relative, False, "absent", CANONICAL_NULL, CANONICAL_NULL, True)


def _validate(document: object, effect_id: str) -> OutboxItem:
    if not isinstance(document, Mapping) or set(document) != {
        "schema_id",
        "schema_version",
        "effect_id",
        "operation",
        "task_id",
        "transaction_id",
        "effect_kind",
        "handler_id",
        "handler_version",
        "payload",
        "payload_digest",
        "idempotency_key",
        "created_at",
        "delivery",
    }:
        raise _failure("outbox item fields are invalid", effect_id=effect_id)
    if document.get("schema_id") != "agent-workflow.task-outbox" or document.get(
        "schema_version"
    ) != 1:
        raise _failure("outbox item schema is unsupported", effect_id=effect_id)
    if document.get("effect_id") != effect_id:
        raise _failure("outbox item path identity differs", effect_id=effect_id)
    _uuid(cast(str, document.get("task_id")), "task_id")
    _uuid(cast(str, document.get("transaction_id")), "transaction_id")
    for field in ("operation", "effect_kind", "handler_id", "handler_version", "created_at"):
        _token(cast(str, document.get(field)), field)
    payload = document.get("payload")
    payload_digest = _sha256(cast(str, document.get("payload_digest")), "payload_digest")
    if digest("agent-workflow.task-outbox-payload.v1", payload) != payload_digest:
        raise _failure("outbox payload digest is stale", effect_id=effect_id)
    idempotency_key = _sha256(
        cast(str, document.get("idempotency_key")), "idempotency_key"
    )
    delivery = document.get("delivery")
    if not isinstance(delivery, Mapping) or set(delivery) != {
        "state",
        "attempt_count",
        "last_attempt_at",
        "delivered_at",
        "failure",
    }:
        raise _failure("outbox delivery fields are invalid", effect_id=effect_id)
    state = delivery.get("state")
    if state not in {"pending", "delivered", "failed"}:
        raise _failure("outbox delivery state is invalid", effect_id=effect_id)
    count = delivery.get("attempt_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise _failure("outbox attempt count is invalid", effect_id=effect_id)
    if state == "pending" and (
        count != 0
        or delivery.get("last_attempt_at") is not None
        or delivery.get("delivered_at") is not None
        or delivery.get("failure") is not None
    ):
        raise _failure("pending outbox item contains delivery evidence", effect_id=effect_id)
    if state == "delivered" and (
        count < 1
        or delivery.get("last_attempt_at") is None
        or delivery.get("delivered_at") is None
        or delivery.get("failure") is not None
    ):
        raise _failure("delivered outbox item is incomplete", effect_id=effect_id)
    if state == "failed" and (
        count < 1
        or delivery.get("last_attempt_at") is None
        or delivery.get("delivered_at") is not None
        or not isinstance(delivery.get("failure"), Mapping)
    ):
        raise _failure("failed outbox item is incomplete", effect_id=effect_id)
    return OutboxItem(
        effect_id,
        idempotency_key,
        cast(str, state),
        count,
        MappingProxyType(dict(document)),
    )


def _read(root: Path, effect_id: str) -> tuple[OutboxItem, FileState, dict[str, object]]:
    relative, path = _path(root, effect_id)
    try:
        observed = observe_file_state(root, relative)
    except ValueError as error:
        raise _failure("outbox item metadata is invalid", effect_id=effect_id) from error
    if not observed.exists or observed.file_type != "regular" or observed.mode != "0600":
        raise _failure("outbox item is missing or has invalid metadata", effect_id=effect_id)
    try:
        payload = path.read_bytes()
        parsed = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _failure("outbox item is corrupt", effect_id=effect_id) from error
    if not isinstance(parsed, dict) or canonical_json_bytes(parsed) != payload:
        raise _failure("outbox item is not canonical", effect_id=effect_id)
    item = _validate(parsed, effect_id)
    return item, observed, cast(dict[str, object], parsed)


def enqueue_effect(
    root: Path,
    *,
    operation: str,
    task_id: str,
    transaction_id: str,
    effect_kind: str,
    handler_id: str,
    handler_version: str,
    payload: object,
    created_at: datetime,
) -> OutboxItem:
    """CAS-create one deterministic immutable pending effect."""

    identity = {
        "operation": _token(operation, "operation"),
        "task_id": _uuid(task_id, "task_id"),
        "transaction_id": _uuid(transaction_id, "transaction_id"),
        "effect_kind": _token(effect_kind, "effect_kind"),
        "handler_id": _token(handler_id, "handler_id"),
        "handler_version": _token(handler_version, "handler_version"),
        "payload_digest": digest("agent-workflow.task-outbox-payload.v1", payload),
    }
    effect_id = digest("agent-workflow.task-outbox.v1", identity)
    idempotency_key = digest(
        "agent-workflow.task-outbox-idempotency.v1",
        {"effect_id": effect_id, "handler_id": handler_id, "handler_version": handler_version},
    )
    document: dict[str, object] = {
        "schema_id": "agent-workflow.task-outbox",
        "schema_version": 1,
        "effect_id": effect_id,
        **identity,
        "payload": payload,
        "idempotency_key": idempotency_key,
        "created_at": _format(created_at, "created_at"),
        "delivery": {
            "state": "pending",
            "attempt_count": 0,
            "last_attempt_at": None,
            "delivered_at": None,
            "failure": None,
        },
    }
    relative, path = _path(root, effect_id)
    parent = path.parent
    if parent.is_symlink():
        raise _failure("outbox root is a symlink")
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise _failure("outbox root is unavailable")
    candidate_bytes = canonical_json_bytes(document)
    observed = observe_file_state(root, relative)
    if observed.exists:
        existing, _, _ = _read(root, effect_id)
        if canonical_json_bytes(existing.document) != candidate_bytes:
            raise _failure("deterministic outbox identity collides with different bytes")
        return existing
    try:
        compare_and_swap(root, _absent(relative), _state(relative, candidate_bytes), candidate_bytes)
    except ValueError as error:
        raise _failure("outbox item changed during CAS", effect_id=effect_id) from error
    return _validate(document, effect_id)


def deliver_effect(
    root: Path,
    *,
    effect_id: str,
    attempted_at: datetime,
    handler: Callable[[Mapping[str, object]], None],
) -> OutboxItem:
    """Attempt idempotent delivery and persist only non-authoritative delivery evidence."""

    item, observed, document = _read(root, effect_id)
    if item.delivery_state == "delivered":
        return item
    attempt_time = _format(attempted_at, "attempted_at")
    delivery = cast(dict[str, object], document["delivery"])
    failure: Exception | None = None
    try:
        handler(MappingProxyType(dict(document)))
    except Exception as error:  # handler boundary must persist retry evidence
        failure = error
    delivery.update(
        state="failed" if failure is not None else "delivered",
        attempt_count=item.attempt_count + 1,
        last_attempt_at=attempt_time,
        delivered_at=None if failure is not None else attempt_time,
        failure=(
            None
            if failure is None
            else {"error_type": type(failure).__name__, "message": str(failure)[:1024]}
        ),
    )
    candidate_bytes = canonical_json_bytes(document)
    try:
        compare_and_swap(root, observed, _state(observed.path, candidate_bytes), candidate_bytes)
    except ValueError as error:
        raise _failure("outbox item changed during delivery CAS", effect_id=effect_id) from error
    result = _validate(document, effect_id)
    if failure is not None:
        raise _failure(
            "outbox handler failed; effect remains retryable",
            effect_id=effect_id,
            idempotency_key=item.idempotency_key,
        ) from failure
    return result
