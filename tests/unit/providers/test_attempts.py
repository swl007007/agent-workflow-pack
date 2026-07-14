from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_stack.core.api import CANONICAL_NULL
from agent_stack.providers.attempts import AttemptStore
from agent_stack.providers.errors import ProviderFailure


WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
TX_ID = "22222222-2222-4222-8222-222222222222"
ATTEMPT_ID = "33333333-3333-4333-8333-333333333333"
PLAN_DIGEST = "a" * 64
TOKEN_DIGEST = "b" * 64


def _store(tmp_path: Path) -> AttemptStore:
    return AttemptStore(
        tmp_path,
        workspace_instance_id=WORKSPACE_ID,
        provider_plan_digest=PLAN_DIGEST,
        prospective_transaction_id=TX_ID,
        approval_digest=CANONICAL_NULL,
    )


def _prepare(store: AttemptStore, attempt_id: str = ATTEMPT_ID, token: str = TOKEN_DIGEST):
    return store.prepare(
        attempt_id=attempt_id,
        release_token_digest=token,
        broker_liveness_identity="pidfd:123:1",
        prepared_at="2026-07-13T16:00:00Z",
        release_deadline="2026-07-13T16:01:00Z",
        command_digest="c" * 64,
        isolation_measurements={"network": "unavailable"},
    )


def _receipt() -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.provider-release-receipt",
        "schema_version": 1,
        "workspace_instance_id": WORKSPACE_ID,
        "provider_plan_digest": PLAN_DIGEST,
        "prospective_transaction_id": TX_ID,
        "attempt_id": ATTEMPT_ID,
        "release_token_digest": TOKEN_DIGEST,
        "broker_liveness_identity": "pidfd:123:1",
        "released_at": "2026-07-13T16:00:10Z",
    }


@pytest.mark.parametrize("terminal", ["succeeded", "failed", "interrupted"])
def test_monotonic_prepared_released_terminal_flow(tmp_path: Path, terminal: str) -> None:
    store = _store(tmp_path)
    _prepare(store)
    released = store.record_released(ATTEMPT_ID, _receipt())

    final = store.record_terminal(
        ATTEMPT_ID,
        state=terminal,
        terminal_at="2026-07-13T16:00:20Z",
        result_category="ok" if terminal == "succeeded" else terminal,
        sanitized_output_digest="d" * 64,
        candidate_output_digest="e" * 64,
    )

    assert released.state == "released"
    assert final.state == terminal
    document = json.loads(store.journal_path.read_text(encoding="utf-8"))
    assert document["attempts"][0]["state"] == terminal
    assert store.release_receipt_path(ATTEMPT_ID).is_file()


def test_prepared_without_receipt_can_recover_to_interrupted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _prepare(store)

    recovered = store.recover_interrupted(
        ATTEMPT_ID,
        containment_state="gone",
        receipt=None,
        recorded_at="2026-07-13T16:02:00Z",
    )

    assert recovered.state == "interrupted"


def test_live_or_ambiguous_containment_blocks_retry(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _prepare(store)
    for state in ("live", "ambiguous"):
        with pytest.raises(ProviderFailure, match="AWP_PROVIDER_CONTAINMENT_AMBIGUOUS"):
            store.recover_interrupted(
                ATTEMPT_ID,
                containment_state=state,
                receipt=None,
                recorded_at="2026-07-13T16:02:00Z",
            )


def test_illegal_transitions_duplicate_ids_and_tokens_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _prepare(store)
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ATTEMPT_CORRUPT"):
        _prepare(store, attempt_id="44444444-4444-4444-8444-444444444444")
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ATTEMPT_CORRUPT"):
        store.record_terminal(
            ATTEMPT_ID,
            state="succeeded",
            terminal_at="2026-07-13T16:00:20Z",
            result_category="ok",
            sanitized_output_digest="d" * 64,
            candidate_output_digest="e" * 64,
        )


def test_receipt_is_immutable_and_must_match_plan_approval_and_attempt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _prepare(store)
    store.record_released(ATTEMPT_ID, _receipt())
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ATTEMPT_CORRUPT"):
        store.record_released(ATTEMPT_ID, _receipt())

    other = _store(tmp_path / "other")
    _prepare(other)
    mismatched = _receipt()
    mismatched["provider_plan_digest"] = "0" * 64
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ATTEMPT_CORRUPT"):
        other.record_released(ATTEMPT_ID, mismatched)


def test_corrupt_or_mismatched_journal_is_never_recreated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.journal_path.parent.mkdir(parents=True, exist_ok=True)
    store.journal_path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ATTEMPT_CORRUPT"):
        _prepare(store)
    assert store.journal_path.read_text(encoding="utf-8") == "{broken"


def test_attempt_schemas_are_registered_and_closed(tmp_path: Path) -> None:
    from agent_stack.core.api import CoreFailure, SchemaCatalog

    root = Path(__file__).resolve().parents[3]
    store = _store(tmp_path)
    _prepare(store)
    catalog = SchemaCatalog.discover(root / "schemas")
    journal = json.loads(store.journal_path.read_text(encoding="utf-8"))
    catalog.load_and_validate(journal)
    catalog.load_and_validate(_receipt())
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**journal, "unknown": True})
