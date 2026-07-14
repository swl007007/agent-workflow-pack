from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable, cast

import pytest

from agent_stack.release.errors import LifecycleFailure
from tools.release import publish_release


def _function(name: str) -> Callable[..., Any]:
    value = getattr(publish_release, name, None)
    assert callable(value), f"missing release validation function: {name}"
    return cast(Callable[..., Any], value)


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "Release Test")
    _git(root, "config", "user.email", "release@example.invalid")
    (root / "tracked.txt").write_text("first\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "Initial release input")
    return root, _git(root, "rev-parse", "HEAD")


def test_release_source_requires_clean_head_and_exact_version_tag(tmp_path: Path) -> None:
    root, head = _repository(tmp_path)
    _git(root, "tag", "v0.1.0")

    release_source_from_git = _function("release_source_from_git")
    assert release_source_from_git(root, "0.1.0") == head

    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(LifecycleFailure, match="clean"):
        release_source_from_git(root, "0.1.0")


def test_release_source_rejects_tag_that_is_not_current_head(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path)
    _git(root, "tag", "v0.1.0")
    (root / "tracked.txt").write_text("second\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "Move head")

    release_source_from_git = _function("release_source_from_git")
    with pytest.raises(LifecycleFailure, match="tag"):
        release_source_from_git(root, "0.1.0")


@pytest.mark.parametrize(
    "source_commit",
    ["a" * 40, "0" * 40, "not-a-commit", "abc"],
)
def test_placeholder_or_invalid_source_commit_is_rejected(source_commit: str) -> None:
    validate_source_commit = _function("validate_source_commit")
    with pytest.raises(LifecycleFailure, match="source commit"):
        validate_source_commit(source_commit)


def test_publication_policy_rejects_placeholder_repository_identity() -> None:
    validate_publication_policy = _function("validate_publication_policy")
    with pytest.raises(LifecycleFailure, match="placeholder"):
        validate_publication_policy(
            {"owner": "pinned-owner", "repository": "agent-workflow-pack"}
        )
