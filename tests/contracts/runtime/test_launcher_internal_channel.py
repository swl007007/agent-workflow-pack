from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.cli.parser import CLIUsageError, parse_launcher_envelope
from agent_stack.cli.parser import parse_cli_args
from agent_stack.cli.production import compose_production_runtime_context


def _envelope(root: Path) -> list[str]:
    return [
        "--bootstrap-project",
        str(root),
        "--caller-context-version",
        "1",
        "--caller-platform",
        "codex",
        "--caller-user-home",
        str(root.parent),
        "--caller-config-root",
        f"codex_home={root.parent}",
        "--caller-harness-executable",
        "/usr/bin/codex",
        "--caller-harness-version-probe-id",
        "codex-version-v1",
        "--caller-tty",
        "stdin=false,stdout=false,stderr=false,direct_confirmation_capable=false",
        "doctor",
        "--json",
    ]


def test_complete_launcher_envelope_is_stripped_before_public_parsing(
    tmp_path: Path,
) -> None:
    invocation, public = parse_launcher_envelope(_envelope(tmp_path))

    assert invocation is not None
    assert invocation.project_root == tmp_path.resolve()
    assert invocation.caller_context_version == 1
    assert invocation.caller_fields["platform"] == "codex"
    assert public == ("doctor", "--json")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda values: ["doctor", *values],
        lambda values: [*values[:2], "--bootstrap-project", values[1], *values[2:]],
        lambda values: [values[2], values[3], *values[:2], *values[4:]],
        lambda values: [*values[:4], "--caller-unknown", "x", *values[4:]],
        lambda values: [*values[:1], "relative", *values[2:]],
        lambda values: [*values[:5], "codex\nattack", *values[6:]],
        lambda values: [*values[:5], "x" * 4097, *values[6:]],
    ],
)
def test_reserved_channel_rejects_public_mixing_duplicates_and_unsafe_values(
    tmp_path: Path, mutate
) -> None:
    with pytest.raises(CLIUsageError, match="AWP_CLI_USAGE"):
        parse_launcher_envelope(mutate(_envelope(tmp_path)))


def test_normal_public_invocation_has_no_launcher_authority() -> None:
    invocation, public = parse_launcher_envelope(["doctor", "--json"])

    assert invocation is None
    assert public == ("doctor", "--json")


def test_verified_launcher_fields_are_bound_to_the_production_owner_payload(
    tmp_path: Path,
) -> None:
    launcher, public = parse_launcher_envelope(_envelope(tmp_path))
    assert launcher is not None
    invocation = parse_cli_args(public)

    context = compose_production_runtime_context(
        invocation,
        repository_root=launcher.project_root,
        caller_context_version=launcher.caller_context_version,
        caller_fields=launcher.caller_fields,
    )
    payload = context.owner_payloads["doctor"]

    assert payload.caller_context_version == 1
    assert payload.caller_fields == launcher.caller_fields
