from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.core.catalog import normalize_workflow_lock
from agent_stack.core.errors import CoreFailure
from agent_stack.core.schema_catalog import SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]


def _lock(*components: dict[str, object]) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.workflow-lock",
        "schema_version": 1,
        "components": list(components),
    }


def _component(component_id: str, sha: str = "a" * 64) -> dict[str, object]:
    return {
        "id": component_id,
        "version": "1.0.0",
        "source_sha256": sha,
        "content_digest": "b" * 64,
        "provider_id": "release-bundle",
        "acquisition_id": f"locked:{component_id}",
    }


def test_workflow_lock_normalizes_to_stable_component_order() -> None:
    normalized = normalize_workflow_lock(
        _lock(_component("skill:z"), _component("adapter:a"))
    )

    assert tuple(component.component_id for component in normalized.components) == (
        "adapter:a",
        "skill:z",
    )


def test_workflow_lock_rejects_duplicate_ids_invalid_hashes_and_unknown_fields() -> None:
    with pytest.raises(CoreFailure, match="AWP_CATALOG_CLOSURE_BLOCKED"):
        normalize_workflow_lock(_lock(_component("skill:a"), _component("skill:a")))
    with pytest.raises(CoreFailure, match="AWP_CATALOG_CLOSURE_BLOCKED"):
        normalize_workflow_lock(_lock(_component("skill:a", sha="latest")))
    with pytest.raises(CoreFailure, match="AWP_CATALOG_CLOSURE_BLOCKED"):
        normalize_workflow_lock(_lock({**_component("skill:a"), "url": "https://example.test"}))


def test_task3_schemas_are_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    for schema_id in (
        "agent-workflow.profile",
        "agent-workflow.catalog",
        "agent-workflow.workflow-lock",
        "agent-workflow.capability-manifest",
    ):
        assert catalog.supported_versions(schema_id) == (1,)

    catalog.load_and_validate(_lock(_component("skill:a")))
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**_lock(_component("skill:a")), "extra": True})
