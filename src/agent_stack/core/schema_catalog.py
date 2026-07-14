"""Duplicate-safe document parsing and closed schema discovery."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from agent_stack._vendor import fastjsonschema, yaml
from agent_stack._vendor.fastjsonschema.exceptions import JsonSchemaException
from agent_stack._vendor.yaml.nodes import MappingNode

from .canonical import JsonValue, normalize_json_value, normalize_nfc
from .errors import CoreFailure


SCHEMA_ERROR: Final = "AWP_SCHEMA_INVALID"


def _schema_failure(
    message: str,
    *,
    path: str = "<input>",
    details: Mapping[str, object] | None = None,
) -> CoreFailure:
    return CoreFailure(SCHEMA_ERROR, message, path=path, details=details)


class _DuplicateSafeLoader(yaml.SafeLoader):
    def construct_mapping(self, node: object, deep: bool = False) -> dict[str, Any]:
        if not isinstance(node, MappingNode):
            raise _schema_failure("YAML mapping node is malformed")
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise _schema_failure("YAML merge keys are forbidden")

        result: dict[str, Any] = {}
        raw_keys: set[str] = set()
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)  # type: ignore[no-untyped-call]
            if not isinstance(key, str):
                raise _schema_failure("YAML object keys must be strings")
            normalized_key = normalize_nfc(key)
            if key in raw_keys or normalized_key in result:
                raise _schema_failure("duplicate YAML object key", details={"key": normalized_key})
            raw_keys.add(key)
            result[normalized_key] = self.construct_object(  # type: ignore[no-untyped-call]
                value_node, deep=deep
            )
        return result


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    raw_keys: set[str] = set()
    for key, value in pairs:
        normalized_key = normalize_nfc(key)
        if key in raw_keys or normalized_key in result:
            raise _schema_failure("duplicate JSON object key", details={"key": normalized_key})
        raw_keys.add(key)
        result[normalized_key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _schema_failure("non-finite JSON number is forbidden", details={"value": value})


def _normalize_parsed(value: object) -> JsonValue:
    try:
        return normalize_json_value(value)
    except CoreFailure as error:
        raise _schema_failure(error.message, details=error.details) from error


def _parse_json_text(text: str, *, path: str = "<input>") -> JsonValue:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_safe_object,
            parse_constant=_reject_json_constant,
        )
    except CoreFailure:
        raise
    except (json.JSONDecodeError, TypeError, UnicodeError) as error:
        raise _schema_failure("invalid JSON document", path=path, details={"error": str(error)}) from error
    return _normalize_parsed(value)


@dataclass(frozen=True)
class SchemaDefinition:
    schema_id: str
    schema_version: int
    definition_owner: str
    implementation_owner: str
    digest_domains: tuple[str, ...]
    path: Path
    schema: dict[str, Any]


class SchemaCatalog:
    """An immutable index of versioned, closed JSON schemas."""

    def __init__(self, definitions: Mapping[tuple[str, int], SchemaDefinition]) -> None:
        self._definitions = dict(definitions)

    @classmethod
    def discover(cls, schema_root: Path) -> SchemaCatalog:
        definitions: dict[tuple[str, int], SchemaDefinition] = {}
        if not schema_root.is_dir():
            raise _schema_failure("schema root does not exist", path=schema_root.as_posix())

        for path in sorted(schema_root.rglob("*.json")):
            relative = path.relative_to(schema_root).as_posix()
            try:
                parsed = _parse_json_text(path.read_text(encoding="utf-8"), path=relative)
            except OSError as error:
                raise _schema_failure(
                    "cannot read schema definition", path=relative, details={"error": str(error)}
                ) from error
            if not isinstance(parsed, dict):
                raise _schema_failure("schema definition must be an object", path=relative)
            metadata = {
                "$id": parsed.get("$id"),
                "x-schema-version": parsed.get("x-schema-version"),
                "x-definition-owner": parsed.get("x-definition-owner"),
                "x-implementation-owner": parsed.get("x-implementation-owner"),
                "x-digest-domains": parsed.get("x-digest-domains"),
            }
            if not isinstance(metadata["$id"], str):
                raise _schema_failure("schema has no string $id", path=relative)
            if not isinstance(metadata["x-schema-version"], int):
                raise _schema_failure("schema has no integer x-schema-version", path=relative)
            if not isinstance(metadata["x-definition-owner"], str) or not isinstance(
                metadata["x-implementation-owner"], str
            ):
                raise _schema_failure("schema ownership metadata is missing", path=relative)
            domains = metadata["x-digest-domains"]
            if not isinstance(domains, list) or not all(isinstance(item, str) for item in domains):
                raise _schema_failure("schema digest-domain metadata is invalid", path=relative)
            schema_id = metadata["$id"]
            schema_version = metadata["x-schema-version"]
            key = (schema_id, schema_version)
            if key in definitions:
                raise _schema_failure(
                    "duplicate schema identity and version",
                    path=relative,
                    details={"schema_id": schema_id, "schema_version": schema_version},
                )
            definitions[key] = SchemaDefinition(
                schema_id=schema_id,
                schema_version=schema_version,
                definition_owner=metadata["x-definition-owner"],
                implementation_owner=metadata["x-implementation-owner"],
                digest_domains=tuple(cast(list[str], domains)),
                path=path,
                schema=parsed,
            )
        return cls(definitions)

    @staticmethod
    def parse_json(text: str) -> JsonValue:
        return _parse_json_text(text)

    @staticmethod
    def parse_yaml(text: str) -> JsonValue:
        try:
            value = yaml.load(text, Loader=_DuplicateSafeLoader)  # type: ignore[no-untyped-call]
        except CoreFailure:
            raise
        except yaml.YAMLError as error:
            raise _schema_failure("invalid YAML document", details={"error": str(error)}) from error
        return _normalize_parsed(value)

    def supported_versions(self, schema_id: str) -> tuple[int, ...]:
        return tuple(sorted(version for candidate, version in self._definitions if candidate == schema_id))

    def definition(self, schema_id: str, schema_version: int) -> SchemaDefinition:
        try:
            return self._definitions[(schema_id, schema_version)]
        except KeyError as error:
            raise _schema_failure(
                "unknown or unsupported schema identity/version",
                details={"schema_id": schema_id, "schema_version": schema_version},
            ) from error

    def load_and_validate(self, document: Mapping[str, object]) -> dict[str, Any]:
        normalized = _normalize_parsed(document)
        if not isinstance(normalized, dict):
            raise _schema_failure("schema-bound document must be an object")
        schema_id = normalized.get("schema_id")
        schema_version = normalized.get("schema_version")
        if not isinstance(schema_id, str) or not isinstance(schema_version, int):
            raise _schema_failure("document must declare schema_id and schema_version")
        definition = self.definition(schema_id, schema_version)
        try:
            validator = fastjsonschema.compile(  # type: ignore[no-untyped-call]
                definition.schema
            )
            validated = validator(normalized)
        except JsonSchemaException as error:
            raise _schema_failure(
                "document does not satisfy its closed schema",
                details={"schema_id": schema_id, "schema_version": schema_version, "error": str(error)},
            ) from error
        if not isinstance(validated, dict):
            raise _schema_failure("schema validator returned a non-object")
        return validated
