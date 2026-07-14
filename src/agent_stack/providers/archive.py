"""Hash-first archive inspection, bounded extraction, and deterministic content roots."""

from __future__ import annotations

import hashlib
import os
import stat
import tarfile
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from agent_stack.core.api import CoreFailure, digest, normalize_mode, normalize_path

from .errors import ProviderFailure


@dataclass(frozen=True)
class ArchiveMember:
    normalized_path: str
    is_directory: bool
    size: int
    mode: str


@dataclass(frozen=True)
class ArchiveInspection:
    archive_format: str
    archive_sha256: str
    member_paths: tuple[str, ...]
    expanded_bytes: int
    inspection_digest: str


@dataclass(frozen=True)
class _ArchivePolicy:
    allowed_formats: tuple[str, ...]
    max_members: int
    max_file_bytes: int
    max_expanded_bytes: int
    max_depth: int
    max_compression_ratio: int
    allow_executable: bool


def _unsafe(message: str, **details: object) -> ProviderFailure:
    return ProviderFailure("AWP_PROVIDER_ARCHIVE_UNSAFE", message, details=details)


def _parse_policy(document: Mapping[str, object]) -> _ArchivePolicy:
    fields = {
        "schema_id",
        "schema_version",
        "allowed_formats",
        "max_members",
        "max_file_bytes",
        "max_expanded_bytes",
        "max_depth",
        "max_compression_ratio",
        "allow_executable",
    }
    if set(document) != fields:
        raise _unsafe("archive policy fields are not closed")
    if document.get("schema_id") != "agent-workflow.archive-policy" or document.get(
        "schema_version"
    ) != 1:
        raise _unsafe("archive policy schema identity/version is invalid")
    formats = document.get("allowed_formats")
    if not isinstance(formats, list) or not formats or not all(
        item in {"zip", "tar"} for item in formats
    ):
        raise _unsafe("archive allowed_formats is invalid")
    if len(formats) != len(set(formats)):
        raise _unsafe("archive allowed_formats contains duplicates")
    limits: dict[str, int] = {}
    for field in (
        "max_members",
        "max_file_bytes",
        "max_expanded_bytes",
        "max_depth",
        "max_compression_ratio",
    ):
        value = document.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise _unsafe("archive policy limit must be positive", field=field)
        limits[field] = value
    if not isinstance(document.get("allow_executable"), bool):
        raise _unsafe("allow_executable must be boolean")
    return _ArchivePolicy(
        allowed_formats=tuple(sorted(formats)),
        max_members=limits["max_members"],
        max_file_bytes=limits["max_file_bytes"],
        max_expanded_bytes=limits["max_expanded_bytes"],
        max_depth=limits["max_depth"],
        max_compression_ratio=limits["max_compression_ratio"],
        allow_executable=bool(document["allow_executable"]),
    )


def _complete_hash(path: Path, expected_sha256: str) -> str:
    if (
        len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID", "expected archive digest is not canonical"
        )
    if path.is_symlink() or not path.is_file():
        raise ProviderFailure(
            "AWP_PROVIDER_CACHE_CORRUPT", "verified archive object is not a regular file"
        )
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    actual = hasher.hexdigest()
    if actual != expected_sha256:
        raise ProviderFailure(
            "AWP_PROVIDER_HASH_MISMATCH", "complete archive bytes do not match locked identity"
        )
    return actual


def _member_path(raw: str) -> str:
    if raw.endswith("/"):
        raw = raw[:-1]
    if not raw:
        raise _unsafe("archive contains an empty member path")
    try:
        normalized = normalize_path(raw)
    except CoreFailure as error:
        raise _unsafe("archive member path is unsafe", path=raw) from error
    if len(normalized.split("/")) == 0:
        raise _unsafe("archive member path is empty")
    return normalized


def _member_mode(raw_mode: int, *, is_directory: bool, policy: _ArchivePolicy) -> str:
    if raw_mode & ~0o777:
        raise _unsafe("archive member uses unsupported or privileged mode bits")
    mode = raw_mode or (0o755 if is_directory else 0o644)
    if not policy.allow_executable and not is_directory and mode & 0o111:
        raise _unsafe("archive executable mode is not authorized")
    return normalize_mode(mode)


