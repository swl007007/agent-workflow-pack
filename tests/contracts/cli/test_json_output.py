from __future__ import annotations

import json
from pathlib import Path

from agent_stack.cli.dispatch import CLIResult
from agent_stack.cli.output import render_cli_human, render_cli_json


def test_json_output_is_exactly_one_closed_object_and_human_uses_same_result(
    tmp_path: Path,
) -> None:
    result = CLIResult.success(
        command="doctor",
        result={"manifest_path": tmp_path / "project" / "Manifest.json", "healthy": True},
        repository_root=tmp_path / "project",
        workspace_diagnostic={
            "workspace_state": {"primary_state_blocker": "AWP_WORKSPACE_MIGRATION_REQUIRED"},
            "command_admission": {"command": "doctor", "allowed": True, "blocker": None},
        },
    )

    rendered = render_cli_json(result)
    document = json.loads(rendered)

    assert rendered.count("\n") == 0
    assert document == result.to_document()
    assert document["result"]["manifest_path"] == "Manifest.json"
    assert document["workspace_diagnostic"]["workspace_state"]["primary_state_blocker"]
    assert document["workspace_diagnostic"]["command_admission"]["allowed"] is True
    human = render_cli_human(result)
    assert "doctor: success" in human
    assert "Manifest.json" in human


def test_error_output_preserves_imported_code_and_exit_category() -> None:
    result = CLIResult.failure(
        command="sync",
        failure={
            "schema_id": "agent-workflow.renderer-failure",
            "schema_version": 1,
            "code": "AWP_TASK_QUIESCENCE_CHANGED",
            "exit_code": 40,
            "message": "task evidence changed",
            "details": {"latest_findings": ["AWP_WORKSPACE_ACTIVE_TASK_BLOCK"]},
        },
    )

    document = json.loads(render_cli_json(result))

    assert document["status"] == "blocked"
    assert document["exit_code"] == 40
    assert document["errors"][0]["code"] == "AWP_TASK_QUIESCENCE_CHANGED"
    assert document["errors"][0]["details"]["latest_findings"] == [
        "AWP_WORKSPACE_ACTIVE_TASK_BLOCK"
    ]
