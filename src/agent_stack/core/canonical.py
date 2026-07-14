"""Schema-normalized JSON canonicalization and digest helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import uuid
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Final, TypeAlias, cast

from .errors import CoreFailure


CANONICAL_NULL: Final = "canonical-null"

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_OCTAL_MODE = re.compile(r"^(?:0o)?[0-7]{3,6}$")


def _failure(message: str, *, details: Mapping[str, object] | None = None) -> CoreFailure:
    return CoreFailure("AWP_CANONICALIZATION_INVALID", message, details=details)


def _reject_surrogates(value: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise _failure("Unicode surrogate code points are not permitted")


def normalize_nfc(value: str) -> str:
    """Return the unique NFC representation of a Unicode string."""

    if not isinstance(value, str):
        raise _failure("expected a Unicode string")
    _reject_surrogates(value)
    return unicodedata.normalize("NFC", value)


def _utf16_sort_key(value: str) -> bytes:
    return value.encode("utf-16-be")


def normalize_string_set(values: Iterable[str]) -> tuple[str, ...]:
    """Normalize, deduplicate, and JCS-sort a set-semantic string array."""

    normalized = {normalize_nfc(value) for value in values}
    return tuple(sorted(normalized, key=_utf16_sort_key))


def normalize_path(value: str) -> str:
    """Normalize one strict repository-relative, forward-slash path."""

    normalized = normalize_nfc(value)
    if not normalized:
        raise _failure("repository path must not be empty")
    if "\0" in normalized or "\\" in normalized:
        raise _failure("repository path contains a forbidden separator or NUL")
    if normalized.startswith("/") or _WINDOWS_DRIVE.match(normalized):
        raise _failure("repository path must be relative")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        raise _failure("repository path contains a control character")
    segments = normalized.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise _failure("repository path contains an empty or alias segment")
    return "/".join(segments)


def normalize_mode(value: int | str) -> str:
    """Mask a POSIX mode to 0777 and return four octal characters."""

    if isinstance(value, bool):
        raise _failure("boolean is not a POSIX mode")
    if isinstance(value, int):
        if value < 0:
            raise _failure("POSIX mode must be nonnegative")
        numeric = value
    elif isinstance(value, str) and _OCTAL_MODE.fullmatch(value):
        numeric = int(value.removeprefix("0o"), 8)
    else:
        raise _failure("POSIX mode must be an octal integer or string")
    return f"{numeric & 0o777:04o}"


def normalize_uuid(value: str | uuid.UUID) -> str:
    """Return the lowercase hyphenated UUID representation."""

    try:
        parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise _failure("invalid UUID value") from error
    return str(parsed)


def _normalize_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, bool):
        return cast(JsonScalar, value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _failure("non-finite JSON number is forbidden")
        return value
    if isinstance(value, str):
        return normalize_nfc(value)
    if isinstance(value, Mapping):
        normalized: dict[str, JsonValue] = {}
        for raw_key, raw_value in value.items():
            if not isinstance(raw_key, str):
                raise _failure("JSON object keys must be strings")
            key = normalize_nfc(raw_key)
            if key in normalized:
                raise _failure("object keys collide after NFC normalization", details={"key": key})
            normalized[key] = _normalize_json_value(raw_value)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_json_value(item) for item in value]
    raise _failure("value is outside the normalized JSON data model")


def normalize_json_value(value: object) -> JsonValue:
    """Normalize an object into the closed JSON data model."""

    return _normalize_json_value(value)


def _format_float(value: float) -> str:
    if not math.isfinite(value):
        raise _failure("non-finite JSON number is forbidden")
    if value == 0:
        return "0"

    shortest = repr(value).lower()
    absolute = abs(value)
    if 1e-6 <= absolute < 1e21:
        fixed = format(Decimal(shortest), "f")
        if "." in fixed:
            fixed = fixed.rstrip("0").rstrip(".")
        return fixed

    if "e" not in shortest:
        scientific = format(Decimal(shortest).normalize(), "e")
        mantissa, exponent_text = scientific.split("e", 1)
    else:
        mantissa, exponent_text = shortest.split("e", 1)
    mantissa = mantissa.rstrip("0").rstrip(".") if "." in mantissa else mantissa
    exponent = int(exponent_text)
    sign = "+" if exponent >= 0 else "-"
    return f"{mantissa}e{sign}{abs(exponent)}"


def _serialize(value: JsonValue) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    ordered_keys = sorted(value, key=_utf16_sort_key)
    members = (
        f"{json.dumps(key, ensure_ascii=False)}:{_serialize(value[key])}" for key in ordered_keys
    )
    return "{" + ",".join(members) + "}"


def canonical_json_bytes(value: object) -> bytes:
    """Return RFC 8785-compatible bytes after schema-independent normalization."""

    normalized = _normalize_json_value(value)
    return _serialize(normalized).encode("utf-8")


def digest(domain: str, value: object) -> str:
    """Hash ASCII domain, one NUL byte, and normalized JCS bytes."""

    if not isinstance(domain, str) or not domain or "\0" in domain:
        raise _failure("digest domain must be nonempty ASCII without NUL")
    try:
        domain_bytes = domain.encode("ascii")
    except UnicodeEncodeError as error:
        raise _failure("digest domain must be ASCII") from error
    return hashlib.sha256(domain_bytes + b"\0" + canonical_json_bytes(value)).hexdigest()
