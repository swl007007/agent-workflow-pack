"""Complete file-state observation and byte-and-mode compare-and-swap."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path

from agent_stack.core.api import CANONICAL_NULL, normalize_mode, normalize_path

from .errors import RendererFailure
from .models import FileState


def _failure(message: str, **details: object) -> RendererFailure:
    return RendererFailure("AWP_FILE_CAS_MISMATCH", message, details=details)


def _root(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise _failure("CAS root is not a real directory", path=str(path))
    return path


def _target(root: Path, relative_path: str) -> Path:
    base = _root(root)
    normalized = normalize_path(relative_path)
    target = base / normalized
    current = base
    for segment in Path(normalized).parts[:-1]:
        current /= segment
        if current.is_symlink():
            raise _failure("CAS path contains a symlink", path=normalized)
        if current.exists() and not current.is_dir():
            raise _failure("CAS path parent is not a directory", path=normalized)
    return target


def _hash_file(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
    except OSError as error:
        raise _failure("cannot hash CAS target", path=str(path)) from error
    return hasher.hexdigest()


def observe_file_state(
    root: Path,
    relative_path: str,
    *,
    managed_block_hash: str = CANONICAL_NULL,
) -> FileState:
    target = _target(root, relative_path)
    try:
        information = target.lstat()
    except FileNotFoundError:
        return FileState(
            normalize_path(relative_path),
            False,
            "absent",
            CANONICAL_NULL,
            CANONICAL_NULL,
            True,
            managed_block_hash,
        )
    if stat.S_ISLNK(information.st_mode):
        raise _failure("CAS target is a symlink", path=relative_path)
    mode = normalize_mode(information.st_mode)
    if stat.S_ISREG(information.st_mode):
        return FileState(
            normalize_path(relative_path),
            True,
            "regular",
            _hash_file(target),
            mode,
            True,
            managed_block_hash,
        )
    if stat.S_ISDIR(information.st_mode):
        return FileState(
            normalize_path(relative_path),
            True,
            "directory",
            CANONICAL_NULL,
            mode,
            True,
            managed_block_hash,
        )
    raise _failure("CAS target has an unsupported type", path=relative_path)


def _assert_state(root: Path, expected: FileState) -> None:
    current = observe_file_state(
        root,
        expected.path,
        managed_block_hash=expected.managed_block_hash,
    )
    if current.to_document() != expected.to_document():
        raise _failure(
            "current file state differs from approved precondition",
            path=expected.path,
            expected=expected.to_document(),
            current=current.to_document(),
        )


def _sync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def compare_and_swap(
    root: Path,
    expected: FileState,
    candidate: FileState,
    candidate_bytes: bytes | None,
) -> FileState:
    """Replace or remove one regular file only from its complete expected state."""

    if expected.path != candidate.path:
        raise _failure("CAS candidate path differs from precondition")
    target = _target(root, expected.path)
    _assert_state(root, expected)

    if not candidate.exists:
        if candidate.file_type != "absent" or candidate_bytes is not None:
            raise _failure("absent CAS candidate contains bytes or type", path=expected.path)
        if expected.exists:
            if expected.file_type != "regular":
                raise _failure("CAS deletion supports regular files only", path=expected.path)
            _assert_state(root, expected)
            target.unlink()
            _sync_directory(target.parent)
        result = observe_file_state(root, expected.path)
        if result.to_document() != candidate.to_document():
            raise _failure("CAS deletion did not reach candidate state", path=expected.path)
        return result

    if (
        candidate.file_type != "regular"
        or candidate_bytes is None
        or not candidate.non_symlink
        or candidate.mode == CANONICAL_NULL
    ):
        raise _failure("CAS replacement candidate is invalid", path=expected.path)
    if hashlib.sha256(candidate_bytes).hexdigest() != candidate.byte_hash:
        raise _failure("CAS candidate bytes differ from candidate digest", path=expected.path)
    if not target.parent.is_dir() or target.parent.is_symlink():
        raise _failure("CAS target parent is unavailable", path=expected.path)

    descriptor, raw_temporary = tempfile.mkstemp(prefix=".awp-cas-", dir=target.parent)
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(candidate_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, int(candidate.mode, 8))
        if temporary.stat().st_dev != target.parent.stat().st_dev:
            raise _failure("CAS replacement is cross-device", path=expected.path)
        _assert_state(root, expected)
        os.replace(temporary, target)
        _sync_directory(target.parent)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
    result = observe_file_state(
        root,
        expected.path,
        managed_block_hash=candidate.managed_block_hash,
    )
    if result.to_document() != candidate.to_document():
        raise _failure(
            "CAS replacement did not reach candidate state",
            path=expected.path,
            current=result.to_document(),
        )
    return result
