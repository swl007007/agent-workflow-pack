from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_stack.core.api import CANONICAL_NULL, canonical_json_bytes, digest
from agent_stack.reconcile.models import FileState
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.ports import bind_route_verifier_ports
from agent_stack.runtime.task_service import (
    MetadataMutation,
    TaskAdmissionRequest,
    TaskFile,
    admit_task,
)


PROJECT_ID = "4e3d0530-901a-4f65-8c41-5faf017026c4"
WORKSPACE_ID = "5f477c7f-a1dc-4a16-8f75-39f153170222"
TASK_ID = "6ea415f2-4823-4a36-9d25-cf00b82f1f70"
TRANSACTION_ID = "78d71641-c23d-45b3-aabb-1c7f4ad8c808"
APPROVAL_ID = "89f80752-d34e-46c4-bbcc-2d805be9d919"
DECISION_ID = "9a091863-e45f-47d5-8cdd-3e916cf0ea2a"
NOW = datetime(2026, 7, 13, 15, tzinfo=UTC)


def workflow_contract() -> dict[str, object]:
    return {
        "version": 1,
        "profile_digest_at_admission": "1" * 64,
        "lock_digest_at_admission": "2" * 64,
        "artifact_bundle_digest_at_admission": "3" * 64,
        "policy_digest_at_admission": "4" * 64,
        "adapter_id": "codex",
        "adapter_version_at_admission": "1.0.0",
        "route_contract_version": 1,
        "task_contract_surfaces": [
            {"surface_id": "platform-adapter:codex", "surface_digest": "5" * 64},
            {"surface_id": "runtime-control-plane", "surface_digest": "6" * 64},
            {"surface_id": "surface-registry", "surface_digest": "7" * 64},
        ],
    }


def route_decision(
    *,
    task_id: str = TASK_ID,
    task_ref: str = ".trellis/tasks/example",
    route: str = "trellis-native",
) -> dict[str, object]:
    surfaces = workflow_contract()["task_contract_surfaces"]
    return {
        "schema_id": "agent-workflow.route-decision",
        "schema_version": 1,
        "operation": "create-integrated-task",
        "route": route,
        "decision_id": DECISION_ID,
        "decision_digest": "a" * 64,
        "requested_task_id": task_id,
        "requested_task_ref": task_ref,
        "intent_id": "feature-intent-id",
        "intent_digest": "b" * 64,
        "approval_challenge": "c" * 64,
        "task_contract_surfaces_digest": digest("agent-workflow.task-surfaces.v1", surfaces),
    }


def approval_proof(
    *, task_id: str = TASK_ID, task_ref: str = ".trellis/tasks/example"
) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.approval-proof",
        "schema_version": 1,
        "operation": "create-integrated-task",
        "approval_id": APPROVAL_ID,
        "workspace_instance_id": WORKSPACE_ID,
        "task_id": task_id,
        "task_ref": task_ref,
        "route_decision_digest": "a" * 64,
        "approval_challenge": "c" * 64,
        "issued_at": "2026-07-13T14:59:00Z",
        "expires_at": "2026-07-13T15:05:00Z",
    }


class RecordingDecisionVerifier:
    def __init__(self, *, reject: bool = False) -> None:
        self.calls: list[tuple[Mapping[str, object], str]] = []
        self.reject = reject

    def __call__(self, decision, authorities, consumer):
        self.calls.append((authorities, consumer))
        if self.reject:
            raise RuntimeFailure("AWP_TASK_STATE_STALE", "decision is stale")
        return {**decision, "verification_kind": "verified-create-integrated-task"}


class RecordingApprovalVerifier:
    def __init__(self, *, reject: bool = False) -> None:
        self.calls: list[Mapping[str, object]] = []
        self.reject = reject

    def __call__(self, proof, decision, capability, runtime_context):
        self.calls.append(decision)
        if self.reject:
            raise RuntimeFailure("AWP_APPROVAL_REPLAY_BLOCKED", "receipt rejected")
        return {
            "schema_id": "agent-workflow.approval-verification-result",
            "schema_version": 1,
            "operation": "create-integrated-task",
            "approval_id": proof["approval_id"],
            "verifier_id": "platform-approval-verifier",
            "verifier_version": "1.0.0",
            "actor_id": "human-actor",
            "mechanism": "platform-user-confirmation",
            "validated_at": "2026-07-13T15:00:00Z",
            "proof_expires_at": proof["expires_at"],
        }


def initialize_project(root: Path) -> None:
    local = root / ".agent-workflow/local"
    local.mkdir(parents=True)
    (root / ".trellis/tasks/archive").mkdir(parents=True)
    replay = {
        "schema_id": "agent-workflow.approval-replay",
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "workspace_instance_id": WORKSPACE_ID,
        "entries": {},
    }
    path = local / "approval-replay.json"
    path.write_bytes(canonical_json_bytes(replay))
    os.chmod(path, 0o600)


def metadata_create(path: str = ".trellis/task-index.json") -> MetadataMutation:
    payload = canonical_json_bytes({"active": [TASK_ID]})
    return MetadataMutation(
        original=FileState(path, False, "absent", CANONICAL_NULL, CANONICAL_NULL, True),
        candidate=FileState(
            path,
            True,
            "regular",
            __import__("hashlib").sha256(payload).hexdigest(),
            "0644",
            True,
        ),
        original_bytes=None,
        candidate_bytes=payload,
    )


