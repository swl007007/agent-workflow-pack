"""Frozen Renderer/Reconciler public API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from agent_stack.core.api import DesiredStateIR, SavedPlanEnvelope, TaskSnapshotAndFindings
from agent_stack.providers.api import ProviderExecutionResult

from .models import FileState, LifecycleJournal, StagedFile, StagedRenderTree
from .ports import TaskQuiescenceScannerPort


RECONCILE_INTERFACE_VERSION: Final = 1
PUBLIC_MODELS: Final = (FileState, LifecycleJournal, StagedFile, StagedRenderTree)


def render(
    ir: DesiredStateIR,
    verified_provider_results: Sequence[ProviderExecutionResult],
) -> StagedRenderTree:
    raise NotImplementedError("deterministic renderer is not implemented yet")


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
