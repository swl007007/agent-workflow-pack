from __future__ import annotations

from pathlib import Path

from tests.e2e import scenario_probe


def test_clone_a_executes_continuous_recovery_and_upgrade_sequence(
    tmp_path: Path,
) -> None:
    result = scenario_probe.clone_a_scenario(tmp_path)

    assert result["steps"] == [
        "registered",
        "doctor",
        "test-routing",
        "no-op-sync",
        "admission-recovered",
        "runtime-loaded",
        "drift-rejected",
        "repair-resumed",
        "completed-gates-upgrade",
        "archive-recovered",
        "ref-reused-with-new-uuid",
        "replacement-archived",
        "quiescent",
        "upgrade-complete",
    ]
    assert result["first_task_id"] != result["replacement_task_id"]
    assert result["protected_legacy_bytes_preserved"] is True
