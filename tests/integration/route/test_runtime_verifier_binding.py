from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

import pytest

from agent_stack.route.calculator import RouteCalculationInputs, calculate_route
from agent_stack.route.errors import RouteFailure
from agent_stack.route.wrappers import production_route_verifier_ports
from agent_stack.runtime.task_service import (
    TaskAdmissionRequest,
    TaskFile,
    admit_task,
)
from tests.integration.runtime.test_task_admission import (
    PROJECT_ID,
    WORKSPACE_ID,
    initialize_project,
    metadata_create,
    read_json,
)
from tests.unit.route.test_calculator import authorities, intent
from tests.unit.route.test_task_approval import (
    ReceiptVerifier,
    capability,
    proof,
    runtime_context,
)


TRANSACTION_ID = "78d71641-c23d-45b3-aabb-1c7f4ad8c808"
NOW = datetime(2026, 7, 13, 15, tzinfo=UTC)


def admission_request(tmp_path, *, receipt: str = "codex-receipt:opaque"):
    auth = authorities()
    decision = calculate_route(
        "create-integrated-task",
        RouteCalculationInputs(
            intent=intent(requested_mode="trellis-native"),
            requested_task_ref=".trellis/tasks/example",
        ),
        auth,
    )
    raw_proof = proof(dict(decision))
    raw_proof["verifier_receipt"] = receipt
    workflow_contract = {
        "version": 1,
        "profile_digest_at_admission": auth.profile_digest,
        "lock_digest_at_admission": auth.lock_digest,
        "artifact_bundle_digest_at_admission": auth.artifact_bundle_digest,
        "policy_digest_at_admission": auth.policy_digest,
        "adapter_id": auth.adapter_id,
        "adapter_version_at_admission": auth.adapter_version,
        "route_contract_version": auth.router_contract_version,
        "task_contract_surfaces": decision["task_contract_surfaces"],
    }
    current_authorities = {
        field.name: getattr(auth, field.name) for field in dataclasses.fields(auth)
    }
    return TaskAdmissionRequest(
        project_root=tmp_path,
        project_id=PROJECT_ID,
        workspace_instance_id=WORKSPACE_ID,
        transaction_id=TRANSACTION_ID,
        decision=decision,
        approval_proof=raw_proof,
        current_authorities=current_authorities,
        capability=capability(),
        runtime_context=runtime_context(
            ReceiptVerifier("codex-receipt:opaque")
        ),
        workflow_contract=workflow_contract,
        mode_state={"task_ref": decision["requested_task_ref"]},
        task_files=(TaskFile("README.md", b"# Task\n", "0644"),),
        metadata_mutations=(metadata_create(),),
        admitted_at=NOW,
        route_ports=production_route_verifier_ports(),
    )


def test_production_composition_binds_real_route_verifiers_and_consumes_proof(
    tmp_path,
) -> None:
    initialize_project(tmp_path)
    ports = production_route_verifier_ports()
    assert ports.decision.__class__.__module__ == "agent_stack.route.wrappers"
    assert ports.approval.__module__ == "agent_stack.route.approval"
    assert "Fake" not in ports.decision.__class__.__name__

    result = admit_task(admission_request(tmp_path))

    assert result.lifecycle_status == "active"
    integration = read_json(tmp_path / ".trellis/tasks/example/integration.yaml")
    assert integration["admission"]["route_decision_digest"]
    assert integration["admission"]["approval_verifier_id"] == "codex-human-verifier"
    replay = read_json(tmp_path / ".agent-workflow/local/approval-replay.json")
    assert {entry["state"] for entry in replay["entries"].values()} == {"consumed"}


def test_real_approval_failure_occurs_before_task_journal_or_target_mutation(tmp_path) -> None:
    initialize_project(tmp_path)
    request = admission_request(tmp_path, receipt="model-authored:yes")

    with pytest.raises(RouteFailure, match="AWP_ROUTE_APPROVAL_INVALID"):
        admit_task(request)

    assert not (tmp_path / ".trellis/tasks/example").exists()
    transactions = tmp_path / ".agent-workflow/task-transactions"
    assert not transactions.exists() or not list(transactions.glob("*.json"))
    replay = json.loads(
        (tmp_path / ".agent-workflow/local/approval-replay.json").read_text()
    )
    assert replay["entries"] == {}

