from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from agent_stack.providers.cache import CacheStore
from agent_stack.providers.errors import ProviderFailure


def test_cache_paths_are_derived_only_from_validated_sha256(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    digest = "a" * 64

    assert store.object_path(digest) == tmp_path / "objects/sha256/aa" / digest
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_CACHE_CORRUPT"):
        store.object_path("../escape")


def test_verified_object_is_published_atomically_and_is_reusable(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    payload = b"verified-provider-object"
    expected = hashlib.sha256(payload).hexdigest()
    temporary = store.create_temporary("download")
    temporary.write_bytes(payload)

    published = store.publish_verified(temporary, expected)

    assert published == store.object_path(expected)
    assert published.read_bytes() == payload
    assert not temporary.exists()
    second = store.create_temporary("download")
    second.write_bytes(payload)
    assert store.publish_verified(second, expected) == published
    assert not second.exists()


@pytest.mark.parametrize("pollution", ["wrong-bytes", "directory", "symlink"])
def test_polluted_final_object_is_never_reused(tmp_path: Path, pollution: str) -> None:
    store = CacheStore(tmp_path)
    payload = b"correct"
    expected = hashlib.sha256(payload).hexdigest()
    destination = store.object_path(expected)
    destination.parent.mkdir(parents=True)
    if pollution == "wrong-bytes":
        destination.write_bytes(b"wrong")
    elif pollution == "directory":
        destination.mkdir()
    else:
        target = tmp_path / "elsewhere"
        target.write_bytes(payload)
        os.symlink(target, destination)
    temporary = store.create_temporary("download")
    temporary.write_bytes(payload)

    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_CACHE_CORRUPT"):
        store.publish_verified(temporary, expected)


def test_quarantine_preserves_failure_evidence_without_cache_authority(tmp_path: Path) -> None:
    store = CacheStore(tmp_path)
    partial = store.create_temporary("download")
    partial.write_bytes(b"partial")

    evidence = store.quarantine(partial, reason="interrupted", expected_sha256="a" * 64)

    assert evidence.is_file()
    assert not partial.exists()
    assert b"interrupted" in evidence.read_bytes()
