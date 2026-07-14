from __future__ import annotations

import hashlib
from collections.abc import Callable

import pytest

from agent_stack.core.api import canonical_json_bytes
from agent_stack.release import kernel
from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.identity import release_id
from agent_stack.release.manifest import (
    ReleaseLocator,
    VerifiedRelease,
    discover_release_locator,
)
from agent_stack.release.trust import FetchedContent, PackagedTrustPolicy
from tests.unit.release.test_trust_policy import policy_document


VERSION = "0.1.0"
SOURCE_COMMIT = "a" * 40
WHEEL_NAME = "agent_workflow_pack-0.1.0-py3-none-any.whl"
SDIST_NAME = "agent_workflow_pack-0.1.0.tar.gz"
BASE = "https://github.com/pinned-owner/agent-workflow-pack/releases/download/v0.1.0"
MANIFEST_URL = f"{BASE}/release-manifest.json"
WHEEL_URL = f"{BASE}/{WHEEL_NAME}"
SDIST_URL = f"{BASE}/{SDIST_NAME}"


def _make_mutable(value: dict[str, object]) -> None:
    value["immutable"] = False


def _change_tag(value: dict[str, object]) -> None:
    value["tag_name"] = "v9.9.9"


def _change_source(value: dict[str, object]) -> None:
    value["tag_commit_sha"] = "b" * 40


def _make_noncanonical(value: bytes) -> bytes:
    return b"\n" + value


def _bundles() -> dict[str, str]:
    return {
        "trust_policy": str(policy_document()["policy_digest"]),
        "workflow_lock": "2" * 64,
        "artifact": "3" * 64,
        "schema": "4" * 64,
        "migration": "5" * 64,
        "compatibility": "6" * 64,
        "launcher": "7" * 64,
    }


def _manifest() -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.release-manifest",
        "schema_version": 1,
        "release_id": release_id(
            "github.com/pinned-owner/agent-workflow-pack",
            "agent-workflow-pack",
            VERSION,
        ),
        "version": VERSION,
        "repository": {
            "host": "github.com",
            "owner": "pinned-owner",
            "name": "agent-workflow-pack",
            "tag": "v0.1.0",
            "immutable_release_required": True,
        },
        "source_commit": SOURCE_COMMIT,
        "bundles": _bundles(),
        "assets": {
            "wheel": {
                "name": WHEEL_NAME,
                "url": WHEEL_URL,
                "size": 101,
                "sha256": "8" * 64,
            },
            "sdist": {
                "name": SDIST_NAME,
                "url": SDIST_URL,
                "size": 202,
                "sha256": "9" * 64,
            },
        },
    }


def _release_metadata(manifest_bytes: bytes) -> dict[str, object]:
    return {
        "tag_name": "v0.1.0",
        "immutable": True,
        "tag_commit_sha": SOURCE_COMMIT,
        "assets": [
            {
                "name": "release-manifest.json",
                "browser_download_url": MANIFEST_URL,
                "size": len(manifest_bytes),
                "digest": f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}",
            },
            {
                "name": WHEEL_NAME,
                "browser_download_url": WHEEL_URL,
                "size": 101,
                "digest": f"sha256:{'8' * 64}",
            },
            {
                "name": SDIST_NAME,
                "browser_download_url": SDIST_URL,
                "size": 202,
                "digest": f"sha256:{'9' * 64}",
            },
        ],
    }


def _install_fetcher(
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict[str, object],
    *,
    metadata_mutator: Callable[[dict[str, object]], None] | None = None,
    manifest_bytes_mutator: Callable[[bytes], bytes] | None = None,
    api_final_url: str | None = None,
) -> tuple[ReleaseLocator, PackagedTrustPolicy]:
    import agent_stack.release.trust as trust

    manifest_bytes = canonical_json_bytes(manifest)
    if manifest_bytes_mutator is not None:
        manifest_bytes = manifest_bytes_mutator(manifest_bytes)
    metadata = _release_metadata(manifest_bytes)
    if metadata_mutator is not None:
        metadata_mutator(metadata)
    metadata_bytes = canonical_json_bytes(metadata)
    policy = PackagedTrustPolicy.from_document(policy_document())
    locator = ReleaseLocator(
        version=VERSION,
        release_manifest_digest=hashlib.sha256(manifest_bytes).hexdigest(),
        expected_bundles=_bundles(),
    )
    api_url = (
        "https://api.github.com/repos/pinned-owner/agent-workflow-pack/"
        "releases/tags/v0.1.0"
    )

    def fetch(url: str, max_bytes: int) -> FetchedContent:
        assert max_bytes > 0
        if url == api_url:
            return FetchedContent(api_final_url or api_url, metadata_bytes)
        if url == MANIFEST_URL:
            return FetchedContent(MANIFEST_URL, manifest_bytes)
        raise AssertionError(f"unexpected fetch URL: {url}")

    monkeypatch.setattr(trust, "fetch_https", fetch)
    return locator, policy