def admission_request(
    root: Path,
    *,
    task_id: str = TASK_ID,
    task_ref: str = ".trellis/tasks/example",
    route: str = "trellis-native",
    transaction_id: str = TRANSACTION_ID,
    decision_verifier: RecordingDecisionVerifier | None = None,
    approval_verifier: RecordingApprovalVerifier | None = None,
) -> TaskAdmissionRequest:
    decision = route_decision(task_id=task_id, task_ref=task_ref, route=route)
    proof = approval_proof(task_id=task_id, task_ref=task_ref)
    mode_state: Mapping[str, object]
    if route == "trellis-native":
        mode_state = {"task_ref": task_ref}
    else:
        mode_state = {
            "router_contract_version": 1,
            "phase": "implementing",
            "executor_claim": None,
            "authority": {"active_feature": "feature-id"},
            "canonical_artifacts": {},
            "reference_only_artifacts": [],
            "completion_flags": {"implementation": False, "verification": False},
        }
    return TaskAdmissionRequest(
        project_root=root,
        project_id=PROJECT_ID,
        workspace_instance_id=WORKSPACE_ID,
        transaction_id=transaction_id,
        decision=decision,
        approval_proof=proof,
        current_authorities={"workspace_instance_id": WORKSPACE_ID},
        capability={"schema_id": "agent-workflow.capability-manifest"},
        runtime_context={"platform": "codex"},
        workflow_contract=workflow_contract(),
        mode_state=mode_state,
        task_files=(TaskFile("README.md", b"# Task\n", "0644"),),
        metadata_mutations=(metadata_create(),),
        admitted_at=NOW,
        route_ports=bind_route_verifier_ports(
            decision_verifier or RecordingDecisionVerifier(),
            approval_verifier or RecordingApprovalVerifier(),
        ),
    )


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_admission_commits_only_after_metadata_and_consumes_proof(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    decision_verifier = RecordingDecisionVerifier()
    approval_verifier = RecordingApprovalVerifier()
    request = admission_request(
        tmp_path,
        decision_verifier=decision_verifier,
        approval_verifier=approval_verifier,
    )

    result = admit_task(request)

    integration = read_json(tmp_path / ".trellis/tasks/example/integration.yaml")
    assert result.lifecycle_status == "active"
    assert result.state_revision == 2
    assert integration["lifecycle"]["status"] == "active"
    assert integration["lifecycle"]["state_revision"] == 2
    assert read_json(tmp_path / ".trellis/task-index.json") == {"active": [TASK_ID]}
    journal = read_json(
        tmp_path / f".agent-workflow/task-transactions/{TRANSACTION_ID}.json"
    )
    assert journal["phase"] == "complete"
    replay = read_json(tmp_path / ".agent-workflow/local/approval-replay.json")
    assert list(replay["entries"].values())[0]["state"] == "consumed"
    assert decision_verifier.calls[0][1] == "task-admit"
    assert approval_verifier.calls


def test_journal_exists_before_replay_reservation(tmp_path: Path, monkeypatch) -> None:
    initialize_project(tmp_path)

    def crash(point: str) -> None:
        if point == "after_planned":
            raise RuntimeError("kill")

    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", crash)
    with pytest.raises(RuntimeError, match="kill"):
        admit_task(admission_request(tmp_path))

    journal = read_json(
        tmp_path / f".agent-workflow/task-transactions/{TRANSACTION_ID}.json"
    )
    replay = read_json(tmp_path / ".agent-workflow/local/approval-replay.json")
    assert journal["phase"] == "planned"
    assert replay["entries"] == {}
    assert not (tmp_path / ".trellis/tasks/example").exists()


def test_verifier_failure_and_duplicate_identity_fail_before_mutation(tmp_path: Path) -> None:
    initialize_project(tmp_path)
    rejecting = RecordingDecisionVerifier(reject=True)

    with pytest.raises(RuntimeFailure, match="AWP_TASK_STATE_STALE"):
        admit_task(admission_request(tmp_path, decision_verifier=rejecting))
    assert not (tmp_path / ".agent-workflow/task-transactions").exists()

    admit_task(admission_request(tmp_path))
    second_transaction = "ab1a2974-f560-48e6-9dee-4fa27d01fb3b"
    with pytest.raises(RuntimeFailure, match="AWP_TASK_REF_CONFLICT"):
        admit_task(
            admission_request(
                tmp_path,
                task_id="bc2b3a85-0671-49f7-8eff-50b38e120c4c",
                transaction_id=second_transaction,
            )
        )
    with pytest.raises(RuntimeFailure, match="AWP_TASK_ID_CONFLICT"):
        admit_task(
            admission_request(
                tmp_path,
                task_ref=".trellis/tasks/other",
                transaction_id="cd3c4b96-1782-4a08-9f00-61c49f231d5d",
            )
        )


def test_admitting_directory_is_not_returned_as_runnable(tmp_path: Path, monkeypatch) -> None:
    initialize_project(tmp_path)

    def crash(point: str) -> None:
        if point == "after_task_moved":
            raise RuntimeError("kill")

    monkeypatch.setattr("agent_stack.runtime.task_service._crash_at", crash)
    with pytest.raises(RuntimeError, match="kill"):
        admit_task(admission_request(tmp_path))

    integration = read_json(tmp_path / ".trellis/tasks/example/integration.yaml")
    assert integration["lifecycle"]["status"] == "admitting"
    assert integration["lifecycle"]["state_revision"] == 1
