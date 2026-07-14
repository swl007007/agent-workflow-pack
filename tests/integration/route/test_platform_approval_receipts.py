from __future__ import annotations

import copy

import pytest

from agent_stack.route.approval import verify_task_creation_approval
from agent_stack.route.errors import RouteFailure
from tests.unit.route.test_task_approval import (
    ReceiptVerifier,
    capability,
    proof,
    runtime_context,
    verified_decision,
)


@pytest.mark.parametrize("platform", ["claude-code", "codex", "opencode"])
def test_each_locked_platform_authenticates_its_own_direct_human_receipt(
    platform: str,
) -> None:
    decision = verified_decision(platform=platform)
    raw = proof(decision, platform=platform)
    raw["verifier_receipt"] = f"{platform}-receipt:opaque"
    verifier = ReceiptVerifier(f"{platform}-receipt:opaque")

    verified = verify_task_creation_approval(
        raw,
        decision,
        capability(platform=platform),
        runtime_context(verifier, platform=platform),
    )

    assert verified["verifier_id"] == f"{platform}-human-verifier"
    assert verifier.projections[0]["platform"] == platform


def test_receipt_cannot_be_replayed_across_platform_or_harness_contract() -> None:
    decision = verified_decision()
    raw = proof(decision)
    wrong_platform = copy.deepcopy(raw)
    wrong_platform["platform"] = "opencode"
    wrong_harness = copy.deepcopy(raw)
    wrong_harness["harness_version"] = "2.0.0"

    for candidate in (wrong_platform, wrong_harness):
        with pytest.raises(RouteFailure, match="AWP_ROUTE_APPROVAL_INVALID"):
            verify_task_creation_approval(
                candidate,
                decision,
                capability(),
                runtime_context(ReceiptVerifier("codex-receipt:opaque")),
            )
