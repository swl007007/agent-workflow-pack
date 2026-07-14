from __future__ import annotations

from pathlib import Path

from tests.e2e import scenario_probe


def test_clone_c_executes_continuous_relationship_diagnostic_sequence(
    tmp_path: Path,
) -> None:
    result = scenario_probe.clone_c_scenario(tmp_path)

    assert result["relationships"] == {
        "ahead": "ahead",
        "diverged": "diverged",
        "invalid": "unknown",
        "missing": "unknown",
        "migration-required": "migration-required",
    }
    assert result["blocked_exit_codes"] == {
        "ahead": 21,
        "diverged": 21,
        "invalid": 30,
        "missing": 21,
    }
    assert result["doctor_allowed_for_all"] is True
    assert result["blocked_commands_are_read_only_only"] is True
    assert result["workspace_state_is_command_independent"] is True
    assert result["unsupported_discovery_preserves_ahead"] is True
