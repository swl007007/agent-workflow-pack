"""Live Linux/WSL advisory locks for reconcile and runtime-state gates."""

from __future__ import annotations

import fcntl
import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import RendererFailure


def _failure(message: str, **details: object) -> RendererFailure:
    return RendererFailure("AWP_RECONCILE_LOCKED", message, details=details)


def _real_directory(path: Path, *, create: bool = False) -> Path:
    if path.is_symlink():
        raise _failure("lock directory is a symlink", path=str(path))
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise _failure("lock directory is unavailable", path=str(path))
    return path


@contextmanager
def _advisory_lock(path: Path, *, blocking: bool) -> Iterator[None]:
    _real_directory(path.parent, create=True)
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise _failure("cannot open OS lock", path=str(path)) from error
    operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
    try:
        try:
            fcntl.flock(descriptor, operation)
        except BlockingIOError as error:
            raise _failure("another live writer holds the OS lock", path=str(path)) from error
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _target_identity(target: Path) -> str:
    absolute = Path(os.path.abspath(target))
    if absolute.is_symlink():
        raise _failure("bootstrap target is a symlink", path=str(absolute))
    existing = absolute
    while not existing.exists():
        if existing.parent == existing:
            raise _failure("bootstrap target has no existing filesystem ancestor")
        existing = existing.parent
    if existing.is_symlink():
        raise _failure("bootstrap target ancestor is a symlink", path=str(existing))
    stat_result = existing.stat()
    projection = f"{absolute}\0{stat_result.st_dev}"
    return hashlib.sha256(projection.encode("utf-8")).hexdigest()


@contextmanager
def acquire_bootstrap_lock(
    target: Path, lock_root: Path, *, blocking: bool = True
) -> Iterator[None]:
    """Acquire the out-of-tree first-init lock for a target/filesystem identity."""

    _real_directory(lock_root, create=True)
    identity = _target_identity(target)
    with _advisory_lock(lock_root / f"bootstrap-{identity}.lock", blocking=blocking):
        yield


@contextmanager
def acquire_runtime_state_gate(
    project_root: Path, *, blocking: bool = True
) -> Iterator[None]:
    root = _real_directory(project_root)
    control = _real_directory(root / ".agent-workflow", create=True)
    with _advisory_lock(control / "runtime-state.lock", blocking=blocking):
        yield


@contextmanager
def acquire_project_locks(
    project_root: Path, *, blocking: bool = True
) -> Iterator[None]:
    """Acquire reconcile then runtime-state locks in the sole lifecycle order."""

    root = _real_directory(project_root)
    control = _real_directory(root / ".agent-workflow", create=True)
    with _advisory_lock(control / "reconcile.lock", blocking=blocking):
        with _advisory_lock(control / "runtime-state.lock", blocking=blocking):
            yield
