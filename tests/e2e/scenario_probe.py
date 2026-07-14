from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import shutil
import subprocess
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import agent_stack
from agent_stack.__main__ import main
from agent_stack.cli.dispatch import OwnerBinding, VerifiedRuntimeContext
from agent_stack.core.api import (
    CANONICAL_NULL,
    CandidateImpact,
    DesiredStateIR,
    VerifiedDiscoverySchemas,
    build_workspace_diagnostic,
    canonical_json_bytes,
    compute_surface_digests,
    digest,
    evaluate_task_gate,
    evaluate_workspace_state_quiescence,
    validate_surface_registry,
    validate_trellis_layout,
)
from agent_stack.core.impact import SurfaceChange
from agent_stack.providers.api import ProviderExecutionResult
from agent_stack.providers.archive import content_root_digest
from agent_stack.reconcile.api import apply_plan, plan_reconcile, render
from agent_stack.reconcile.cas import compare_and_swap
from agent_stack.reconcile.models import FileState, StagedFile, StagedRenderTree
from agent_stack.reconcile.repair import stage_restorative_repair
from agent_stack.release.compatibility import (
    CompatibilityResult,
    LocalStateContract,
    RuntimeJournalReference,
    classify_compatibility,
    inspect_source_static_metadata,
)
from agent_stack.release.distribution import UpgradePorts, UpgradeRequest, orchestrate_upgrade
from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.identity import ReleaseIdentity
from agent_stack.release.manifest import VerifiedRelease
from agent_stack.route.approval import VerifiedPlatformRuntimeContext
from agent_stack.route.calculator import (
    RouteCalculationInputs,
    VerifiedRouteAuthoritySnapshot,
    calculate_route,
)
from agent_stack.route.intent import validate_task_intent
from agent_stack.route.signals import load_compiled_policy
from agent_stack.route.wrappers import (
    IntegratedWrapperInvocation,
    invoke_integrated_wrapper,
    production_route_verifier_ports,
)
from agent_stack.runtime.caller_context import VerifiedCallerContext
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.recovery import TaskRecoveryRequest, recover_task_transaction
from agent_stack.runtime.runtime_load import RuntimeEntryDescriptor, TaskRuntimeLoadRequest
from agent_stack.runtime.scanner import NormativeTaskScanner
from agent_stack.runtime import task_service as task_service_module
from agent_stack.runtime import workspace as workspace_module
from agent_stack.runtime.task_service import (
    MetadataMutation,
    TaskAdmissionRequest,
    TaskArchiveRequest,
    TaskFile,
    TaskTransitionRequest,
    admit_task,
    archive_task,
    derive_archive_ref,
    transition_task,
)
from agent_stack.runtime.workspace import (
    migrate_workspace,
    recover_workspace_migration,
    register_workspace,
)


ROOT = Path(__file__).resolve().parents[2]
PROJECT_ID = "4e3d0530-901a-4f65-8c41-5faf017026c4"
WORKSPACE_ID = "5f477c7f-a1dc-4a16-8f75-39f153170222"
NOW = datetime(2026, 7, 13, 15, tzinfo=UTC)
IGNORE_BLOCK = """# BEGIN AGENT-WORKFLOW-PACK EPHEMERAL
.agent-workflow/local/
.agent-workflow/task-transactions/
.agent-workflow/transactions/
.agent-workflow/reconcile.lock
.agent-workflow/runtime-state.lock
.agent-workflow/maintenance.json
# END AGENT-WORKFLOW-PACK EPHEMERAL
"""


class _InjectedTermination(BaseException):
    pass


class _ReceiptVerifier:
    def __init__(self, expected_receipt: str) -> None:
        self.expected_receipt = expected_receipt

    def __call__(self, receipt: str, projection: dict[str, object]) -> bool:
        assert "verifier_receipt" not in projection
        return receipt == self.expected_receipt


def _resource(relative: str) -> Path:
    package_root = Path(agent_stack.__file__).resolve().parent
    candidates = (package_root / "data" / relative, package_root.parents[1] / relative)
    matches = [path for path in candidates if path.is_file()]
    assert len(matches) == 1, (relative, candidates)
    return matches[0]


def _verified_layout(document: dict[str, object] | None = None):
    raw = document or json.loads(
        (ROOT / "tests/fixtures/runtime/trellis_layouts/layout.json").read_text(
            encoding="utf-8"
        )
    )
    return validate_trellis_layout(raw, source_roots=("src",))


def _discovery_schemas() -> VerifiedDiscoverySchemas:
    normalized = json.loads(
        (
            ROOT / "tests/fixtures/runtime/trellis_layouts/discovery-schemas.json"
        ).read_text(encoding="utf-8")
    )
    production = {
        "agent-workflow.integration": _resource("schemas/runtime/integration.v1.json"),
        "agent-workflow.task-transaction": _resource(
            "schemas/runtime/task-transaction.v1.json"
        ),
    }
    for entry in normalized["schemas"]:
        path = production.get(entry["schema_id"])
        if path is not None:
            entry["schema"] = json.loads(path.read_text(encoding="utf-8"))
    return VerifiedDiscoverySchemas(
        hashlib.sha256(canonical_json_bytes(normalized)).hexdigest(), normalized
    )


def _caller_context(root: Path) -> VerifiedCallerContext:
    home = root / "caller-home"
    config = home / "codex"
    harness = home / "bin/codex"
    config.mkdir(parents=True)
    harness.parent.mkdir(parents=True)
    harness.write_text("#!/bin/sh\n", encoding="utf-8")
    harness.chmod(0o755)
    return VerifiedCallerContext(
        "codex",
        home,
        MappingProxyType({"codex_home": config}),
        harness,
        "codex-version-v1",
        MappingProxyType(
            {
                "direct_confirmation_capable": True,
                "stderr": True,
                "stdin": True,
                "stdout": True,
            }
        ),
    )


def _workspace_manifest(
    layout,
    *,
    release_id: str = "a" * 64,
    release_version: str = "0.1.0",
    release_manifest_digest: str = "b" * 64,
    generation: int = 1,
) -> dict[str, object]:
    contract = {
        "release_id": release_id,
        "release_version": release_version,
        "workspace_schema": 1,
        "approval_replay_schema": 1,
        "task_outbox_schema": 1,
        "trellis_task_layout_digest": layout.layout_digest,
    }
    contract["contract_digest"] = hashlib.sha256(
        canonical_json_bytes(contract)
    ).hexdigest()
    return {
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "generation": generation,
        "pack_version": release_version,
        "release_id": release_id,
        "release_manifest_digest": release_manifest_digest,
        "local_state_contract": contract,
    }


def _register_clone(
    project: Path,
    state_root: Path,
    *,
    manifest: Mapping[str, object] | None = None,
    workspace_instance_id: str = WORKSPACE_ID,
    transaction_id: str = "11111111-1111-4111-8111-111111111111",
):
    project.mkdir(parents=True)
    (project / ".agent-workflow").mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / ".gitignore").write_text(IGNORE_BLOCK, encoding="utf-8")
    layout = _verified_layout()
    selected_manifest = manifest or _workspace_manifest(layout)
    result = register_workspace(
        project,
        selected_manifest,
        _caller_context(state_root),
        trellis_task_layout=layout,
        bootstrap_lock_root=state_root / "bootstrap-locks",
        transaction_id=transaction_id,
        workspace_instance_id=workspace_instance_id,
        recovery_runtime=RuntimeJournalReference(
            "committed",
            str(selected_manifest["release_id"]),
            str(selected_manifest["release_manifest_digest"]),
        ),
    )
    (project / ".trellis/tasks/archive").mkdir(parents=True)
    return layout, result


def _surface(surface_id: str, kind: str, unit_id: str, references: list[str]):
    return {
        "surface_id": surface_id,
        "surface_kind": kind,
        "descriptor_version": 1,
        "digest_recipe_id": "surface-content-v1",
        "owned_unit_ids": [unit_id],
        "references": references,
        "contract_change_class": "runtime-visible",
    }


def _unit(unit_id: str, owner: str, path: str, scope: str):
    return {
        "unit_id": unit_id,
        "unit_kind": unit_id.split(":", 1)[0],
        "distribution_scope": scope,
        "normalized_path": path,
        "owning_surface_id": owner,
        "leaf_recipe_id": "bytes-mode-contract-v1",
        "runtime_visible": True,
    }


