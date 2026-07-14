"""Production-only composition root for the installed console entry point."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

from .dispatch import OWNER_MATRIX, OwnerBinding, VerifiedRuntimeContext
from .parser import CommandInvocation


@dataclass(frozen=True)
class ProductionCommand:
    """One parsed console invocation bound to its normalized repository root."""

    invocation: CommandInvocation
    repository_root: Path
    caller_context_version: int | None = None
    caller_fields: Mapping[str, str] | None = None


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _package_data_root() -> Path:
    root = files("agent_stack").joinpath("data")
    path = Path(str(root))
    if not path.is_dir():
        raise RuntimeError("installed package data root is unavailable")
    return path


def _authorize_running_release() -> object:
    from agent_stack._vendor import yaml
    from agent_stack.release.manifest import (
        discover_release_locator,
        verify_release_manifest,
    )
    from agent_stack.release.trust import PackagedTrustPolicy

    policy_document = yaml.safe_load(  # type: ignore[no-untyped-call]
        (_package_data_root() / "release/trust-policy.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(policy_document, Mapping):
        raise RuntimeError("packaged trust policy is invalid")
    policy = PackagedTrustPolicy.from_document(policy_document)
    version = importlib.metadata.version("agent-workflow-pack")
    locator = discover_release_locator(version, policy)
    return verify_release_manifest(locator, policy)


def _bootstrap(payload: object) -> Mapping[str, object]:
    command = cast(ProductionCommand, payload)
    _authorize_running_release()
    data_root = _package_data_root()
    required = (
        "release/trust-policy.yaml",
        "catalog/platforms.yaml",
        "catalog/route-policy.yaml",
        "schemas/release/release-manifest.v1.json",
        "runtime-launcher/agent-stack.sh.tmpl",
    )
    inventory: list[dict[str, str]] = []
    for relative in required:
        path = data_root / relative
        if not path.is_file():
            raise RuntimeError(f"required packaged bootstrap input is missing: {relative}")
        inventory.append({"path": relative, "sha256": _sha256(path)})
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.bootstrap-result",
            "schema_version": 1,
            "repository_root": str(command.repository_root),
            "packaged_inputs": inventory,
            "acquired_components": [],
            "cache_status": "ready",
        }
    )


def _lazy(module: str, name: str) -> Callable[[object], object]:
    def invoke(payload: object) -> object:
        loaded = importlib.import_module(module)
        implementation = getattr(loaded, name)
        return cast(Callable[[object], object], implementation)(payload)

    return invoke


_IMPLEMENTATIONS: Final = MappingProxyType(
    {
        "bootstrap": _bootstrap,
        "init": _lazy("agent_stack.reconcile.commands", "run_init"),
        "sync": _lazy("agent_stack.reconcile.commands", "run_sync"),
        "upgrade": _lazy("agent_stack.release.commands", "run_upgrade"),
        "doctor": _lazy("agent_stack.release.commands", "run_doctor"),
        "test-routing": _lazy("agent_stack.route.commands", "run_test_routing"),
        "recover": _lazy("agent_stack.reconcile.commands", "run_recover"),
        "workspace-register": _lazy("agent_stack.runtime.commands", "run_workspace_register"),
        "workspace-migrate": _lazy("agent_stack.runtime.commands", "run_workspace_migrate"),
        "route-decide": _lazy("agent_stack.route.commands", "run_route_decide"),
        "task-runtime-load": _lazy("agent_stack.runtime.commands", "run_task_runtime_load"),
        "task-admit": _lazy("agent_stack.runtime.commands", "run_task_admit"),
        "task-claim": _lazy("agent_stack.runtime.commands", "run_task_claim"),
        "task-transition": _lazy("agent_stack.runtime.commands", "run_task_transition"),
        "task-release": _lazy("agent_stack.runtime.commands", "run_task_release"),
        "task-archive": _lazy("agent_stack.runtime.commands", "run_task_archive"),
        "task-recover": _lazy("agent_stack.runtime.commands", "run_task_recover"),
    }
)


def production_owner_bindings() -> Mapping[str, OwnerBinding]:
    """Return the complete, non-empty production binding registry."""

    if set(_IMPLEMENTATIONS) != set(OWNER_MATRIX):
        raise RuntimeError("production command registry differs from the owner matrix")
    return MappingProxyType(
        {
            command: OwnerBinding(owner=OWNER_MATRIX[command], invoke=implementation)
            for command, implementation in _IMPLEMENTATIONS.items()
        }
    )


def compose_production_runtime_context(
    invocation: CommandInvocation,
    *,
    repository_root: Path | None = None,
    caller_context_version: int | None = None,
    caller_fields: Mapping[str, str] | None = None,
) -> VerifiedRuntimeContext:
    """Bind a real parsed console invocation to the production registry."""

    root = (repository_root or Path.cwd()).resolve(strict=True)
    if (caller_context_version is None) != (caller_fields is None):
        raise RuntimeError("production caller envelope is incomplete")
    payload = ProductionCommand(
        invocation=invocation,
        repository_root=root,
        caller_context_version=caller_context_version,
        caller_fields=(
            None if caller_fields is None else MappingProxyType(dict(caller_fields))
        ),
    )
    return VerifiedRuntimeContext(
        owner_bindings=production_owner_bindings(),
        owner_payloads=MappingProxyType({invocation.command: payload}),
        repository_root=root,
    )
