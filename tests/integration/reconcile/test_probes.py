from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from agent_stack.reconcile.errors import RendererFailure
from agent_stack.reconcile.probes import (
    cleanup_probe_residue,
    ensure_same_filesystem,
    run_write_probe,
    validate_path_collisions,
)


def test_live_probe_verifies_lock_replace_mode_and_cleans_residue(tmp_path: Path) -> None:
    evidence = run_write_probe(tmp_path, probe_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    assert evidence.supported is True
    assert evidence.advisory_lock is True
    assert evidence.atomic_replace is True
    assert evidence.posix_mode is True
    assert evidence.case_behavior in {"distinct", "aliases"}
    assert evidence.unicode_behavior in {"distinct", "aliases"}
    assert not list(tmp_path.glob(".agent-workflow-probe-*"))


def test_case_and_unicode_equivalent_target_paths_are_rejected() -> None:
    validate_path_collisions(["Config/A.txt", "config/B.txt"])
    with pytest.raises(RendererFailure, match="AWP_FILESYSTEM_UNSUPPORTED"):
        validate_path_collisions(["Config/A.txt", "config/A.txt"])

    composed = "generated/café.txt"
    decomposed = unicodedata.normalize("NFD", composed)
    with pytest.raises(RendererFailure, match="AWP_FILESYSTEM_UNSUPPORTED"):
        validate_path_collisions([composed, decomposed])


def test_same_filesystem_guard_rejects_cross_device_when_available(tmp_path: Path) -> None:
    candidate = Path("/dev/shm")
    if not candidate.is_dir() or candidate.stat().st_dev == tmp_path.stat().st_dev:
        pytest.skip("no second local filesystem is available")
    with pytest.raises(RendererFailure, match="AWP_FILESYSTEM_UNSUPPORTED"):
        ensure_same_filesystem(tmp_path, candidate)


def test_probe_refuses_symlink_target_root(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)

    with pytest.raises(RendererFailure, match="AWP_FILESYSTEM_UNSUPPORTED"):
        run_write_probe(linked)


def test_probe_residue_cleanup_uses_exact_recorded_hashes(tmp_path: Path) -> None:
    import hashlib

    probe_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    residue = tmp_path / f".agent-workflow-probe-{probe_id}"
    residue.mkdir()
    (residue / "lock").write_bytes(b"")
    (residue / "original").write_bytes(b"candidate")
    expected = {
        "lock": hashlib.sha256(b"").hexdigest(),
        "original": hashlib.sha256(b"candidate").hexdigest(),
    }

    cleanup_probe_residue(tmp_path, probe_id, expected)

    assert not residue.exists()

    residue.mkdir()
    (residue / "original").write_bytes(b"external")
    with pytest.raises(RendererFailure, match="AWP_RECONCILE_RECOVERY_REQUIRED"):
        cleanup_probe_residue(tmp_path, probe_id, expected)
    assert (residue / "original").read_bytes() == b"external"


def test_probe_cleanup_retries_transient_empty_directory_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_rmdir = Path.rmdir
    attempts = 0

    def transient_rmdir(path: Path) -> None:
        nonlocal attempts
        if path.name.startswith(".agent-workflow-probe-") and attempts == 0:
            attempts += 1
            raise PermissionError("transient drvfs denial")
        original_rmdir(path)

    monkeypatch.setattr(Path, "rmdir", transient_rmdir)

    evidence = run_write_probe(tmp_path)

    assert evidence.supported is True
    assert attempts == 1
    assert not list(tmp_path.glob(".agent-workflow-probe-*"))
