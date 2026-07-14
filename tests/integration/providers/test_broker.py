from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_stack.core.api import CANONICAL_NULL
from agent_stack.providers.attempts import AttemptStore
from agent_stack.providers.broker import TrustedBroker
from agent_stack.providers.errors import ProviderFailure
from agent_stack.providers.sandbox import (
    containment_liveness,
    start_containment,
    terminate_containment,
)


WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
TX_ID = "22222222-2222-4222-8222-222222222222"
ATTEMPT_ID = "33333333-3333-4333-8333-333333333333"
TOKEN = b"one-time-provider-release-token"


def _store(tmp_path: Path) -> AttemptStore:
    return AttemptStore(
        tmp_path,
        workspace_instance_id=WORKSPACE_ID,
        provider_plan_digest="a" * 64,
        prospective_transaction_id=TX_ID,
        approval_digest=CANONICAL_NULL,
    )


def _prepare(store: AttemptStore, broker: TrustedBroker) -> None:
    store.prepare(
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        broker_liveness_identity=broker.liveness_identity,
        prepared_at="2026-07-13T16:00:00Z",
        release_deadline="2026-07-13T16:01:00Z",
        command_digest="b" * 64,
        isolation_measurements={},
    )


def test_broker_releases_once_only_after_durable_prepared(tmp_path: Path) -> None:
    store = _store(tmp_path)
    broker = TrustedBroker.start(
        store,
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        deadline_seconds=3,
    )
    assert not store.release_receipt_path(ATTEMPT_ID).exists()
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ATTEMPT_CORRUPT"):
        broker.release_once(TOKEN)
    _prepare(store, broker)

    record = broker.release_once(TOKEN)

    assert record.state == "released"
    assert store.release_receipt_path(ATTEMPT_ID).is_file()
    broker.wait(timeout=2)
    assert broker.liveness() == "gone"
    with pytest.raises(ProviderFailure):
        broker.release_once(TOKEN)


def test_malformed_token_eof_and_deadline_never_create_receipt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    broker = TrustedBroker.start(
        store,
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        deadline_seconds=2,
    )
    _prepare(store, broker)
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_CONTAINMENT_AMBIGUOUS"):
        broker.release_once(b"wrong-token")
    broker.wait(timeout=2)
    assert not store.release_receipt_path(ATTEMPT_ID).exists()

    second_store = _store(tmp_path / "eof")
    second = TrustedBroker.start(
        second_store,
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        deadline_seconds=2,
    )
    second.close_without_release()
    second.wait(timeout=2)
    assert not second_store.release_receipt_path(ATTEMPT_ID).exists()

    deadline_store = _store(tmp_path / "deadline")
    deadline = TrustedBroker.start(
        deadline_store,
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        deadline_seconds=0.15,
    )
    deadline.wait(timeout=2)
    assert not deadline_store.release_receipt_path(ATTEMPT_ID).exists()


def test_containment_liveness_and_safe_process_group_termination(tmp_path: Path) -> None:
    containment = start_containment(
        ["sh", "-c", "sleep 30"], cwd=tmp_path, environment={"PATH": "/usr/bin:/bin"}
    )
    assert containment_liveness(containment) == "live"

    terminate_containment(containment, timeout=1)

    assert containment_liveness(containment) == "gone"
