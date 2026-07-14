from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agent_stack.core.api import digest
from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.manifest import ReleaseLocator
from agent_stack.release.trust import (
    PackagedTrustPolicy,
    derive_manifest_locator,
)
from agent_stack._vendor import yaml


ROOT = Path(__file__).resolve().parents[3]


def policy_document() -> dict[str, object]:
    projection: dict[str, object] = {
        "schema_id": "agent-workflow.release-trust-policy",
        "schema_version": 1,
        "policy_id": "github-immutable-release-v1",
        "host": "github.com",
        "owner": "pinned-owner",
        "repository": "agent-workflow-pack",
        "tag_template": "v{version}",
        "manifest_asset_name": "release-manifest.json",
        "api_base_url": "https://api.github.com",
        "allowed_redirect_hosts": ["github.com", "objects.githubusercontent.com"],
        "immutable_release_required": True,
    }
    return {
        **projection,
        "policy_digest": digest("agent-workflow.release-trust-policy.v1", projection),
    }


def test_packaged_policy_derives_the_only_manifest_locator() -> None:
    policy = PackagedTrustPolicy.from_document(policy_document())
    locator = ReleaseLocator(version="0.1.0", release_manifest_digest="a" * 64)

    derived = derive_manifest_locator(locator, policy)

    assert derived.api_url == (
        "https://api.github.com/repos/pinned-owner/agent-workflow-pack/"
        "releases/tags/v0.1.0"
    )
    assert derived.tag_commit_url == (
        "https://api.github.com/repos/pinned-owner/agent-workflow-pack/commits/v0.1.0"
    )
    assert derived.tag == "v0.1.0"
    assert derived.manifest_asset_name == "release-manifest.json"
    assert policy.repository_id == "github.com/pinned-owner/agent-workflow-pack"


def test_checked_in_trust_policy_uses_the_real_release_repository() -> None:
    document = yaml.safe_load(  # type: ignore[no-untyped-call]
        (ROOT / "release/trust-policy.yaml").read_text(encoding="utf-8")
    )

    assert isinstance(document, dict)
    policy = PackagedTrustPolicy.from_document(document)
    assert policy.owner == "swl007007"
    assert policy.repository == "agent-workflow-pack"


def test_locator_has_no_repository_url_hash_or_trust_override_fields() -> None:
    locator = ReleaseLocator(
        version="0.1.0",
        release_manifest_digest="a" * 64,
        expected_bundles={"workflow_lock": "b" * 64},
    )
    assert set(locator.to_document()) == {
        "version",
        "release_manifest_digest",
        "expected_bundles",
    }
    with pytest.raises(TypeError):
        replace(locator, repository="attacker/repo")


def test_packaged_policy_rejects_any_unbound_trust_root_change() -> None:
    changed = {**policy_document(), "owner": "attacker"}
    with pytest.raises(LifecycleFailure, match="AWP_RELEASE_TRUST_POLICY_INVALID"):
        PackagedTrustPolicy.from_document(changed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "example.com"),
        ("tag_template", "release-{version}"),
        ("manifest_asset_name", "other.json"),
        ("api_base_url", "http://api.github.com"),
        ("immutable_release_required", False),
    ],
)
def test_v01_policy_contract_is_closed(field: str, value: object) -> None:
    projection = policy_document()
    projection[field] = value
    digest_projection = dict(projection)
    digest_projection.pop("policy_digest")
    projection["policy_digest"] = digest(
        "agent-workflow.release-trust-policy.v1", digest_projection
    )
    with pytest.raises(LifecycleFailure, match="AWP_RELEASE_TRUST_POLICY_INVALID"):
        PackagedTrustPolicy.from_document(projection)
