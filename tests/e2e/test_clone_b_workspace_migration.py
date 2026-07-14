from __future__ import annotations

from pathlib import Path

from tests.e2e import scenario_probe


def test_clone_b_executes_continuous_pull_gate_and_migration_sequence(
    tmp_path: Path,
) -> None:
    result = scenario_probe.clone_b_scenario(tmp_path)

    assert result["steps"] == [
        "static-source-verified",
        "registered",
        "source-only-active-blocked",
        "target-only-active-blocked",
        "active-task-blocked",
        "task-archived",
        "unfinished-transaction-blocked",
        "transaction-recovered-and-archived",
        "migration-crashed",
        "migration-recovered",
        "stale-evidence-rejected",
        "stale-migration-rolled-back",
        "doctor",
        "no-op-sync",
        "checkout-local",
    ]
    assert result["workspace_release_changed"] is True
    assert result["manifest_bytes_unchanged"] is True


def test_scanner_scope_is_checkout_local(tmp_path: Path) -> None:
    result = scenario_probe.clone_b_scenario(tmp_path)

    assert result["checkout_local_visibility"] is True
