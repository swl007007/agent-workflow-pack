from __future__ import annotations

import pytest

from agent_stack.cli.parser import CLIUsageError, parse_cli_args


@pytest.mark.parametrize(
    ("argv", "command", "expected"),
    [
        (["bootstrap"], "bootstrap", {}),
        (["init", "--dry-run"], "init", {"dry_run": True}),
        (["sync"], "sync", {"repair": False}),
        (["sync", "--repair", "--dry-run"], "sync", {"repair": True, "dry_run": True}),
        (["upgrade"], "upgrade", {"target": None}),
        (["upgrade", "--to", "0.2.0"], "upgrade", {"target": "0.2.0"}),
        (["doctor"], "doctor", {"write_probe": False}),
        (["doctor", "--write-probe"], "doctor", {"write_probe": True}),
        (["test-routing"], "test-routing", {}),
        (
            ["recover", "--transaction", "tx-1", "--resume"],
            "recover",
            {"journal_kind": "lifecycle", "journal_id": "tx-1", "recovery_action": "resume"},
        ),
        (["workspace", "register"], "workspace-register", {}),
        (["workspace", "migrate"], "workspace-migrate", {}),
        (["route", "decide"], "route-decide", {}),
        (
            [
                "task",
                "runtime",
                "load",
                "--task-ref",
                "task-a",
                "--task-id",
                "id-a",
                "--revision",
                "3",
                "--phase",
                "implementing",
                "--claim",
                "worker-a",
                "--surface",
                "runtime-entry:heavy-development-router",
                "--entry",
                "heavy-development-router",
            ],
            "task-runtime-load",
            {"revision": 3, "phase": "implementing"},
        ),
        (["task", "admit", "--task-ref", "task-a"], "task-admit", {"task_ref": "task-a"}),
        (
            ["task", "claim", "--task-ref", "task-a", "--revision", "1", "--executor", "w1"],
            "task-claim",
            {"revision": 1, "executor": "w1"},
        ),
        (
            [
                "task",
                "transition",
                "--task-ref",
                "task-a",
                "--revision",
                "2",
                "--to",
                "completed",
            ],
            "task-transition",
            {"revision": 2, "target_status": "completed"},
        ),
        (
            ["task", "release", "--task-ref", "task-a", "--revision", "3", "--executor", "w1"],
            "task-release",
            {"revision": 3, "executor": "w1"},
        ),
        (["task", "archive", "--task-ref", "task-a", "--revision", "4"], "task-archive", {"revision": 4}),
        (
            ["task", "recover", "--transaction", "tx-2", "--rollback"],
            "task-recover",
            {"transaction_id": "tx-2", "recovery_action": "rollback"},
        ),
    ],
)
def test_parser_produces_one_closed_command_branch(
    argv: list[str], command: str, expected: dict[str, object]
) -> None:
    invocation = parse_cli_args([*argv, "--json"])

    assert invocation.command == command
    assert invocation.json_output is True
    for key, value in expected.items():
        assert invocation.options[key] == value


@pytest.mark.parametrize(
    "argv",
    [
        ["doctor", "--to", "0.2.0"],
        ["sync", "--write-probe"],
        ["recover", "--transaction", "tx", "--resume", "--rollback"],
        ["recover", "--resume"],
        ["task", "runtime", "load", "--task-ref", "task-a"],
        ["doctor", "--bootstrap-project", "/tmp/forged"],
        ["route", "decide", "--caller-platform", "forged"],
        ["unknown"],
    ],
)
def test_parser_rejects_unknown_cross_branch_or_reserved_arguments(argv: list[str]) -> None:
    with pytest.raises(CLIUsageError) as caught:
        parse_cli_args(argv)

    assert caught.value.exit_code == 2
    assert caught.value.code == "AWP_CLI_USAGE"
