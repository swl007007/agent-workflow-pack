from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_stack.core.api import canonical_json_bytes
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.runtime_load import load_task_runtime
from tests.integration.runtime.test_runtime_load import load_case


def test_integration_change_during_bundle_construction_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    request, _, integration = load_case(tmp_path)

    def race(point: str) -> None:
        if point == "after-unit-reads":
            document = json.loads(integration.read_text())
            document["lifecycle"]["state_revision"] = 3
            integration.write_bytes(canonical_json_bytes(document))

    monkeypatch.setattr("agent_stack.runtime.runtime_load._race_check", race)
    with pytest.raises(RuntimeFailure, match="AWP_TASK_STATE_STALE"):
        load_task_runtime(request)


def test_runtime_unit_change_during_bundle_construction_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    request, units, _ = load_case(tmp_path)
    entry = units["runtime-entry:trellis-implement"][0]

    def race(point: str) -> None:
        if point == "after-unit-reads":
            entry.write_bytes(b"raced\n")

    monkeypatch.setattr("agent_stack.runtime.runtime_load._race_check", race)
    with pytest.raises(RuntimeFailure, match="AWP_TASK_SURFACE_MISMATCH"):
        load_task_runtime(request)


def test_runtime_load_rejects_unfinished_task_transaction(tmp_path: Path) -> None:
    request, _, _ = load_case(tmp_path)
    transaction_root = request.project_root / ".agent-workflow/task-transactions"
    transaction_root.mkdir(parents=True)
    (transaction_root / "not-a-journal").write_text("blocked")

    with pytest.raises(RuntimeFailure, match="AWP_TASK_TRANSACTION_RECOVERY_REQUIRED"):
        load_task_runtime(request)
