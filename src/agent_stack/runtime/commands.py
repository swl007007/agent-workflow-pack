"""Production Runtime/Task-state command adapters."""

from __future__ import annotations

import json
import hashlib
import os
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.cli.production import ProductionCommand, _authorize_running_release
from agent_stack.core.api import (
    canonical_json_bytes,
    normalize_mode,
    normalize_path,
    validate_surface_registry,
    validate_trellis_layout,
)
from agent_stack.reconcile.production_bundle import load_production_bundle
from agent_stack.release.compatibility import (
    LocalStateContract,
    RuntimeJournalReference,
    classify_compatibility,
)
from agent_stack.release.identity import ReleaseIdentity
from agent_stack.release.manifest import VerifiedRelease

from .authority import RuntimeAuthorityInputs, RuntimeJournalEvidence, verify_runtime_authority
from .bootstrap import launcher_contract_from_release
from .caller_context import VerifiedCallerContext, verify_caller_context
from .errors import RuntimeFailure
from .integration import VerifiedIntegration, validate_integration
from .runtime_load import (
    RuntimeEntryDescriptor,
    TaskRuntimeLoadRequest,
    load_task_runtime,
)
from .scanner import NormativeTaskScanner
from .task_service import (
    TaskClaimRequest,
    TaskArchiveRequest,
    TaskReleaseRequest,
    TaskTransitionRequest,
    claim_task,
    archive_task,
    release_task,
    transition_task,
)
from .recovery import TaskRecoveryRequest, recover_task_transaction
from .task_journal import read_task_journal
from .workspace import migrate_workspace, register_workspace


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


def _verified_project(
    command: ProductionCommand,
    *,
    journal: RuntimeJournalEvidence | None = None,
    recovery_transaction_id: str | None = None,
) -> tuple[
    VerifiedRelease, Mapping[str, object], VerifiedCallerContext
]:
    release = cast(VerifiedRelease, _authorize_running_release())
    root = command.repository_root
    manifest = _canonical_object(root / ".agent-workflow/manifest.json")
    try:
        launcher = (root / ".agent-workflow/bin/agent-stack").read_bytes()
        control = (root / ".agent-workflow/runtime-control.json").read_bytes()
    except OSError as error:
        raise RuntimeFailure(
            "AWP_RUNTIME_BINDING_MISMATCH", "project runtime control is unavailable"
        ) from error
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
            journal=journal,
            maintenance_marker=None,
            command=command.invocation.command,
            recovery_transaction_id=recovery_transaction_id,
        )
    )
    caller = verify_caller_context(
        _caller_document(command), authority, probe=_caller_probe
    )
    return release, manifest, caller


def _load_integration(root: Path, task_ref: object) -> VerifiedIntegration:
    if not isinstance(task_ref, str):
        raise RuntimeFailure("AWP_TASK_STATE_STALE", "task ref is unavailable")
    document = _canonical_object(root / task_ref / "integration.yaml")
    return validate_integration(document)


def _mutation_result(result: object) -> Mapping[str, object]:
    claim = getattr(result, "executor_claim")
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.task-mutation-result",
            "schema_version": 1,
            "transaction_id": getattr(result, "transaction_id"),
            "task_id": getattr(result, "task_id"),
            "task_ref": getattr(result, "task_ref"),
            "lifecycle_status": getattr(result, "lifecycle_status"),
            "state_revision": getattr(result, "state_revision"),
            "mode": getattr(result, "mode"),
            "phase": getattr(result, "phase"),
            "executor_claim": None if claim is None else dict(claim),
            "outcome": getattr(result, "outcome"),
        }
    )


def _runtime_evidence(
    bundle: object, project_root: Path
) -> tuple[Mapping[str, object], ...]:
    inventory = getattr(bundle, "runtime_unit_inventory")
    evidence = {
        str(item["unit_id"]): dict(item)
        for item in getattr(bundle, "runtime_unit_evidence")
    }
    units = inventory.get("units")
    if not isinstance(units, list):
        raise RuntimeFailure("AWP_TASK_SURFACE_MISMATCH", "runtime inventory is invalid")
    for raw in units:
        if not isinstance(raw, Mapping) or raw.get("distribution_scope") != "rendered-project":
            continue
        unit_id = raw.get("unit_id")
        relative = raw.get("normalized_path")
        if not isinstance(unit_id, str) or not isinstance(relative, str):
            raise RuntimeFailure("AWP_TASK_SURFACE_MISMATCH", "runtime unit is invalid")
        path = project_root / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeFailure(
                "AWP_TASK_SURFACE_MISMATCH", "rendered runtime unit is unavailable"
            )
        payload = path.read_bytes()
        evidence[unit_id].update(
            byte_hash=hashlib.sha256(payload).hexdigest(),
            mode=normalize_mode(os.stat(path, follow_symlinks=False).st_mode),
        )
    return tuple(evidence[unit_id] for unit_id in sorted(evidence))


