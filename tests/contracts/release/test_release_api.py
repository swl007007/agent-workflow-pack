from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from agent_stack.core.api import CoreFailure, SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]


def _identity() -> dict[str, object]:
    from agent_stack.release.identity import release_id

    return {
        "schema_id": "agent-workflow.release-identity",
        "schema_version": 1,
        "repository_id": "github.com/example/agent-workflow-pack",
        "distribution_name": "agent-workflow-pack",
        "version": "0.1.0",
        "release_id": release_id(
            "github.com/example/agent-workflow-pack", "agent-workflow-pack", "0.1.0"
        ),
    }


def _manifest() -> dict[str, object]:
    identity = _identity()
    return {
        "schema_id": "agent-workflow.release-manifest",
        "schema_version": 1,
        "release_id": identity["release_id"],
        "version": "0.1.0",
        "repository": {
            "host": "github.com",
            "owner": "example",
            "name": "agent-workflow-pack",
            "tag": "v0.1.0",
            "immutable_release_required": True,
        },
        "source_commit": "a" * 40,
        "bundles": {
            name: character * 64
            for name, character in zip(
                (
                    "trust_policy",
                    "workflow_lock",
                    "artifact",
                    "schema",
                    "migration",
                    "compatibility",
                    "launcher",
                ),
                "bcdef12",
                strict=True,
            )
        },
        "assets": {
            "wheel": {
                "name": "agent_workflow_pack-0.1.0-py3-none-any.whl",
                "url": "https://github.com/example/agent-workflow-pack/releases/download/v0.1.0/agent_workflow_pack-0.1.0-py3-none-any.whl",
                "size": 100,
                "sha256": "1" * 64,
            },
            "sdist": {
                "name": "agent_workflow_pack-0.1.0.tar.gz",
                "url": "https://github.com/example/agent-workflow-pack/releases/download/v0.1.0/agent_workflow_pack-0.1.0.tar.gz",
                "size": 200,
                "sha256": "2" * 64,
            },
        },
    }


def test_release_kernel_exports_frozen_callables_and_models() -> None:
    from agent_stack.release import kernel
    from agent_stack.release.identity import ReleaseIdentity

    assert callable(kernel.release_id)
    assert callable(kernel.verify_release_manifest)
    assert callable(kernel.classify_compatibility)
    assert callable(kernel.select_candidate_runtime)
    assert ReleaseIdentity in kernel.PUBLIC_MODELS
    assert tuple(inspect.signature(kernel.release_id).parameters) == (
        "repository_id",
        "distribution_name",
        "version",
    )


def test_release_schemas_are_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    for schema_id in (
        "agent-workflow.release-identity",
        "agent-workflow.release-manifest",
        "agent-workflow.release-trust-policy",
        "agent-workflow.release-compatibility",
        "agent-workflow.release-gate-result",
    ):
        assert catalog.supported_versions(schema_id) == (1,)
    catalog.load_and_validate(_identity())
    catalog.load_and_validate(_manifest())


@pytest.mark.parametrize(
    "forbidden",
    [
        {"manifest_digest": "f" * 64},
        {"wheel_sha256": "f" * 64},
        {"source_url": "https://example.invalid/wheel"},
    ],
)
def test_release_identity_rejects_container_and_source_fields(
    forbidden: dict[str, object],
) -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**_identity(), **forbidden})


def test_manifest_rejects_its_own_digest() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**_manifest(), "manifest_digest": "f" * 64})


def test_lifecycle_failure_is_structured() -> None:
    from agent_stack.release.errors import LifecycleFailure

    failure = LifecycleFailure(
        "AWP_RELEASE_IDENTITY_INVALID",
        "release identity is invalid",
        exit_code=30,
        details={"field": "release_id"},
    )
    assert failure.to_document() == {
        "schema_id": "agent-workflow.lifecycle-failure",
        "schema_version": 1,
        "code": "AWP_RELEASE_IDENTITY_INVALID",
        "exit_code": 30,
        "message": "release identity is invalid",
        "details": {"field": "release_id"},
    }
