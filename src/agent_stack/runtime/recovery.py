"""Public explicit task-transaction recovery entry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .task_service import TaskMutationResult, recover_task_transaction_internal


@dataclass(frozen=True)
class TaskRecoveryRequest:
    project_root: Path
    transaction_id: str
    action: str


def recover_task_transaction(request: TaskRecoveryRequest) -> TaskMutationResult:
    """Resume or roll back exactly one journal-selected task transaction."""

    return recover_task_transaction_internal(
        request.project_root, request.transaction_id, request.action
    )
