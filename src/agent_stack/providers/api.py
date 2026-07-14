"""Frozen public provider acquisition and execution API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final
from urllib.request import urlopen

from agent_stack.core.api import digest

from .approval import VerifiedProviderApproval
from .archive import content_root_digest, extract_verified_archive, inspect_archive
from .cache import CacheStore
from .download import DownloadResponse, download_verified
from .errors import ProviderFailure
from .initializer import execute_initializer, provider_cache_root
from .models import AcquisitionRequest, AcquisitionResult, ProviderExecutionResult, ProviderPlan


PROVIDER_INTERFACE_VERSION: Final = 1
PUBLIC_MODELS: Final = (
    AcquisitionRequest,
    AcquisitionResult,
    ProviderExecutionResult,
    ProviderPlan,
)


class _UrllibTransport:
    def open(self, url: str) -> DownloadResponse:
        response = urlopen(url, timeout=30)  # noqa: S310 - URL was authorized upstream.

        def chunks() -> Iterator[bytes]:
            try:
                while chunk := response.read(1024 * 1024):
                    yield chunk
            finally:
                response.close()

        return DownloadResponse(final_url=response.geturl(), chunks=chunks())


def acquire(request: AcquisitionRequest) -> AcquisitionResult:
    """Acquire and optionally extract one exact workflow-lock object."""

    cache_root = provider_cache_root()
    cache = CacheStore(cache_root)
    object_path = download_verified(request, cache, _UrllibTransport())
    archive_digest: str | None = None
    content_digest: str | None = None
    if request.archive_policy is not None:
        inspection = inspect_archive(
            object_path, request.expected_sha256, request.archive_policy
        )
        archive_digest = inspection.inspection_digest
        if request.extract:
            destination = (
                cache_root
                / "extracted/sha256"
                / request.expected_sha256[:2]
                / request.expected_sha256
            )
            if destination.exists():
                content_digest = content_root_digest(destination)
            else:
                content_digest = extract_verified_archive(
                    object_path,
                    request.expected_sha256,
                    request.archive_policy,
                    destination,
                )
    diagnostics_digest = digest(
        "agent-workflow.provider-diagnostics.v1",
        {
            "component_id": request.component_id,
            "source_digest": request.expected_sha256,
            "archive_evidence_digest": archive_digest,
            "content_root_digest": content_digest,
        },
    )
    return AcquisitionResult(
        component_id=request.component_id,
        source_digest=request.expected_sha256,
        cache_object_path=str(Path(object_path)),
        archive_evidence_digest=archive_digest,
        content_root_digest=content_digest,
        diagnostics_digest=diagnostics_digest,
        provenance_records=(),
    )


def execute_provider(
    plan: ProviderPlan, approval: VerifiedProviderApproval | None
) -> ProviderExecutionResult:
    """Execute one immutable plan through approval, broker, sandbox, and validation."""

    return execute_initializer(plan, approval)


__all__ = [
    "AcquisitionRequest",
    "AcquisitionResult",
    "PROVIDER_INTERFACE_VERSION",
    "PUBLIC_MODELS",
    "ProviderExecutionResult",
    "ProviderFailure",
    "ProviderPlan",
    "acquire",
    "execute_provider",
]
