"""Thin command-to-owner composition."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from .parser import CommandInvocation
from .redaction import sanitize_document

if TYPE_CHECKING:
    from agent_stack.release.distribution import (
        UpgradePorts,
        UpgradeRecoveryPorts,
        UpgradeRecoveryRequest,
        UpgradeRequest,
    )


OWNER_MATRIX: Final = MappingProxyType(
    {
        "bootstrap": "providers",
        "init": "reconcile",
        "sync": "reconcile",
        "upgrade": "lifecycle",
        "doctor": "lifecycle",
        "test-routing": "route",
        "recover": "reconcile",
        "workspace-register": "runtime",
        "workspace-migrate": "runtime",
        "route-decide": "route",
        "task-runtime-load": "runtime",
        "task-admit": "runtime",
        "task-claim": "runtime",
        "task-transition": "runtime",
        "task-release": "runtime",
        "task-archive": "runtime",
        "task-recover": "runtime",
    }
)


@dataclass(frozen=True)
class OwnerBinding:
    owner: str
    invoke: Callable[[object], object]


@dataclass(frozen=True)
class VerifiedRuntimeContext:
    owner_bindings: Mapping[str, OwnerBinding]
    owner_payloads: Mapping[str, object]
    repository_root: Path | None = None
    workspace_diagnostic: object | None = None


@dataclass(frozen=True)
class CLIResult:
    command: str
    status: str
    exit_code: int
    result: object | None
    workspace_diagnostic: object | None
    errors: tuple[Mapping[str, object], ...]
    warnings: tuple[Mapping[str, object], ...]

    @classmethod
    def success(
        cls,
        *,
        command: str,
        result: object,
        repository_root: Path | None = None,
        workspace_diagnostic: object | None = None,
    ) -> CLIResult:
        return cls(
            command=command,
            status="success",
            exit_code=0,
            result=sanitize_document(result, repository_root=repository_root),
            workspace_diagnostic=sanitize_document(
                workspace_diagnostic, repository_root=repository_root
            ),
            errors=(),
            warnings=(),
        )

    @classmethod
    def failure(
        cls,
        *,
        command: str,
        failure: Mapping[str, object],
        repository_root: Path | None = None,
        workspace_diagnostic: object | None = None,
    ) -> CLIResult:
        sanitized = sanitize_document(failure, repository_root=repository_root)
        assert isinstance(sanitized, dict)
        exit_code = int(sanitized.get("exit_code", 70))
        return cls(
            command=command,
            status="blocked" if exit_code in {20, 21, 22, 23, 40} else "error",
            exit_code=exit_code,
            result=None,
            workspace_diagnostic=sanitize_document(
                workspace_diagnostic, repository_root=repository_root
            ),
            errors=(sanitized,),
            warnings=(),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.cli-result",
            "schema_version": 1,
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "result": self.result,
            "workspace_diagnostic": self.workspace_diagnostic,
            "errors": [dict(error) for error in self.errors],
            "warnings": [dict(warning) for warning in self.warnings],
        }


def _internal_failure(code: str, message: str, **details: object) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.cli-diagnostic",
        "schema_version": 1,
        "code": code,
        "exit_code": 70,
        "message": message,
        "details": details,
    }


def _failure_document(error: Exception, *, debug: bool) -> Mapping[str, object]:
    projector = getattr(error, "to_document", None)
    if callable(projector):
        projected = projector()
        if isinstance(projected, Mapping):
            return projected
    details: dict[str, object] = {}
    if debug:
        details["exception_type"] = type(error).__name__
    return _internal_failure("AWP_CLI_INTERNAL", "unexpected internal error", **details)


def compose_lifecycle_command(
    invocation: CommandInvocation, runtime_context: VerifiedRuntimeContext
) -> CLIResult:
    """Delegate one closed invocation to its verified semantic owner."""

    expected_owner = OWNER_MATRIX.get(invocation.command)
    binding = runtime_context.owner_bindings.get(invocation.command)
    if expected_owner is None or binding is None:
        return CLIResult.failure(
            command=invocation.command,
            failure=_internal_failure(
                "AWP_CLI_OWNER_UNAVAILABLE", "verified command owner is unavailable"
            ),
            repository_root=runtime_context.repository_root,
            workspace_diagnostic=runtime_context.workspace_diagnostic,
        )
    if binding.owner != expected_owner:
        return CLIResult.failure(
            command=invocation.command,
            failure=_internal_failure(
                "AWP_CLI_OWNER_MISMATCH",
                "verified command owner does not match the frozen matrix",
                expected_owner=expected_owner,
                actual_owner=binding.owner,
            ),
            repository_root=runtime_context.repository_root,
            workspace_diagnostic=runtime_context.workspace_diagnostic,
        )
    try:
        value = binding.invoke(runtime_context.owner_payloads.get(invocation.command))
    except Exception as error:  # Domain errors are projected without reclassification.
        return CLIResult.failure(
            command=invocation.command,
            failure=_failure_document(error, debug=invocation.debug),
            repository_root=runtime_context.repository_root,
            workspace_diagnostic=runtime_context.workspace_diagnostic,
        )
    return CLIResult.success(
        command=invocation.command,
        result=value,
        repository_root=runtime_context.repository_root,
        workspace_diagnostic=runtime_context.workspace_diagnostic,
    )


def bind_upgrade_command(request: UpgradeRequest, ports: UpgradePorts) -> OwnerBinding:
    """Bind Task 5's lifecycle orchestrator without changing its domain results."""

    from agent_stack.release.distribution import orchestrate_upgrade

    return OwnerBinding(owner="lifecycle", invoke=lambda _: orchestrate_upgrade(request, ports))


def bind_upgrade_recovery_command(
    request: UpgradeRecoveryRequest, ports: UpgradeRecoveryPorts
) -> OwnerBinding:
    """Bind exact lifecycle recovery selected by the journal runtime allowlist."""

    from agent_stack.release.distribution import recover_upgrade

    return OwnerBinding(owner="reconcile", invoke=lambda _: recover_upgrade(request, ports))