def run_workspace_register(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    release, manifest, caller = _verified_project(command)
    root = command.repository_root
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
    command = cast(ProductionCommand, payload)
    target_release, target_manifest, _ = _verified_project(command)
    root = command.repository_root
    workspace = _canonical_object(root / ".agent-workflow/local/workspace.json")
    bundle = load_production_bundle(_data_root())
    source_layout_document = workspace.get("trellis_task_layout")
    if not isinstance(source_layout_document, Mapping):
        raise RuntimeFailure(
            "AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED",
            "workspace source layout is unavailable",
        )
    claimed_layout_digest = source_layout_document.get("layout_digest")
    normalized_layout = {
        key: value
        for key, value in source_layout_document.items()
        if key != "layout_digest"
    }
    artifact_targets = tuple(
        str(target["path"])
        for definition in bundle.artifact_definitions
        for target in cast(list[Mapping[str, object]], definition["targets"])
    )
    source_layout = validate_trellis_layout(
        normalized_layout, artifact_targets=artifact_targets
    )
    if source_layout.layout_digest != claimed_layout_digest:
        raise RuntimeFailure(
            "AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED",
            "workspace source layout digest changed",
        )
    schema_versions = {
        "manifest": 1,
        "workflow_lock": 1,
        "integration": 1,
        "task_transaction": 1,
        "workspace": 1,
        "approval_replay": 1,
        "task_outbox": 1,
    }
    source_contract = LocalStateContract(
        contract_digest=str(workspace.get("local_state_contract_digest")),
        trellis_task_layout_digest=source_layout.layout_digest,
        schema_versions=MappingProxyType(schema_versions),
    )
    target_local = target_manifest.get("local_state_contract")
    if not isinstance(target_local, Mapping):
        raise RuntimeFailure(
            "AWP_WORKSPACE_MIGRATION_RECOVERY_REQUIRED",
            "target local-state contract is unavailable",
        )
    target_contract = LocalStateContract(
        contract_digest=str(target_local.get("contract_digest")),
        trellis_task_layout_digest=bundle.trellis_layout.layout_digest,
        schema_versions=MappingProxyType(schema_versions),
    )
    source_identity = ReleaseIdentity(
        target_release.identity.repository_id,
        target_release.identity.distribution_name,
        str(workspace.get("local_state_release_version")),
    )
    if source_identity.release_id != workspace.get("local_state_release_id"):
        raise RuntimeFailure(
            "AWP_WORKSPACE_SOURCE_METADATA_REQUIRED",
            "workspace source release identity is invalid",
        )
    source_release = VerifiedRelease(
        identity=source_identity,
        manifest_digest=str(workspace.get("local_state_release_manifest_digest")),
        source_commit="0" * 40,
        bundles=MappingProxyType(
            {"trust_policy": str(target_release.bundles.get("trust_policy"))}
        ),
        assets=MappingProxyType({}),
        immutable_release=True,
    )
    compatibility = classify_compatibility(
        source_release, target_release, source_contract
    )
    scanner = NormativeTaskScanner(root)
    snapshot = scanner(
        source_layout,
        bundle.trellis_layout,
        bundle.discovery_schemas,
        bundle.discovery_schemas,
    )
    result = migrate_workspace(
        root,
        source_contract,
        target_contract,
        compatibility,
        snapshot,
        target_manifest=target_manifest,
        source_layout=source_layout,
        target_layout=bundle.trellis_layout,
        source_schemas=bundle.discovery_schemas,
        target_schemas=bundle.discovery_schemas,
        scanner=scanner,
        transaction_id=str(uuid.uuid4()),
        recovery_runtime=RuntimeJournalReference(
            "committed",
            target_release.identity.release_id,
            target_release.manifest_digest,
        ),
    )
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.workspace-migration-result",
            "schema_version": 1,
            "committed": result.committed,
            "workspace_instance_id": result.workspace["workspace_instance_id"],
        }
    )


