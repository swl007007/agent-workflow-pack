from __future__ import annotations

import hashlib
import io
import os
import tarfile
import zipfile
from pathlib import Path

import pytest

from agent_stack.providers.archive import (
    content_root_digest,
    extract_verified_archive,
    inspect_archive,
)
from agent_stack.providers.errors import ProviderFailure


def _policy(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_id": "agent-workflow.archive-policy",
        "schema_version": 1,
        "allowed_formats": ["tar", "zip"],
        "max_members": 16,
        "max_file_bytes": 4096,
        "max_expanded_bytes": 8192,
        "max_depth": 4,
        "max_compression_ratio": 100,
        "allow_executable": False,
    }
    value.update(overrides)
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _zip(path: Path, entries: list[tuple[str, bytes, int]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload, mode in entries:
            info = zipfile.ZipInfo(name)
            info.external_attr = (mode & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)


def test_complete_hash_is_verified_before_any_archive_parser_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "bad.zip"
    archive.write_bytes(b"not even an archive")
    parser_called = False

    def forbidden_parser(*args: object, **kwargs: object) -> object:
        nonlocal parser_called
        parser_called = True
        raise AssertionError("parser called before hash verification")

    monkeypatch.setattr(zipfile, "ZipFile", forbidden_parser)
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_HASH_MISMATCH"):
        inspect_archive(archive, "0" * 64, _policy())
    assert parser_called is False


def test_valid_archive_extracts_regular_files_and_has_stable_content_root(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "valid.zip"
    _zip(archive, [("pkg/a.txt", b"a", 0o644), ("pkg/b.txt", b"b", 0o600)])
    destination = tmp_path / "out"

    inspection = inspect_archive(archive, _sha(archive), _policy())
    root = extract_verified_archive(archive, _sha(archive), _policy(), destination)

    assert inspection.archive_format == "zip"
    assert inspection.member_paths == ("pkg/a.txt", "pkg/b.txt")
    assert root == content_root_digest(destination)
    assert (destination / "pkg/a.txt").read_bytes() == b"a"
    assert os.stat(destination / "pkg/b.txt").st_mode & 0o777 == 0o600


def test_links_special_files_unsafe_modes_and_collisions_are_rejected(tmp_path: Path) -> None:
    tar_path = tmp_path / "hostile.tar"
    with tarfile.open(tar_path, "w") as archive:
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "target"
        archive.addfile(link)
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ARCHIVE_UNSAFE"):
        inspect_archive(tar_path, _sha(tar_path), _policy())

    mode_path = tmp_path / "mode.tar"
    with tarfile.open(mode_path, "w") as archive:
        info = tarfile.TarInfo("unsafe")
        info.mode = 0o4755
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ARCHIVE_UNSAFE"):
        inspect_archive(mode_path, _sha(mode_path), _policy())

    collision = tmp_path / "collision.zip"
    _zip(collision, [("A.txt", b"a", 0o644), ("a.txt", b"b", 0o644)])
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ARCHIVE_UNSAFE"):
        inspect_archive(collision, _sha(collision), _policy())


@pytest.mark.parametrize(
    ("overrides", "entries"),
    [
        ({"max_members": 1}, [("a", b"a", 0o644), ("b", b"b", 0o644)]),
        ({"max_file_bytes": 1}, [("a", b"ab", 0o644)]),
        ({"max_expanded_bytes": 1}, [("a", b"ab", 0o644)]),
        ({"max_depth": 1}, [("a/b", b"x", 0o644)]),
        ({"max_compression_ratio": 1}, [("a", b"x" * 2048, 0o644)]),
    ],
)
def test_archive_resource_limits_are_enforced(
    tmp_path: Path,
    overrides: dict[str, object],
    entries: list[tuple[str, bytes, int]],
) -> None:
    archive = tmp_path / "limited.zip"
    _zip(archive, entries)
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ARCHIVE_UNSAFE"):
        inspect_archive(archive, _sha(archive), _policy(**overrides))


def test_archive_policy_schema_is_closed(tmp_path: Path) -> None:
    from agent_stack.core.api import CoreFailure, SchemaCatalog

    root = Path(__file__).resolve().parents[3]
    catalog = SchemaCatalog.discover(root / "schemas")
    catalog.load_and_validate(_policy())
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**_policy(), "unknown": True})
