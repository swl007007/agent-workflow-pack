from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.gates import build_release_artifacts
from tools.release.publish_release import publish_immutable_release
from tools.release.verify_published_release import verify_published_release


ROOT = Path(__file__).resolve().parents[3]


class FakeGitHub:
    def __init__(self, *, mutate_after_create: Path | None = None) -> None:
        self.events: list[str] = []
        self.assets: dict[str, bytes] = {}
        self.source_commit = ""
        self.tag = ""
        self.immutable = False
        self.mutate_after_create = mutate_after_create

    def immutable_releases_enabled(self) -> bool:
        self.events.append("check-immutable-policy")
        return True

    def create_release_once(self, tag: str, source_commit: str) -> str:
        self.events.append("create-release")
        self.tag = tag
        self.source_commit = source_commit
        if self.mutate_after_create is not None:
            self.mutate_after_create.write_bytes(b"mutated")
        return "release-1"

    def upload_asset_once(self, release_id: str, path: Path) -> None:
        assert release_id == "release-1"
        self.events.append(f"upload:{path.name}")
        if path.name in self.assets:
            raise AssertionError("asset replacement attempted")
        self.assets[path.name] = path.read_bytes()

    def publish_release(self, release_id: str) -> None:
        assert release_id == "release-1"
        self.events.append("publish-release")
        self.immutable = True

    def resolve_tag_commit(self, tag: str) -> str:
        self.events.append("resolve-tag")
        assert tag == self.tag
        return self.source_commit

    def fetch_release(self, tag: str) -> dict[str, object]:
        self.events.append("fetch-release")
        assert tag == self.tag
        return {
            "tag_name": self.tag,
            "target_commitish": self.source_commit,
            "immutable": self.immutable,
            "assets": [
                {
                    "name": name,
                    "size": len(body),
                    "digest": f"sha256:{hashlib.sha256(body).hexdigest()}",
                    "browser_download_url": f"https://objects.githubusercontent.com/{name}",
                }
                for name, body in sorted(self.assets.items())
            ],
        }

    def download_asset(self, url: str) -> bytes:
        name = url.rsplit("/", 1)[-1]
        self.events.append(f"download:{name}")
        return self.assets[name]


def test_publication_sequence_uses_final_bytes_once_then_re_fetches_every_asset() -> None:
    artifact_set = build_release_artifacts(ROOT, ROOT / "dist", rebuild=False)
    client = FakeGitHub()

    result = publish_immutable_release(
        artifact_set_path=ROOT / "dist/release-artifact-set.json",
        version="0.1.0",
        source_commit="276b74ba2c4f7347a9cf01a4c76eea972e90906e",
        client=client,
    )

    assert result["status"] == "verified"
    assert client.events[:4] == [
        "check-immutable-policy",
        "create-release",
        f"upload:{artifact_set.wheel.path.name}",
        f"upload:{artifact_set.sdist.path.name}",
    ]
    assert "upload:release-manifest.json" in client.events
    assert "publish-release" in client.events
    assert client.events.index("publish-release") < client.events.index("resolve-tag")
    assert client.events.count("create-release") == 1
    assert sorted(name for name in client.assets) == sorted(
        [artifact_set.wheel.path.name, artifact_set.sdist.path.name, "release-manifest.json"]
    )
    assert sum(event.startswith("download:") for event in client.events) == 3


def test_publication_fails_if_final_artifact_changes_after_release_creation() -> None:
    artifact_set = build_release_artifacts(ROOT, ROOT / "dist", rebuild=False)
    original = artifact_set.wheel.path.read_bytes()
    client = FakeGitHub(mutate_after_create=artifact_set.wheel.path)
    try:
        with pytest.raises(LifecycleFailure, match="final artifact changed"):
            publish_immutable_release(
                artifact_set_path=ROOT / "dist/release-artifact-set.json",
                version="0.1.0",
                source_commit="276b74ba2c4f7347a9cf01a4c76eea972e90906e",
                client=client,
            )
    finally:
        artifact_set.wheel.path.write_bytes(original)

    assert not any(event.startswith("upload:") for event in client.events)


def test_published_verifier_rejects_non_immutable_or_replaced_assets() -> None:
    artifact_set = build_release_artifacts(ROOT, ROOT / "dist", rebuild=False)
    manifest = ROOT / "dist/release-manifest.json"
    if not manifest.exists():
        manifest.write_text("{}", encoding="utf-8")
    client = FakeGitHub()
    client.tag = "v0.1.0"
    client.source_commit = "c" * 40
    for path in (artifact_set.wheel.path, artifact_set.sdist.path, manifest):
        client.assets[path.name] = path.read_bytes()

    with pytest.raises(LifecycleFailure, match="not immutable"):
        verify_published_release(
            client=client,
            tag="v0.1.0",
            source_commit="c" * 40,
            local_assets={path.name: path for path in (artifact_set.wheel.path, artifact_set.sdist.path, manifest)},
        )


def test_publication_refuses_to_create_release_without_repository_immutability() -> None:
    build_release_artifacts(ROOT, ROOT / "dist", rebuild=False)
    client = FakeGitHub()
    client.immutable_releases_enabled = lambda: False  # type: ignore[method-assign]

    with pytest.raises(LifecycleFailure, match="repository immutable releases are not enabled"):
        publish_immutable_release(
            artifact_set_path=ROOT / "dist/release-artifact-set.json",
            version="0.1.0",
            source_commit="276b74ba2c4f7347a9cf01a4c76eea972e90906e",
            client=client,
        )

    assert "create-release" not in client.events


def test_published_verifier_uses_resolved_remote_tag_commit() -> None:
    artifact_set = build_release_artifacts(ROOT, ROOT / "dist", rebuild=False)
    manifest = ROOT / "dist/release-manifest.json"
    if not manifest.exists():
        manifest.write_text("{}", encoding="utf-8")
    client = FakeGitHub()
    client.tag = "v0.1.0"
    client.source_commit = "c" * 40
    client.immutable = True
    for path in (artifact_set.wheel.path, artifact_set.sdist.path, manifest):
        client.assets[path.name] = path.read_bytes()

    result = verify_published_release(
        client=client,
        tag="v0.1.0",
        source_commit="c" * 40,
        local_assets={
            path.name: path
            for path in (artifact_set.wheel.path, artifact_set.sdist.path, manifest)
        },
    )

    assert result["status"] == "verified"
    assert "resolve-tag" in client.events
