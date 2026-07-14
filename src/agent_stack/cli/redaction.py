"""Sanitize CLI documents before presentation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "traceback",
)
_SENSITIVE_QUERY_KEYS = frozenset(
    {"access_token", "api_key", "apikey", "auth", "password", "secret", "signature", "token"}
)
_INLINE_SECRET = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+|bearer\s+|password\s*[=:]\s*|token\s*[=: ]\s*)[^\s,;]+"
)


def _sanitize_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value
    hostname = parsed.hostname or ""
    if parsed.port is not None:
        hostname = f"{hostname}:{parsed.port}"
    query = urlencode(
        [
            (key, "[REDACTED]" if key.casefold() in _SENSITIVE_QUERY_KEYS else item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parsed.scheme, hostname, parsed.path, query, parsed.fragment))


def _sanitize_string(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return _sanitize_url(value)[:4096]
    return _INLINE_SECRET.sub(lambda match: f"{match.group(1)}[REDACTED]", value)[:4096]


def _path_value(value: Path, repository_root: Path | None) -> str:
    if repository_root is None:
        return value.as_posix() if not value.is_absolute() else "<external>"
    try:
        return value.resolve(strict=False).relative_to(repository_root.resolve(strict=False)).as_posix()
    except ValueError:
        return "<external>"


def sanitize_document(
    value: object,
    *,
    repository_root: Path | None = None,
    _key: str = "",
) -> Any:
    """Return a recursively redacted, JSON-compatible projection."""

    folded_key = _key.casefold()
    if any(part in folded_key for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Path):
        return _path_value(value, repository_root)
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_document(item, repository_root=repository_root, _key=str(key))
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_document(item, repository_root=repository_root) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if hasattr(value, "to_document"):
        return sanitize_document(value.to_document(), repository_root=repository_root)
    return _sanitize_string(str(value))
