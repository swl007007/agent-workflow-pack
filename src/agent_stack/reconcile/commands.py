"""Production Reconciler command handlers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.cli.production import ProductionCommand, _authorize_running_release
from agent_stack.release.manifest import VerifiedRelease

from .errors import RendererFailure
from .production_bundle import load_production_bundle
from .production import compose_init, compose_sync


def _data_root() -> Path:
    return Path(str(files("agent_stack").joinpath("data")))


def _planned_paths() -> list[str]:
    bundle = load_production_bundle(_data_root())
    paths: list[str] = []
    for definition in bundle.artifact_definitions:
        targets = definition.get("targets")
        if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)):
            raise RendererFailure(
                "AWP_OWNERSHIP_CONFLICT", "packaged artifact targets are invalid"
            )
        for target in targets:
            if not isinstance(target, Mapping) or not isinstance(target.get("path"), str):
                raise RendererFailure(
                    "AWP_OWNERSHIP_CONFLICT", "packaged artifact target is invalid"
                )
            paths.append(str(target["path"]))
    return sorted(paths)


def _dry_run(command: ProductionCommand, operation: str) -> Mapping[str, object]:
    manifest = command.repository_root / ".agent-workflow/Manifest.json"
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.reconcile-preview",
            "schema_version": 1,
            "operation": operation,
            "dry_run": True,
            "initialized": manifest.is_file(),
            "planned_paths": _planned_paths(),
            "writes_performed": 0,
        }
    )


def run_init(payload: object) -> Mapping[str, object]:
    command = cast(ProductionCommand, payload)
    release = _authorize_running_release()
    if bool(command.invocation.options.get("dry_run")):
        return _dry_run(command, "init")
    return compose_init(
        command,
        cast(VerifiedRelease, release),
        apply=True,
        data_root=_data_root(),
    )


def run_sync(payload: object) -> Mapping[str, object]:
    command = cast(ProductionCommand, payload)
    release = cast(VerifiedRelease, _authorize_running_release())
    if bool(command.invocation.options.get("dry_run")):
        return compose_sync(
            command, release, apply=False, data_root=_data_root()
        )
    return compose_sync(
        command,
        release,
        apply=True,
        data_root=_data_root(),
    )


def run_recover(payload: object) -> object:
    from agent_stack.runtime.commands import _verified_project
    from agent_stack.runtime.workspace import recover_workspace_registration

    command = cast(ProductionCommand, payload)
    kind = command.invocation.options.get("journal_kind")
    transaction_id = command.invocation.options.get("journal_id")
    action = command.invocation.options.get("recovery_action")
    if not isinstance(transaction_id, str) or action not in {"resume", "rollback"}:
        raise RendererFailure(
            "AWP_RECONCILE_RECOVERY_REQUIRED", "recovery selection is invalid"
        )
    _verified_project(command)
    if kind == "workspace-registration":
        result = recover_workspace_registration(
            command.repository_root,
            transaction_id,
            action=action,
            bootstrap_lock_root=command.repository_root.parent / ".awp-bootstrap-locks",
        )
        return MappingProxyType(
            {
                "schema_id": "agent-workflow.recovery-result",
                "schema_version": 1,
                "journal_kind": kind,
                "transaction_id": transaction_id,
                "committed": result.committed,
            }
        )
    raise RendererFailure(
        "AWP_RECONCILE_RECOVERY_REQUIRED", "recovery journal kind is not yet bound"
    )
