from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.core.diagnostics import build_workspace_diagnostic
from agent_stack.core.task_policy import (
    evaluate_task_gate,
    evaluate_workspace_state_quiescence,
)
from tests.unit.core.test_task_policy import (
    _ambiguous_finding,
    _impact,
    _snapshot,
)


@given(st.sampled_from(("doctor", "workspace-migrate", "sync", "upgrade")))
def test_requested_command_never_changes_fixed_workspace_quiescence(command: str) -> None:
    snapshot, findings_document = _snapshot([_ambiguous_finding()])
    state = evaluate_workspace_state_quiescence(snapshot, findings_document)
    gate_operation = command if command != "doctor" else "workspace-migrate"
    gate = evaluate_task_gate(gate_operation, _impact(), snapshot, findings_document)

    diagnostic = build_workspace_diagnostic(
        command=command,
        relationship="matching",
        relationship_evidence="verified",
        discovery_evidence="verified",
        workspace_task_state=state,
        task_gate_result=gate,
    )

    assert diagnostic.workspace_state.task_quiescence == "ambiguous"


@given(st.permutations(("migration-required", "ahead", "diverged")))
def test_verified_relationship_classification_does_not_depend_on_call_order(
    relationships: list[str],
) -> None:
    snapshot, findings_document = _snapshot()
    state = evaluate_workspace_state_quiescence(snapshot, findings_document)
    gate = evaluate_task_gate("workspace-migrate", _impact(), snapshot, findings_document)

    results = {
        relationship: build_workspace_diagnostic(
            command="doctor",
            relationship=relationship,
            relationship_evidence="verified",
            discovery_evidence="unsupported",
            workspace_task_state=state,
            task_gate_result=gate,
        ).workspace_state.primary_state_blocker
        for relationship in relationships
    }

    assert results == {
        "migration-required": "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS",
        "ahead": "AWP_WORKSPACE_CONTRACT_AHEAD",
        "diverged": "AWP_WORKSPACE_CONTRACT_DIVERGED",
    }