def test_verified_manifest_binds_repository_assets_source_and_bundles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locator, policy = _install_fetcher(monkeypatch, _manifest())

    verified = kernel.verify_release_manifest(locator, policy)

    assert isinstance(verified, VerifiedRelease)
    assert verified.identity.release_id == _manifest()["release_id"]
    assert verified.source_commit == SOURCE_COMMIT
    assert verified.manifest_digest == locator.release_manifest_digest
    assert verified.bundles == _bundles()
    assert verified.assets["wheel"]["sha256"] == "8" * 64


def test_immutable_release_metadata_discovers_the_detached_manifest_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected, policy = _install_fetcher(monkeypatch, _manifest())

    discovered = discover_release_locator(VERSION, policy)

    assert discovered.version == VERSION
    assert discovered.release_manifest_digest == expected.release_manifest_digest
    assert discovered.expected_bundles is None


@pytest.mark.parametrize(
    "mutation",
    [
        "mutable-release",
        "wrong-tag",
        "wrong-source",
        "wrong-asset-size",
        "wrong-asset-hash",
        "wrong-repository",
        "wrong-bundle",
        "redirect-host",
        "noncanonical-manifest",
    ],
)
def test_manifest_verification_fails_closed(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    manifest = _manifest()
    metadata_mutator: Callable[[dict[str, object]], None] | None = None
    bytes_mutator: Callable[[bytes], bytes] | None = None
    api_final_url: str | None = None

    if mutation == "mutable-release":
        metadata_mutator = _make_mutable
    elif mutation == "wrong-tag":
        metadata_mutator = _change_tag
    elif mutation == "wrong-source":
        metadata_mutator = _change_source
    elif mutation == "wrong-asset-size":
        manifest["assets"]["wheel"]["size"] = 999  # type: ignore[index]
    elif mutation == "wrong-asset-hash":
        manifest["assets"]["wheel"]["sha256"] = "f" * 64  # type: ignore[index]
    elif mutation == "wrong-repository":
        manifest["repository"]["owner"] = "attacker"  # type: ignore[index]
    elif mutation == "wrong-bundle":
        manifest["bundles"]["schema"] = "f" * 64  # type: ignore[index]
    elif mutation == "redirect-host":
        api_final_url = "https://attacker.invalid/release"
    elif mutation == "noncanonical-manifest":
        bytes_mutator = _make_noncanonical

    locator, policy = _install_fetcher(
        monkeypatch,
        manifest,
        metadata_mutator=metadata_mutator,
        manifest_bytes_mutator=bytes_mutator,
        api_final_url=api_final_url,
    )
    if mutation == "wrong-bundle":
        locator = ReleaseLocator(
            version=locator.version,
            release_manifest_digest=locator.release_manifest_digest,
            expected_bundles=_bundles(),
        )

    with pytest.raises(LifecycleFailure) as captured:
        kernel.verify_release_manifest(locator, policy)
    assert captured.value.exit_code == 30


def test_manifest_digest_mismatch_fails_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locator, policy = _install_fetcher(monkeypatch, _manifest())
    locator = ReleaseLocator(
        version=locator.version,
        release_manifest_digest="f" * 64,
        expected_bundles=locator.expected_bundles,
    )
    with pytest.raises(LifecycleFailure, match="AWP_RELEASE_MANIFEST_INVALID"):
        kernel.verify_release_manifest(locator, policy)
