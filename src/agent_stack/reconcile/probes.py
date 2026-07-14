"""Explicit live filesystem mutation probes and path-collision validation."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import time
import unicodedata
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_stack.core.api import digest, normalize_path

from .errors import RendererFailure


_NETWORK_FILESYSTEMS = frozenset(
    {"nfs", "nfs4", "cifs", "smb3", "fuse.sshfs", "sshfs"}
)


@dataclass(frozen=True)
class ProbeEvidence:
    probe_id: str
    supported: bool
    advisory_lock: bool
    atomic_replace: bool
    posix_mode: bool
    case_behavior: str
    unicode_behavior: str
    filesystem_type: str
    evidence_digest: str


def _failure(message: str, **details: object) -> RendererFailure:
    return RendererFailure("AWP_FILESYSTEM_UNSUPPORTED", message, details=details)


def _remove_empty_probe_directory(path: Path) -> None:
    last_error: OSError | None = None
    for attempt in range(20):
        if not path.exists():
            return
        if path.is_symlink() or not path.is_dir() or any(path.iterdir()):
            raise RendererFailure(
                "AWP_RECONCILE_RECOVERY_REQUIRED",
                "probe residue directory is not an empty real directory",
                details={"path": str(path)},
            )
        try:
            path.rmdir()
            return
        except FileNotFoundError:
            return
        except OSError as error:
            last_error = error
            if attempt < 19:
                time.sleep(0.01)
    raise RendererFailure(
        "AWP_RECONCILE_RECOVERY_REQUIRED",
        "probe residue could not be cleaned by exact path",
        details={"path": str(path)},
    ) from last_error


def ensure_same_filesystem(first: Path, second: Path) -> None:
    if first.stat().st_dev != second.stat().st_dev:
        raise _failure(
            "replacement and target are on different filesystems",
            first=str(first),
            second=str(second),
        )


def validate_path_collisions(paths: list[str] | tuple[str, ...]) -> None:
    identities: dict[str, str] = {}
    for raw_path in paths:
        path = normalize_path(raw_path)
        identity = unicodedata.normalize("NFC", path).casefold()
        if identity in identities:
            raise _failure(
                "target paths collide by case-folding or Unicode normalization",
                first=identities[identity],
                second=path,
            )
        identities[identity] = path


def _filesystem_type(path: Path) -> str:
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return "unknown"
    resolved = str(path.resolve(strict=True))
    best_mount = ""
    best_type = "unknown"
    for line in lines:
        fields = line.split()
        try:
            separator = fields.index("-")
        except ValueError:
            continue
        mount = fields[4].replace("\\040", " ")
        filesystem_type = fields[separator + 1]
        if (
            resolved == mount or resolved.startswith(mount.rstrip("/") + "/")
        ) and len(mount) > len(best_mount):
            best_mount = mount
            best_type = filesystem_type
    return best_type


def _probe_advisory_lock(path: Path) -> bool:
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if not hasattr(os, "fork"):
            return False
        child = os.fork()
        if child == 0:
            os.close(descriptor)
            child_descriptor = os.open(path, os.O_RDWR)
            try:
                try:
                    fcntl.flock(child_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os._exit(0)
                os._exit(1)
            finally:
                os.close(child_descriptor)
        _, status = os.waitpid(child, 0)
        return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def cleanup_probe_residue(
    root: Path,
    probe_id: str,
    expected_file_hashes: Mapping[str, str],
) -> None:
    """Remove only journal-recorded probe files that still match their hashes."""

    try:
        parsed = str(uuid.UUID(probe_id))
    except ValueError as error:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "probe residue identity is invalid"
        ) from error
    if parsed != probe_id or root.is_symlink() or not root.is_dir():
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "probe residue root is invalid"
        )
    residue = root / f".agent-workflow-probe-{probe_id}"
    if not residue.exists():
        return
    if residue.is_symlink() or not residue.is_dir():
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "probe residue is not a real directory"
        )
    expected_names = set(expected_file_hashes)
    if any(
        not name
        or Path(name).name != name
        or len(expected) != 64
        for name, expected in expected_file_hashes.items()
    ):
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "probe residue record is invalid"
        )
    actual_names = {entry.name for entry in residue.iterdir()}
    unknown = sorted(actual_names - expected_names)
    if unknown:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "probe residue contains an unrecorded path",
            details={"paths": unknown},
        )
    for name in sorted(expected_names):
        path = residue / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file():
            raise RendererFailure(
                "AWP_RECONCILE_RECOVERY_REQUIRED",
                "probe residue path changed type",
                details={"path": str(path)},
            )
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_file_hashes[name]:
            raise RendererFailure(
                "AWP_RECONCILE_RECOVERY_REQUIRED",
                "probe residue path differs from recorded candidate",
                details={"path": str(path)},
            )
        path.unlink()
    _remove_empty_probe_directory(residue)


def _probe_alias(directory: Path, first_name: str, second_name: str) -> str:
    first = directory / first_name
    second = directory / second_name
    first.write_bytes(b"first")
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(second, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError as error:
            if error.errno == errno.EEXIST:
                return "aliases"
            raise
        os.write(descriptor, b"second")
        return "distinct"
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if second.exists() and second != first:
            second.unlink()
        if first.exists():
            first.unlink()


def run_write_probe(root: Path, *, probe_id: str | None = None) -> ProbeEvidence:
    if root.is_symlink() or not root.is_dir():
        raise _failure("probe target root is not a real directory", path=str(root))
    filesystem_type = _filesystem_type(root)
    if filesystem_type in _NETWORK_FILESYSTEMS:
        raise _failure("network filesystem is unsupported", filesystem_type=filesystem_type)
    identity = probe_id or str(uuid.uuid4())
    probe_root = root / f".agent-workflow-probe-{identity}"
    if probe_root.exists() or probe_root.is_symlink():
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "probe residue already exists",
            details={"path": str(probe_root)},
        )
    probe_root.mkdir(mode=0o700)
    known_paths: list[Path] = []
    try:
        lock_path = probe_root / "lock"
        known_paths.append(lock_path)
        advisory_lock = _probe_advisory_lock(lock_path)

        original = probe_root / "original"
        candidate = probe_root / "candidate"
        known_paths.extend([original, candidate])
        original.write_bytes(b"original")
        candidate.write_bytes(b"candidate")
        ensure_same_filesystem(original, candidate)
        os.replace(candidate, original)
        atomic_replace = original.read_bytes() == b"candidate"

        os.chmod(original, 0o750)
        posix_mode = original.stat().st_mode & 0o777 == 0o750
        case_behavior = _probe_alias(probe_root, "CaseProbe", "caseprobe")
        unicode_behavior = _probe_alias(
            probe_root,
            "café-probe",
            unicodedata.normalize("NFD", "café-probe"),
        )
        if not advisory_lock or not atomic_replace or not posix_mode:
            raise _failure(
                "one or more live filesystem probes failed",
                advisory_lock=advisory_lock,
                atomic_replace=atomic_replace,
                posix_mode=posix_mode,
            )
        projection = {
            "probe_id": identity,
            "advisory_lock": advisory_lock,
            "atomic_replace": atomic_replace,
            "posix_mode": posix_mode,
            "case_behavior": case_behavior,
            "unicode_behavior": unicode_behavior,
            "filesystem_type": filesystem_type,
        }
        return ProbeEvidence(
            probe_id=identity,
            supported=True,
            advisory_lock=advisory_lock,
            atomic_replace=atomic_replace,
            posix_mode=posix_mode,
            case_behavior=case_behavior,
            unicode_behavior=unicode_behavior,
            filesystem_type=filesystem_type,
            evidence_digest=digest("agent-workflow.filesystem-probe.v1", projection),
        )
    finally:
        for path in reversed(known_paths):
            if path.exists() and path.is_file() and not path.is_symlink():
                path.unlink()
        _remove_empty_probe_directory(probe_root)