def run_task_runtime_load(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    _verified_project(command)
    options = command.invocation.options
    integration = _load_integration(command.repository_root, options.get("task_ref"))
    task_id = options.get("task_id")
    revision = options.get("revision")
    phase = options.get("phase")
    claim_token = options.get("claim")
    surface = options.get("surface")
    entry_id = options.get("entry")
    if (
        not isinstance(task_id, str)
        or not isinstance(revision, int)
        or isinstance(revision, bool)
        or not isinstance(phase, str)
        or not isinstance(claim_token, str)
        or not isinstance(surface, str)
        or not isinstance(entry_id, str)
    ):
        raise RuntimeFailure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime-load input is invalid")
    expected_phase = None if phase == "none" else phase
    expected_claim: Mapping[str, object] | None = None
    if claim_token != "none":
        if integration.executor_claim is None or integration.executor_claim.get(
            "claim_id"
        ) != claim_token:
            raise RuntimeFailure("AWP_TASK_STATE_STALE", "runtime-load claim changed")
        expected_claim = integration.executor_claim
    bundle = load_production_bundle(_data_root())
    raw_entries = bundle.runtime_entries.get("entries")
    if not isinstance(raw_entries, list):
        raise RuntimeFailure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime-entry registry is invalid")
    entries: dict[str, RuntimeEntryDescriptor] = {}
    for raw in raw_entries:
        if not isinstance(raw, Mapping):
            raise RuntimeFailure(
                "AWP_TASK_RUNTIME_LOAD_DENIED", "runtime-entry registry is invalid"
            )
        descriptor = RuntimeEntryDescriptor(
            entry_id=str(raw.get("entry_id")),
            owning_surface_id=str(raw.get("owning_surface_id")),
            allowed_modes=tuple(str(value) for value in raw.get("allowed_modes", ())),
            allowed_lifecycle_statuses=tuple(
                str(value) for value in raw.get("allowed_lifecycle_statuses", ())
            ),
            allowed_phases=tuple(str(value) for value in raw.get("allowed_phases", ())),
            claim_policy=str(raw.get("claim_policy")),
        )
        if descriptor.entry_id in entries:
            raise RuntimeFailure(
                "AWP_TASK_RUNTIME_LOAD_DENIED", "runtime-entry identity repeats"
            )
        entries[descriptor.entry_id] = descriptor
    registry = validate_surface_registry(
        bundle.surface_registry, bundle.runtime_unit_inventory
    )
    contract_evidence = _runtime_evidence(bundle, command.repository_root)
    loaded = load_task_runtime(
        TaskRuntimeLoadRequest(
            project_root=command.repository_root,
            package_root=_data_root().parent,
            task_ref=integration.task_ref,
            task_id=task_id,
            expected_state_revision=revision,
            expected_lifecycle_status=integration.lifecycle_status,
            expected_phase=expected_phase,
            expected_claim=expected_claim,
            surface_id=surface,
            runtime_entry_id=entry_id,
            registry=registry,
            contract_evidence=contract_evidence,
            runtime_entries=MappingProxyType(entries),
        )
    )
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.runtime-load-result",
            "schema_version": 1,
            "task_id": loaded.task_id,
            "task_ref": loaded.task_ref,
            "state_revision": loaded.state_revision,
            "surface_id": loaded.surface_id,
            "runtime_entry_id": loaded.runtime_entry_id,
            "unit_ids": sorted(loaded.units),
        }
    )


