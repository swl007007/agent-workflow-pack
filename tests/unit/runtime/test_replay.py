from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_stack.core.api import canonical_json_bytes
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.replay import consume_proof, proof_key, reserve_proof


PROJECT_ID = "4e3d0530-901a-4f65-8c41-5faf017026c4"
WORKSPACE_ID = "5f477c7f-a1dc-4a16-8f75-39f153170222"
TRANSACTION_ID = "6ea415f2-3823-4a36-9d25-cf00b82f1f70"
OTHER_TRANSACTION_ID = "78d71641-c23d-45b3-aabb-1c7f4ad8c808"
APPROVAL_ID = "89f80752-d34e-46c4-bbcc-2d805be9d919"
CHALLENGE = "a" * 64
DECISION_DIGEST = "b" * 64


def write_ledger(root: Path, *, corrupt: bool = False) -> Path:
    path = root / ".agent-workflow/local/approval-replay.json"
    path.parent.mkdir(parents=True)
    if corrupt:
        path.write_text("{not-json", encoding="utf-8")
    else:
        path.write_bytes(
            canonical_json_bytes(
                {
                    "schema_id": "agent-workflow.approval-replay",
                    "schema_version": 1,
                    "project_id": PROJECT_ID,
                    "workspace_instance_id": WORKSPACE_ID,
                    "entries": {},
                }
            )
        )
    os.chmod(path, 0o600)
    return path


def reservation_times() -> tuple[datetime, datetime]:
    validated = datetime(2026, 7, 13, 15, tzinfo=UTC)
    return validated, validated + timedelta(minutes=5)


def reserve(root: Path, *, transaction_id: str = TRANSACTION_ID, recovery: bool = False,
            now: datetime | None = None):
    validated, expires = reservation_times()
    return reserve_proof(
        root,
        project_id=PROJECT_ID,
        workspace_instance_id=WORKSPACE_ID,
        approval_id=APPROVAL_ID,
        approval_challenge=CHALLENGE,
        route_decision_digest=DECISION_DIGEST,
        transaction_id=transaction_id,
        validated_at=validated,
        proof_expires_at=expires,
        now=now or validated,
        recovery=recovery,
    )


def test_proof_key_excludes_transaction_identity() -> None:
    first = proof_key(APPROVAL_ID, CHALLENGE, DECISION_DIGEST, WORKSPACE_ID)
    second = proof_key(APPROVAL_ID, CHALLENGE, DECISION_DIGEST, WORKSPACE_ID)

    assert first == second
    assert len(first) == 64


def test_ledger_follows_only_absent_reserved_consumed(tmp_path: Path) -> None:
    path = write_ledger(tmp_path)
    reserved = reserve(tmp_path)

    assert reserved.state == "reserved"
    assert reserved.bound_transaction_id == TRANSACTION_ID
    reserved_again = reserve(tmp_path, now=reservation_times()[1] + timedelta(days=1))
    assert reserved_again == reserved

    consumed = consume_proof(
        tmp_path,
        proof_key=reserved.proof_key,
        transaction_id=TRANSACTION_ID,
        consumed_at=reservation_times()[0] + timedelta(minutes=1),
    )
    assert consumed.state == "consumed"
    assert consume_proof(
        tmp_path,
        proof_key=reserved.proof_key,
        transaction_id=TRANSACTION_ID,
        consumed_at=reservation_times()[0] + timedelta(minutes=2),
    ) == consumed

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["entries"][reserved.proof_key]["state"] == "consumed"
    with pytest.raises(RuntimeFailure, match="AWP_APPROVAL_REPLAY_BLOCKED"):
        reserve(tmp_path, transaction_id=OTHER_TRANSACTION_ID)


def test_first_reservation_requires_ttl_but_same_transaction_recovery_can_resume(
    tmp_path: Path,
) -> None:
    write_ledger(tmp_path)
    _, expires = reservation_times()
    after_expiry = expires + timedelta(days=1)

    with pytest.raises(RuntimeFailure, match="expired"):
        reserve(tmp_path, now=after_expiry)

    recovered = reserve(tmp_path, recovery=True, now=after_expiry)
    assert recovered.state == "reserved"


def test_rollback_window_preserves_reserved_then_consumed_path(tmp_path: Path) -> None:
    write_ledger(tmp_path)
    _, expires = reservation_times()

    reserved = reserve(tmp_path, recovery=True, now=expires + timedelta(days=2))
    consumed = consume_proof(
        tmp_path,
        proof_key=reserved.proof_key,
        transaction_id=TRANSACTION_ID,
        consumed_at=expires + timedelta(days=2),
    )

    assert reserved.state == "reserved"
    assert consumed.state == "consumed"


@pytest.mark.parametrize("state", ["missing", "corrupt"])
def test_missing_or_corrupt_registered_ledger_fails_closed(tmp_path: Path, state: str) -> None:
    if state == "corrupt":
        write_ledger(tmp_path, corrupt=True)

    with pytest.raises(RuntimeFailure, match="AWP_APPROVAL_REPLAY_BLOCKED"):
        reserve(tmp_path)