def _write_file(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    os.chmod(path, mode)


def _runtime_surface_case(project_root: Path):
    package_root = project_root / ".e2e-package"
    units = {
        "schema:surface-registry": (
            package_root / "schemas/registry.json",
            b'{"schema":1}\n',
            "runtime-package",
            "surface-registry",
        ),
        "module:runtime-control": (
            package_root / "runtime/control.py",
            b"CONTROL = 1\n",
            "runtime-package",
            "runtime-control-plane",
        ),
        "runtime-entry:trellis-implement": (
            project_root / ".agent-workflow/runtime/trellis/entry.txt",
            b"run trellis\n",
            "rendered-project",
            "runtime-entry:trellis-implement",
        ),
    }
    for path, payload, _, _ in units.values():
        _write_file(path, payload)
    registry = validate_surface_registry(
        {
            "schema_id": "agent-workflow.runtime-surface-registry",
            "schema_version": 1,
            "surfaces": [
                _surface(
                    "runtime-control-plane",
                    "runtime-control-plane",
                    "module:runtime-control",
                    ["surface-registry"],
                ),
                _surface(
                    "runtime-entry:trellis-implement",
                    "runtime-entry",
                    "runtime-entry:trellis-implement",
                    ["runtime-control-plane"],
                ),
                _surface(
                    "surface-registry",
                    "surface-registry",
                    "schema:surface-registry",
                    [],
                ),
            ],
        },
        {
            "schema_id": "agent-workflow.runtime-unit-inventory",
            "schema_version": 1,
            "units": [
                _unit(
                    unit_id,
                    owner,
                    path.relative_to(
                        package_root if scope == "runtime-package" else project_root
                    ).as_posix(),
                    scope,
                )
                for unit_id, (path, _, scope, owner) in units.items()
            ],
        },
    )
    evidence = tuple(
        {
            "unit_id": unit_id,
            "byte_hash": hashlib.sha256(payload).hexdigest(),
            "mode": "0644",
            "contract_digest": hashlib.sha256(
                f"{unit_id}-contract".encode()
            ).hexdigest(),
            "distributions": (
                ["git-checkout", "sdist", "wheel"]
                if scope == "runtime-package"
                else ["rendered-project"]
            ),
        }
        for unit_id, (_, payload, scope, _) in units.items()
    )
    return package_root, units, registry, evidence, compute_surface_digests(
        registry, evidence
    )


def _route_authorities(surface_digests: Mapping[str, str]):
    policy = load_compiled_policy(_resource("catalog/route-policy.yaml"))
    inventory = {"tasks": [], "unfinished_task_journals": [], "active_pointers": []}
    pins = tuple(
        {"surface_id": surface_id, "surface_digest": surface_digests[surface_id]}
        for surface_id in sorted(surface_digests)
    )
    return VerifiedRouteAuthoritySnapshot(
        project_id=PROJECT_ID,
        workspace_instance_id=WORKSPACE_ID,
        manifest_generation=1,
        manifest_digest="4" * 64,
        profile_digest="5" * 64,
        lock_digest="6" * 64,
        artifact_bundle_digest="7" * 64,
        policy=policy,
        policy_digest=policy.policy_digest,
        platform="codex",
        adapter_id="codex",
        adapter_version="1.0.0",
        router_contract_version=1,
        entry_owners={
            "native-light": "sol-native",
            "trellis-native": "trellis-implement",
            "speckit-superpowers": "heavy-development-router",
        },
        task_inventory=inventory,
        task_state_digest=digest("agent-workflow.route-task-state.v1", inventory),
        task_surface_closures={
            "trellis-native": pins,
            "speckit-superpowers": pins,
        },
        maintenance=False,
        unfinished_task_transaction=False,
    )


def _task_intent(
    policy,
    *,
    requested_mode: str | None = None,
    intent_id: str = "clone-a-intent",
):
    return validate_task_intent(
        {
            "schema_id": "agent-workflow.task-intent",
            "schema_version": 1,
            "intent_id": intent_id,
            "title": "Clone A task",
            "objective": "Exercise the complete task lifecycle",
            "requested_mode": requested_mode,
            "acceptance_summary": "The task recovers, runs, repairs, and archives",
            "signals": [],
        },
        policy=policy,
    )


def _capability() -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.capability-manifest",
        "schema_version": 1,
        "platform": "codex",
        "adapter_id": "codex",
        "adapter_version": "1.0.0",
        "harness_id": "codex-cli",
        "harness_version": "1.2.3",
        "probe_suite_id": "codex-approval-probes",
        "probe_suite_version": 1,
        "capabilities": {
            "task_admission_gate": "enforced",
            "direct_human_confirmation": "enforced",
        },
        "approval_verifiers": {
            "task_creation": {
                "verifier_id": "codex-human-verifier",
                "verifier_version": "1.0.0",
                "actor_source": "direct-human",
                "receipt_source": "codex-confirmation",
            }
        },
        "evidence_digest": "9" * 64,
    }


def _platform_runtime_context() -> VerifiedPlatformRuntimeContext:
    return VerifiedPlatformRuntimeContext(
        platform="codex",
        harness_id="codex-cli",
        harness_version="1.2.3",
        confirmation_mechanism="codex-confirmation",
        direct_confirmation_capable=True,
        now=NOW,
        max_approval_ttl=timedelta(minutes=15),
        max_clock_skew=timedelta(seconds=60),
        receipt_verifier=_ReceiptVerifier("codex-receipt:opaque"),
    )


