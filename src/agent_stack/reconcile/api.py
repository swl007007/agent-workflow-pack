"""Frozen Renderer/Reconciler public API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from agent_stack.core.api import DesiredStateIR, SavedPlanEnvelope, TaskSnapshotAndFindings
from .models import FileState, LifecycleJournal, StagedFile, StagedRenderTree
from .ports import TaskQuiescenceScannerPort
from .render import render


RECONCILE_INTERFACE_VERSION: Final = 1
PUBLIC_MODELS: Final = (FileState, LifecycleJournal, StagedFile, StagedRenderTree)


def plan_reconcile(
    ir: DesiredStateIR,
    staged: StagedRenderTree,
    manifest: Mapping[str, object] | None,
    observed: Mapping[str, object],
    task_snapshot: TaskSnapshotAndFindings,
) -> SavedPlanEnvelope:
    raise NotImplementedError("reconcile planning is not implemented yet")


def apply_plan(
    saved_plan: SavedPlanEnvelope,
    approval: Mapping[str, object] | None = None,
    *,
    scanner: TaskQuiescenceScannerPort | None = None,
) -> Mapping[str, object]:
    raise NotImplementedError("reconcile apply is not implemented yet")


def recover_transaction(transaction_id: str, action: str) -> Mapping[str, object]:
    raise NotImplementedError("reconcile recovery is not implemented yet")


__all__ = [
    "FileState",
    "LifecycleJournal",
    "PUBLIC_MODELS",
    "RECONCILE_INTERFACE_VERSION",
    "StagedFile",
    "StagedRenderTree",
    "TaskQuiescenceScannerPort",
    "apply_plan",
    "plan_reconcile",
    "recover_transaction",
    "render",
]
