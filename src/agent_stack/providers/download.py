"""Verified streaming download into the content-addressed provider cache."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from .cache import CacheStore
from .errors import ProviderFailure
from .models import AcquisitionRequest


@dataclass(frozen=True)
class DownloadResponse:
    final_url: str
    chunks: Iterable[bytes]


class DownloadTransport(Protocol):
    def open(self, url: str) -> DownloadResponse: ...


def _validate_url(url: str, *, expected_host: str | None = None) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID", "authorized download URL is invalid"
        ) from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID", "download URL violates the HTTPS authority policy"
        )
    host = parsed.hostname.lower()
    if expected_host is not None and host != expected_host:
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID", "redirect destination host is not authorized"
        )
    return host


def download_verified(
    request: AcquisitionRequest,
    cache: CacheStore,
    transport: DownloadTransport,
) -> Path:
    """Download, bound, fully hash, rehash, and atomically publish one object."""

    if request.max_download_bytes <= 0:
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID", "download size limit must be positive"
        )
    initial_host = _validate_url(request.source_url)
    temporary = cache.create_temporary("download")
    try:
        response = transport.open(request.source_url)
        _validate_url(response.final_url, expected_host=initial_host)
        total = 0
        hasher = hashlib.sha256()
        with temporary.open("wb") as stream:
            for chunk in response.chunks:
                if not isinstance(chunk, bytes):
                    raise ProviderFailure(
                        "AWP_PROVIDER_CACHE_CORRUPT", "download transport yielded non-bytes"
                    )
                total += len(chunk)
                if total > request.max_download_bytes:
                    raise ProviderFailure(
                        "AWP_PROVIDER_DOWNLOAD_LIMIT", "compressed download exceeded its limit"
                    )
                stream.write(chunk)
                hasher.update(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if hasher.hexdigest() != request.expected_sha256:
            raise ProviderFailure(
                "AWP_PROVIDER_HASH_MISMATCH", "complete downloaded bytes do not match the lock"
            )
        with temporary.open("rb") as stream:
            rehashed = hashlib.file_digest(stream, "sha256").hexdigest()
        if rehashed != request.expected_sha256:
            raise ProviderFailure(
                "AWP_PROVIDER_HASH_MISMATCH", "download changed before cache publication"
            )
        return cache.publish_verified(temporary, request.expected_sha256)
    except ProviderFailure as error:
        if temporary.exists() or temporary.is_symlink():
            cache.quarantine(
                temporary,
                reason=error.code,
                expected_sha256=request.expected_sha256,
            )
        raise
    except (OSError, RuntimeError) as error:
        if temporary.exists() or temporary.is_symlink():
            cache.quarantine(
                temporary,
                reason="download-interrupted",
                expected_sha256=request.expected_sha256,
            )
        raise ProviderFailure(
            "AWP_PROVIDER_CACHE_CORRUPT", "download ended before complete verification"
        ) from error
