from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_stack.reconcile.cas import compare_and_swap, observe_file_state
from agent_stack.reconcile.errors import RendererFailure
from agent_stack.reconcile.models import FileState


def test_compare_and_swap_binds_bytes_type_mode_and_non_symlink(tmp_path: Path) -> None:
    target = tmp_path / "config.txt"
    target.write_bytes(b"before\n")
    os.chmod(target, 0o644)
    expected = observe_file_state(tmp_path, "config.txt")
    candidate = FileState(
        "config.txt",
        True,
        "regular",
        __import__("hashlib").sha256(b"after\n").hexdigest(),
        "0755",
        True,
    )

    result = compare_and_swap(tmp_path, expected, candidate, b"after\n")

    assert result == candidate
    assert target.read_bytes() == b"after\n"
    assert target.stat().st_mode & 0o777 == 0o755


@pytest.mark.parametrize("mutation", ["bytes", "mode", "directory", "symlink"])
def test_compare_and_swap_rejects_every_changed_precondition(
    tmp_path: Path, mutation: str
) -> None:
    target = tmp_path / "config.txt"
    target.write_bytes(b"before\n")
    os.chmod(target, 0o644)
    expected = observe_file_state(tmp_path, "config.txt")
    if mutation == "bytes":
        target.write_bytes(b"external\n")
    elif mutation == "mode":
        os.chmod(target, 0o600)
    elif mutation == "directory":
        target.unlink()
        target.mkdir()
    else:
        target.unlink()
        target.symlink_to("elsewhere")
    candidate = FileState(
        "config.txt",
        True,
        "regular",
        __import__("hashlib").sha256(b"after\n").hexdigest(),
        "0644",
        True,
    )

    with pytest.raises(RendererFailure, match="AWP_FILE_CAS_MISMATCH"):
        compare_and_swap(tmp_path, expected, candidate, b"after\n")


def test_compare_and_swap_creates_and_deletes_under_absence_cas(tmp_path: Path) -> None:
    absent = observe_file_state(tmp_path, "created.txt")
    created = FileState(
        "created.txt",
        True,
        "regular",
        __import__("hashlib").sha256(b"created\n").hexdigest(),
        "0644",
        True,
    )
    compare_and_swap(tmp_path, absent, created, b"created\n")

    compare_and_swap(
        tmp_path,
        created,
        FileState(
            "created.txt",
            False,
            "absent",
            "canonical-null",
            "canonical-null",
            True,
        ),
        None,
    )

    assert not (tmp_path / "created.txt").exists()
