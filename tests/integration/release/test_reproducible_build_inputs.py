from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

from agent_stack.release.gates import (
    _deterministic_gzip,
    _normalize_distribution_archives,
    _source_date_epoch,
)


def test_source_date_epoch_is_frozen_outside_commit_and_checkout_metadata() -> None:
    assert _source_date_epoch() == "315532800"


def test_deterministic_gzip_has_fixed_stored_block_framing() -> None:
    compressed = _deterministic_gzip(b"x" * 70_000)

    assert gzip.decompress(compressed) == b"x" * 70_000
    assert hashlib.sha256(compressed).hexdigest() == (
        "7296010aa02c3f6283458d5abb80ac124323c61b4ae648d8d2923116376bf568"
    )


def _archives(root: Path, stamp: int, mode: int) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    wheel = root / "package.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        info = zipfile.ZipInfo("package/value.txt", (2020, 1, 1, 0, 0, stamp))
        info.create_system = 3
        info.external_attr = mode << 16
        archive.writestr(info, b"stable\n")
    sdist = root / "package.tar.gz"
    with gzip.GzipFile(filename=str(sdist), mode="wb", mtime=stamp) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            info = tarfile.TarInfo("package/value.txt")
            info.size = len(b"stable\n")
            info.mtime = stamp
            info.mode = mode
            archive.addfile(info, io.BytesIO(b"stable\n"))
    return wheel, sdist


def test_archive_normalization_removes_source_container_metadata(tmp_path: Path) -> None:
    first = _archives(tmp_path / "first", 2, 0o755)
    second = _archives(tmp_path / "second", 4, 0o644)

    for pair in (first, second):
        _normalize_distribution_archives(*pair)

    assert first[0].read_bytes() == second[0].read_bytes()
    assert first[1].read_bytes() == second[1].read_bytes()