def run_task_admit(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    _verified_project(command)
    task_ref = command.invocation.options.get("task_ref")
    if not isinstance(task_ref, str):
        raise RuntimeFailure("AWP_TASK_REF_CONFLICT", "task ref is unavailable")
    normalized = normalize_path(task_ref)
    if normalized != task_ref or (command.repository_root / normalized).exists():
        raise RuntimeFailure("AWP_TASK_REF_CONFLICT", "task ref is unavailable")
    raise RuntimeFailure(
        "AWP_ROUTE_APPROVAL_INVALID",
        "public task admission lacks a verified platform Decision and approval envelope",
    )


def run_task_claim(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    _, _, caller = _verified_project(command)
    options = command.invocation.options
    integration = _load_integration(command.repository_root, options.get("task_ref"))
    revision = options.get("revision")
    executor = options.get("executor")
    if not isinstance(revision, int) or isinstance(revision, bool) or not isinstance(
        executor, str
    ):
        raise RuntimeFailure("AWP_TASK_STATE_STALE", "task claim input is invalid")
    result = claim_task(
        TaskClaimRequest(
            project_root=command.repository_root,
            task_ref=integration.task_ref,
            task_id=integration.task_id,
            expected_revision=revision,
            claim_id=str(uuid.uuid4()),
            executor=executor,
            actor=caller.platform,
            claimed_at=datetime.now(UTC),
        )
    )
    return _mutation_result(result)


def run_task_transition(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    _verified_project(command)
    options = command.invocation.options
    integration = _load_integration(command.repository_root, options.get("task_ref"))
    revision = options.get("revision")
    target = options.get("target_status")
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or not isinstance(target, str)
    ):
        raise RuntimeFailure("AWP_TASK_STATE_STALE", "task transition input is invalid")
    if integration.mode != "trellis-native":
        raise RuntimeFailure(
            "AWP_TASK_TRANSITION_INVALID",
            "heavy task transition requires an explicit phase contract",
        )
    result = transition_task(
        TaskTransitionRequest(
            project_root=command.repository_root,
            task_ref=integration.task_ref,
            task_id=integration.task_id,
            expected_revision=revision,
            transition_id=str(uuid.uuid4()),
            target_lifecycle_status=target,
            target_phase=None,
            completion_flags=None,
            changed_at=datetime.now(UTC),
        )
    )
    return _mutation_result(result)


def run_task_release(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    _, _, caller = _verified_project(command)
    options = command.invocation.options
    integration = _load_integration(command.repository_root, options.get("task_ref"))
    revision = options.get("revision")
    executor = options.get("executor")
    claim = integration.executor_claim
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or not isinstance(executor, str)
        or claim is None
        or claim.get("executor") != executor
        or not isinstance(claim.get("claim_id"), str)
    ):
        raise RuntimeFailure("AWP_TASK_STATE_STALE", "task release input is invalid")
    result = release_task(
        TaskReleaseRequest(
            project_root=command.repository_root,
            task_ref=integration.task_ref,
            task_id=integration.task_id,
            expected_revision=revision,
            claim_id=str(claim["claim_id"]),
            actor=caller.platform,
            released_at=datetime.now(UTC),
        )
    )
    return _mutation_result(result)


def run_task_archive(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    _verified_project(command)
    options = command.invocation.options
    integration = _load_integration(command.repository_root, options.get("task_ref"))
    revision = options.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise RuntimeFailure("AWP_TASK_STATE_STALE", "task archive input is invalid")
    bundle = load_production_bundle(_data_root())
    result = archive_task(
        TaskArchiveRequest(
            project_root=command.repository_root,
            transaction_id=str(uuid.uuid4()),
            task_ref=integration.task_ref,
            task_id=integration.task_id,
            expected_revision=revision,
            archive_root=bundle.trellis_layout.archive_root,
            metadata_mutations=(),
            archived_at=datetime.now(UTC),
        )
    )
    return _mutation_result(result)


def run_task_recover(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    transaction_id = command.invocation.options.get("transaction_id")
    action = command.invocation.options.get("recovery_action")
    if not isinstance(transaction_id, str) or action not in {"resume", "rollback"}:
        raise RuntimeFailure(
            "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "task recovery input is invalid"
        )
    document = read_task_journal(command.repository_root, transaction_id)
    header = document.get("immutable_header")
    if not isinstance(header, Mapping):
        raise RuntimeFailure(
            "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "task journal header is invalid"
        )
    runtime = header.get("recovery_runtime")
    if not isinstance(runtime, Mapping):
        raise RuntimeFailure(
            "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED", "task recovery runtime is invalid"
        )
    evidence = RuntimeJournalEvidence(
        transaction_id=transaction_id,
        journal_kind="task",
        phase=str(document["phase"]),
        recovery_runtime=RuntimeJournalReference(
            str(runtime.get("runtime_role")),
            str(runtime.get("release_id")),
            str(runtime.get("release_manifest_digest")),
        ),
        file_transitions=MappingProxyType({}),
        journal_binding_digest=str(document["journal_binding_digest"]),
    )
    _verified_project(
        command, journal=evidence, recovery_transaction_id=transaction_id
    )
    result = recover_task_transaction(
        TaskRecoveryRequest(command.repository_root, transaction_id, action)
    )
    return _mutation_result(result)


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