def _approval_proof(decision: Mapping[str, object], approval_id: str):
    return {
        "schema_id": "agent-workflow.approval-proof",
        "schema_version": 1,
        "approval_id": approval_id,
        "verifier_id": "codex-human-verifier",
        "verifier_version": "1.0.0",
        "platform": "codex",
        "harness_version": "1.2.3",
        "actor": {"id": "human-actor", "kind": "direct-human"},
        "issued_at": (NOW - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "expires_at": (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "workspace_instance_id": decision["workspace_instance_id"],
        "operation": "create-integrated-task",
        "task_id": decision["requested_task_id"],
        "task_ref": decision["requested_task_ref"],
        "task_contract_surfaces_digest": decision[
            "task_contract_surfaces_digest"
        ],
        "intent_digest": decision["intent_digest"],
        "route_decision_digest": decision["decision_digest"],
        "approval_challenge": decision["approval_challenge"],
        "verifier_receipt": "codex-receipt:opaque",
    }


def _metadata_mutation(
    before: Mapping[str, object] | None, after: Mapping[str, object]
) -> MetadataMutation:
    before_bytes = None if before is None else canonical_json_bytes(before)
    after_bytes = canonical_json_bytes(after)
    return MetadataMutation(
        original=FileState(
            ".trellis/task-index.json",
            before is not None,
            "regular" if before is not None else "absent",
            (
                hashlib.sha256(before_bytes).hexdigest()
                if before_bytes is not None
                else CANONICAL_NULL
            ),
            "0644" if before is not None else CANONICAL_NULL,
            True,
        ),
        candidate=FileState(
            ".trellis/task-index.json",
            True,
            "regular",
            hashlib.sha256(after_bytes).hexdigest(),
            "0644",
            True,
        ),
        original_bytes=before_bytes,
        candidate_bytes=after_bytes,
    )


def _admission_request(
    project: Path,
    authorities: VerifiedRouteAuthoritySnapshot,
    *,
    transaction_id: str,
    approval_id: str,
    metadata_mutation: MetadataMutation,
    intent_id: str = "clone-a-intent",
    task_ref: str = ".trellis/tasks/example",
) -> TaskAdmissionRequest:
    decision = calculate_route(
        "create-integrated-task",
        RouteCalculationInputs(
            intent=_task_intent(
                authorities.policy,
                requested_mode="trellis-native",
                intent_id=intent_id,
            ),
            requested_task_ref=task_ref,
        ),
        authorities,
    )
    workflow_contract = {
        "version": 1,
        "profile_digest_at_admission": authorities.profile_digest,
        "lock_digest_at_admission": authorities.lock_digest,
        "artifact_bundle_digest_at_admission": authorities.artifact_bundle_digest,
        "policy_digest_at_admission": authorities.policy_digest,
        "adapter_id": authorities.adapter_id,
        "adapter_version_at_admission": authorities.adapter_version,
        "route_contract_version": authorities.router_contract_version,
        "task_contract_surfaces": decision["task_contract_surfaces"],
    }
    return TaskAdmissionRequest(
        project_root=project,
        project_id=PROJECT_ID,
        workspace_instance_id=WORKSPACE_ID,
        transaction_id=transaction_id,
        decision=decision,
        approval_proof=_approval_proof(decision, approval_id),
        current_authorities={
            field.name: getattr(authorities, field.name)
            for field in dataclasses.fields(authorities)
        },
        capability=_capability(),
        runtime_context=_platform_runtime_context(),
        workflow_contract=workflow_contract,
        mode_state={"task_ref": decision["requested_task_ref"]},
        task_files=(TaskFile("README.md", b"# Task\n", "0644"),),
        metadata_mutations=(metadata_mutation,),
        admitted_at=NOW,
        route_ports=production_route_verifier_ports(),
    )


def _launcher(project: Path) -> Path:
    path = project / ".agent-workflow/bin/agent-stack"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _invoke_cli(
    arguments: list[str],
    command: str,
    owner: str,
    invoke,
    project: Path,
) -> dict[str, object]:
    exit_code, result = _invoke_cli_result(
        arguments, command, owner, invoke, project
    )
    assert exit_code == 0
    assert result["status"] == "success"
    return result


def _invoke_cli_result(
    arguments: list[str],
    command: str,
    owner: str,
    invoke,
    project: Path,
    *,
    workspace_diagnostic: Mapping[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    context = VerifiedRuntimeContext(
        owner_bindings=MappingProxyType(
            {command: OwnerBinding(owner=owner, invoke=invoke)}
        ),
        owner_payloads=MappingProxyType({command: None}),
        repository_root=project,
        workspace_diagnostic=workspace_diagnostic,
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main([*arguments, "--json"], runtime_context=context)
    result = json.loads(output.getvalue())
    assert isinstance(result, dict)
    return exit_code, result


def _repair_runtime_entry(
    project: Path,
    relative_path: str,
    payload: bytes,
    surface_id: str,
    surface_digest: str,
) -> None:
    change = SurfaceChange(
        surface_id,
        "repair",
        surface_digest,
        CANONICAL_NULL,
        surface_digest,
    )
    impact = CandidateImpact("runtime-visible", (), (change,), False, "8" * 64)
    base = _distribution_ir(b"probe\n", b"probe\n")
    ir = dataclasses.replace(
        base,
        operation="repair",
        surface_digests=MappingProxyType({surface_id: surface_digest}),
        candidate_impact=impact,
    )
    byte_hash = hashlib.sha256(payload).hexdigest()
    staged_file = StagedFile(
        path=relative_path,
        definition_id="runtime-entry-repair",
        surface_id=surface_id,
        ownership="managed",
        merge_strategy="whole-file",
        source_digest=byte_hash,
        render_digest=byte_hash,
        candidate_byte_hash=byte_hash,
        mode_policy="exact",
        candidate_mode="0644",
        candidate_bytes=payload,
        neutral_source_bytes=payload,
    )
    selected = stage_restorative_repair(
        ir, StagedRenderTree((staged_file,), "9" * 64)
    )
    assert selected.files == (staged_file,)
    compare_and_swap(
        project,
        FileState(
            relative_path,
            False,
            "absent",
            CANONICAL_NULL,
            CANONICAL_NULL,
            True,
        ),
        FileState(relative_path, True, "regular", byte_hash, "0644", True),
        payload,
    )


def _local_contract() -> LocalStateContract:
    return LocalStateContract(
        contract_digest="8" * 64,
        trellis_task_layout_digest="9" * 64,
        schema_versions={
            "manifest": 1,
            "workflow_lock": 1,
            "integration": 1,
            "task_transaction": 1,
            "workspace": 1,
            "approval_replay": 1,
            "task_outbox": 1,
        },
    )


def _release(version: str, marker: str, *, compatibility=None) -> VerifiedRelease:
    identity = ReleaseIdentity(
        "github.com/example/agent-workflow-pack", "agent-workflow-pack", version
    )
    bundles = {
        "trust_policy": "1" * 64,
        "workflow_lock": marker * 64,
        "artifact": "3" * 64,
        "schema": "4" * 64,
        "migration": "5" * 64,
        "compatibility": "6" * 64,
        "launcher": "7" * 64,
    }
    return VerifiedRelease(
        identity=identity,
        manifest_digest=marker * 64,
        source_commit=marker * 40,
        bundles=MappingProxyType(bundles),
        assets=MappingProxyType(
            {
                "wheel": MappingProxyType(
                    {
                        "name": f"agent_workflow_pack-{version}-py3-none-any.whl",
                        "url": f"https://github.com/example/releases/{version}/wheel.whl",
                        "size": 100,
                        "sha256": marker * 64,
                    }
                ),
                "sdist": MappingProxyType(
                    {
                        "name": f"agent_workflow_pack-{version}.tar.gz",
                        "url": f"https://github.com/example/releases/{version}/source.tar.gz",
                        "size": 200,
                        "sha256": ("f" if marker != "f" else "e") * 64,
                    }
                ),
            }
        ),
        immutable_release=True,
        compatibility=compatibility,
    )


def _compatibility_edge(source: VerifiedRelease, target: VerifiedRelease):
    contract = _local_contract()
    return {
        "from_release_id": source.identity.release_id,
        "to_release_id": target.identity.release_id,
        "from_version": source.identity.version,
        "to_version": target.identity.version,
        "trust_policy_digest": "1" * 64,
        "target_bundles": {
            key: target.bundles[key]
            for key in (
                "trust_policy",
                "workflow_lock",
                "artifact",
                "schema",
                "migration",
                "launcher",
            )
        },
        "schema_transitions": {
            key: {"from": 1, "to": 1} for key in contract.schema_versions
        },
        "local_state_contracts": {
            "from": contract.contract_digest,
            "to": contract.contract_digest,
        },
        "trellis_task_layouts": {
            "from": contract.trellis_task_layout_digest,
            "to": contract.trellis_task_layout_digest,
        },
        "migrations": [],
    }


def _with_edge(owner: VerifiedRelease, edge: Mapping[str, object]):
    return dataclasses.replace(
        owner,
        compatibility=MappingProxyType(
            {
                "schema_id": "agent-workflow.release-compatibility",
                "schema_version": 1,
                "release_id": owner.identity.release_id,
                "edges": [dict(edge)],
            }
        ),
    )


def _upgrade_ports(
    candidate: VerifiedRelease,
    scanned,
    events: list[str],
    *,
    candidate_impact: CandidateImpact | None = None,
) -> UpgradePorts:
    def verify(locator):
        events.append(f"verify-manifest:{locator.version}")
        return dataclasses.replace(candidate, compatibility=None)

    def acquire(verified):
        events.append("acquire-wheel")
        return {"sha256": verified.assets["wheel"]["sha256"]}

    def inspect(artifact, verified):
        assert artifact["sha256"] == verified.assets["wheel"]["sha256"]
        events.append("inspect-static")
        return candidate

    def resolve(verified, compatibility):
        events.append("resolve")
        return {"candidate": verified.identity.release_id, "edge": compatibility.edge_owner}

    def scan(_):
        events.append("scan")
        return scanned

    def gate(_, snapshot):
        impact = candidate_impact or CandidateImpact("none", (), (), False, "0" * 64)
        evaluated = evaluate_task_gate(
            "upgrade", impact, snapshot.snapshot, snapshot.findings
        )
        if evaluated.primary_evaluator_blocker is not None:
            raise RuntimeFailure(
                evaluated.primary_evaluator_blocker,
                "task gate blocks upgrade",
            )
        events.append("task-gate")

    def plan(resolved, snapshot, compatibility, recovery_runtime):
        events.append("plan")
        return {
            "resolved": resolved,
            "snapshot": snapshot.task_quiescence_digest,
            "edge": compatibility.edge_owner,
            "recovery_runtime": recovery_runtime,
            "plan_digest": "b" * 64,
        }

    def approve(plan):
        events.append("approve")
        return MappingProxyType({"plan_digest": plan["plan_digest"]})

    def apply(plan, approval, scanner):
        assert approval["plan_digest"] == plan["plan_digest"]
        assert scanner().task_quiescence_digest == scanned.task_quiescence_digest
        events.extend(("apply-local-state", "manifest-commit"))
        return MappingProxyType({"transaction_id": "upgrade-tx", "committed": True})

    return UpgradePorts(
        locate_exact_release=lambda version: (_ for _ in ()).throw(
            AssertionError(version)
        ),
        verify_candidate_release=verify,
        acquire_candidate_wheel=acquire,
        inspect_candidate_static=inspect,
        classify_compatibility=classify_compatibility,
        resolve_candidate=resolve,
        scan_task_quiescence=scan,
        assert_task_gate=gate,
        plan_reconcile=plan,
        approve_plan=approve,
        apply_plan=apply,
    )


def _distribution_ir(source: bytes, candidate: bytes) -> DesiredStateIR:
    unit = {
        "schema_id": "agent-workflow.render-unit",
        "schema_version": 1,
        "unit_id": "unit:distribution-probe",
        "definition_id": "distribution-probe",
        "source": {
            "source_id": "probe.txt",
            "source_digest": hashlib.sha256(source).hexdigest(),
        },
        "target": {
            "path": ".agent-workflow/probe.txt",
            "ownership": "managed",
            "merge_strategy": "whole-file",
            "mode_policy": "exact",
            "mode": "0644",
        },
        "surface_id": "runtime-control-plane",
        "validator_ids": ["utf8-text-v1", "newline-v1"],
        "candidate_leaf_digest": hashlib.sha256(candidate).hexdigest(),
    }
    definition = {
        "id": "distribution-probe",
        "source": "probe.txt",
        "targets": [
            {
                "path": ".agent-workflow/probe.txt",
                "ownership": "managed",
                "merge_strategy": "whole-file",
                "mode_policy": "exact",
                "mode": "0644",
                "markers": None,
            }
        ],
        "forbidden_paths": [],
        "validators": [
            {"id": "utf8-text-v1", "version": 1},
            {"id": "newline-v1", "version": 1},
        ],
    }
    return DesiredStateIR(
        operation="sync",
        release_contract=MappingProxyType(
            {"release_id": "a" * 64, "release_manifest_digest": "b" * 64}
        ),
        resolved_profile=MappingProxyType({"profile_id": "default"}),
        authority_digests=MappingProxyType({"profile": "c" * 64}),
        workflow_lock_projection=MappingProxyType({}),
        selected_platforms=(),
        capability_results=(),
        catalog_closure=(),
        reference_closure=(),
        route_policy=MappingProxyType({}),
        entry_ownership=(),
        discoverable_leaf_ids=(),
        runtime_catalog_entry_ids=(),
        trellis_task_layout=MappingProxyType({}),
        surface_registry=MappingProxyType({}),
        surface_digests=MappingProxyType({}),
        coverage_result=MappingProxyType({}),
        render_units=(MappingProxyType(unit),),
        artifact_definitions=(MappingProxyType(definition),),
        candidate_impact=CandidateImpact("none", (), (), False, "d" * 64),
        workspace_state_evaluation=MappingProxyType({}),
        task_gate_evaluation=MappingProxyType({}),
        diagnostics=(),
        desired_state_ir_digest="e" * 64,
    )


def _provider_result(root: Path) -> ProviderExecutionResult:
    return ProviderExecutionResult.without_approval(
        provider_plan_digest="1" * 64,
        attempt_id="11111111-1111-4111-8111-111111111111",
        terminal_state="succeeded",
        containment_evidence_digest="2" * 64,
        result_category="validated",
        candidate_output_root_digest=content_root_digest(root),
        candidate_output_path=str(root),
        diagnostics_digest="3" * 64,
        provenance_records=(),
    )


def _no_op_sync(project: Path, scanned) -> Mapping[str, object]:
    workspace_state = evaluate_workspace_state_quiescence(
        scanned.snapshot, scanned.findings
    )
    impact = CandidateImpact("none", (), (), False, "d" * 64)
    task_gate = evaluate_task_gate(
        "sync", impact, scanned.snapshot, scanned.findings
    )
    base = _distribution_ir(b"probe\n", b"probe\n")
    ir = dataclasses.replace(
        base,
        render_units=(),
        artifact_definitions=(),
        release_contract=MappingProxyType(
            {
                "release_id": "a" * 64,
                "release_manifest_digest": "b" * 64,
                "release_trust_policy_id": "github-immutable-v0.1",
                "release_trust_policy_digest": "c" * 64,
                "version": "0.1.0",
            }
        ),
        authority_digests=MappingProxyType(
            {
                "profile": "d" * 64,
                "workflow-lock": "e" * 64,
                "artifact-bundle": "f" * 64,
            }
        ),
        candidate_impact=impact,
        workspace_state_evaluation=MappingProxyType(
            {
                "evaluator_id": workspace_state.evaluator_id,
                "evaluator_version": workspace_state.evaluator_version,
                "task_quiescence": workspace_state.task_quiescence,
                "blockers": list(workspace_state.evidence_kinds),
            }
        ),
        task_gate_evaluation=MappingProxyType(
            {
                "evaluator_id": task_gate.evaluator_id,
                "evaluator_version": task_gate.evaluator_version,
                "blockers": [],
                "primary_evaluator_blocker": None,
            }
        ),
    )
    manifest = {
        "schema_version": 1,
        "project_id": PROJECT_ID,
        "generation": 1,
        "pack_version": "0.1.0",
        "release_id": "a" * 64,
        "release_manifest_digest": "b" * 64,
        "files": [],
    }
    observed = {
        "transaction_id": "22222222-2222-4222-8222-222222222222",
        "workspace_instance_id": WORKSPACE_ID,
        "manifest_digest": hashlib.sha256(canonical_json_bytes(manifest)).hexdigest(),
        "files": {},
        "candidate_local_state_contract": {},
        "provider_approval_bindings": [],
        "recovery_runtime": {
            "runtime_role": "committed",
            "release_id": "a" * 64,
            "release_manifest_digest": "b" * 64,
        },
    }
    envelope = plan_reconcile(
        ir,
        StagedRenderTree((), "a" * 64),
        manifest,
        observed,
        scanned,
    )
    return apply_plan(envelope, {"plan_digest": envelope.plan_digest})


def _contract_from_manifest(
    manifest: Mapping[str, object], layout
) -> LocalStateContract:
    local = manifest["local_state_contract"]
    assert isinstance(local, Mapping)
    return LocalStateContract(
        contract_digest=str(local["contract_digest"]),
        trellis_task_layout_digest=layout.layout_digest,
        schema_versions={
            "manifest": 1,
            "workflow_lock": 1,
            "integration": 1,
            "task_transaction": 1,
            "workspace": int(local["workspace_schema"]),
            "approval_replay": int(local["approval_replay_schema"]),
            "task_outbox": int(local["task_outbox_schema"]),
        },
    )


def _migration_compatibility(
    source: LocalStateContract, target: LocalStateContract
) -> CompatibilityResult:
    edge = {
        "local_state_contracts": {
            "from": source.contract_digest,
            "to": target.contract_digest,
        },
        "trellis_task_layouts": {
            "from": source.trellis_task_layout_digest,
            "to": target.trellis_task_layout_digest,
        },
        "schema_transitions": {
            field: {
                "from": source.schema_versions[field],
                "to": target.schema_versions[field],
            }
            for field in source.schema_versions
        },
        "migrations": [
            {"migration_id": "local-state-v1", "migration_digest": "f" * 64}
        ],
    }
    return CompatibilityResult(
        "migration-required",
        edge_owner="target",
        edge=MappingProxyType(edge),
        target_local_state_contract_digest=target.contract_digest,
        target_trellis_task_layout_digest=target.trellis_task_layout_digest,
    )


def _workspace_migration_case(
    workspace: Path,
    name: str,
    *,
    target_layout=None,
) -> dict[str, object]:
    source_layout = _verified_layout()
    selected_target_layout = target_layout or source_layout
    source_identity = ReleaseIdentity(
        "github.com/example/agent-workflow-pack", "agent-workflow-pack", "0.1.0"
    )
    target_identity = ReleaseIdentity(
        "github.com/example/agent-workflow-pack", "agent-workflow-pack", "0.2.0"
    )
    source_manifest = _workspace_manifest(
        source_layout,
        release_id=source_identity.release_id,
        release_version=source_identity.version,
        release_manifest_digest="b" * 64,
    )
    target_manifest = _workspace_manifest(
        selected_target_layout,
        release_id=target_identity.release_id,
        release_version=target_identity.version,
        release_manifest_digest="d" * 64,
        generation=2,
    )
    project = workspace / name
    _, registration = _register_clone(
        project,
        workspace / f"{name}-state",
        manifest=source_manifest,
        transaction_id=str(
            {
                "clone-b": "11111111-1111-4111-8111-111111111111",
                "source-only": "12111111-1111-4111-8111-111111111111",
                "target-only": "13111111-1111-4111-8111-111111111111",
                "stale": "14111111-1111-4111-8111-111111111111",
                "donor": "15111111-1111-4111-8111-111111111111",
                "sibling": "16111111-1111-4111-8111-111111111111",
            }.get(name, "17111111-1111-4111-8111-111111111111")
        ),
    )
    assert registration.committed is True
    manifest_path = project / ".agent-workflow/manifest.json"
    manifest_bytes = canonical_json_bytes(target_manifest)
    manifest_path.write_bytes(manifest_bytes)
    os.chmod(manifest_path, 0o644)
    source_contract = _contract_from_manifest(source_manifest, source_layout)
    target_contract = _contract_from_manifest(
        target_manifest, selected_target_layout
    )
    schemas = _discovery_schemas()
    scanner = NormativeTaskScanner(project)
    return {
        "project": project,
        "source_identity": source_identity,
        "target_identity": target_identity,
        "source_manifest": source_manifest,
        "target_manifest": target_manifest,
        "manifest_bytes": manifest_bytes,
        "source_layout": source_layout,
        "target_layout": selected_target_layout,
        "source_contract": source_contract,
        "target_contract": target_contract,
        "compatibility": _migration_compatibility(source_contract, target_contract),
        "schemas": schemas,
        "scanner": scanner,
    }


def _scan_migration_case(case: Mapping[str, object]):
    scanner = case["scanner"]
    assert isinstance(scanner, NormativeTaskScanner)
    return scanner(
        case["source_layout"],
        case["target_layout"],
        case["schemas"],
        case["schemas"],
    )


def _migrate_case(
    case: Mapping[str, object], snapshot, transaction_id: str
):
    project = case["project"]
    target_identity = case["target_identity"]
    target_manifest = case["target_manifest"]
    assert isinstance(project, Path)
    assert isinstance(target_identity, ReleaseIdentity)
    assert isinstance(target_manifest, Mapping)
    return migrate_workspace(
        project,
        case["source_contract"],
        case["target_contract"],
        case["compatibility"],
        snapshot,
        target_manifest=target_manifest,
        source_layout=case["source_layout"],
        target_layout=case["target_layout"],
        source_schemas=case["schemas"],
        target_schemas=case["schemas"],
        scanner=case["scanner"],
        transaction_id=transaction_id,
        recovery_runtime=RuntimeJournalReference(
            "committed",
            target_identity.release_id,
            str(target_manifest["release_manifest_digest"]),
        ),
    )


def _write_static_source_archive(
    path: Path,
    identity: ReleaseIdentity,
    contract: LocalStateContract,
) -> str:
    compatibility = {
        "schema_id": "agent-workflow.release-compatibility",
        "schema_version": 1,
        "release_id": identity.release_id,
        "edges": [],
    }
    document = {
        "schema_id": "agent-workflow.release-static-metadata",
        "schema_version": 1,
        "release_identity": identity.to_document(),
        "local_state_contract": contract.to_document(),
        "compatibility": compatibility,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "agent_workflow_pack/release-static.json",
            canonical_json_bytes(document),
        )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _admit_indexed_task(
    project: Path,
    authorities: VerifiedRouteAuthoritySnapshot,
    *,
    transaction_id: str,
    approval_id: str,
    intent_id: str,
    task_ref: str,
    before_index: Mapping[str, object] | None,
    after_index,
) -> tuple[TaskAdmissionRequest, object]:
    provisional = _admission_request(
        project,
        authorities,
        transaction_id=transaction_id,
        approval_id=approval_id,
        metadata_mutation=_metadata_mutation(
            before_index,
            after_index("pending-task"),
        ),
        intent_id=intent_id,
        task_ref=task_ref,
    )
    task_id = str(provisional.decision["requested_task_id"])
    request = dataclasses.replace(
        provisional,
        metadata_mutations=(
            _metadata_mutation(before_index, after_index(task_id)),
        ),
    )
    return request, admit_task(request)


def distribution_scenario(workspace: Path) -> int:
    expected_root = Path(os.environ["AWP_EXPECT_AGENT_STACK_ROOT"]).resolve()
    assert Path(agent_stack.__file__).resolve().is_relative_to(expected_root)

    provider_root = workspace / "provider"
    provider_root.mkdir(parents=True)
    source = b"release={{release_id}}\nprofile={{profile_digest}}\n"
    candidate = f"release={'a' * 64}\nprofile={'c' * 64}\n".encode()
    (provider_root / "probe.txt").write_bytes(source)
    tree = render(_distribution_ir(source, candidate), [_provider_result(provider_root)])
    context = VerifiedRuntimeContext(
        owner_bindings=MappingProxyType(
            {
                "doctor": OwnerBinding(
                    owner="lifecycle",
                    invoke=lambda _: {
                        "distribution_render_digest": tree.distribution_render_digest,
                        "rendered_paths": [record.path for record in tree.files],
                        "rendered_sha256": [
                            hashlib.sha256(record.candidate_bytes).hexdigest()
                            for record in tree.files
                        ],
                    },
                )
            }
        ),
        owner_payloads=MappingProxyType({"doctor": None}),
        repository_root=workspace,
    )
    return main(["doctor", "--json"], runtime_context=context)


def clone_a_scenario(workspace: Path) -> dict[str, object]:
    project = workspace / "clone-a"
    state_root = workspace / "state"
    layout, registration = _register_clone(project, state_root)
    assert registration.workspace["workspace_instance_id"] == WORKSPACE_ID
    steps = ["registered"]

    legacy_fixture = ROOT / "tests/fixtures/e2e/legacy-workflow-pack"
    shutil.copytree(legacy_fixture, project, dirs_exist_ok=True)
    protected = project / ".trellis/spec/legacy-contract.md"
    protected_before = protected.read_bytes()

    package_root, units, registry, evidence, surface_digests = _runtime_surface_case(
        project
    )
    authorities = _route_authorities(surface_digests)
    schemas = _discovery_schemas()
    scanner = NormativeTaskScanner(project)
    empty_scan = scanner(layout, layout, schemas, schemas)
    empty_state = evaluate_workspace_state_quiescence(
        empty_scan.snapshot, empty_scan.findings
    )
    empty_gate = evaluate_task_gate(
        "sync",
        CandidateImpact("none", (), (), False, "0" * 64),
        empty_scan.snapshot,
        empty_scan.findings,
    )
    diagnostic = build_workspace_diagnostic(
        command="doctor",
        relationship="matching",
        relationship_evidence="verified",
        discovery_evidence="verified",
        workspace_task_state=empty_state,
        task_gate_result=empty_gate,
    )
    doctor = _invoke_cli(
        ["doctor"],
        "doctor",
        "lifecycle",
        lambda _: diagnostic.to_document(),
        project,
    )
    assert doctor["workspace_diagnostic"] is None
    steps.append("doctor")

    route_result = _invoke_cli(
        ["test-routing"],
        "test-routing",
        "route",
        lambda _: calculate_route(
            "classify-only", RouteCalculationInputs(), authorities
        ),
        project,
    )
    assert route_result["result"]["operation"] == "classify-only"
    steps.append("test-routing")

    sync_result = _invoke_cli(
        ["sync"],
        "sync",
        "reconcile",
        lambda _: _no_op_sync(project, empty_scan),
        project,
    )
    assert sync_result["result"]["no_op"] is True
    steps.append("no-op-sync")

    first_transaction = "78d71641-c23d-45b3-aabb-1c7f4ad8c808"
    first_request = _admission_request(
        project,
        authorities,
        transaction_id=first_transaction,
        approval_id="11111111-1111-4111-8111-111111111111",
        metadata_mutation=_metadata_mutation(
            None,
            {"active": ["pending-first-task"]},
        ),
    )
    first_task_id = str(first_request.decision["requested_task_id"])
    first_request = dataclasses.replace(
        first_request,
        metadata_mutations=(
            _metadata_mutation(None, {"active": [first_task_id]}),
        ),
    )

    original_crash = task_service_module._crash_at

    def admission_crash(point: str) -> None:
        if point == "after_task_moved":
            raise _InjectedTermination()

    task_service_module._crash_at = admission_crash
    try:
        try:
            admit_task(first_request)
        except _InjectedTermination:
            pass
        else:
            raise AssertionError("admission killpoint did not terminate")
    finally:
        task_service_module._crash_at = original_crash
    admitted = recover_task_transaction(
        TaskRecoveryRequest(project, first_transaction, "resume")
    )
    assert admitted.lifecycle_status == "active"
    steps.append("admission-recovered")

    entry = RuntimeEntryDescriptor(
        entry_id="trellis-implement",
        owning_surface_id="runtime-entry:trellis-implement",
        allowed_modes=("trellis-native",),
        allowed_lifecycle_statuses=("active", "blocked", "completed"),
        allowed_phases=(),
        claim_policy="forbidden",
    )
    load_request = TaskRuntimeLoadRequest(
        project_root=project,
        package_root=package_root,
        task_ref=admitted.task_ref,
        task_id=admitted.task_id,
        expected_state_revision=admitted.state_revision,
        expected_lifecycle_status="active",
        expected_phase=None,
        expected_claim=None,
        surface_id="runtime-entry:trellis-implement",
        runtime_entry_id="trellis-implement",
        registry=registry,
        contract_evidence=evidence,
        runtime_entries={"trellis-implement": entry},
    )
    invocation = IntegratedWrapperInvocation(
        repository_launcher=_launcher(project),
        load_request=load_request,
        dispatcher=lambda bundle: bundle.units[
            "runtime-entry:trellis-implement"
        ].content,
    )
    runtime_bytes = invoke_integrated_wrapper(invocation)
    assert runtime_bytes == b"run trellis\n"
    steps.append("runtime-loaded")

    runtime_path, expected_runtime_bytes, _, _ = units[
        "runtime-entry:trellis-implement"
    ]
    runtime_path.unlink()
    try:
        invoke_integrated_wrapper(invocation)
    except RuntimeFailure as error:
        assert error.code == "AWP_TASK_SURFACE_MISMATCH"
    else:
        raise AssertionError("missing runtime entry was accepted")
    steps.append("drift-rejected")

    _repair_runtime_entry(
        project,
        runtime_path.relative_to(project).as_posix(),
        expected_runtime_bytes,
        "runtime-entry:trellis-implement",
        surface_digests["runtime-entry:trellis-implement"],
    )
    assert invoke_integrated_wrapper(invocation) == expected_runtime_bytes
    steps.append("repair-resumed")

    completed = transition_task(
        TaskTransitionRequest(
            project,
            admitted.task_ref,
            admitted.task_id,
            admitted.state_revision,
            "task-completed",
            target_lifecycle_status="completed",
            target_phase=None,
            completion_flags=None,
            changed_at=NOW + timedelta(minutes=1),
        )
    )
    completed_scan = scanner(layout, layout, schemas, schemas)
    changed_surface = SurfaceChange(
        "runtime-entry:trellis-implement",
        "contract-change",
        surface_digests["runtime-entry:trellis-implement"],
        surface_digests["runtime-entry:trellis-implement"],
        "0" * 64,
    )
    upgrade_impact = CandidateImpact(
        "runtime-visible", (), (changed_surface,), False, "1" * 64
    )
    gate = evaluate_task_gate(
        "upgrade",
        upgrade_impact,
        completed_scan.snapshot,
        completed_scan.findings,
    )
    assert gate.primary_evaluator_blocker == "AWP_WORKSPACE_ACTIVE_TASK_BLOCK"

    installed = _release("0.1.0", "b")
    target_base = _release("0.2.0", "c")
    target = _with_edge(target_base, _compatibility_edge(installed, target_base))
    try:
        orchestrate_upgrade(
            UpgradeRequest(installed, target, _local_contract()),
            _upgrade_ports(
                target,
                completed_scan,
                [],
                candidate_impact=upgrade_impact,
            ),
        )
    except RuntimeFailure as error:
        assert error.code == "AWP_WORKSPACE_ACTIVE_TASK_BLOCK"
    else:
        raise AssertionError("completed task did not gate affected upgrade")
    steps.append("completed-gates-upgrade")

    first_archive_transaction = "1a7a8fda-5bc6-4e4c-9344-a508d3675191"
    archive_request = TaskArchiveRequest(
        project_root=project,
        transaction_id=first_archive_transaction,
        task_ref=completed.task_ref,
        task_id=completed.task_id,
        expected_revision=completed.state_revision,
        archive_root=".trellis/tasks/archive",
        metadata_mutations=(
            _metadata_mutation(
                {"active": [completed.task_id]},
                {"active": [], "archived": [completed.task_id]},
            ),
        ),
        archived_at=NOW + timedelta(minutes=2),
    )

    def archive_crash(point: str) -> None:
        if point == "after_archive_task_moved":
            raise _InjectedTermination()

    task_service_module._crash_at = archive_crash
    try:
        try:
            archive_task(archive_request)
        except _InjectedTermination:
            pass
        else:
            raise AssertionError("archive killpoint did not terminate")
    finally:
        task_service_module._crash_at = original_crash
    archived = recover_task_transaction(
        TaskRecoveryRequest(project, first_archive_transaction, "resume")
    )
    assert archived.task_ref == derive_archive_ref(
        ".trellis/tasks/archive", completed.task_id, completed.task_ref
    )
    steps.append("archive-recovered")

    replacement_inventory = {
        "tasks": [
            {"task_id": archived.task_id, "task_ref": archived.task_ref},
        ],
        "unfinished_task_journals": [],
        "active_pointers": [],
    }
    replacement_authorities = dataclasses.replace(
        authorities,
        task_inventory=replacement_inventory,
        task_state_digest=digest(
            "agent-workflow.route-task-state.v1", replacement_inventory
        ),
    )
    replacement_transaction = "9b29f6ef-03a5-49cc-a6c3-c176a4625a24"
    replacement_request = _admission_request(
        project,
        replacement_authorities,
        transaction_id=replacement_transaction,
        approval_id="22222222-2222-4222-8222-222222222222",
        metadata_mutation=_metadata_mutation(
            {"active": [], "archived": [archived.task_id]},
            {"active": ["pending-replacement"], "archived": [archived.task_id]},
        ),
        intent_id="clone-a-replacement-intent",
    )
    replacement_task_id = str(replacement_request.decision["requested_task_id"])
    replacement_request = dataclasses.replace(
        replacement_request,
        metadata_mutations=(
            _metadata_mutation(
                {"active": [], "archived": [archived.task_id]},
                {
                    "active": [replacement_task_id],
                    "archived": [archived.task_id],
                },
            ),
        ),
    )
    replacement = admit_task(replacement_request)
    assert replacement.task_ref == completed.task_ref
    assert replacement.task_id != completed.task_id
    steps.append("ref-reused-with-new-uuid")

    replacement_completed = transition_task(
        TaskTransitionRequest(
            project,
            replacement.task_ref,
            replacement.task_id,
            replacement.state_revision,
            "replacement-completed",
            target_lifecycle_status="completed",
            target_phase=None,
            completion_flags=None,
            changed_at=NOW + timedelta(minutes=3),
        )
    )
    replacement_archived = archive_task(
        TaskArchiveRequest(
            project_root=project,
            transaction_id="c9c60711-93a5-4c89-86db-931e683f6448",
            task_ref=replacement_completed.task_ref,
            task_id=replacement_completed.task_id,
            expected_revision=replacement_completed.state_revision,
            archive_root=".trellis/tasks/archive",
            metadata_mutations=(
                _metadata_mutation(
                    {
                        "active": [replacement_completed.task_id],
                        "archived": [archived.task_id],
                    },
                    {
                        "active": [],
                        "archived": [
                            archived.task_id,
                            replacement_completed.task_id,
                        ],
                    },
                ),
            ),
            archived_at=NOW + timedelta(minutes=4),
        )
    )
    assert replacement_archived.lifecycle_status == "archived"
    steps.append("replacement-archived")

    final_scan = scanner(layout, layout, schemas, schemas)
    final_state = evaluate_workspace_state_quiescence(
        final_scan.snapshot, final_scan.findings
    )
    assert final_state.task_quiescence == "quiescent"
    steps.append("quiescent")

    upgrade_events: list[str] = []
    upgraded = orchestrate_upgrade(
        UpgradeRequest(installed, target, _local_contract()),
        _upgrade_ports(
            target,
            final_scan,
            upgrade_events,
            candidate_impact=upgrade_impact,
        ),
    )
    assert upgraded.committed is True
    assert upgrade_events[-2:] == ["apply-local-state", "manifest-commit"]
    steps.append("upgrade-complete")

    return {
        "steps": steps,
        "first_task_id": completed.task_id,
        "replacement_task_id": replacement_completed.task_id,
        "protected_legacy_bytes_preserved": protected.read_bytes() == protected_before,
    }


def clone_b_scenario(workspace: Path) -> dict[str, object]:
    steps: list[str] = []
    main_case = _workspace_migration_case(workspace, "clone-b")
    source_archive = workspace / "source-release.whl"
    source_identity = main_case["source_identity"]
    source_contract = main_case["source_contract"]
    assert isinstance(source_identity, ReleaseIdentity)
    assert isinstance(source_contract, LocalStateContract)
    source_archive_digest = _write_static_source_archive(
        source_archive, source_identity, source_contract
    )
    static_evidence = inspect_source_static_metadata(
        source_archive, source_archive_digest
    )
    assert static_evidence.identity == source_identity
    assert static_evidence.local_state_contract == source_contract
    steps.append("static-source-verified")

    project = main_case["project"]
    assert isinstance(project, Path)
    steps.append("registered")

    changed_layout_document = json.loads(
        (ROOT / "tests/fixtures/runtime/trellis_layouts/layout.json").read_text(
            encoding="utf-8"
        )
    )
    changed_layout_document["active_root"] = ".trellis/work-items"
    changed_layout_document["archive_root"] = ".trellis/work-items/archive"
    changed_layout = _verified_layout(changed_layout_document)

    source_only = _workspace_migration_case(
        workspace, "source-only", target_layout=changed_layout
    )
    source_project = source_only["project"]
    assert isinstance(source_project, Path)
    _, _, _, _, source_surface_digests = _runtime_surface_case(source_project)
    source_authorities = _route_authorities(source_surface_digests)
    _admit_indexed_task(
        source_project,
        source_authorities,
        transaction_id="21111111-1111-4111-8111-111111111111",
        approval_id="31111111-1111-4111-8111-111111111111",
        intent_id="clone-b-source-only",
        task_ref=".trellis/tasks/source-only",
        before_index=None,
        after_index=lambda task_id: {"active": [task_id]},
    )
    try:
        _migrate_case(
            source_only,
            _scan_migration_case(source_only),
            "41111111-1111-4111-8111-111111111111",
        )
    except RuntimeFailure as error:
        assert error.code == "AWP_WORKSPACE_ACTIVE_TASK_BLOCK"
    else:
        raise AssertionError("source-only active task did not block migration")
    steps.append("source-only-active-blocked")

    target_only = _workspace_migration_case(
        workspace, "target-only", target_layout=changed_layout
    )
    target_project = target_only["project"]
    assert isinstance(target_project, Path)
    _, _, _, _, target_surface_digests = _runtime_surface_case(target_project)
    target_authorities = _route_authorities(target_surface_digests)
    _admit_indexed_task(
        target_project,
        target_authorities,
        transaction_id="22111111-1111-4111-8111-111111111111",
        approval_id="32111111-1111-4111-8111-111111111111",
        intent_id="clone-b-target-only",
        task_ref=".trellis/work-items/target-only",
        before_index=None,
        after_index=lambda task_id: {"active": [task_id]},
    )
    try:
        _migrate_case(
            target_only,
            _scan_migration_case(target_only),
            "42111111-1111-4111-8111-111111111111",
        )
    except RuntimeFailure as error:
        assert error.code == "AWP_WORKSPACE_ACTIVE_TASK_BLOCK"
    else:
        raise AssertionError("target-only active task did not block migration")
    steps.append("target-only-active-blocked")

    _, _, _, _, surface_digests = _runtime_surface_case(project)
    authorities = _route_authorities(surface_digests)
    _, first_task = _admit_indexed_task(
        project,
        authorities,
        transaction_id="23111111-1111-4111-8111-111111111111",
        approval_id="33111111-1111-4111-8111-111111111111",
        intent_id="clone-b-active",
        task_ref=".trellis/tasks/example",
        before_index=None,
        after_index=lambda task_id: {"active": [task_id]},
    )
    active_snapshot = _scan_migration_case(main_case)
    try:
        _migrate_case(
            main_case,
            active_snapshot,
            "43111111-1111-4111-8111-111111111111",
        )
    except RuntimeFailure as error:
        assert error.code == "AWP_WORKSPACE_ACTIVE_TASK_BLOCK"
    else:
        raise AssertionError("active task did not block workspace migration")
    steps.append("active-task-blocked")

    completed = transition_task(
        TaskTransitionRequest(
            project,
            first_task.task_ref,
            first_task.task_id,
            first_task.state_revision,
            "clone-b-first-completed",
            target_lifecycle_status="completed",
            target_phase=None,
            completion_flags=None,
            changed_at=NOW + timedelta(minutes=1),
        )
    )
    archived = archive_task(
        TaskArchiveRequest(
            project_root=project,
            transaction_id="24111111-1111-4111-8111-111111111111",
            task_ref=completed.task_ref,
            task_id=completed.task_id,
            expected_revision=completed.state_revision,
            archive_root=".trellis/tasks/archive",
            metadata_mutations=(
                _metadata_mutation(
                    {"active": [completed.task_id]},
                    {"active": [], "archived": [completed.task_id]},
                ),
            ),
            archived_at=NOW + timedelta(minutes=2),
        )
    )
    assert archived.lifecycle_status == "archived"
    steps.append("task-archived")

    archived_inventory = {
        "tasks": [{"task_id": archived.task_id, "task_ref": archived.task_ref}],
        "unfinished_task_journals": [],
        "active_pointers": [],
    }
    second_authorities = dataclasses.replace(
        authorities,
        task_inventory=archived_inventory,
        task_state_digest=digest(
            "agent-workflow.route-task-state.v1", archived_inventory
        ),
    )
    second_provisional = _admission_request(
        project,
        second_authorities,
        transaction_id="25111111-1111-4111-8111-111111111111",
        approval_id="35111111-1111-4111-8111-111111111111",
        metadata_mutation=_metadata_mutation(
            {"active": [], "archived": [archived.task_id]},
            {"active": ["pending-task"], "archived": [archived.task_id]},
        ),
        intent_id="clone-b-recovery",
    )
    second_task_id = str(second_provisional.decision["requested_task_id"])
    second_request = dataclasses.replace(
        second_provisional,
        metadata_mutations=(
            _metadata_mutation(
                {"active": [], "archived": [archived.task_id]},
                {"active": [second_task_id], "archived": [archived.task_id]},
            ),
        ),
    )
    original_task_crash = task_service_module._crash_at

    def planned_crash(point: str) -> None:
        if point == "after_planned":
            raise _InjectedTermination()

    task_service_module._crash_at = planned_crash
    try:
        try:
            admit_task(second_request)
        except _InjectedTermination:
            pass
        else:
            raise AssertionError("unfinished admission was not injected")
    finally:
        task_service_module._crash_at = original_task_crash

    unfinished_snapshot = _scan_migration_case(main_case)
    try:
        _migrate_case(
            main_case,
            unfinished_snapshot,
            "44111111-1111-4111-8111-111111111111",
        )
    except RuntimeFailure as error:
        assert error.code == "AWP_WORKSPACE_TASK_RECOVERY_BLOCK"
    else:
        raise AssertionError("unfinished transaction did not block migration")
    steps.append("unfinished-transaction-blocked")

    recovered = recover_task_transaction(
        TaskRecoveryRequest(
            project, "25111111-1111-4111-8111-111111111111", "resume"
        )
    )
    recovered_completed = transition_task(
        TaskTransitionRequest(
            project,
            recovered.task_ref,
            recovered.task_id,
            recovered.state_revision,
            "clone-b-recovered-completed",
            target_lifecycle_status="completed",
            target_phase=None,
            completion_flags=None,
            changed_at=NOW + timedelta(minutes=3),
        )
    )
    recovered_archived = archive_task(
        TaskArchiveRequest(
            project_root=project,
            transaction_id="26111111-1111-4111-8111-111111111111",
            task_ref=recovered_completed.task_ref,
            task_id=recovered_completed.task_id,
            expected_revision=recovered_completed.state_revision,
            archive_root=".trellis/tasks/archive",
            metadata_mutations=(
                _metadata_mutation(
                    {
                        "active": [recovered_completed.task_id],
                        "archived": [archived.task_id],
                    },
                    {
                        "active": [],
                        "archived": [archived.task_id, recovered_completed.task_id],
                    },
                ),
            ),
            archived_at=NOW + timedelta(minutes=4),
        )
    )
    assert recovered_archived.lifecycle_status == "archived"
    steps.append("transaction-recovered-and-archived")

    quiet_snapshot = _scan_migration_case(main_case)
    migration_transaction = "45111111-1111-4111-8111-111111111111"
    original_workspace_crash = workspace_module._crash_at

    def migration_crash(point: str) -> None:
        if point == "local_candidates_applied":
            raise _InjectedTermination()

    workspace_module._crash_at = migration_crash
    try:
        try:
            _migrate_case(main_case, quiet_snapshot, migration_transaction)
        except _InjectedTermination:
            pass
        else:
            raise AssertionError("workspace migration killpoint did not terminate")
    finally:
        workspace_module._crash_at = original_workspace_crash
    steps.append("migration-crashed")

    migrated = recover_workspace_migration(
        project,
        migration_transaction,
        action="resume",
        source_layout=main_case["source_layout"],
        target_layout=main_case["target_layout"],
        source_schemas=main_case["schemas"],
        target_schemas=main_case["schemas"],
        scanner=main_case["scanner"],
    )
    assert migrated.committed is True
    steps.append("migration-recovered")

    donor = _workspace_migration_case(workspace, "donor")
    donor_project = donor["project"]
    assert isinstance(donor_project, Path)
    _, _, _, _, donor_surface_digests = _runtime_surface_case(donor_project)
    donor_authorities = _route_authorities(donor_surface_digests)
    _, donor_task = _admit_indexed_task(
        donor_project,
        donor_authorities,
        transaction_id="27111111-1111-4111-8111-111111111111",
        approval_id="37111111-1111-4111-8111-111111111111",
        intent_id="clone-b-raced",
        task_ref=".trellis/tasks/raced",
        before_index=None,
        after_index=lambda task_id: {"active": [task_id]},
    )
    assert donor_task.lifecycle_status == "active"

    stale = _workspace_migration_case(workspace, "stale")
    stale_project = stale["project"]
    assert isinstance(stale_project, Path)
    stale_snapshot = _scan_migration_case(stale)
    stale_transaction = "46111111-1111-4111-8111-111111111111"

    def stale_mutation(point: str) -> None:
        if point == "local_candidates_applied":
            shutil.copytree(
                donor_project / ".trellis/tasks/raced",
                stale_project / ".trellis/tasks/raced",
            )

    workspace_module._crash_at = stale_mutation
    try:
        try:
            _migrate_case(stale, stale_snapshot, stale_transaction)
        except RuntimeFailure as error:
            assert error.code == "AWP_TASK_QUIESCENCE_CHANGED"
            assert "AWP_WORKSPACE_ACTIVE_TASK_BLOCK" in error.details[
                "secondary_diagnostics"
            ]
        else:
            raise AssertionError("stale task evidence was accepted")
    finally:
        workspace_module._crash_at = original_workspace_crash
    steps.append("stale-evidence-rejected")

    shutil.rmtree(stale_project / ".trellis/tasks/raced")
    recovery_layout = _verified_layout()
    recovery_schemas = _discovery_schemas()
    rolled_back = recover_workspace_migration(
        stale_project,
        stale_transaction,
        action="rollback",
        source_layout=recovery_layout,
        target_layout=recovery_layout,
        source_schemas=recovery_schemas,
        target_schemas=recovery_schemas,
        scanner=stale["scanner"],
    )
    assert rolled_back.committed is False
    steps.append("stale-migration-rolled-back")

    migrated_scan = _scan_migration_case(main_case)
    migrated_state = evaluate_workspace_state_quiescence(
        migrated_scan.snapshot, migrated_scan.findings
    )
    migrated_gate = evaluate_task_gate(
        "sync",
        CandidateImpact("none", (), (), False, "0" * 64),
        migrated_scan.snapshot,
        migrated_scan.findings,
    )
    migrated_diagnostic = build_workspace_diagnostic(
        command="doctor",
        relationship="matching",
        relationship_evidence="verified",
        discovery_evidence="verified",
        workspace_task_state=migrated_state,
        task_gate_result=migrated_gate,
    )
    _invoke_cli(
        ["doctor"],
        "doctor",
        "lifecycle",
        lambda _: migrated_diagnostic.to_document(),
        project,
    )
    steps.append("doctor")
    no_op = _invoke_cli(
        ["sync"],
        "sync",
        "reconcile",
        lambda _: _no_op_sync(project, migrated_scan),
        project,
    )
    assert no_op["result"]["no_op"] is True
    steps.append("no-op-sync")

    sibling = _workspace_migration_case(workspace, "sibling")
    sibling_project = sibling["project"]
    assert isinstance(sibling_project, Path)
    _, _, _, _, sibling_surface_digests = _runtime_surface_case(sibling_project)
    sibling_authorities = _route_authorities(sibling_surface_digests)
    _admit_indexed_task(
        sibling_project,
        sibling_authorities,
        transaction_id="28111111-1111-4111-8111-111111111111",
        approval_id="38111111-1111-4111-8111-111111111111",
        intent_id="clone-b-sibling-active",
        task_ref=".trellis/tasks/sibling-active",
        before_index=None,
        after_index=lambda task_id: {"active": [task_id]},
    )
    assert _scan_migration_case(main_case).findings["findings"] == []
    sibling_findings = [
        finding["kind"]
        for finding in _scan_migration_case(sibling).findings["findings"]
    ]
    assert sibling_findings == ["non-archived-task"]
    steps.append("checkout-local")

    workspace_document = json.loads(
        (project / ".agent-workflow/local/workspace.json").read_text(
            encoding="utf-8"
        )
    )
    target_identity = main_case["target_identity"]
    assert isinstance(target_identity, ReleaseIdentity)
    return {
        "steps": steps,
        "workspace_release_changed": workspace_document[
            "local_state_release_id"
        ]
        == target_identity.release_id,
        "manifest_bytes_unchanged": (
            project / ".agent-workflow/manifest.json"
        ).read_bytes()
        == main_case["manifest_bytes"],
        "checkout_local_visibility": sibling_findings == ["non-archived-task"],
    }


def clone_c_scenario(workspace: Path) -> dict[str, object]:
    case = _workspace_migration_case(workspace, "clone-c")
    project = case["project"]
    assert isinstance(project, Path)
    assert _launcher(project).is_file()
    scanned = _scan_migration_case(case)
    state = evaluate_workspace_state_quiescence(
        scanned.snapshot, scanned.findings
    )
    gate = evaluate_task_gate(
        "workspace-migrate",
        CandidateImpact("none", (), (), False, "0" * 64),
        scanned.snapshot,
        scanned.findings,
    )

    current = _release("0.1.0", "b")
    candidate_base = _release("0.2.0", "c")
    candidate = _with_edge(
        candidate_base, _compatibility_edge(current, candidate_base)
    )
    migration = classify_compatibility(current, candidate, _local_contract())
    ahead = classify_compatibility(candidate, current, _local_contract())

    current_empty = dataclasses.replace(
        current,
        compatibility=MappingProxyType(
            {
                "schema_id": "agent-workflow.release-compatibility",
                "schema_version": 1,
                "release_id": current.identity.release_id,
                "edges": [],
            }
        ),
    )
    candidate_empty = dataclasses.replace(
        candidate_base,
        compatibility=MappingProxyType(
            {
                "schema_id": "agent-workflow.release-compatibility",
                "schema_version": 1,
                "release_id": candidate_base.identity.release_id,
                "edges": [],
            }
        ),
    )
    diverged = classify_compatibility(
        current_empty, candidate_empty, _local_contract()
    )
    missing = classify_compatibility(current, candidate_base, _local_contract())

    invalid_edge = {
        **_compatibility_edge(current, candidate_base),
        "wheel_url": "https://invalid.example/wheel.whl",
    }
    invalid_candidate = dataclasses.replace(
        candidate_base,
        compatibility=MappingProxyType(
            {
                "schema_id": "agent-workflow.release-compatibility",
                "schema_version": 1,
                "release_id": candidate_base.identity.release_id,
                "edges": [invalid_edge],
            }
        ),
    )
    try:
        classify_compatibility(current, invalid_candidate, _local_contract())
    except LifecycleFailure as error:
        assert error.exit_code == 30
    else:
        raise AssertionError("invalid compatibility evidence was accepted")

    classifications = {
        "ahead": (ahead.relationship, "verified", "unsupported"),
        "diverged": (diverged.relationship, "verified", "verified"),
        "invalid": ("unknown", "invalid", "verified"),
        "missing": ("unknown", missing.relationship, "missing"),
        "migration-required": (
            migration.relationship,
            "verified",
            "verified",
        ),
    }
    relationships: dict[str, str] = {}
    blocked_exit_codes: dict[str, int] = {}
    doctor_allowed: list[bool] = []
    blocked_only_read_only: list[bool] = []
    command_independent: list[bool] = []

    command_specs = {
        "doctor": (["doctor"], "lifecycle"),
        "workspace-migrate": (["workspace", "migrate"], "runtime"),
        "sync": (["sync"], "reconcile"),
    }
    blocked_cases = {"ahead", "diverged", "invalid", "missing"}
    for case_id, (
        relationship,
        relationship_evidence,
        discovery_evidence,
    ) in classifications.items():
        diagnostics = {
            command: build_workspace_diagnostic(
                command=command,
                relationship=relationship,
                relationship_evidence=relationship_evidence,
                discovery_evidence=discovery_evidence,
                workspace_task_state=state,
                task_gate_result=gate,
            )
            for command in command_specs
        }
        relationships[case_id] = diagnostics[
            "doctor"
        ].workspace_state.relationship
        workspace_states = [
            diagnostic.workspace_state.to_document()
            for diagnostic in diagnostics.values()
        ]
        command_independent.append(
            all(candidate_state == workspace_states[0] for candidate_state in workspace_states)
        )

        doctor_diagnostic = diagnostics["doctor"]
        doctor_exit, doctor_result = _invoke_cli_result(
            ["doctor"],
            "doctor",
            "lifecycle",
            lambda _: doctor_diagnostic.to_document(),
            project,
            workspace_diagnostic=doctor_diagnostic.to_document(),
        )
        doctor_allowed.append(
            doctor_exit == 0
            and doctor_result["status"] == "success"
            and doctor_diagnostic.command_admission.allowed
        )

        non_read_only_allowed: list[bool] = []
        for command in ("workspace-migrate", "sync"):
            diagnostic = diagnostics[command]
            arguments, owner = command_specs[command]

            def invoke(_, selected=diagnostic):
                blocker = selected.command_admission.blocker
                if blocker is not None:
                    raise RuntimeFailure(blocker, "workspace state blocks command")
                return {"admitted": True}

            exit_code, result = _invoke_cli_result(
                arguments,
                command,
                owner,
                invoke,
                project,
                workspace_diagnostic=diagnostic.to_document(),
            )
            non_read_only_allowed.append(exit_code == 0)
            if case_id in blocked_cases:
                assert result["status"] in {"blocked", "error"}
                assert exit_code != 0
                if command == "workspace-migrate":
                    blocked_exit_codes[case_id] = exit_code
        if case_id in blocked_cases:
            blocked_only_read_only.append(not any(non_read_only_allowed))

    ahead_unsupported = build_workspace_diagnostic(
        command="doctor",
        relationship="ahead",
        relationship_evidence="verified",
        discovery_evidence="unsupported",
        workspace_task_state=state,
        task_gate_result=gate,
    )
    return {
        "relationships": relationships,
        "blocked_exit_codes": blocked_exit_codes,
        "doctor_allowed_for_all": all(doctor_allowed),
        "blocked_commands_are_read_only_only": all(blocked_only_read_only),
        "workspace_state_is_command_independent": all(command_independent),
        "unsupported_discovery_preserves_ahead": (
            ahead_unsupported.workspace_state.relationship == "ahead"
            and ahead_unsupported.workspace_state.primary_state_blocker
            == "AWP_WORKSPACE_CONTRACT_AHEAD"
        ),
    }


def main_probe() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario", choices=("distribution", "clone-a", "clone-b", "clone-c")
    )
    parser.add_argument("workspace", type=Path)
    arguments = parser.parse_args()
    if arguments.scenario == "distribution":
        return distribution_scenario(arguments.workspace)
    if arguments.scenario == "clone-a":
        print(json.dumps(clone_a_scenario(arguments.workspace), sort_keys=True))
        return 0
    if arguments.scenario == "clone-b":
        print(json.dumps(clone_b_scenario(arguments.workspace), sort_keys=True))
        return 0
    if arguments.scenario == "clone-c":
        print(json.dumps(clone_c_scenario(arguments.workspace), sort_keys=True))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main_probe())
