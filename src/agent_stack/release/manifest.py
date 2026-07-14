"""Detached release-manifest verification against immutable GitHub metadata."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import SchemaCatalog, canonical_json_bytes

from . import trust as release_trust
from .errors import LifecycleFailure
from .identity import ReleaseIdentity
from .trust import (
    PackagedTrustPolicy,
    derive_manifest_locator,
    validate_https_url,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_BUNDLE_FIELDS = {
    "trust_policy",
    "workflow_lock",
    "artifact",
    "schema",
    "migration",
    "compatibility",
    "launcher",
}
_MANIFEST_FIELDS = {
    "schema_id",
    "schema_version",
    "release_id",
    "version",
    "repository",
    "source_commit",
    "bundles",
    "assets",
}


def _manifest_failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_RELEASE_MANIFEST_INVALID", message, exit_code=30, details=details
    )


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise _manifest_failure("release digest is invalid", field=field)
    return value


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _manifest_failure("release object is invalid", field=field)
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _manifest_failure("release string is invalid", field=field)
    return value


@dataclass(frozen=True)
class ReleaseLocator:
    version: str
    release_manifest_digest: str
    expected_bundles: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        _string(self.version, "version")
        _sha256(self.release_manifest_digest, "release_manifest_digest")
        if self.expected_bundles is not None:
            for field, value in self.expected_bundles.items():
                if field not in _BUNDLE_FIELDS:
                    raise _manifest_failure("expected bundle identity is unknown", field=field)
                _sha256(value, field)

    def to_document(self) -> dict[str, object]:
        return {
            "version": self.version,
            "release_manifest_digest": self.release_manifest_digest,
            "expected_bundles": (
                dict(sorted(self.expected_bundles.items()))
                if self.expected_bundles is not None
                else None
            ),
        }


@dataclass(frozen=True)
class VerifiedRelease:
    identity: ReleaseIdentity
    manifest_digest: str
    source_commit: str
    bundles: Mapping[str, str]
    assets: Mapping[str, Mapping[str, object]]
    immutable_release: bool
    compatibility: Mapping[str, object] | None = None


def _parse_json_object(body: bytes, label: str) -> dict[str, object]:
    try:
        text = body.decode("utf-8")
        parsed = SchemaCatalog.parse_json(text)
    except (UnicodeError, LifecycleFailure) as error:
        raise _manifest_failure(f"{label} is not valid canonical JSON") from error
    except Exception as error:
        raise _manifest_failure(f"{label} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise _manifest_failure(f"{label} must be an object")
    if canonical_json_bytes(parsed) != body:
        raise _manifest_failure(f"{label} is not canonical JSON")
    return cast(dict[str, object], parsed)


def _asset_inventory(metadata: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    raw_assets = metadata.get("assets")
    if not isinstance(raw_assets, Sequence) or isinstance(raw_assets, (str, bytes)):
        raise _manifest_failure("GitHub release assets are invalid")
    assets: dict[str, Mapping[str, object]] = {}
    for raw in raw_assets:
        asset = _mapping(raw, "release.assets")
        name = _string(asset.get("name"), "release.assets.name")
        if name in assets:
            raise _manifest_failure("GitHub release asset name repeats", asset=name)
        assets[name] = asset
    return assets


def _manifest_asset_url(
    metadata_assets: Mapping[str, Mapping[str, object]],
    name: str,
    policy: PackagedTrustPolicy,
) -> str:
    try:
        asset = metadata_assets[name]
    except KeyError as error:
        raise _manifest_failure("detached manifest asset is missing") from error
    url = _string(asset.get("browser_download_url"), "manifest_asset.url")
    validate_https_url(url, set(policy.allowed_redirect_hosts))
    return url


def _validate_asset(
    kind: str,
    manifest_asset: Mapping[str, object],
    release_assets: Mapping[str, Mapping[str, object]],
    policy: PackagedTrustPolicy,
) -> dict[str, object]:
    if set(manifest_asset) != {"name", "url", "size", "sha256"}:
        raise _manifest_failure("manifest asset fields are not closed", kind=kind)
    name = _string(manifest_asset.get("name"), f"assets.{kind}.name")
    url = _string(manifest_asset.get("url"), f"assets.{kind}.url")
    size = manifest_asset.get("size")
    sha256 = _sha256(manifest_asset.get("sha256"), f"assets.{kind}.sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise _manifest_failure("manifest asset size is invalid", kind=kind)
    validate_https_url(url, set(policy.allowed_redirect_hosts))
    try:
        release_asset = release_assets[name]
    except KeyError as error:
        raise _manifest_failure("manifest names an absent GitHub asset", kind=kind) from error
    expected = {
        "browser_download_url": url,
        "size": size,
        "digest": f"sha256:{sha256}",
    }
    mismatches = sorted(
        field for field, value in expected.items() if release_asset.get(field) != value
    )
    if mismatches:
        raise _manifest_failure(
            "manifest asset disagrees with immutable release metadata",
            kind=kind,
            fields=mismatches,
        )
    return {"name": name, "url": url, "size": size, "sha256": sha256}


def verify_release_manifest(
    locator: ReleaseLocator, packaged_policy: PackagedTrustPolicy
) -> VerifiedRelease:
    derived = derive_manifest_locator(locator, packaged_policy)
    metadata_response = release_trust.fetch_https(derived.api_url, 2 * 1024 * 1024)
    validate_https_url(metadata_response.final_url, {"api.github.com"})
    metadata = _parse_json_object(metadata_response.body, "GitHub release metadata")
    if metadata.get("tag_name") != derived.tag:
        raise _manifest_failure("GitHub release tag does not match the requested version")
    if metadata.get("immutable") is not True:
        raise _manifest_failure("GitHub release is not immutable")
    source_commit = metadata.get("tag_commit_sha")
    if not isinstance(source_commit, str) or not _COMMIT.fullmatch(source_commit):
        raise _manifest_failure("GitHub release source commit is invalid")
    release_assets = _asset_inventory(metadata)
    manifest_url = _manifest_asset_url(
        release_assets, derived.manifest_asset_name, packaged_policy
    )
    manifest_response = release_trust.fetch_https(manifest_url, 1024 * 1024)
    validate_https_url(
        manifest_response.final_url, set(packaged_policy.allowed_redirect_hosts)
    )
    actual_manifest_digest = hashlib.sha256(manifest_response.body).hexdigest()
    if actual_manifest_digest != locator.release_manifest_digest:
        raise _manifest_failure("detached manifest bytes do not match the pinned digest")
    manifest_release_asset = release_assets[derived.manifest_asset_name]
    expected_manifest_evidence = {
        "size": len(manifest_response.body),
        "digest": f"sha256:{actual_manifest_digest}",
    }
    if any(
        manifest_release_asset.get(field) != value
        for field, value in expected_manifest_evidence.items()
    ):
        raise _manifest_failure("detached manifest disagrees with release asset evidence")
    manifest = _parse_json_object(manifest_response.body, "detached manifest")
    if set(manifest) != _MANIFEST_FIELDS:
        raise _manifest_failure("detached manifest fields are not closed")
    if (
        manifest.get("schema_id") != "agent-workflow.release-manifest"
        or manifest.get("schema_version") != 1
        or manifest.get("version") != locator.version
    ):
        raise _manifest_failure("detached manifest identity/version is invalid")
    repository = _mapping(manifest.get("repository"), "repository")
    expected_repository = {
        "host": packaged_policy.host,
        "owner": packaged_policy.owner,
        "name": packaged_policy.repository,
        "tag": derived.tag,
        "immutable_release_required": True,
    }
    if dict(repository) != expected_repository:
        raise _manifest_failure("detached manifest repository authority is invalid")
    identity = ReleaseIdentity(
        packaged_policy.repository_id, "agent-workflow-pack", locator.version
    )
    if manifest.get("release_id") != identity.release_id:
        raise _manifest_failure("detached manifest Release Identity is invalid")
    if manifest.get("source_commit") != source_commit:
        raise _manifest_failure("detached manifest source commit is invalid")
    bundles = _mapping(manifest.get("bundles"), "bundles")
    if set(bundles) != _BUNDLE_FIELDS:
        raise _manifest_failure("detached manifest bundle fields are not closed")
    normalized_bundles = {
        field: _sha256(bundles.get(field), f"bundles.{field}")
        for field in sorted(_BUNDLE_FIELDS)
    }
    if normalized_bundles["trust_policy"] != packaged_policy.policy_digest:
        raise _manifest_failure("detached manifest trust-policy root changed")
    if locator.expected_bundles is not None:
        mismatches = sorted(
            field
            for field, value in locator.expected_bundles.items()
            if normalized_bundles.get(field) != value
        )
        if mismatches:
            raise _manifest_failure(
                "detached manifest bundle roots disagree with the locator",
                fields=mismatches,
            )
    assets = _mapping(manifest.get("assets"), "assets")
    if set(assets) != {"wheel", "sdist"}:
        raise _manifest_failure("detached manifest distribution assets are not closed")
    normalized_assets = {
        kind: _validate_asset(
            kind,
            _mapping(assets.get(kind), f"assets.{kind}"),
            release_assets,
            packaged_policy,
        )
        for kind in ("wheel", "sdist")
    }
    return VerifiedRelease(
        identity=identity,
        manifest_digest=actual_manifest_digest,
        source_commit=source_commit,
        bundles=MappingProxyType(normalized_bundles),
        assets=MappingProxyType(
            {kind: MappingProxyType(value) for kind, value in normalized_assets.items()}
        ),
        immutable_release=True,
    )
