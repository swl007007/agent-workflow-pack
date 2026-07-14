"""Provider provenance validation and deterministic third-party notices."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence, Set

from agent_stack.core.api import CANONICAL_NULL, digest, normalize_path

from .errors import ProviderFailure


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SPDX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+() -]*$")
_FIELDS = {
    "schema_id",
    "schema_version",
    "component_id",
    "source_artifact",
    "license_expression",
    "license_text_digest",
    "modified",
    "modification_notice_digest",
    "projected_unit_ids",
    "provenance_digest",
}


def _incomplete(message: str, **details: object) -> ProviderFailure:
    return ProviderFailure("AWP_PROVENANCE_INCOMPLETE", message, details=details)


def build_provenance_record(
    *,
    component_id: str,
    version: str,
    source_digest: str,
    upstream_path: str,
    license_expression: str,
    license_text_digest: str,
    modified: bool,
    modification_notice_digest: str,
    projected_unit_ids: Sequence[str],
) -> dict[str, object]:
    projection: dict[str, object] = {
        "schema_id": "agent-workflow.provenance-record",
        "schema_version": 1,
        "component_id": component_id,
        "source_artifact": {
            "version": version,
            "source_digest": source_digest,
            "upstream_path": normalize_path(upstream_path),
        },
        "license_expression": license_expression,
        "license_text_digest": license_text_digest,
        "modified": modified,
        "modification_notice_digest": modification_notice_digest,
        "projected_unit_ids": sorted(set(projected_unit_ids)),
    }
    return {
        **projection,
        "provenance_digest": digest("agent-workflow.provenance-record.v1", projection),
    }


def _validate_record(record: Mapping[str, object]) -> None:
    if set(record) != _FIELDS:
        raise _incomplete("provenance record fields are not closed")
    if record.get("schema_id") != "agent-workflow.provenance-record" or record.get(
        "schema_version"
    ) != 1:
        raise _incomplete("provenance schema identity/version is invalid")
    source = record.get("source_artifact")
    if not isinstance(source, Mapping) or set(source) != {
        "version",
        "source_digest",
        "upstream_path",
    }:
        raise _incomplete("provenance source_artifact fields are not closed")
    if not isinstance(source.get("version"), str) or not source.get("version"):
        raise _incomplete("provenance source version is missing")
    if not isinstance(source.get("source_digest"), str) or not _SHA256.fullmatch(
        str(source.get("source_digest"))
    ):
        raise _incomplete("provenance source digest is invalid")
    normalize_path(str(source.get("upstream_path")))
    license_expression = record.get("license_expression")
    if not isinstance(license_expression, str) or not _SPDX.fullmatch(license_expression):
        raise _incomplete("SPDX license expression is missing or invalid")
    for field in ("license_text_digest", "provenance_digest"):
        value = record.get(field)
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise _incomplete("provenance digest is invalid", field=field)
    if not isinstance(record.get("modified"), bool):
        raise _incomplete("provenance modified flag is invalid")
    notice = record.get("modification_notice_digest")
    if record.get("modified") is True:
        if not isinstance(notice, str) or not _SHA256.fullmatch(notice):
            raise _incomplete("modified content requires a modification notice digest")
    elif notice != CANONICAL_NULL:
        raise _incomplete("unmodified content must use canonical-null modification notice")
    units = record.get("projected_unit_ids")
    if not isinstance(units, list) or not units or not all(
        isinstance(item, str) and item for item in units
    ):
        raise _incomplete("provenance projected units are missing")
    projection = dict(record)
    claimed = projection.pop("provenance_digest")
    if digest("agent-workflow.provenance-record.v1", projection) != claimed:
        raise _incomplete("provenance digest does not match its projection")


def validate_provenance_closure(
    records: Sequence[Mapping[str, object]], projected_unit_ids: Set[str]
) -> tuple[dict[str, object], ...]:
    normalized: list[dict[str, object]] = []
    covered: set[str] = set()
    for record in records:
        _validate_record(record)
        document = dict(record)
        normalized.append(document)
        units = document["projected_unit_ids"]
        assert isinstance(units, list)
        covered.update(str(item) for item in units)
    if covered != set(projected_unit_ids):
        raise _incomplete(
            "provenance projected-unit closure is incomplete",
            missing=sorted(set(projected_unit_ids) - covered),
            unexpected=sorted(covered - set(projected_unit_ids)),
        )
    return tuple(sorted(normalized, key=lambda item: str(item["component_id"])))


def generate_third_party_notices(records: Sequence[Mapping[str, object]]) -> str:
    lines = ["THIRD-PARTY NOTICES", ""]
    for record in records:
        source = record["source_artifact"]
        assert isinstance(source, Mapping)
        lines.extend(
            [
                f"{record['component_id']} {source['version']}",
                f"License: {record['license_expression']}",
                f"Source digest: {source['source_digest']}",
                "",
            ]
        )
    return "\n".join(lines)
