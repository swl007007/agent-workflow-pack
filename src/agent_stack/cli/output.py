"""Human and canonical JSON projections of one CLI result."""

from __future__ import annotations

import json

from agent_stack.core.api import canonical_json_bytes

from .dispatch import CLIResult


def render_cli_json(result: CLIResult) -> str:
    return canonical_json_bytes(result.to_document()).decode("utf-8")


def render_cli_human(result: CLIResult) -> str:
    lines = [f"{result.command}: {result.status} (exit {result.exit_code})"]
    if result.result is not None:
        lines.append(json.dumps(result.result, ensure_ascii=False, sort_keys=True))
    for error in result.errors:
        lines.append(f"{error.get('code', 'AWP_CLI_INTERNAL')}: {error.get('message', '')}")
    return "\n".join(lines)
