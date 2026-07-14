from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_stack._vendor import fastjsonschema
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.outbox import deliver_effect, enqueue_effect


ROOT = Path(__file__).resolve().parents[3]
TASK_ID = "5f477c7f-a1dc-4a16-8f75-39f153170222"
TRANSACTION_ID = "6ea415f2-3823-4a36-9d25-cf00b82f1f70"
CREATED_AT = datetime(2026, 7, 13, 15, tzinfo=UTC)


def enqueue(root: Path):
    return enqueue_effect(
        root,
        operation="task-admit",
        task_id=TASK_ID,
        transaction_id=TRANSACTION_ID,
        effect_kind="notify-task-admitted",
        handler_id="platform-notifier",
        handler_version="1.0.0",
        payload={"task_id": TASK_ID, "status": "active"},
        created_at=CREATED_AT,
    )


def test_effect_identity_and_idempotency_key_are_deterministic(tmp_path: Path) -> None:
    first = enqueue(tmp_path)
    second = enqueue(tmp_path)

    assert first == second
    assert len(first.effect_id) == 64
    assert len(first.idempotency_key) == 64
    files = list((tmp_path / ".agent-workflow/local/task-outbox").glob("*.json"))
    assert [path.name for path in files] == [f"{first.effect_id}.json"]

    schema = json.loads(
        (ROOT / "schemas/runtime/task-outbox.v1.json").read_text(encoding="utf-8")
    )
    document = json.loads(files[0].read_text(encoding="utf-8"))
    assert fastjsonschema.compile(schema)(document) == document


def test_delivery_is_idempotent_and_does_not_reopen_delivered_effect(tmp_path: Path) -> None:
    item = enqueue(tmp_path)
    calls: list[str] = []

    def handler(document) -> None:
        calls.append(str(document["idempotency_key"]))

    delivered = deliver_effect(
        tmp_path,
        effect_id=item.effect_id,
        attempted_at=CREATED_AT + timedelta(minutes=1),
        handler=handler,
    )
    delivered_again = deliver_effect(
        tmp_path,
        effect_id=item.effect_id,
        attempted_at=CREATED_AT + timedelta(minutes=2),
        handler=handler,
    )

    assert delivered.delivery_state == "delivered"
    assert delivered_again == delivered
    assert calls == [item.idempotency_key]


def test_failed_delivery_can_retry_with_the_same_idempotency_key(tmp_path: Path) -> None:
    item = enqueue(tmp_path)
    calls: list[str] = []

    def failing(document) -> None:
        calls.append(str(document["idempotency_key"]))
        raise OSError("offline")

    with pytest.raises(RuntimeFailure, match="outbox handler failed"):
        deliver_effect(
            tmp_path,
            effect_id=item.effect_id,
            attempted_at=CREATED_AT + timedelta(minutes=1),
            handler=failing,
        )

    delivered = deliver_effect(
        tmp_path,
        effect_id=item.effect_id,
        attempted_at=CREATED_AT + timedelta(minutes=2),
        handler=lambda document: calls.append(str(document["idempotency_key"])),
    )

    assert delivered.delivery_state == "delivered"
    assert calls == [item.idempotency_key, item.idempotency_key]


def test_unknown_or_corrupt_outbox_item_fails_without_task_authority_change(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeFailure, match="outbox item"):
        deliver_effect(
            tmp_path,
            effect_id="a" * 64,
            attempted_at=CREATED_AT,
            handler=lambda _: None,
        )
