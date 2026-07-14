from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.core.errors import CoreFailure
from agent_stack.core.schema_catalog import SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def schema_catalog() -> SchemaCatalog:
    return SchemaCatalog.discover(ROOT / "schemas")


def test_duplicate_yaml_keys_are_rejected(schema_catalog: SchemaCatalog) -> None:
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        schema_catalog.parse_yaml("id: one\nid: two\n")


def test_duplicate_json_keys_are_rejected(schema_catalog: SchemaCatalog) -> None:
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        schema_catalog.parse_json('{"id":"one","id":"two"}')


def test_catalog_discovers_separate_schema_ids_and_versions(schema_catalog: SchemaCatalog) -> None:
    assert schema_catalog.supported_versions("agent-workflow.schema-catalog") == (1,)
    assert schema_catalog.supported_versions("agent-workflow.resolution-failure") == (1,)
    assert schema_catalog.supported_versions("agent-workflow.runtime-vendor-lock") == (1,)


def test_resolution_failure_validates_as_a_closed_schema(schema_catalog: SchemaCatalog) -> None:
    failure = {
        "schema_id": "agent-workflow.resolution-failure",
        "schema_version": 1,
        "code": "AWP_SCHEMA_INVALID",
        "exit_code": 2,
        "message": "duplicate key",
        "path": "profiles/demo.yaml",
        "details": {"key": "id"},
    }

    assert schema_catalog.load_and_validate(failure) == failure
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        schema_catalog.load_and_validate({**failure, "unknown": True})


def test_unknown_schema_and_version_fail_closed(schema_catalog: SchemaCatalog) -> None:
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        schema_catalog.load_and_validate(
            {"schema_id": "agent-workflow.unknown", "schema_version": 1}
        )
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        schema_catalog.load_and_validate(
            {"schema_id": "agent-workflow.resolution-failure", "schema_version": 2}
        )


def test_yaml_is_converted_to_the_json_data_model(schema_catalog: SchemaCatalog) -> None:
    document = schema_catalog.parse_yaml("name: demo\nitems: [1, true, null]\n")

    assert document == {"name": "demo", "items": [1, True, None]}


def test_yaml_non_json_native_values_are_rejected(schema_catalog: SchemaCatalog) -> None:
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        schema_catalog.parse_yaml("created: 2026-07-13\n")
