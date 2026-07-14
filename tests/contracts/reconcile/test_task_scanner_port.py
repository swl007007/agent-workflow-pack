from __future__ import annotations

import inspect
import subprocess
import sys
from types import MappingProxyType

from agent_stack.core.api import (
    TaskSnapshotAndFindings,
    VerifiedDiscoverySchemas,
    VerifiedTrellisTaskLayout,
)
from agent_stack.reconcile.ports import TaskQuiescenceScannerPort


class ScannerFake:
    def __init__(self, result: TaskSnapshotAndFindings) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []

    def __call__(
        self,
        source_layout: VerifiedTrellisTaskLayout,
        target_layout: VerifiedTrellisTaskLayout,
        source_schemas: VerifiedDiscoverySchemas,
        target_schemas: VerifiedDiscoverySchemas,
    ) -> TaskSnapshotAndFindings:
        self.calls.append((source_layout, target_layout, source_schemas, target_schemas))
        return self.result


def test_scanner_port_uses_the_exact_core_frozen_signature() -> None:
    signature = inspect.signature(TaskQuiescenceScannerPort.__call__)
    assert tuple(signature.parameters) == (
        "self",
        "source_layout",
        "target_layout",
        "source_schemas",
        "target_schemas",
    )
    assert signature.return_annotation == "TaskSnapshotAndFindings"


def test_contract_fake_records_all_four_inputs_without_runtime_import() -> None:
    result = TaskSnapshotAndFindings(
        snapshot=MappingProxyType({"schema_id": "agent-workflow.task-quiescence-snapshot"}),
        findings=MappingProxyType({"schema_id": "agent-workflow.task-findings"}),
        task_quiescence_digest="a" * 64,
    )
    schemas = VerifiedDiscoverySchemas(
        schema_bundle_digest="b" * 64,
        normalized=MappingProxyType({"schemas": []}),
    )
    layout = object.__new__(VerifiedTrellisTaskLayout)
    fake: TaskQuiescenceScannerPort = ScannerFake(result)

    assert fake(layout, layout, schemas, schemas) is result
    assert len(fake.calls) == 1
    isolated = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.dont_write_bytecode = True; "
            "import agent_stack.reconcile.ports; "
            "assert not any(name.startswith('agent_stack.runtime') for name in sys.modules)",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert isolated.returncode == 0, isolated.stderr
