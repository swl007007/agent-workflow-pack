"""Content-addressed provider cache with OS locks and atomic publication."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import ProviderFailure


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CacheStore:
    """One fixed cache namespace whose final objects are addressed by complete SHA-256."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.objects_root = root / "objects/sha256"
        self.quarantine_root = root / "quarantine"
        self.locks_root = root / "locks"
        self.temporary_root = root / "tmp"
        for path in (
            self.objects_root,
            self.quarantine_root,
            self.locks_root,
            self.temporary_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_digest(value: str) -> str:
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ProviderFailure(
                "AWP_PROVIDER_CACHE_CORRUPT", "cache object digest is not canonical"
            )
        return value

    def object_path(self, sha256: str) -> Path:
        digest_value = self._validate_digest(sha256)
        return self.objects_root / digest_value[:2] / digest_value

    def create_temporary(self, purpose: str) -> Path:
        if not purpose or not re.fullmatch(r"[a-z][a-z0-9-]*", purpose):
            raise ProviderFailure(
                "AWP_PROVIDER_CACHE_CORRUPT", "temporary cache purpose is invalid"
            )
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f"{purpose}-", suffix=".partial", dir=self.temporary_root
        )
        os.close(descriptor)
        return Path(raw_path)

    @contextmanager
    def acquire_lock(self, sha256: str) -> Iterator[None]:
        digest_value = self._validate_digest(sha256)
        lock_path = self.locks_root / f"object-{digest_value}.lock"
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as error:
            raise ProviderFailure(
                "AWP_PROVIDER_CACHE_CORRUPT", "cannot open cache object lock"
            ) from error
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _file_digest(path: Path) -> str:
        hasher = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    hasher.update(chunk)
        except OSError as error:
            raise ProviderFailure(
                "AWP_PROVIDER_CACHE_CORRUPT", "cannot hash cache object"
            ) from error
        return hasher.hexdigest()

    def quarantine(self, path: Path, *, reason: str, expected_sha256: str) -> Path:
        self._validate_digest(expected_sha256)
        quarantine_id = str(uuid.uuid4())
        destination = self.quarantine_root / quarantine_id
        destination.mkdir(mode=0o700)
        payload = destination / "payload"
        if path.exists() or path.is_symlink():
            try:
                os.replace(path, payload)
            except OSError:
                if path.is_dir() and not path.is_symlink():
                    shutil.move(path, payload)
                else:
                    raise
        evidence = destination / "evidence.json"
        evidence.write_text(
            json.dumps(
                {
                    "reason": reason,
                    "expected_sha256": expected_sha256,
                    "quarantine_id": quarantine_id,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        return evidence

    def publish_verified(self, temporary: Path, expected_sha256: str) -> Path:
        expected = self._validate_digest(expected_sha256)
        with self.acquire_lock(expected):
            if temporary.is_symlink() or not temporary.is_file():
                raise ProviderFailure(
                    "AWP_PROVIDER_CACHE_CORRUPT", "candidate cache object is not a regular file"
                )
            if self._file_digest(temporary) != expected:
                self.quarantine(
                    temporary, reason="candidate-hash-mismatch", expected_sha256=expected
                )
                raise ProviderFailure(
                    "AWP_PROVIDER_HASH_MISMATCH", "candidate cache bytes do not match identity"
                )
            destination = self.object_path(expected)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                if (
                    not destination.is_symlink()
                    and destination.is_file()
                    and self._file_digest(destination) == expected
                ):
                    temporary.unlink()
                    return destination
                self.quarantine(
                    destination, reason="polluted-final-object", expected_sha256=expected
                )
                raise ProviderFailure(
                    "AWP_PROVIDER_CACHE_CORRUPT", "existing cache object is polluted"
                )
            os.replace(temporary, destination)
            os.chmod(destination, 0o444)
            if self._file_digest(destination) != expected:
                self.quarantine(
                    destination, reason="post-publish-hash-mismatch", expected_sha256=expected
                )
                raise ProviderFailure(
                    "AWP_PROVIDER_CACHE_CORRUPT", "published cache object changed"
                )
            return destination
