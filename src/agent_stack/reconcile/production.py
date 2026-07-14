"""Production composition for verified init and sync operations."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from agent_stack.cli.production import ProductionCommand
from agent_stack.core.api import (
    CANONICAL_NULL,
    DesiredStateIR,
    ResolverInputs,
    TaskSnapshotAndFindings,
    canonical_json_bytes,
    digest,
    resolve,
)
from agent_stack.providers.api import ProviderExecutionResult
from agent_stack.providers.archive import content_root_digest
from agent_stack.release.manifest import VerifiedRelease
from agent_stack.runtime.scanner import NormativeTaskScanner
from agent_stack.runtime.bootstrap import launcher_contract_from_release

from .api import apply_plan, plan_reconcile, render
from .cas import observe_file_state
from .models import StagedFile, StagedRenderTree
from .production_bundle import ProductionBundle, load_production_bundle


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} is not a string-keyed object")
    return value


def _release_contract(
    release: VerifiedRelease, bundle: ProductionBundle
) -> Mapping[str, object]:
    policy_id = bundle.trust_policy.get("policy_id")
    trust_digest = release.bundles.get("trust_policy")
    if not isinstance(policy_id, str) or not isinstance(trust_digest, str):
        raise ValueError("verified release lacks packaged trust-policy authority")
    return MappingProxyType(
        {
            "release_id": release.identity.release_id,
            "release_manifest_digest": release.manifest_digest,
            "release_trust_policy_id": policy_id,
            "release_trust_policy_digest": trust_digest,
            "version": release.identity.version,
        }
    )


def _resolver_inputs(
    operation: str,
    release: VerifiedRelease,
    bundle: ProductionBundle,
    task_state: TaskSnapshotAndFindings,
    *,
    render_units: Sequence[Mapping[str, object]] = (),
    current_contract: Mapping[str, object] | None = None,
    observed_state: Mapping[str, object] | None = None,
) -> ResolverInputs:
    return ResolverInputs(
        operation=operation,
        release_contract=_release_contract(release, bundle),
        profile_sources=(bundle.profile,),
        selected_profile_id="default",
        catalog_document=bundle.catalog,
        workflow_lock_document=bundle.workflow_lock,
        capability_manifests=(),
        artifact_definition_documents=bundle.artifact_definitions,
        trellis_layout_document=bundle.trellis_layout.normalized,
        surface_registry_document=bundle.surface_registry,
        runtime_unit_inventory_document=bundle.runtime_unit_inventory,
        runtime_unit_evidence=bundle.runtime_unit_evidence,
        route_policy_document=bundle.route_policy,
        router_contract_document=bundle.router_contract,
        entry_ownership=(),
        render_units=render_units,
        current_contract=current_contract
        or {
            "authority_digests": {},
            "surface_digests": {},
            "registry_graph_digest": CANONICAL_NULL,
        },
        observed_state=observed_state
        or {"surface_digests": {}, "unclassified_runtime_units": []},
        repair_surface_ids=(),
        diagnostics=(),
        task_snapshot=task_state.snapshot,
        task_findings=task_state.findings,
    )


def _substitute(source: bytes, release: VerifiedRelease, profile_digest: str) -> bytes:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    values = {
        "release_id": release.identity.release_id,
        "release_manifest_digest": release.manifest_digest,
        "profile_digest": profile_digest,
    }
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text.encode("utf-8")


def _render_units(
    bundle: ProductionBundle, release: VerifiedRelease, profile_digest: str
) -> tuple[Mapping[str, object], ...]:
    units: list[Mapping[str, object]] = []
    for definition in bundle.artifact_definitions:
        definition_id = str(definition["id"])
        source_id = str(definition["source"])
        source = bundle.template_root.parent.joinpath(source_id).read_bytes()
        targets = definition.get("targets")
        validators = definition.get("validators")
        if not isinstance(targets, Sequence) or not isinstance(validators, Sequence):
            raise ValueError("packaged artifact definition is invalid")
        for target_value in targets:
            target = _mapping(target_value, "artifact target")
            candidate = _substitute(source, release, profile_digest)
            units.append(
                MappingProxyType(
                    {
                        "schema_id": "agent-workflow.render-unit",
                        "schema_version": 1,
                        "unit_id": f"render-unit:{definition_id}",
                        "definition_id": definition_id,
                        "source": {
                            "source_id": source_id,
                            "source_digest": hashlib.sha256(source).hexdigest(),
                        },
                        "target": dict(target),
                        "surface_id": "platform-adapter:codex",
                        "validator_ids": [
                            str(_mapping(item, "validator")["id"]) for item in validators
                        ],
                        "candidate_leaf_digest": hashlib.sha256(candidate).hexdigest(),
                    }
                )
            )
    return tuple(units)


def _control_record(
    definition_id: str,
    path: str,
    mode: str,
    candidate: bytes,
    neutral: bytes,
) -> StagedFile:
    candidate_hash = hashlib.sha256(candidate).hexdigest()
    return StagedFile(
        path=path,
        definition_id=definition_id,
        surface_id="runtime-control-plane",
        ownership="managed",
        merge_strategy="whole-file",
        source_digest=hashlib.sha256(neutral).hexdigest(),
        render_digest=digest(
            "agent-workflow.rendered-file.v1",
            {
                "path": path,
                "definition_id": definition_id,
                "surface_id": "runtime-control-plane",
                "source_digest": hashlib.sha256(neutral).hexdigest(),
                "candidate_byte_hash": candidate_hash,
                "candidate_mode": mode,
                "renderer_version": 1,
                "validator_ids": ["utf8-text-v1"],
            },
        ),
        candidate_byte_hash=candidate_hash,
        mode_policy="exact",
        candidate_mode=mode,
        validator_results=(),
        candidate_bytes=candidate,
        neutral_source_bytes=neutral,
    )


def _with_control_artifacts(
    ir: DesiredStateIR,
    staged: StagedRenderTree,
    release: VerifiedRelease,
    data_root: Path,
    bundle: ProductionBundle,
) -> StagedRenderTree:
    contract = launcher_contract_from_release(release)
    launcher_template = (data_root / "runtime-launcher/agent-stack.sh.tmpl").read_bytes()
    launcher = contract.render(launcher_template)
    control_template = (data_root / "templates/control/runtime-control.json.tmpl").read_bytes()
    control = canonical_json_bytes(contract.runtime_control(launcher))
    lock_source = (data_root / "catalog/workflow.lock").read_bytes()
    lock_candidate = canonical_json_bytes(bundle.workflow_lock)
    records = tuple(
        sorted(
            (
                *staged.files,
                _control_record(
                    "project-launcher",
                    ".agent-workflow/bin/agent-stack",
                    "0755",
                    launcher,
                    launcher_template,
                ),
                _control_record(
                    "runtime-control",
                    ".agent-workflow/runtime-control.json",
                    "0644",
                    control,
                    control_template,
                ),
                _control_record(
                    "project-workflow-lock",
                    ".agent-workflow/workflow.lock",
                    "0644",
                    lock_candidate,
                    lock_source,
                ),
            ),
            key=lambda record: record.path,
        )
    )
    projection = [
        {
            "path": record.path,
            "candidate_byte_hash": record.candidate_byte_hash,
            "candidate_mode": record.candidate_mode,
            "render_digest": record.render_digest,
        }
        for record in records
    ]
    return StagedRenderTree(
        files=records,
        content_root_digest=digest("agent-workflow.staged-render-tree.v1", projection),
        launcher_bundle_digest=staged.launcher_bundle_digest,
        distribution_render_digest=digest(
            "agent-workflow.distribution-render.v1",
            {"release_contract": dict(ir.release_contract), "files": projection},
        ),
    )


def _provider_result(data_root: Path) -> ProviderExecutionResult:
    return ProviderExecutionResult.without_approval(
        provider_plan_digest="0" * 64,
        attempt_id="00000000-0000-4000-8000-000000000000",
        terminal_state="succeeded",
        containment_evidence_digest="0" * 64,
        result_category="validated",
        candidate_output_root_digest=content_root_digest(data_root),
        candidate_output_path=str(data_root),
        diagnostics_digest="0" * 64,
        provenance_records=(),
    )


def _observed_files(root: Path, staged: StagedRenderTree) -> Mapping[str, object]:
    observed: dict[str, object] = {}
    for record in staged.files:
        state = observe_file_state(root, record.path)
        content = None
        if state.exists and state.file_type == "regular":
            content = (root / record.path).read_text(encoding="utf-8")
        observed[record.path] = {"state": state.to_document(), "content": content}
    return MappingProxyType(observed)


def _local_contract(
    release: VerifiedRelease, bundle: ProductionBundle
) -> Mapping[str, object]:
    projection = {
        "release_id": release.identity.release_id,
        "release_version": release.identity.version,
        "workspace_schema": 1,
        "approval_replay_schema": 1,
        "task_outbox_schema": 1,
        "trellis_task_layout_digest": bundle.trellis_layout.layout_digest,
    }
    return MappingProxyType(
        {
            **projection,
            "contract_digest": hashlib.sha256(canonical_json_bytes(projection)).hexdigest(),
        }
    )


def _read_canonical_object(path: Path) -> Mapping[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required committed authority is unavailable: {path.name}")
    payload = path.read_bytes()
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise ValueError(f"committed authority is invalid JSON: {path.name}") from error
    if not isinstance(document, Mapping) or canonical_json_bytes(document) != payload:
        raise ValueError(f"committed authority is not canonical JSON: {path.name}")
    return document


def _require_sync_authority(
    root: Path,
    release: VerifiedRelease,
    bundle: ProductionBundle,
    candidate: DesiredStateIR,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    manifest = _read_canonical_object(root / ".agent-workflow/manifest.json")
    workspace = _read_canonical_object(root / ".agent-workflow/local/workspace.json")
    if (
        manifest.get("release_id") != release.identity.release_id
        or manifest.get("release_manifest_digest") != release.manifest_digest
        or manifest.get("pack_version") != release.identity.version
        or workspace.get("project_id") != manifest.get("project_id")
        or workspace.get("local_state_contract_digest")
        != _mapping(manifest.get("local_state_contract"), "local state contract").get(
            "contract_digest"
        )
    ):
        raise ValueError("committed project authority differs from the verified release")
    expected_manifest_digests = {
        "profile_digest": candidate.authority_digests["profile"],
        "lock_digest": candidate.authority_digests["workflow-lock"],
        "artifact_bundle_digest": candidate.authority_digests["artifact-bundle"],
    }
    if any(manifest.get(field) != value for field, value in expected_manifest_digests.items()):
        raise ValueError("committed Manifest authority differs from the packaged bundle")
    contract = launcher_contract_from_release(release)
    launcher = (root / ".agent-workflow/bin/agent-stack").read_bytes()
    expected_control = canonical_json_bytes(contract.runtime_control(launcher))
    if (root / ".agent-workflow/runtime-control.json").read_bytes() != expected_control:
        raise ValueError("committed runtime-control differs from the verified launcher")
    if (root / ".agent-workflow/workflow.lock").read_bytes() != canonical_json_bytes(
        bundle.workflow_lock
    ):
        raise ValueError("committed workflow lock differs from the packaged lock")
    return manifest, workspace


def compose_init(
    command: ProductionCommand,
    release: VerifiedRelease,
    *,
    apply: bool,
    data_root: Path,
) -> Mapping[str, object]:
    bundle = load_production_bundle(data_root)
    scanner = NormativeTaskScanner(command.repository_root)
    task_state = scanner(
        bundle.trellis_layout,
        bundle.trellis_layout,
        bundle.discovery_schemas,
        bundle.discovery_schemas,
    )
    preliminary = resolve(_resolver_inputs("init", release, bundle, task_state))
    profile_digest = preliminary.authority_digests["profile"]
    units = _render_units(bundle, release, profile_digest)
    ir = resolve(
        _resolver_inputs(
            "init", release, bundle, task_state, render_units=units
        )
    )
    staged = _with_control_artifacts(
        ir,
        render(ir, (_provider_result(data_root),)),
        release,
        data_root,
        bundle,
    )
    project_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    replay = {
        "schema_id": "agent-workflow.approval-replay",
        "schema_version": 1,
        "project_id": project_id,
        "workspace_instance_id": workspace_id,
        "entries": {},
    }
    observed = {
        "transaction_id": str(uuid.uuid4()),
        "candidate_project_id": project_id,
        "candidate_workspace_instance_id": workspace_id,
        "manifest_digest": CANONICAL_NULL,
        "files": _observed_files(command.repository_root, staged),
        "candidate_local_state_contract": _local_contract(release, bundle),
        "provider_approval_bindings": [],
        "recovery_runtime": {
            "release_id": release.identity.release_id,
            "release_manifest_digest": release.manifest_digest,
            "runtime_role": "committed",
        },
        "empty_replay_ledger_candidate_digest": hashlib.sha256(
            canonical_json_bytes(replay)
        ).hexdigest(),
        "target_path_digest": digest(
            "agent-workflow.target-path.v1", str(command.repository_root)
        ),
    }
    envelope = plan_reconcile(ir, staged, None, observed, task_state)
    if not apply:
        return MappingProxyType(
            {
                "schema_id": "agent-workflow.reconcile-preview",
                "schema_version": 1,
                "operation": "init",
                "dry_run": True,
                "planned_paths": [record.path for record in staged.files],
                "writes_performed": 0,
                "plan_digest": envelope.plan_digest,
            }
        )
    approval = {
        "plan_digest": envelope.plan_digest,
        "project_root": str(command.repository_root),
        "bootstrap_lock_root": str(command.repository_root.parent / ".awp-bootstrap-locks"),
        "source_layout": bundle.trellis_layout,
        "target_layout": bundle.trellis_layout,
        "source_schemas": bundle.discovery_schemas,
        "target_schemas": bundle.discovery_schemas,
    }
    return apply_plan(envelope, approval, scanner=scanner)


def compose_sync(
    command: ProductionCommand,
    release: VerifiedRelease,
    *,
    apply: bool,
    data_root: Path,
) -> Mapping[str, object]:
    bundle = load_production_bundle(data_root)
    scanner = NormativeTaskScanner(command.repository_root)
    task_state = scanner(
        bundle.trellis_layout,
        bundle.trellis_layout,
        bundle.discovery_schemas,
        bundle.discovery_schemas,
    )
    preliminary = resolve(_resolver_inputs("sync", release, bundle, task_state))
    manifest, workspace = _require_sync_authority(
        command.repository_root, release, bundle, preliminary
    )
    current_contract = {
        "authority_digests": dict(preliminary.authority_digests),
        "surface_digests": dict(preliminary.surface_digests),
        "registry_graph_digest": preliminary.authority_digests["surface-registry"],
    }
    observed_state = {
        "surface_digests": dict(preliminary.surface_digests),
        "unclassified_runtime_units": [],
    }
    units = _render_units(
        bundle, release, preliminary.authority_digests["profile"]
    )
    ir = resolve(
        _resolver_inputs(
            "sync",
            release,
            bundle,
            task_state,
            render_units=units,
            current_contract=current_contract,
            observed_state=observed_state,
        )
    )
    staged = _with_control_artifacts(
        ir,
        render(ir, (_provider_result(data_root),)),
        release,
        data_root,
        bundle,
    )
    observed = {
        "transaction_id": str(uuid.uuid4()),
        "workspace_instance_id": workspace["workspace_instance_id"],
        "manifest_digest": hashlib.sha256(
            canonical_json_bytes(manifest)
        ).hexdigest(),
        "files": _observed_files(command.repository_root, staged),
        "candidate_local_state_contract": _local_contract(release, bundle),
        "provider_approval_bindings": [],
        "recovery_runtime": {
            "release_id": release.identity.release_id,
            "release_manifest_digest": release.manifest_digest,
            "runtime_role": "committed",
        },
    }
    envelope = plan_reconcile(ir, staged, manifest, observed, task_state)
    no_op = not bool(envelope.plan_core["candidate_file_states"])
    if not apply:
        return MappingProxyType(
            {
                "schema_id": "agent-workflow.reconcile-preview",
                "schema_version": 1,
                "operation": "sync",
                "dry_run": True,
                "planned_paths": [record.path for record in staged.files],
                "writes_performed": 0,
                "no_op": no_op,
                "plan_digest": envelope.plan_digest,
            }
        )
    approval = {
        "plan_digest": envelope.plan_digest,
        "project_root": str(command.repository_root),
        "source_layout": bundle.trellis_layout,
        "target_layout": bundle.trellis_layout,
        "source_schemas": bundle.discovery_schemas,
        "target_schemas": bundle.discovery_schemas,
    }
    return apply_plan(envelope, approval, scanner=scanner)


__all__ = ["compose_init", "compose_sync"]
