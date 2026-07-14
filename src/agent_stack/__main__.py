"""Public ``python -m agent_stack`` entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from .cli.dispatch import CLIResult, VerifiedRuntimeContext, compose_lifecycle_command
from .cli.output import render_cli_human, render_cli_json
from .cli.parser import CLIUsageError, parse_cli_args, parse_launcher_envelope
from .cli.production import compose_production_runtime_context
from .runtime.bootstrap import LauncherInvocation, bootstrap_project_runtime


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime_context: VerifiedRuntimeContext | None = None,
) -> int:
    try:
        raw_argv = tuple(sys.argv[1:] if argv is None else argv)
        launcher, public_argv = parse_launcher_envelope(raw_argv)
        invocation = parse_cli_args(public_argv)
    except CLIUsageError as error:
        result = CLIResult.failure(command="usage", failure=error.to_document())
        sys.stderr.write(render_cli_human(result) + "\n")
        return result.exit_code
    if launcher is not None:
        verified_launcher = bootstrap_project_runtime(
            LauncherInvocation(
                project_root=launcher.project_root,
                caller_context_version=launcher.caller_context_version,
                command=launcher.command,
                caller_fields=launcher.caller_fields,
            )
        )
        repository_root = verified_launcher.project_root
        caller_context_version = verified_launcher.caller_context_version
        caller_fields = verified_launcher.caller_fields
    else:
        repository_root = None
        caller_context_version = None
        caller_fields = None
    context = runtime_context or compose_production_runtime_context(
        invocation,
        repository_root=repository_root,
        caller_context_version=caller_context_version,
        caller_fields=caller_fields,
    )
    result = compose_lifecycle_command(invocation, context)
    if invocation.json_output:
        sys.stdout.write(render_cli_json(result) + "\n")
    else:
        sys.stdout.write(render_cli_human(result) + "\n")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
