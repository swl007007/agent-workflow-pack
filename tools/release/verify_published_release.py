#!/usr/bin/env python3
"""Re-fetch and verify one immutable published release and all local assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.first_install import canonical_first_install_command_digest


class PublishedReleaseClient(Protocol):
    def fetch_release(self, tag: str) -> Mapping[str, object]: ...

    def resolve_tag_commit(self, tag: str) -> str: ...

    def download_asset(self, url: str) -> bytes: ...


def _failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_RELEASE_PUBLICATION_INVALID", message, exit_code=30, details=details
    )


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_published_release(
    *,
    client: PublishedReleaseClient,
    tag: str,
    source_commit: str,
    local_assets: Mapping[str, Path],
    expected_body: str,
) -> dict[str, object]:
    metadata = client.fetch_release(tag)
    if metadata.get("tag_name") != tag:
        raise _failure("published release identity/source commit changed")
    if client.resolve_tag_commit(tag) != source_commit:
        raise _failure("published release identity/source commit changed")
    if metadata.get("immutable") is not True:
        raise _failure("published release is not immutable")
    body = metadata.get("body")
    if not isinstance(body, str) or not body or body != expected_body:
        raise _failure("published release body differs from the deterministic candidate")
    raw_assets = metadata.get("assets")
    if not isinstance(raw_assets, list):
        raise _failure("published release asset inventory is invalid")
    remote: dict[str, Mapping[str, object]] = {}
    for item in raw_assets:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise _failure("published release asset record is invalid")
        name = str(item["name"])
        if name in remote:
            raise _failure("published release asset name repeats", asset=name)
        remote[name] = item
    if set(remote) != set(local_assets):
        raise _failure(
            "published release assets differ from the gated set",
            missing=sorted(set(local_assets) - set(remote)),
            unexpected=sorted(set(remote) - set(local_assets)),
        )
    verified: list[dict[str, object]] = []
    for name, path in sorted(local_assets.items()):
        local_size = path.stat().st_size
        local_hash = _hash(path)
        record = remote[name]
        if record.get("size") != local_size or record.get("digest") != f"sha256:{local_hash}":
            raise _failure("published asset metadata differs", asset=name)
        url = record.get("browser_download_url")
        if not isinstance(url, str):
            raise _failure("published asset has no immutable download URL", asset=name)
        downloaded = client.download_asset(url)
        if len(downloaded) != local_size or hashlib.sha256(downloaded).hexdigest() != local_hash:
            raise _failure("published asset bytes differ after re-fetch", asset=name)
        verified.append({"name": name, "size": local_size, "sha256": local_hash})
    return {
        "schema_id": "agent-workflow.published-release-verification",
        "schema_version": 1,
        "status": "verified",
        "tag": tag,
        "source_commit": source_commit,
        "assets": verified,
        "canonical_first_install_command_digest": canonical_first_install_command_digest(
            expected_body.split("```sh\n", 1)[1].split("```", 1)[0]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", default="swl007007/agent-workflow-pack")
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    arguments = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.release.publish_release import GitHubAPIClient, release_source_from_git

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    source_commit = release_source_from_git(
        Path(__file__).resolve().parents[2], arguments.version
    )
    client = GitHubAPIClient(arguments.repository, token)
    assets = {
        path.name: path
        for path in sorted(arguments.dist.iterdir())
        if path.name == "release-manifest.json"
        or path.name.endswith((".whl", ".tar.gz"))
    }
    from tools.release.publish_release import _candidate_release

    candidate = _candidate_release(arguments.dist / "release-manifest.json")
    from agent_stack.release.first_install import render_release_body

    expected_body = render_release_body(candidate, candidate.manifest_digest)
    result = verify_published_release(
        client=client,
        tag=f"v{arguments.version}",
        source_commit=source_commit,
        local_assets=assets,
        expected_body=expected_body,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
