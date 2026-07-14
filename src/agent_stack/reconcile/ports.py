"""Injected cross-feature ports used by the Reconciler component."""

from __future__ import annotations

from typing import Protocol

from agent_stack.core.api import (
    TaskSnapshotAndFindings,
    VerifiedDiscoverySchemas,
    VerifiedTrellisTaskLayout,
)


class TaskQuiescenceScannerPort(Protocol):
    def __call__(
        self,
        source_layout: VerifiedTrellisTaskLayout,
        target_layout: VerifiedTrellisTaskLayout,
        source_schemas: VerifiedDiscoverySchemas,
        target_schemas: VerifiedDiscoverySchemas,
    ) -> TaskSnapshotAndFindings: ...
