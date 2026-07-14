"""Closed executable TaskIntent normalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import digest
from agent_stack.core.canonical import normalize_nfc

from .errors import RouteFailure
from .signals import CompiledRoutePolicy, normalize_signals


_FIELDS = {
    "schema_id",
    "schema_version",
    "intent_id",
    "title",
    "objective",
    "requested_mode",
    "acceptance_summary",
    "signals",
}
_MODES = {None, "native-light", "trellis-native", "speckit-superpowers"}


@dataclass(frozen=True)
class VerifiedTaskIntent:
    document: Mapping[str, object]
    intent_id: str
    requested_mode: str | None
    signals: tuple[str, ...]
    intent_digest: str


def _failure(message: str, **details: object) -> RouteFailure:
    return RouteFailure("AWP_ROUTE_SIGNAL_INVALID", message, details=details)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise _failure("TaskIntent text is invalid", field=field)
    normalized = normalize_nfc(value).strip()
    if not normalized or len(normalized.encode("utf-8")) > 4096:
        raise _failure("TaskIntent text is empty or oversized", field=field)
    return normalized


def validate_task_intent(
    document: Mapping[str, object],
    *,
    policy: CompiledRoutePolicy,
    separate_signals: Sequence[str] | None = None,
) -> VerifiedTaskIntent:
    """Validate one executable Intent and reject any parallel signal channel."""

    if separate_signals is not None:
        raise _failure("executable operations reject a separate --signals option")
    if set(document) != _FIELDS:
        raise _failure(
            "TaskIntent fields are not closed",
            missing=sorted(_FIELDS - set(document)),
            unknown=sorted(set(document) - _FIELDS),
        )
    if document.get("schema_id") != "agent-workflow.task-intent" or document.get(
        "schema_version"
    ) != 1:
        raise _failure("TaskIntent schema is unsupported")
    requested = document.get("requested_mode")
    if requested not in _MODES:
        raise _failure("TaskIntent requested mode is invalid")
    raw_signals = document.get("signals")
    if not isinstance(raw_signals, Sequence) or isinstance(
        raw_signals, (str, bytes, bytearray)
    ):
        raise _failure("TaskIntent signals are invalid")
    signals = normalize_signals(cast(Sequence[str], raw_signals), policy)
    normalized: dict[str, object] = {
        "schema_id": "agent-workflow.task-intent",
        "schema_version": 1,
        "intent_id": _text(document.get("intent_id"), "intent_id"),
        "title": _text(document.get("title"), "title"),
        "objective": _text(document.get("objective"), "objective"),
        "requested_mode": requested,
        "acceptance_summary": _text(
            document.get("acceptance_summary"), "acceptance_summary"
        ),
        "signals": list(signals),
    }
    frozen = MappingProxyType(normalized)
    return VerifiedTaskIntent(
        frozen,
        cast(str, normalized["intent_id"]),
        requested,
        signals,
        digest("agent-workflow.task-intent.v1", normalized),
    )
