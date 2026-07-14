from __future__ import annotations

import inspect
from collections.abc import Mapping

import pytest

from agent_stack.runtime.ports import (
    RouteDecisionVerifierPort,
    RouteVerifierPorts,
    TaskCreationApprovalVerifierPort,
    bind_route_verifier_ports,
)


class DecisionVerifierFake:
    def __call__(
        self,
        decision: Mapping[str, object],
        current_authorities: Mapping[str, object],
        consumer: str,
    ) -> Mapping[str, object]:
        assert decision["schema_id"] == "agent-workflow.route-decision"
        assert current_authorities["workspace_instance_id"] == "workspace"
        assert consumer == "task-admit"
        return {
            "schema_id": "agent-workflow.verified-route-decision",
            "schema_version": 1,
            "operation": "create-integrated-task",
            "decision": dict(decision),
        }


class ApprovalVerifierFake:
    def __call__(
        self,
        proof: Mapping[str, object],
        decision: Mapping[str, object],
        capability: Mapping[str, object],
        runtime_context: Mapping[str, object],
    ) -> Mapping[str, object]:
        assert proof["schema_id"] == "agent-workflow.approval-proof"
        assert decision["operation"] == "create-integrated-task"
        assert capability["schema_id"] == "agent-workflow.capability-manifest"
        assert runtime_context["platform"] == "codex"
        return {
            "schema_id": "agent-workflow.approval-verification-result",
            "schema_version": 1,
            "operation": "create-integrated-task",
            "approval_id": proof["approval_id"],
            "validated_at": "2026-07-13T15:00:00Z",
        }


def test_route_ports_expose_the_exact_frozen_argument_order() -> None:
    assert list(inspect.signature(RouteDecisionVerifierPort.__call__).parameters) == [
        "self",
        "decision",
        "current_authorities",
        "consumer",
    ]
    assert list(inspect.signature(TaskCreationApprovalVerifierPort.__call__).parameters) == [
        "self",
        "proof",
        "decision",
        "capability",
        "runtime_context",
    ]


def test_only_explicit_injected_verifiers_can_form_runtime_ports() -> None:
    decision = DecisionVerifierFake()
    approval = ApprovalVerifierFake()

    ports = bind_route_verifier_ports(decision, approval)

    assert isinstance(ports, RouteVerifierPorts)
    assert ports.decision is decision
    assert ports.approval is approval
    assert isinstance(decision, RouteDecisionVerifierPort)
    assert isinstance(approval, TaskCreationApprovalVerifierPort)

    with pytest.raises(TypeError, match="explicit Route verifier ports"):
        bind_route_verifier_ports(None, approval)
    with pytest.raises(TypeError, match="explicit Route verifier ports"):
        bind_route_verifier_ports(decision, None)


def test_contract_fakes_return_complete_schema_tagged_verified_values() -> None:
    ports = bind_route_verifier_ports(DecisionVerifierFake(), ApprovalVerifierFake())
    raw_decision = {
        "schema_id": "agent-workflow.route-decision",
        "schema_version": 1,
        "operation": "create-integrated-task",
    }
    verified_decision = ports.decision(
        raw_decision,
        {"workspace_instance_id": "workspace"},
        "task-admit",
    )
    verified_approval = ports.approval(
        {
            "schema_id": "agent-workflow.approval-proof",
            "schema_version": 1,
            "approval_id": "9a091863-e45f-47d5-8cdd-3e916cf0ea2a",
        },
        verified_decision,
        {"schema_id": "agent-workflow.capability-manifest"},
        {"platform": "codex"},
    )

    assert verified_decision["schema_id"] == "agent-workflow.verified-route-decision"
    assert verified_approval["schema_id"] == "agent-workflow.approval-verification-result"
