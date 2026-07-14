"""Production Runtime/Task-state command adapters."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.cli.production import ProductionCommand, _authorize_running_release
from agent_stack.core.api import canonical_json_bytes
from agent_stack.reconcile.production_bundle import load_production_bundle
from agent_stack.release.compatibility import RuntimeJournalReference
from agent_stack.release.manifest import VerifiedRelease

from .authority import RuntimeAuthorityInputs, verify_runtime_authority
from .bootstrap import launcher_contract_from_release
from .caller_context import VerifiedCallerContext, verify_caller_context
from .errors import RuntimeFailure
from .workspace import register_workspace


def _data_root() -> Path:
    return Path(str(files("agent_stack").joinpath("data")))


def _canonical_object(path: Path) -> Mapping[str, object]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeFailure(
            "AWP_WORKSPACE_REGISTRATION_REQUIRED",
            "command requires committed project authority",
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeFailure(
            "AWP_RUNTIME_BINDING_MISMATCH", "committed authority is invalid"
        ) from error
    if not isinstance(document, Mapping) or path.read_bytes() != canonical_json_bytes(document):
        raise RuntimeFailure(
            "AWP_RUNTIME_BINDING_MISMATCH", "committed authority is not canonical"
        )
    return cast(Mapping[str, object], document)


def _caller_document(command: ProductionCommand) -> Mapping[str, object]:
    fields = command.caller_fields
    if command.caller_context_version != 1 or fields is None:
        raise RuntimeFailure(
            "AWP_CALLER_CONTEXT_INVALID", "workspace registration requires launcher context"
        )
    tty_fields: dict[str, bool] = {}
    for item in fields.get("tty", "").split(","):
        if "=" not in item:
            raise RuntimeFailure("AWP_CALLER_CONTEXT_INVALID", "caller TTY is invalid")
        name, value = item.split("=", 1)
        if value not in {"true", "false"} or name in tty_fields:
            raise RuntimeFailure("AWP_CALLER_CONTEXT_INVALID", "caller TTY is invalid")
        tty_fields[name] = value == "true"
    config_roots = {
        key.removeprefix("config_root."): value
        for key, value in fields.items()
        if key.startswith("config_root.")
    }
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.caller-context",
            "schema_version": 1,
            "platform": fields.get("platform"),
            "user_home": fields.get("user_home"),
            "config_roots": config_roots,
            "harness": {
                "executable": fields.get("harness_executable"),
                "version_probe_id": fields.get("harness_version_probe_id"),
            },
            "tty": tty_fields,
        }
    )


def _caller_probe(context: VerifiedCallerContext) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "user_home": str(context.user_home),
            "harness_executable": str(context.harness_executable),
            "harness_version_probe_id": context.harness_version_probe_id,
            "tty": dict(context.tty),
        }
    )


def _workspace_registration_required(payload: object) -> object:
    raise RuntimeFailure(
        "AWP_WORKSPACE_REGISTRATION_REQUIRED",
        "command requires a verified initialized workspace contract",
    )


def _task_authority_required(payload: object) -> object:
    raise RuntimeFailure(
        "AWP_TASK_RUNTIME_LOAD_DENIED",
        "command requires verified task integration and transaction authority",
    )


def run_workspace_register(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    release = cast(VerifiedRelease, _authorize_running_release())
    root = command.repository_root
    manifest = _canonical_object(root / ".agent-workflow/manifest.json")
    launcher = (root / ".agent-workflow/bin/agent-stack").read_bytes()
    control = (root / ".agent-workflow/runtime-control.json").read_bytes()
    authority = verify_runtime_authority(
        RuntimeAuthorityInputs(
            packaged_release=release,
            committed_release=release,
            candidate_release=None,
            committed_manifest=manifest,
            candidate_manifest=None,
            workflow_lock_digest=str(manifest.get("lock_digest")),
            launcher_contract=launcher_contract_from_release(release),
            launcher_bytes=launcher,
            runtime_control_bytes=control,
            journal=None,
            maintenance_marker=None,
            command="workspace-register",
            recovery_transaction_id=None,
        )
    )
    caller = verify_caller_context(
        _caller_document(command), authority, probe=_caller_probe
    )
    bundle = load_production_bundle(_data_root())
    result = register_workspace(
        root,
        manifest,
        caller,
        trellis_task_layout=bundle.trellis_layout,
        bootstrap_lock_root=root.parent / ".awp-bootstrap-locks",
        transaction_id=str(uuid.uuid4()),
        workspace_instance_id=str(uuid.uuid4()),
        recovery_runtime=RuntimeJournalReference(
            "committed", release.identity.release_id, release.manifest_digest
        ),
    )
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.workspace-registration-result",
            "schema_version": 1,
            "committed": result.committed,
            "workspace_instance_id": result.workspace["workspace_instance_id"],
        }
    )


def run_workspace_migrate(payload: object) -> object:
    return _workspace_registration_required(payload)


def run_task_runtime_load(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_admit(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_claim(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_transition(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_release(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_archive(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_recover(payload: object) -> object:
    return _task_authority_required(payload)


__all__ = [
    "run_task_admit",
    "run_task_archive",
    "run_task_claim",
    "run_task_recover",
    "run_task_release",
    "run_task_runtime_load",
    "run_task_transition",
    "run_workspace_migrate",
    "run_workspace_register",
]
