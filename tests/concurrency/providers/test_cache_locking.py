from __future__ import annotations

import multiprocessing
import time
from pathlib import Path

from agent_stack.providers.cache import CacheStore


def _hold_lock(cache_root: str, digest: str, ready: multiprocessing.Event) -> None:
    store = CacheStore(Path(cache_root))
    with store.acquire_lock(digest):
        ready.set()
        time.sleep(0.35)


def test_object_lock_serializes_two_processes(tmp_path: Path) -> None:
    digest = "a" * 64
    ready = multiprocessing.Event()
    process = multiprocessing.Process(target=_hold_lock, args=(str(tmp_path), digest, ready))
    process.start()
    assert ready.wait(timeout=3)
    started = time.monotonic()

    with CacheStore(tmp_path).acquire_lock(digest):
        waited = time.monotonic() - started

    process.join(timeout=3)
    assert process.exitcode == 0
    assert waited >= 0.2
