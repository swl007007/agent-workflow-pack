from __future__ import annotations

import multiprocessing
from pathlib import Path

from agent_stack.core.api import CANONICAL_NULL
from agent_stack.providers.attempts import AttemptStore
from agent_stack.providers.errors import ProviderFailure


def _try_prepare(root: str, attempt_id: str, queue: multiprocessing.Queue) -> None:
    store = AttemptStore(
        Path(root),
        workspace_instance_id="11111111-1111-4111-8111-111111111111",
        provider_plan_digest="a" * 64,
        prospective_transaction_id="22222222-2222-4222-8222-222222222222",
        approval_digest=CANONICAL_NULL,
    )
    try:
        store.prepare(
            attempt_id=attempt_id,
            release_token_digest=("b" if attempt_id.startswith("3") else "c") * 64,
            broker_liveness_identity=f"pidfd:{attempt_id[0]}",
            prepared_at="2026-07-13T16:00:00Z",
            release_deadline="2026-07-13T16:01:00Z",
            command_digest="d" * 64,
            isolation_measurements={},
        )
    except ProviderFailure:
        queue.put("blocked")
    else:
        queue.put("prepared")


def test_two_attempts_for_one_plan_cannot_overlap(tmp_path: Path) -> None:
    queue: multiprocessing.Queue = multiprocessing.Queue()
    processes = [
        multiprocessing.Process(
            target=_try_prepare,
            args=(str(tmp_path), attempt_id, queue),
        )
        for attempt_id in (
            "33333333-3333-4333-8333-333333333333",
            "44444444-4444-4444-8444-444444444444",
        )
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=4)
        assert process.exitcode == 0

    assert sorted(queue.get(timeout=1) for _ in processes) == ["blocked", "prepared"]
