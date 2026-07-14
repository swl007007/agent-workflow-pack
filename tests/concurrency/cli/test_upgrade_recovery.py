from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import pytest

from agent_stack.release.compatibility import RuntimeJournalReference
from agent_stack.release.distribution import (
    UpgradeRecoveryPorts,
    UpgradeRecoveryRequest,
    recover_upgrade,
)
from agent_stack.release.errors import LifecycleFailure
from tests.integration.cli.test_upgrade import release


def test_recovery_uses_only_journal_allowlisted_candidate_runtime() -> None:
    committed = release("0.1.0", "b")
    candidate = release("0.2.0", "c")
    reference = RuntimeJournalReference(
        runtime_role="candidate",
        release_id=candidate.identity.release_id,
        release_manifest_digest=candidate.manifest_digest,
    )
    calls: list[object] = []
    ports = UpgradeRecoveryPorts(
        load_runtime_reference=lambda transaction_id: reference,
        load_verified_candidate=lambda loaded: candidate,
        recover_transaction=lambda transaction_id, action, runtime: calls.append(
            (transaction_id, action, runtime.identity.release_id)
        )
        or MappingProxyType({"transaction_id": transaction_id, "rolled_back": False}),
    )

    result = recover_upgrade(
        UpgradeRecoveryRequest(
            transaction_id="tx-crash",
            action="resume",
            committed_release=committed,
            running_release=candidate,
        ),
        ports,
    )

    assert result == {"transaction_id": "tx-crash", "rolled_back": False}
    assert calls == [("tx-crash", "resume", candidate.identity.release_id)]


def test_recovery_rejects_a_runtime_not_selected_by_journal() -> None:
    committed = release("0.1.0", "b")
    candidate = release("0.2.0", "c")
    reference = RuntimeJournalReference(
        runtime_role="candidate",
        release_id=candidate.identity.release_id,
        release_manifest_digest=candidate.manifest_digest,
    )
    ports = UpgradeRecoveryPorts(
        load_runtime_reference=lambda transaction_id: reference,
        load_verified_candidate=lambda loaded: candidate,
        recover_transaction=lambda transaction_id, action, runtime: {},
    )

    with pytest.raises(LifecycleFailure, match="AWP_RELEASE_RUNTIME_NOT_ALLOWED"):
        recover_upgrade(
            UpgradeRecoveryRequest(
                transaction_id="tx-crash",
                action="resume",
                committed_release=committed,
                running_release=committed,
            ),
            ports,
        )


def test_recovery_preserves_explicit_resume_or_rollback_action() -> None:
    committed = release("0.2.0", "c")
    reference = RuntimeJournalReference(
        runtime_role="committed",
        release_id=committed.identity.release_id,
        release_manifest_digest=committed.manifest_digest,
    )
    actions: list[str] = []

    def recover(transaction_id: str, action: str, runtime: object) -> Mapping[str, object]:
        actions.append(action)
        return {"transaction_id": transaction_id, "action": action}

    ports = UpgradeRecoveryPorts(
        load_runtime_reference=lambda transaction_id: reference,
        load_verified_candidate=lambda loaded: None,
        recover_transaction=recover,
    )

    recover_upgrade(
        UpgradeRecoveryRequest("tx", "rollback", committed, committed), ports
    )

    assert actions == ["rollback"]
