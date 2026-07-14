"""Public ``python -m agent_stack`` entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from .cli.dispatch import CLIResult, VerifiedRuntimeContext, compose_lifecycle_command
from .cli.output import render_cli_human, render_cli_json
from .cli.parser import CLIUsageError, parse_cli_args
from .cli.production import compose_production_runtime_context


def main(
    argv: Sequence[str] | None = None,
    *,
    runtime_context: VerifiedRuntimeContext | None = None,
) -> int:
    try:
        invocation = parse_cli_args(argv)
    except CLIUsageError as error:
        result = CLIResult.failure(command="usage", failure=error.to_document())
        sys.stderr.write(render_cli_human(result) + "\n")
        return result.exit_code
    context = runtime_context or compose_production_runtime_context(invocation)
    result = compose_lifecycle_command(invocation, context)
    if invocation.json_output:
        sys.stdout.write(render_cli_json(result) + "\n")
    else:
        sys.stdout.write(render_cli_human(result) + "\n")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
