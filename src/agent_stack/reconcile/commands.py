"""Production Reconciler command handlers."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack._vendor import yaml
from agent_stack.cli.production import ProductionCommand, _authorize_running_release

from .errors import RendererFailure


def _data_root() -> Path:
    return Path(str(files("agent_stack").joinpath("data")))


def _planned_paths() -> list[str]:
    document = yaml.safe_load(  # type: ignore[no-untyped-call]
        (_data_root() / "artifact-definitions/platforms/codex.yaml").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(document, Mapping) or not isinstance(document.get("targets"), list):
        raise RendererFailure("AWP_OWNERSHIP_CONFLICT", "packaged artifact definition is invalid")
    paths = [str(target["path"]) for target in document["targets"] if isinstance(target, Mapping)]
    paths.extend(
        [
            ".agent-workflow/Manifest.json",
            ".agent-workflow/bin/agent-stack",
            ".agent-workflow/runtime-control.json",
        ]
    )
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
    _authorize_running_release()
    if bool(command.invocation.options.get("dry_run")):
        return _dry_run(command, "init")
    raise RendererFailure(
        "AWP_RECONCILE_RECOVERY_REQUIRED",
        "production init apply composition is not yet available",
    )


def run_sync(payload: object) -> Mapping[str, object]:
    command = cast(ProductionCommand, payload)
    if bool(command.invocation.options.get("dry_run")):
        return _dry_run(command, "sync")
    raise RendererFailure(
        "AWP_RECONCILE_RECOVERY_REQUIRED",
        "production sync apply composition is not yet available",
    )


def run_recover(payload: object) -> object:
    raise RendererFailure(
        "AWP_RECONCILE_RECOVERY_REQUIRED",
        "recovery requires a verified production journal binding",
    )
