"""Frozen Renderer/Reconciler public API."""

from __future__ import annotations

from typing import Final

from .apply import apply_plan
from .models import FileState, LifecycleJournal, StagedFile, StagedRenderTree
from .plan import plan_reconcile
from .ports import TaskQuiescenceScannerPort
from .recovery import recover_transaction
from .render import render


RECONCILE_INTERFACE_VERSION: Final = 1
PUBLIC_MODELS: Final = (FileState, LifecycleJournal, StagedFile, StagedRenderTree)


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
