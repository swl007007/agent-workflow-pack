"""Packaged GitHub immutable-release trust policy and bounded HTTPS retrieval."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from agent_stack.core.api import digest

from .errors import LifecycleFailure

if TYPE_CHECKING:
    from .manifest import ReleaseLocator


_POLICY_FIELDS = {
    "schema_id",
    "schema_version",
    "policy_id",
    "host",
    "owner",
    "repository",
    "tag_template",
    "manifest_asset_name",
    "api_base_url",
    "allowed_redirect_hosts",
    "immutable_release_required",
    "policy_digest",
}


def _trust_failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_RELEASE_TRUST_POLICY_INVALID", message, exit_code=30, details=details
    )


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _trust_failure("trust-policy string is invalid", field=field)
    return value


def validate_https_url(url: str, allowed_hosts: set[str]) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise _trust_failure("release URL is invalid") from error
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or host not in allowed_hosts
    ):
        raise _trust_failure("release URL violates the packaged HTTPS authority policy")
    return host


@dataclass(frozen=True)
class FetchedContent:
    final_url: str
    body: bytes


def fetch_https(url: str, max_bytes: int) -> FetchedContent:
    """Fetch one bounded HTTPS object; callers validate initial and final authorities."""

    if max_bytes <= 0:
        raise _trust_failure("release fetch limit must be positive")
    request = Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - URL is policy-derived.
            body = response.read(max_bytes + 1)
            final_url = response.geturl()
    except OSError as error:
        raise LifecycleFailure(
            "AWP_RELEASE_MANIFEST_INVALID",
            "release metadata could not be retrieved",
            exit_code=30,
        ) from error
    if len(body) > max_bytes:
        raise LifecycleFailure(
            "AWP_RELEASE_MANIFEST_INVALID",
            "release metadata exceeded its size limit",
            exit_code=30,
        )
    return FetchedContent(final_url=final_url, body=body)


@dataclass(frozen=True)
class PackagedTrustPolicy:
    policy_id: str
    host: str
    owner: str
    repository: str
    tag_template: str
    manifest_asset_name: str
    api_base_url: str
    allowed_redirect_hosts: tuple[str, ...]
    immutable_release_required: bool
    policy_digest: str

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> PackagedTrustPolicy:
        if set(document) != _POLICY_FIELDS:
            raise _trust_failure("trust-policy fields are not closed")
        hosts = document.get("allowed_redirect_hosts")
        if not isinstance(hosts, list) or not hosts or not all(
            isinstance(host, str) and host and host == host.lower() for host in hosts
        ):
            raise _trust_failure("trust-policy redirect hosts are invalid")
        normalized_hosts = tuple(hosts)
        if len(set(normalized_hosts)) != len(normalized_hosts):
            raise _trust_failure("trust-policy redirect hosts repeat")
        projection = dict(document)
        claimed_digest = projection.pop("policy_digest", None)
        actual_digest = digest("agent-workflow.release-trust-policy.v1", projection)
        if claimed_digest != actual_digest:
            raise _trust_failure("trust-policy digest does not match packaged bytes")
        expected = {
            "schema_id": "agent-workflow.release-trust-policy",
            "schema_version": 1,
            "policy_id": "github-immutable-release-v1",
            "host": "github.com",
            "tag_template": "v{version}",
            "manifest_asset_name": "release-manifest.json",
            "api_base_url": "https://api.github.com",
            "immutable_release_required": True,
        }
        mismatches = sorted(
            field for field, value in expected.items() if document.get(field) != value
        )
        if mismatches:
            raise _trust_failure("v0.1 trust-policy constants changed", fields=mismatches)
        owner = _nonempty(document.get("owner"), "owner")
        repository = _nonempty(document.get("repository"), "repository")
        if "github.com" not in normalized_hosts:
            raise _trust_failure("manifest release host is not in the redirect allowlist")
        return cls(
            policy_id="github-immutable-release-v1",
            host="github.com",
            owner=owner,
            repository=repository,
            tag_template="v{version}",
            manifest_asset_name="release-manifest.json",
            api_base_url="https://api.github.com",
            allowed_redirect_hosts=normalized_hosts,
            immutable_release_required=True,
            policy_digest=str(claimed_digest),
        )

    @property
    def repository_id(self) -> str:
        return f"{self.host}/{self.owner}/{self.repository}"


@dataclass(frozen=True)
class DerivedManifestLocator:
    api_url: str
    tag: str
    manifest_asset_name: str


def derive_manifest_locator(
    locator: ReleaseLocator, policy: PackagedTrustPolicy
) -> DerivedManifestLocator:
    version = _nonempty(locator.version, "version")
    tag = policy.tag_template.format(version=version)
    owner = quote(policy.owner, safe="")
    repository = quote(policy.repository, safe="")
    encoded_tag = quote(tag, safe="")
    api_url = (
        f"{policy.api_base_url}/repos/{owner}/{repository}/releases/tags/{encoded_tag}"
    )
    validate_https_url(api_url, {"api.github.com"})
    return DerivedManifestLocator(api_url, tag, policy.manifest_asset_name)
