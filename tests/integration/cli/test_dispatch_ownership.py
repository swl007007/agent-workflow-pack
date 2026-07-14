from __future__ import annotations

from types import MappingProxyType

import pytest

from agent_stack.cli.dispatch import (
    OWNER_MATRIX,
    OwnerBinding,
    VerifiedRuntimeContext,
    compose_lifecycle_command,
)
from agent_stack.cli.parser import CommandInvocation
from agent_stack.runtime.errors import RuntimeFailure


def invocation(command: str) -> CommandInvocation:
    return CommandInvocation(
        command=command,
        options=MappingProxyType({}),
        json_output=True,
        debug=False,
    )


@pytest.mark.parametrize("command", sorted(OWNER_MATRIX))
def test_every_command_delegates_once_to_its_frozen_owner(command: str) -> None:
    calls: list[object] = []
    binding = OwnerBinding(
        owner=OWNER_MATRIX[command],
        invoke=lambda payload: calls.append(payload) or {"delegated": command},
    )
    context = VerifiedRuntimeContext(
        owner_bindings=MappingProxyType({command: binding}),
        owner_payloads=MappingProxyType({command: {"payload": command}}),
    )

    result = compose_lifecycle_command(invocation(command), context)

    assert result.exit_code == 0
    assert result.result == {"delegated": command}
    assert calls == [{"payload": command}]


def test_dispatch_rejects_an_owner_binding_from_another_domain() -> None:
    context = VerifiedRuntimeContext(
        owner_bindings=MappingProxyType(
            {"task-admit": OwnerBinding(owner="route", invoke=lambda payload: payload)}
        ),
        owner_payloads=MappingProxyType({"task-admit": {}}),
    )

    result = compose_lifecycle_command(invocation("task-admit"), context)

    assert result.exit_code == 70
    assert result.errors[0]["code"] == "AWP_CLI_OWNER_MISMATCH"


def test_imported_domain_failure_is_preserved_without_reclassification() -> None:
    def fail(_: object) -> object:
        raise RuntimeFailure("AWP_WORKSPACE_ACTIVE_TASK_BLOCK", "active task")

    context = VerifiedRuntimeContext(
        owner_bindings=MappingProxyType(
            {"workspace-migrate": OwnerBinding(owner="runtime", invoke=fail)}
        ),
        owner_payloads=MappingProxyType({"workspace-migrate": {}}),
    )

    result = compose_lifecycle_command(invocation("workspace-migrate"), context)

    assert result.exit_code == 22
    assert result.errors[0]["code"] == "AWP_WORKSPACE_ACTIVE_TASK_BLOCK"
    assert result.errors[0]["schema_id"] == "agent-workflow.runtime-failure"