def _validate_members(
    members: list[ArchiveMember], policy: _ArchivePolicy, *, compressed_bytes: int
) -> None:
    if len(members) > policy.max_members:
        raise _unsafe("archive member count exceeds policy")
    seen: dict[str, str] = {}
    expanded = 0
    for member in members:
        alias = member.normalized_path.casefold()
        if alias in seen:
            raise _unsafe(
                "archive member paths collide after Unicode/case normalization",
                first=seen[alias],
                second=member.normalized_path,
            )
        seen[alias] = member.normalized_path
        if len(member.normalized_path.split("/")) > policy.max_depth:
            raise _unsafe("archive member exceeds maximum depth", path=member.normalized_path)
        if not member.is_directory:
            if member.size > policy.max_file_bytes:
                raise _unsafe("archive member exceeds per-file size", path=member.normalized_path)
            expanded += member.size
    if expanded > policy.max_expanded_bytes:
        raise _unsafe("archive expanded size exceeds policy")
    if expanded and expanded / max(compressed_bytes, 1) > policy.max_compression_ratio:
        raise _unsafe("archive compression ratio exceeds policy")


def _zip_members(path: Path, policy: _ArchivePolicy) -> tuple[list[ArchiveMember], int]:
    members: list[ArchiveMember] = []
    compressed = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                normalized = _member_path(info.filename)
                raw_mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(raw_mode)
                is_directory = info.is_dir()
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise _unsafe("zip contains a link or unsupported special member")
                if file_type == stat.S_IFDIR:
                    is_directory = True
                if is_directory and info.file_size != 0:
                    raise _unsafe("zip directory member has file bytes")
                members.append(
                    ArchiveMember(
                        normalized_path=normalized,
                        is_directory=is_directory,
                        size=info.file_size,
                        mode=_member_mode(raw_mode & 0o7777, is_directory=is_directory, policy=policy),
                    )
                )
                compressed += info.compress_size
    except (OSError, zipfile.BadZipFile) as error:
        raise _unsafe("invalid zip archive") from error
    return members, compressed


def _tar_members(path: Path, policy: _ArchivePolicy) -> tuple[list[ArchiveMember], int]:
    members: list[ArchiveMember] = []
    try:
        with tarfile.open(path, "r:*") as archive:
            for info in archive.getmembers():
                if not (info.isfile() or info.isdir()):
                    raise _unsafe("tar contains a link or unsupported special member")
                normalized = _member_path(info.name)
                members.append(
                    ArchiveMember(
                        normalized_path=normalized,
                        is_directory=info.isdir(),
                        size=info.size,
                        mode=_member_mode(info.mode, is_directory=info.isdir(), policy=policy),
                    )
                )
    except (OSError, tarfile.TarError) as error:
        raise _unsafe("invalid tar archive") from error
    return members, path.stat().st_size


def _inspect(
    path: Path, expected_sha256: str, policy_document: Mapping[str, object]
) -> tuple[ArchiveInspection, list[ArchiveMember]]:
    archive_sha = _complete_hash(path, expected_sha256)
    policy = _parse_policy(policy_document)
    if zipfile.is_zipfile(path):
        archive_format = "zip"
        members, compressed = _zip_members(path, policy)
    elif tarfile.is_tarfile(path):
        archive_format = "tar"
        members, compressed = _tar_members(path, policy)
    else:
        raise _unsafe("archive format is unsupported or malformed")
    if archive_format not in policy.allowed_formats:
        raise _unsafe("archive format is not allowed", archive_format=archive_format)
    _validate_members(members, policy, compressed_bytes=compressed)
    ordered = sorted(members, key=lambda member: member.normalized_path)
    projection = {
        "archive_format": archive_format,
        "archive_sha256": archive_sha,
        "members": [
            {
                "path": member.normalized_path,
                "directory": member.is_directory,
                "size": member.size,
                "mode": member.mode,
            }
            for member in ordered
        ],
    }
    return (
        ArchiveInspection(
            archive_format=archive_format,
            archive_sha256=archive_sha,
            member_paths=tuple(member.normalized_path for member in ordered),
            expanded_bytes=sum(member.size for member in ordered if not member.is_directory),
            inspection_digest=digest("agent-workflow.archive-inspection.v1", projection),
        ),
        ordered,
    )


