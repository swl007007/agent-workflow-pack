from __future__ import annotations

from datetime import timedelta

import pytest

from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.task_service import (
    TaskClaimRequest,
    TaskReleaseRequest,
    TaskTransitionRequest,
    claim_task,
    release_task,
    transition_task,
)
from tests.integration.runtime.test_task_admission import (
    NOW,
    TASK_ID,
    admission_request,
    initialize_project,
)
from agent_stack.runtime.task_service import admit_task


def test_heavy_claim_serializes_and_requires_exact_release(tmp_path) -> None:
    initialize_project(tmp_path)
    admitted = admit_task(admission_request(tmp_path, route="speckit-superpowers"))
    claim_id = "de4d5ca7-2893-4b19-a011-72d5a0342e6e"
    claim = TaskClaimRequest(
        tmp_path,
        admitted.task_ref,
        TASK_ID,
        2,
        claim_id,
        "speckit-implement",
        "human-actor",
        NOW + timedelta(minutes=1),
    )

    claimed = claim_task(claim)

    assert claimed.state_revision == 3
    assert claimed.executor_claim is not None
    with pytest.raises(RuntimeFailure, match="AWP_TASK_STATE_STALE"):
        claim_task(claim)
    with pytest.raises(RuntimeFailure, match="AWP_TASK_TRANSITION_INVALID"):
        release_task(
            TaskReleaseRequest(
                tmp_path,
                admitted.task_ref,
                TASK_ID,
                3,
                claim_id,
                "other-actor",
                NOW + timedelta(minutes=2),
            )
        )

    released = release_task(
        TaskReleaseRequest(
            tmp_path,
            admitted.task_ref,
            TASK_ID,
            3,
            claim_id,
            "human-actor",
            NOW + timedelta(minutes=2),
        )
    )
    assert released.state_revision == 4
    assert released.executor_claim is None


def test_transition_out_of_implementation_rejects_live_claim_then_completes(tmp_path) -> None:
    initialize_project(tmp_path)
    admitted = admit_task(admission_request(tmp_path, route="speckit-superpowers"))
    claim_id = "ef5e6db8-39a4-4c2a-b122-83e6b1453f7f"
    claimed = claim_task(
        TaskClaimRequest(
            tmp_path,
            admitted.task_ref,
            TASK_ID,
            2,
            claim_id,
            "speckit-implement",
            "human-actor",
            NOW + timedelta(minutes=1),
        )
    )

    with pytest.raises(RuntimeFailure, match="unresolved executor claim"):
        transition_task(
            TaskTransitionRequest(
                tmp_path,
                admitted.task_ref,
                TASK_ID,
                claimed.state_revision,
                "implementation-verified",
                target_lifecycle_status="active",
                target_phase="verifying",
                completion_flags={"implementation": True, "verification": False},
                changed_at=NOW + timedelta(minutes=2),
            )
        )

    released = release_task(
        TaskReleaseRequest(
            tmp_path,
            admitted.task_ref,
            TASK_ID,
            claimed.state_revision,
            claim_id,
            "human-actor",
            NOW + timedelta(minutes=2),
        )
    )
    verifying = transition_task(
        TaskTransitionRequest(
            tmp_path,
            admitted.task_ref,
            TASK_ID,
            released.state_revision,
            "implementation-verified",
            target_lifecycle_status="active",
            target_phase="verifying",
            completion_flags={"implementation": True, "verification": False},
            changed_at=NOW + timedelta(minutes=3),
        )
    )
    completed = transition_task(
        TaskTransitionRequest(
            tmp_path,
            admitted.task_ref,
            TASK_ID,
            verifying.state_revision,
            "task-completed",
            target_lifecycle_status="completed",
            target_phase="finishing",
            completion_flags={"implementation": True, "verification": True},
            changed_at=NOW + timedelta(minutes=4),
        )
    )

    assert completed.lifecycle_status == "completed"
    assert completed.state_revision == 6


def test_trellis_native_cannot_claim_or_accept_heavy_phase(tmp_path) -> None:
    initialize_project(tmp_path)
    admitted = admit_task(admission_request(tmp_path))

    with pytest.raises(RuntimeFailure, match="AWP_TASK_TRANSITION_INVALID"):
        claim_task(
            TaskClaimRequest(
                tmp_path,
                admitted.task_ref,
                TASK_ID,
                2,
                "f06f7ec9-4ab5-4d3b-8233-94f7c2564080",
                "executor",
                "actor",
                NOW,
            )
        )
    with pytest.raises(RuntimeFailure, match="AWP_TASK_TRANSITION_INVALID"):
        transition_task(
            TaskTransitionRequest(
                tmp_path,
                admitted.task_ref,
                TASK_ID,
                2,
                "bad-heavy-phase",
                target_lifecycle_status="active",
                target_phase="implementing",
                completion_flags=None,
                changed_at=NOW,
            )
        )
