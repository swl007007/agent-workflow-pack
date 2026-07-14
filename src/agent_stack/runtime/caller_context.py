"""Validated non-sensitive caller context restored only after runtime authority."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .authority import VerifiedRuntimeAuthority
from .errors import RuntimeFailure


_FIELDS = {
    "schema_id",
    "schema_version",
    "platform",
    "user_home",
    "config_roots",
    "harness",
    "tty",
}
_CONFIG_KEYS = {"codex_home", "claude_home", "opencode_home"}
_TTY_FIELDS = {"stdin", "stdout", "stderr", "direct_confirmation_capable"}


def _invalid(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure("AWP_CALLER_CONTEXT_INVALID", message, details=details)


def _string(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise _invalid("caller-context string is invalid", field=field)
    return value


def _absolute(value: object, field: str) -> Path:
    path = Path(_string(value, field))
    if not path.is_absolute() or path != Path(os.path.normpath(path)):
        raise _invalid("caller-context path is not absolute and normalized", field=field)
    return path


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _invalid("caller-context object is invalid", field=field)
    return value


@dataclass(frozen=True)
class VerifiedCallerContext:
    platform: str
    user_home: Path
    config_roots: Mapping[str, Path]
    harness_executable: Path
    harness_version_probe_id: str
    tty: Mapping[str, bool]


CallerContextProbe = Callable[[VerifiedCallerContext], Mapping[str, object]]


def _parse(document: Mapping[str, object]) -> VerifiedCallerContext:
    if set(document) != _FIELDS:
        raise _invalid("caller-context fields are not closed")
    if (
        document.get("schema_id") != "agent-workflow.caller-context"
        or document.get("schema_version") != 1
    ):
        raise _invalid("caller-context identity is invalid")
    platform = _string(document.get("platform"), "platform")
    if platform not in {"codex", "claude", "opencode"}:
        raise _invalid("caller platform is unsupported")
    user_home = _absolute(document.get("user_home"), "user_home")
    raw_roots = _mapping(document.get("config_roots"), "config_roots")
    if not set(raw_roots).issubset(_CONFIG_KEYS) or not raw_roots:
        raise _invalid("caller config-root fields are not closed")
    config_roots = {
        key: _absolute(value, f"config_roots.{key}") for key, value in raw_roots.items()
    }
    harness = _mapping(document.get("harness"), "harness")
    if set(harness) != {"executable", "version_probe_id"}:
        raise _invalid("caller harness fields are not closed")
    harness_executable = _absolute(harness.get("executable"), "harness.executable")
    version_probe_id = _string(harness.get("version_probe_id"), "harness.version_probe_id")
    raw_tty = _mapping(document.get("tty"), "tty")
    if set(raw_tty) != _TTY_FIELDS or not all(
        isinstance(value, bool) for value in raw_tty.values()
    ):
        raise _invalid("caller TTY facts are invalid")
    tty = {key: bool(raw_tty[key]) for key in sorted(_TTY_FIELDS)}
    if tty["direct_confirmation_capable"] and not (tty["stdin"] and tty["stdout"]):
        raise _invalid("direct confirmation lacks interactive input/output")
    return VerifiedCallerContext(
        platform,
        user_home,
        MappingProxyType(config_roots),
        harness_executable,
        version_probe_id,
        MappingProxyType(tty),
    )


def _verify_paths(context: VerifiedCallerContext) -> None:
    if context.user_home.is_symlink() or not context.user_home.is_dir():
        raise _invalid("caller user home is unavailable")
    for name, path in context.config_roots.items():
        if path.is_symlink() or not path.is_dir():
            raise _invalid("caller config root is unavailable", field=name)
    harness = context.harness_executable
    if harness.is_symlink() or not harness.is_file() or not os.access(harness, os.X_OK):
        raise _invalid("caller harness is not a regular executable")


def _verify_probe(
    context: VerifiedCallerContext, observed: Mapping[str, object]
) -> None:
    expected = {
        "user_home": str(context.user_home),
        "harness_executable": str(context.harness_executable),
        "harness_version_probe_id": context.harness_version_probe_id,
        "tty": dict(context.tty),
    }
    if dict(observed) != expected:
        raise _invalid("caller context changed during post-authority re-probe")


def verify_caller_context(
    document: Mapping[str, object],
    authority: object,
    *,
    probe: CallerContextProbe,
) -> VerifiedCallerContext:
    """Validate and re-probe caller context only after authority is established."""

    if not isinstance(authority, VerifiedRuntimeAuthority):
        raise RuntimeFailure(
            "AWP_RUNTIME_BINDING_MISMATCH",
            "caller context cannot be inspected before runtime authority",
        )
    context = _parse(document)
    _verify_paths(context)
    _verify_probe(context, probe(context))
    return context
