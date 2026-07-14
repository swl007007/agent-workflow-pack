"""Closed public command parser with no domain policy."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Never, Sequence

class CLIUsageError(ValueError):
    """A parser failure with the frozen usage exit category."""

    code: Final = "AWP_CLI_USAGE"
    exit_code: Final = 2

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.cli-diagnostic",
            "schema_version": 1,
            "code": self.code,
            "exit_code": self.exit_code,
            "message": self.message,
            "details": {},
        }


class _ClosedParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CLIUsageError(message)


@dataclass(frozen=True)
class CommandInvocation:
    command: str
    options: MappingProxyType[str, object]
    json_output: bool
    debug: bool


@dataclass(frozen=True)
class LauncherEnvelope:
    project_root: Path
    caller_context_version: int
    command: tuple[str, ...]
    caller_fields: MappingProxyType[str, str]


_RESERVED_PREFIXES = ("--bootstrap-", "--caller-")


def _internal_value(value: str, field: str) -> str:
    if not value or len(value) > 4096 or any(ord(character) < 32 for character in value):
        raise CLIUsageError(f"launcher {field} is invalid")
    return value


def _absolute_path(value: str, field: str, *, must_exist: bool = False) -> Path:
    raw = _internal_value(value, field)
    path = Path(raw)
    if not path.is_absolute() or os.path.normpath(raw) != raw:
        raise CLIUsageError(f"launcher {field} must be a normalized absolute path")
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise CLIUsageError(f"launcher {field} is unavailable") from error
        if resolved != path or not resolved.is_dir():
            raise CLIUsageError(f"launcher {field} is not a real normalized directory")
    return path


def parse_launcher_envelope(
    argv: Sequence[str],
) -> tuple[LauncherEnvelope | None, tuple[str, ...]]:
    """Validate and strip the reserved launcher prefix before public argparse."""

    values = tuple(argv)
    reserved_positions = [
        index
        for index, value in enumerate(values)
        if value.startswith(_RESERVED_PREFIXES)
    ]
    if not reserved_positions:
        return None, values
    if not values or values[0] != "--bootstrap-project":
        raise CLIUsageError("reserved launcher arguments require a complete prefix envelope")

    index = 0

    def take(name: str) -> str:
        nonlocal index
        if index + 1 >= len(values) or values[index] != name:
            raise CLIUsageError(f"launcher envelope expected {name}")
        value = _internal_value(values[index + 1], name.removeprefix("--"))
        index += 2
        return value

    project_root = _absolute_path(
        take("--bootstrap-project"), "bootstrap-project", must_exist=True
    )
    version = take("--caller-context-version")
    if version != "1":
        raise CLIUsageError("launcher caller-context-version is unsupported")
    platform = take("--caller-platform")
    if platform not in {"codex", "claude", "opencode", "unknown"}:
        raise CLIUsageError("launcher caller-platform is unsupported")
    user_home = _absolute_path(take("--caller-user-home"), "caller-user-home")

    caller_fields: dict[str, str] = {
        "platform": platform,
        "user_home": str(user_home),
    }
    if index < len(values) and values[index] == "--caller-config-root":
        config = take("--caller-config-root")
        if "=" not in config:
            raise CLIUsageError("launcher caller-config-root is invalid")
        config_id, config_path = config.split("=", 1)
        if config_id not in {"codex_home", "claude_home", "opencode_home"}:
            raise CLIUsageError("launcher caller-config-root identity is unsupported")
        caller_fields[f"config_root.{config_id}"] = str(
            _absolute_path(config_path, "caller-config-root")
        )
    if index < len(values) and values[index] == "--caller-harness-executable":
        caller_fields["harness_executable"] = str(
            _absolute_path(
                take("--caller-harness-executable"),
                "caller-harness-executable",
            )
        )
        caller_fields["harness_version_probe_id"] = take(
            "--caller-harness-version-probe-id"
        )
    caller_fields["tty"] = take("--caller-tty")
    public = values[index:]
    if not public:
        raise CLIUsageError("launcher envelope lacks a public command")
    if any(value.startswith(_RESERVED_PREFIXES) for value in public):
        raise CLIUsageError("reserved launcher argument appears in the public command")
    return (
        LauncherEnvelope(
            project_root=project_root,
            caller_context_version=1,
            command=public,
            caller_fields=MappingProxyType(caller_fields),
        ),
        public,
    )


def _leaf(
    subparsers: argparse._SubParsersAction[_ClosedParser], name: str
) -> _ClosedParser:
    parser = subparsers.add_parser(name)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--debug", action="store_true")
    return parser


def _dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")


def _task_ref(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-ref", required=True)


def _revision(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--revision", required=True, type=int)


def _recovery_action(parser: argparse.ArgumentParser) -> None:
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--resume", action="store_const", const="resume", dest="recovery_action")
    action.add_argument(
        "--rollback", action="store_const", const="rollback", dest="recovery_action"
    )


def build_parser() -> _ClosedParser:
    parser = _ClosedParser(prog="agent-stack", add_help=True)
    commands = parser.add_subparsers(dest="_root_command", required=True)

    _leaf(commands, "bootstrap").set_defaults(command="bootstrap")

    init = _leaf(commands, "init")
    _dry_run(init)
    init.set_defaults(command="init")

    sync = _leaf(commands, "sync")
    sync.add_argument("--repair", action="store_true")
    _dry_run(sync)
    sync.set_defaults(command="sync")

    upgrade = _leaf(commands, "upgrade")
    upgrade.add_argument("--to", dest="target")
    _dry_run(upgrade)
    upgrade.set_defaults(command="upgrade")

    doctor = _leaf(commands, "doctor")
    doctor.add_argument("--write-probe", action="store_true", dest="write_probe")
    doctor.set_defaults(command="doctor")

    _leaf(commands, "test-routing").set_defaults(command="test-routing")

    recover = _leaf(commands, "recover")
    journal = recover.add_mutually_exclusive_group(required=True)
    journal.add_argument("--transaction", dest="journal_id")
    journal.add_argument("--probe", dest="probe_id")
    journal.add_argument("--workspace-registration", dest="workspace_registration_id")
    journal.add_argument("--workspace-migration", dest="workspace_migration_id")
    _recovery_action(recover)
    recover.set_defaults(command="recover")

    workspace = commands.add_parser("workspace")
    workspace_commands = workspace.add_subparsers(dest="_workspace_command", required=True)
    _leaf(workspace_commands, "register").set_defaults(command="workspace-register")
    _leaf(workspace_commands, "migrate").set_defaults(command="workspace-migrate")

    route = commands.add_parser("route")
    route_commands = route.add_subparsers(dest="_route_command", required=True)
    _leaf(route_commands, "decide").set_defaults(command="route-decide")

    task = commands.add_parser("task")
    task_commands = task.add_subparsers(dest="_task_command", required=True)

    runtime = task_commands.add_parser("runtime")
    runtime_commands = runtime.add_subparsers(dest="_runtime_command", required=True)
    load = _leaf(runtime_commands, "load")
    _task_ref(load)
    load.add_argument("--task-id", required=True)
    _revision(load)
    load.add_argument("--phase", required=True)
    load.add_argument("--claim", required=True)
    load.add_argument("--surface", required=True)
    load.add_argument("--entry", required=True)
    load.set_defaults(command="task-runtime-load")

    admit = _leaf(task_commands, "admit")
    _task_ref(admit)
    admit.set_defaults(command="task-admit")

    claim = _leaf(task_commands, "claim")
    _task_ref(claim)
    _revision(claim)
    claim.add_argument("--executor", required=True)
    claim.set_defaults(command="task-claim")

    transition = _leaf(task_commands, "transition")
    _task_ref(transition)
    _revision(transition)
    transition.add_argument("--to", required=True, dest="target_status")
    transition.set_defaults(command="task-transition")

    release = _leaf(task_commands, "release")
    _task_ref(release)
    _revision(release)
    release.add_argument("--executor", required=True)
    release.set_defaults(command="task-release")

    archive = _leaf(task_commands, "archive")
    _task_ref(archive)
    _revision(archive)
    archive.set_defaults(command="task-archive")

    task_recover = _leaf(task_commands, "recover")
    task_recover.add_argument("--transaction", required=True, dest="transaction_id")
    _recovery_action(task_recover)
    task_recover.set_defaults(command="task-recover")
    return parser


def parse_cli_args(argv: Sequence[str] | None = None) -> CommandInvocation:
    namespace = vars(build_parser().parse_args(argv))
    command = str(namespace.pop("command"))
    json_output = bool(namespace.pop("json_output", False))
    debug = bool(namespace.pop("debug", False))
    namespace = {key: value for key, value in namespace.items() if not key.startswith("_")}
    if command == "recover":
        for kind, key in (
            ("lifecycle", "journal_id"),
            ("probe", "probe_id"),
            ("workspace-registration", "workspace_registration_id"),
            ("workspace-migration", "workspace_migration_id"),
        ):
            value = namespace.pop(key, None)
            if value is not None:
                namespace["journal_kind"] = kind
                namespace["journal_id"] = value
                break
    return CommandInvocation(
        command=command,
        options=MappingProxyType(namespace),
        json_output=json_output,
        debug=debug,
    )
