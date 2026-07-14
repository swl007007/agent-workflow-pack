from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_stack.core.api import CANONICAL_NULL
from agent_stack.providers.attempts import AttemptStore
from agent_stack.providers.broker import TrustedBroker
from agent_stack.providers.errors import ProviderFailure


TOKEN = b"release-token"
ATTEMPT_ID = "33333333-3333-4333-8333-333333333333"


def _store(root: Path) -> AttemptStore:
    return AttemptStore(
        root,
        workspace_instance_id="11111111-1111-4111-8111-111111111111",
        provider_plan_digest="a" * 64,
        prospective_transaction_id="22222222-2222-4222-8222-222222222222",
        approval_digest=CANONICAL_NULL,
    )


@pytest.mark.parametrize("killpoint", ["spawned", "prepared", "receipt", "released"])
def test_sigkill_boundaries_leave_recoverable_durable_evidence(
    tmp_path: Path, killpoint: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path / killpoint)
    broker = TrustedBroker.start(
        store,
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        deadline_seconds=3,
    )
    if killpoint == "spawned":
        broker.terminate()
        broker.wait(timeout=2)
        assert not store.journal_path.exists()
        return

    store.prepare(
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        broker_liveness_identity=broker.liveness_identity,
        prepared_at="2026-07-13T16:00:00Z",
        release_deadline="2026-07-13T16:01:00Z",
        command_digest="b" * 64,
        isolation_measurements={},
    )
    if killpoint == "prepared":
        broker.terminate()
        broker.wait(timeout=2)
        recovered = store.recover_interrupted(
            ATTEMPT_ID,
            containment_state="gone",
            receipt=None,
            recorded_at="2026-07-13T16:02:00Z",
        )
        assert recovered.state == "interrupted"
        return

    if killpoint == "receipt":
        original = store.record_released

        def crash_after_receipt(attempt_id: str, receipt: dict[str, object]):
            assert store.release_receipt_path(attempt_id).exists()
            raise RuntimeError("parent killed after receipt")

        monkeypatch.setattr(store, "record_released", crash_after_receipt)
        with pytest.raises(RuntimeError):
            broker.release_once(TOKEN)
        monkeypatch.setattr(store, "record_released", original)
    else:
        broker.release_once(TOKEN)
    broker.wait(timeout=2)

    recovered = store.recover_interrupted(
        ATTEMPT_ID,
        containment_state="gone",
        receipt=None,
        recorded_at="2026-07-13T16:02:00Z",
    )
    assert recovered.state == "interrupted"


def test_live_or_ambiguous_broker_evidence_blocks_retry(tmp_path: Path) -> None:
    store = _store(tmp_path)
    broker = TrustedBroker.start(
        store,
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        deadline_seconds=3,
    )
    store.prepare(
        attempt_id=ATTEMPT_ID,
        release_token_digest=hashlib.sha256(TOKEN).hexdigest(),
        broker_liveness_identity=broker.liveness_identity,
        prepared_at="2026-07-13T16:00:00Z",
        release_deadline="2026-07-13T16:01:00Z",
        command_digest="b" * 64,
        isolation_measurements={},
    )
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_CONTAINMENT_AMBIGUOUS"):
        store.recover_interrupted(
            ATTEMPT_ID,
            containment_state=broker.liveness(),
            receipt=None,
            recorded_at="2026-07-13T16:02:00Z",
        )
    broker.terminate()
    broker.wait(timeout=2)
