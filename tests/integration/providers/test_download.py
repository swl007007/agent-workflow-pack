from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_stack.providers.cache import CacheStore
from agent_stack.providers.download import DownloadResponse, download_verified
from agent_stack.providers.errors import ProviderFailure
from agent_stack.providers.models import AcquisitionRequest


class FakeTransport:
    def __init__(
        self,
        payload: bytes,
        *,
        final_url: str = "https://releases.example.test/object.tar.gz",
        interrupt_after: int | None = None,
    ) -> None:
        self.payload = payload
        self.final_url = final_url
        self.interrupt_after = interrupt_after

    def open(self, url: str) -> DownloadResponse:
        def chunks():
            midpoint = max(1, len(self.payload) // 2)
            emitted = 0
            for chunk in (self.payload[:midpoint], self.payload[midpoint:]):
                if self.interrupt_after is not None and emitted >= self.interrupt_after:
                    raise OSError("connection interrupted")
                emitted += len(chunk)
                yield chunk

        return DownloadResponse(final_url=self.final_url, chunks=chunks())


def _request(payload: bytes, *, limit: int | None = None) -> AcquisitionRequest:
    return AcquisitionRequest(
        component_id="component:test",
        source_url="https://releases.example.test/object.tar.gz",
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        max_download_bytes=limit if limit is not None else len(payload) + 1,
        cache_namespace="workflow-lock",
    )


def test_verified_streaming_download_publishes_complete_object(tmp_path: Path) -> None:
    payload = b"provider archive bytes"
    store = CacheStore(tmp_path)

    path = download_verified(_request(payload), store, FakeTransport(payload))

    assert path.read_bytes() == payload
    assert path == store.object_path(hashlib.sha256(payload).hexdigest())


def test_partial_download_is_never_promoted(tmp_path: Path) -> None:
    payload = b"x" * 512
    store = CacheStore(tmp_path)
    transport = FakeTransport(payload, interrupt_after=200)

    with pytest.raises(ProviderFailure):
        download_verified(_request(payload), store, transport)

    assert not store.object_path(hashlib.sha256(payload).hexdigest()).exists()
    assert any((tmp_path / "quarantine").iterdir())


def test_download_limit_and_complete_hash_are_enforced(tmp_path: Path) -> None:
    payload = b"x" * 128
    store = CacheStore(tmp_path)
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_DOWNLOAD_LIMIT"):
        download_verified(_request(payload, limit=64), store, FakeTransport(payload))

    wrong = _request(payload)
    wrong = AcquisitionRequest(
        component_id=wrong.component_id,
        source_url=wrong.source_url,
        expected_sha256="0" * 64,
        max_download_bytes=wrong.max_download_bytes,
        cache_namespace=wrong.cache_namespace,
    )
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_HASH_MISMATCH"):
        download_verified(wrong, store, FakeTransport(payload))


@pytest.mark.parametrize(
    "final_url",
    [
        "http://releases.example.test/object.tar.gz",
        "https://evil.example.test/object.tar.gz",
        "https://user:pass@releases.example.test/object.tar.gz",
        "https://releases.example.test:444/object.tar.gz",
    ],
)
def test_redirect_destination_is_revalidated(tmp_path: Path, final_url: str) -> None:
    payload = b"archive"
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_PLAN_INVALID"):
        download_verified(
            _request(payload), CacheStore(tmp_path), FakeTransport(payload, final_url=final_url)
        )