def inspect_archive(
    path: Path, expected_sha256: str, policy: Mapping[str, object]
) -> ArchiveInspection:
    """Verify full bytes first, then validate a closed bounded member inventory."""

    return _inspect(path, expected_sha256, policy)[0]


def _ensure_directory(root: Path, relative: str) -> Path:
    current = root
    for segment in relative.split("/"):
        current = current / segment
        if current.exists():
            if current.is_symlink() or not current.is_dir():
                raise _unsafe("extraction directory path is not a real directory")
        else:
            current.mkdir(mode=0o755)
    return current


def _write_member(root: Path, member: ArchiveMember, chunks: Iterator[bytes]) -> None:
    path = root / member.normalized_path
    if member.is_directory:
        directory = _ensure_directory(root, member.normalized_path)
        os.chmod(directory, int(member.mode, 8))
        return
    parent = member.normalized_path.rpartition("/")[0]
    if parent:
        _ensure_directory(root, parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, int(member.mode, 8))
    try:
        for chunk in chunks:
            os.write(descriptor, chunk)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, int(member.mode, 8))


def _read_zip(path: Path, members: list[ArchiveMember]) -> Iterator[tuple[ArchiveMember, Iterator[bytes]]]:
    with zipfile.ZipFile(path) as archive:
        by_path = {_member_path(info.filename): info for info in archive.infolist()}
        for member in members:
            if member.is_directory:
                yield member, iter(())
            else:
                with archive.open(by_path[member.normalized_path]) as stream:
                    data = stream.read()
                yield member, iter((data,))


def _read_tar(path: Path, members: list[ArchiveMember]) -> Iterator[tuple[ArchiveMember, Iterator[bytes]]]:
    with tarfile.open(path, "r:*") as archive:
        by_path = {_member_path(info.name): info for info in archive.getmembers()}
        for member in members:
            if member.is_directory:
                yield member, iter(())
            else:
                stream = archive.extractfile(by_path[member.normalized_path])
                if stream is None:
                    raise _unsafe("tar regular file has no readable payload")
                with stream:
                    data = stream.read()
                yield member, iter((data,))


def extract_verified_archive(
    path: Path,
    expected_sha256: str,
    policy: Mapping[str, object],
    destination: Path,
) -> str:
    """Extract only a previously fully validated inventory into a new private root."""

    inspection, members = _inspect(path, expected_sha256, policy)
    if destination.exists() or destination.is_symlink():
        raise _unsafe("extraction destination must have original absence")
    destination.mkdir(parents=True, mode=0o700)
    reader = _read_zip(path, members) if inspection.archive_format == "zip" else _read_tar(path, members)
    try:
        for member, chunks in reader:
            _write_member(destination, member, chunks)
    except Exception:
        for child in sorted(destination.rglob("*"), reverse=True):
            if child.is_dir() and not child.is_symlink():
                child.rmdir()
            else:
                child.unlink(missing_ok=True)
        destination.rmdir()
        raise
    return content_root_digest(destination)


def content_root_digest(root: Path) -> str:
    """Hash normalized regular-file paths, bytes, and normalized modes in path order."""

    if root.is_symlink() or not root.is_dir():
        raise _unsafe("content root is not a real directory")
    records: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise _unsafe("content root contains a symlink")
        if path.is_dir():
            continue
        if not path.is_file():
            raise _unsafe("content root contains a special file")
        relative = normalize_path(path.relative_to(root).as_posix())
        records.append(
            {
                "path": relative,
                "byte_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
                "mode": normalize_mode(path.stat().st_mode),
            }
        )
    return digest("agent-workflow.initializer-content-root.v1", records)
