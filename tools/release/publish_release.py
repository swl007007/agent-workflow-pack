#!/usr/bin/env python3
"""Generate a detached manifest, publish final bytes once, and re-verify."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast

from agent_stack._vendor import yaml
from agent_stack.core.api import canonical_json_bytes, digest
from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.gates import run_release_gates, verify_release_artifact_set
from agent_stack.release.identity import release_id

if __package__:
    from .verify_published_release import verify_published_release
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.release.verify_published_release import verify_published_release


class PublicationClient(Protocol):
    def create_release_once(self, tag: str, source_commit: str) -> str: ...

    def upload_asset_once(self, release_id: str, path: Path) -> None: ...

    def make_release_immutable(self, release_id: str) -> None: ...

    def fetch_release(self, tag: str) -> Mapping[str, object]: ...

    def download_asset(self, url: str) -> bytes: ...


def _failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_RELEASE_PUBLICATION_INVALID", message, exit_code=30, details=details
    )


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _tree_digest(root: Path, relatives: tuple[str, ...], domain: str) -> str:
    records: list[dict[str, str]] = []
    for relative in relatives:
        path = root / relative
        paths = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for item in paths:
            records.append(
                {
                    "path": item.relative_to(root).as_posix(),
                    "sha256": _hash(item),
                }
            )
    return digest(domain, {"files": records})


def _trust_policy(root: Path) -> Mapping[str, object]:
    value = yaml.safe_load(  # type: ignore[no-untyped-call]
        (root / "release/trust-policy.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(value, Mapping):
        raise _failure("packaged release trust policy is invalid")
    return cast(Mapping[str, object], value)


def _bundle_roots(root: Path) -> dict[str, str]:
    policy = _trust_policy(root)
    policy_digest = policy.get("policy_digest")
    if not isinstance(policy_digest, str):
        raise _failure("packaged trust policy digest is missing")
    return {
        "trust_policy": policy_digest,
        "workflow_lock": _tree_digest(
            root, ("catalog",), "agent-workflow.workflow-lock-bundle.v1"
        ),
        "artifact": _tree_digest(
            root,
            ("artifact-definitions", "overlays"),
            "agent-workflow.artifact-bundle.v1",
        ),
        "schema": _tree_digest(root, ("schemas",), "agent-workflow.schema-bundle.v1"),
        "migration": _tree_digest(
            root, ("compatibility",), "agent-workflow.migration-bundle.v1"
        ),
        "compatibility": _tree_digest(
            root, ("compatibility",), "agent-workflow.compatibility-bundle.v1"
        ),
        "launcher": _tree_digest(
            root, ("runtime-launcher",), "agent-workflow.launcher-bundle.v1"
        ),
    }


def generate_release_manifest(
    *, artifact_set_path: Path, version: str, source_commit: str
) -> Path:
    artifact_set = verify_release_artifact_set(artifact_set_path)
    run_release_gates(artifact_set)
    root = artifact_set.root
    policy = _trust_policy(root)
    owner = str(policy["owner"])
    repository = str(policy["repository"])
    tag = str(policy["tag_template"]).format(version=version)
    logical_release_id = release_id(
        f"github.com/{owner}/{repository}", "agent-workflow-pack", version
    )
    assets = {}
    for record in (artifact_set.wheel, artifact_set.sdist):
        assets[record.kind] = {
            "name": record.path.name,
            "url": f"https://github.com/{owner}/{repository}/releases/download/{tag}/{record.path.name}",
            "size": record.size,
            "sha256": record.sha256,
        }
    manifest = {
        "schema_id": "agent-workflow.release-manifest",
        "schema_version": 1,
        "release_id": logical_release_id,
        "version": version,
        "repository": {
            "host": "github.com",
            "owner": owner,
            "name": repository,
            "tag": tag,
            "immutable_release_required": True,
        },
        "source_commit": source_commit,
        "bundles": _bundle_roots(root),
        "assets": assets,
    }
    path = artifact_set_path.parent / "release-manifest.json"
    path.write_bytes(canonical_json_bytes(manifest))
    return path


def _assert_final_bytes(artifact_set_path: Path) -> None:
    verify_release_artifact_set(artifact_set_path)


def publish_immutable_release(
    *,
    artifact_set_path: Path,
    version: str,
    source_commit: str,
    client: PublicationClient,
) -> dict[str, object]:
    artifact_set = verify_release_artifact_set(artifact_set_path)
    run_release_gates(artifact_set)
    manifest = generate_release_manifest(
        artifact_set_path=artifact_set_path,
        version=version,
        source_commit=source_commit,
    )
    tag = f"v{version}"
    release_id = client.create_release_once(tag, source_commit)
    try:
        _assert_final_bytes(artifact_set_path)
    except LifecycleFailure as error:
        raise _failure("final artifact changed after release creation") from error
    assets = (artifact_set.wheel.path, artifact_set.sdist.path, manifest)
    for path in assets:
        _assert_final_bytes(artifact_set_path)
        client.upload_asset_once(release_id, path)
    _assert_final_bytes(artifact_set_path)
    client.make_release_immutable(release_id)
    return verify_published_release(
        client=client,
        tag=tag,
        source_commit=source_commit,
        local_assets={path.name: path for path in assets},
    )


class GitHubAPIClient:
    """Minimal GitHub immutable-release transport used only by release CI."""

    def __init__(self, repository: str, token: str) -> None:
        self.repository = repository
        self.token = token
        self.api = f"https://api.github.com/repos/{repository}"
        self._upload_urls: dict[str, str] = {}

    def _request(
        self,
        method: str,
        url: str,
        body: object | None = None,
        *,
        content_type: str = "application/vnd.github+json",
    ) -> object:
        raw = None if body is None else (
            body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        )
        request = urllib.request.Request(
            url,
            data=raw,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": content_type,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            data = response.read()
        if content_type == "application/octet-stream" and method == "GET":
            return data
        return json.loads(data) if data else {}

    def create_release_once(self, tag: str, source_commit: str) -> str:
        payload = self._request(
            "POST",
            f"{self.api}/releases",
            {
                "tag_name": tag,
                "target_commitish": source_commit,
                "name": tag,
                "draft": True,
                "prerelease": False,
            },
        )
        if not isinstance(payload, Mapping) or not isinstance(payload.get("id"), int):
            raise _failure("GitHub did not create one release")
        release_id = str(payload["id"])
        upload_url = payload.get("upload_url")
        if not isinstance(upload_url, str):
            raise _failure("GitHub release lacks an upload URL")
        self._upload_urls[release_id] = upload_url.split("{", 1)[0]
        return release_id

    def upload_asset_once(self, release_id: str, path: Path) -> None:
        upload_url = self._upload_urls.get(release_id)
        if upload_url is None:
            raise _failure("unknown GitHub release upload authority")
        self._request(
            "POST",
            f"{upload_url}?name={urllib.parse.quote(path.name)}",
            path.read_bytes(),
            content_type="application/octet-stream",
        )

    def make_release_immutable(self, release_id: str) -> None:
        self._request(
            "PATCH",
            f"{self.api}/releases/{release_id}",
            {"draft": False, "immutable": True},
        )

    def fetch_release(self, tag: str) -> Mapping[str, object]:
        payload = self._request("GET", f"{self.api}/releases/tags/{urllib.parse.quote(tag)}")
        if not isinstance(payload, Mapping):
            raise _failure("GitHub release metadata is invalid")
        return cast(Mapping[str, object], payload)

    def download_asset(self, url: str) -> bytes:
        payload = self._request("GET", url, content_type="application/octet-stream")
        if not isinstance(payload, bytes):
            raise _failure("GitHub asset download did not return bytes")
        return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-set", type=Path, default=Path("dist/release-artifact-set.json"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository", default="pinned-owner/agent-workflow-pack")
    arguments = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    result = publish_immutable_release(
        artifact_set_path=arguments.artifact_set,
        version=arguments.version,
        source_commit=arguments.source_commit,
        client=GitHubAPIClient(arguments.repository, token),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
