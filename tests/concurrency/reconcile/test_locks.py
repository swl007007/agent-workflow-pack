from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from agent_stack.reconcile.errors import RendererFailure
from agent_stack.reconcile.locks import acquire_bootstrap_lock, acquire_project_locks


def _hold_project_locks(root: str, ready, release) -> None:
    with acquire_project_locks(Path(root)):
        ready.set()
        release.wait(timeout=10)


def test_bootstrap_to_project_lock_handoff_uses_fixed_order(tmp_path: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()
    lock_root = tmp_path / "cache-locks"

    with acquire_bootstrap_lock(target, lock_root):
        with acquire_project_locks(target):
            assert (target / ".agent-workflow/reconcile.lock").is_file()
            assert (target / ".agent-workflow/runtime-state.lock").is_file()


def test_project_locks_serialize_two_processes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_project_locks,
        args=(str(project), ready, release),
    )
    process.start()
    assert ready.wait(timeout=10)
    try:
        with pytest.raises(RendererFailure, match="AWP_RECONCILE_LOCKED"):
            with acquire_project_locks(project, blocking=False):
                raise AssertionError("contended lock unexpectedly acquired")
    finally:
        release.set()
        process.join(timeout=10)
        assert process.exitcode == 0
