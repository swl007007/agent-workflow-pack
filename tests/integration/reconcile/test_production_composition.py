from __future__ import annotations

from pathlib import Path
import shutil
import json
import subprocess
from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

import pytest

from agent_stack.cli.parser import CommandInvocation
from agent_stack.core.api import canonical_json_bytes, compute_surface_digests, validate_surface_registry
from agent_stack.cli.production import ProductionCommand
from agent_stack.reconcile import commands
from agent_stack.release import commands as release_commands
from agent_stack.reconcile.production_bundle import load_production_bundle
from agent_stack.release.identity import ReleaseIdentity
from agent_stack.release.manifest import VerifiedRelease
from agent_stack.runtime import commands as runtime_commands
from agent_stack.runtime.task_service import admit_task
from agent_stack.runtime.errors import RuntimeFailure
from tests.integration.runtime.test_task_admission import admission_request, initialize_project


ROOT = Path(__file__).resolve().parents[3]


def _verified_release() -> VerifiedRelease:
    return VerifiedRelease(
        identity=ReleaseIdentity(
            "github.com/swl007007/agent-workflow-pack",
            "agent-workflow-pack",
            "0.1.0",
        ),
        manifest_digest="a" * 64,
        source_commit="b" * 40,
        bundles={
            "trust_policy": "1" * 64,
            "workflow_lock": "2" * 64,
            "artifact": "3" * 64,
            "schema": "4" * 64,
            "migration": "5" * 64,
            "compatibility": "6" * 64,
            "launcher": "7" * 64,
        },
        assets={
            "wheel": {
                "url": "https://github.com/swl007007/agent-workflow-pack/releases/download/v0.1.0/agent_workflow_pack-0.1.0-py3-none-any.whl",
                "sha256": "8" * 64,
                "size": 1,
            }
        },
        immutable_release=True,
    )


def _command(
    root: Path, *, dry_run: bool, command: str = "init"
) -> ProductionCommand:
    return ProductionCommand(
        invocation=CommandInvocation(
            command=command,
            options=MappingProxyType({"dry_run": dry_run}),
            json_output=True,
            debug=False,
        ),
        repository_root=root,
    )


def _launcher_command(
    root: Path,
    caller_root: Path,
    *,
    command: str = "workspace-register",
    options: Mapping[str, object] | None = None,
) -> ProductionCommand:
    home = caller_root / "home"
    config = home / ".codex"
    harness = home / "bin/codex"
    config.mkdir(parents=True)
    harness.parent.mkdir(parents=True)
    harness.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    harness.chmod(0o755)
    return ProductionCommand(
        invocation=CommandInvocation(
            command=command,
            options=options or MappingProxyType({}),
            json_output=True,
            debug=False,
        ),
        repository_root=root,
        caller_context_version=1,
        caller_fields=MappingProxyType(
            {
                "platform": "codex",
                "user_home": str(home),
                "config_root.codex_home": str(config),
                "harness_executable": str(harness),
                "harness_version_probe_id": "codex-version-v1",
                "tty": (
                    "stdin=false,stdout=false,stderr=false,"
                    "direct_confirmation_capable=false"
                ),
            }
        ),
    )


def _installed_data_tree(root: Path) -> Path:
    data = root / "package/agent_stack/data"
    for name in (
        "artifact-definitions",
        "catalog",
        "profiles",
        "release",
        "runtime-launcher",
        "schemas",
        "templates",
    ):
        shutil.copytree(ROOT / name, data / name)
    module = data.parent / "reconcile/production_bundle.py"
    module.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "src/agent_stack/reconcile/production_bundle.py", module)
    for path in data.rglob("*"):
        if path.is_file():
            path.chmod(0o644)
    module.chmod(0o644)
    return data


def test_init_dry_run_uses_the_closed_production_bundle_without_writes(
    tmp_path: Path, monkeypatch
) -> None:
    loaded: list[Path] = []

    def load(root: Path):
        loaded.append(root)
        return load_production_bundle(ROOT)

    monkeypatch.setattr(commands, "load_production_bundle", load, raising=False)
    monkeypatch.setattr(commands, "_data_root", lambda: ROOT)
    monkeypatch.setattr(commands, "_authorize_running_release", lambda: object())
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    command = _command(tmp_path, dry_run=True)

    result = commands.run_init(command)

    assert loaded == [ROOT]
    assert result["planned_paths"] == [
        ".agent-workflow/bin/codex-wrapper",
        ".agents/skills/agent-workflow/SKILL.md",
        ".gitignore",
        "AGENTS.md",
    ]
    assert result["writes_performed"] == 0
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before


def test_init_apply_uses_real_bundle_and_commits_complete_project_contract(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = _installed_data_tree(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    (project / ".trellis").mkdir()
    (project / ".specify").mkdir()
    (project / "user.txt").write_text("keep me\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("User instructions stay.\n", encoding="utf-8")
    monkeypatch.setattr(commands, "_data_root", lambda: data_root)
    monkeypatch.setattr(commands, "_authorize_running_release", _verified_release)
    monkeypatch.setattr(release_commands, "_data_root", lambda: data_root)
    monkeypatch.setattr(
        release_commands, "_authorize_running_release", _verified_release
    )

    result = commands.run_init(_command(project, dry_run=False))

    assert result["committed"] is True
    assert (project / "user.txt").read_text(encoding="utf-8") == "keep me\n"
    assert (project / "AGENTS.md").read_text(encoding="utf-8").startswith(
        "User instructions stay.\n"
    )
    assert (project / ".agents/skills/agent-workflow/SKILL.md").is_file()
    assert (project / ".agent-workflow/bin/codex-wrapper").is_file()
    assert (project / ".agent-workflow/bin/agent-stack").is_file()
    assert (project / ".agent-workflow/runtime-control.json").is_file()
    assert (project / ".agent-workflow/workflow.lock").is_file()
    assert (project / ".agent-workflow/manifest.json").is_file()
    assert (project / ".agent-workflow/local/workspace.json").is_file()
    assert (project / ".agent-workflow/local/approval-replay.json").is_file()
    doctor = release_commands.run_doctor(
        _command(project, dry_run=False, command="doctor")
    )
    assert doctor["initialized"] is True
    assert doctor["authority_verified"] is True

    manifest_path = project / ".agent-workflow/manifest.json"
    generation = json.loads(manifest_path.read_text(encoding="utf-8"))["generation"]
    transaction_paths = sorted(
        path.name for path in (project / ".agent-workflow/transactions").glob("*.json")
    )
    before = {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    }

    preview = commands.run_sync(_command(project, dry_run=True, command="sync"))
    first_sync = commands.run_sync(_command(project, dry_run=False, command="sync"))
    second_sync = commands.run_sync(_command(project, dry_run=False, command="sync"))

    assert preview["no_op"] is True
    assert preview["writes_performed"] == 0
    assert first_sync["no_op"] is True
    assert second_sync["no_op"] is True
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["generation"] == generation
    assert sorted(
        path.name for path in (project / ".agent-workflow/transactions").glob("*.json")
    ) == transaction_paths
    assert {
        path.relative_to(project).as_posix(): path.read_bytes()
        for path in project.rglob("*")
        if path.is_file()
    } == before


def test_production_workspace_register_recreates_clone_local_contract(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = _installed_data_tree(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    monkeypatch.setattr(commands, "_data_root", lambda: data_root)
    monkeypatch.setattr(commands, "_authorize_running_release", _verified_release)

    commands.run_init(_command(project, dry_run=False))
    local = project / ".agent-workflow/local"
    shutil.rmtree(local)
    manifest = json.loads(
        (project / ".agent-workflow/manifest.json").read_text(encoding="utf-8")
    )
    release = _verified_release()
    registered_release = VerifiedRelease(
        identity=release.identity,
        manifest_digest=release.manifest_digest,
        source_commit=release.source_commit,
        bundles={
            **dict(release.bundles),
            "artifact": manifest["artifact_bundle_digest"],
            "workflow_lock": manifest["lock_digest"],
            "trust_policy": manifest["release_trust_policy_digest"],
        },
        assets=release.assets,
        immutable_release=True,
    )
    monkeypatch.setattr(
        runtime_commands, "_authorize_running_release", lambda: registered_release
    )
    monkeypatch.setattr(runtime_commands, "_data_root", lambda: data_root)

    result = runtime_commands.run_workspace_register(
        _launcher_command(project, tmp_path / "caller")
    )

    assert result["committed"] is True
    assert (local / "workspace.json").is_file()
    assert (local / "approval-replay.json").is_file()


def test_production_task_claim_loads_real_integration_and_calls_domain_service(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = _installed_data_tree(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    monkeypatch.setattr(commands, "_data_root", lambda: data_root)
    monkeypatch.setattr(commands, "_authorize_running_release", _verified_release)
    commands.run_init(_command(project, dry_run=False))

    task_source = tmp_path / "task-source"
    initialize_project(task_source)
    admitted = admit_task(admission_request(task_source, route="speckit-superpowers"))
    source = task_source / admitted.task_ref
    target = project / admitted.task_ref
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    manifest = json.loads(
        (project / ".agent-workflow/manifest.json").read_text(encoding="utf-8")
    )
    release = _verified_release()
    registered_release = VerifiedRelease(
        identity=release.identity,
        manifest_digest=release.manifest_digest,
        source_commit=release.source_commit,
        bundles={
            **dict(release.bundles),
            "artifact": manifest["artifact_bundle_digest"],
            "workflow_lock": manifest["lock_digest"],
            "trust_policy": manifest["release_trust_policy_digest"],
        },
        assets=release.assets,
        immutable_release=True,
    )
    monkeypatch.setattr(
        runtime_commands, "_authorize_running_release", lambda: registered_release
    )
    monkeypatch.setattr(runtime_commands, "_data_root", lambda: data_root)
    command = _launcher_command(
        project,
        tmp_path / "caller-claim",
        command="task-claim",
        options=MappingProxyType(
            {
                "task_ref": admitted.task_ref,
                "revision": admitted.state_revision,
                "executor": "speckit-implement",
            }
        ),
    )

    result = runtime_commands.run_task_claim(command)

    assert result["state_revision"] == admitted.state_revision + 1
    assert result["executor_claim"]["executor"] == "speckit-implement"

    released = runtime_commands.run_task_release(
        _launcher_command(
            project,
            tmp_path / "caller-release",
            command="task-release",
            options=MappingProxyType(
                {
                    "task_ref": admitted.task_ref,
                    "revision": result["state_revision"],
                    "executor": "speckit-implement",
                }
            ),
        )
    )

    assert released["state_revision"] == result["state_revision"] + 1
    assert released["executor_claim"] is None


def test_production_native_task_transition_calls_domain_service(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = _installed_data_tree(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    monkeypatch.setattr(commands, "_data_root", lambda: data_root)
    monkeypatch.setattr(commands, "_authorize_running_release", _verified_release)
    commands.run_init(_command(project, dry_run=False))

    task_source = tmp_path / "native-source"
    initialize_project(task_source)
    admitted = admit_task(admission_request(task_source))
    target = project / admitted.task_ref
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(task_source / admitted.task_ref, target)
    manifest = json.loads(
        (project / ".agent-workflow/manifest.json").read_text(encoding="utf-8")
    )
    release = _verified_release()
    registered_release = VerifiedRelease(
        identity=release.identity,
        manifest_digest=release.manifest_digest,
        source_commit=release.source_commit,
        bundles={
            **dict(release.bundles),
            "artifact": manifest["artifact_bundle_digest"],
            "workflow_lock": manifest["lock_digest"],
            "trust_policy": manifest["release_trust_policy_digest"],
        },
        assets=release.assets,
        immutable_release=True,
    )
    monkeypatch.setattr(
        runtime_commands, "_authorize_running_release", lambda: registered_release
    )
    monkeypatch.setattr(runtime_commands, "_data_root", lambda: data_root)

    result = runtime_commands.run_task_transition(
        _launcher_command(
            project,
            tmp_path / "caller-transition",
            command="task-transition",
            options=MappingProxyType(
                {
                    "task_ref": admitted.task_ref,
                    "revision": admitted.state_revision,
                    "target_status": "completed",
                }
            ),
        )
    )

    assert result["lifecycle_status"] == "completed"
    assert result["state_revision"] == admitted.state_revision + 1

    archived = runtime_commands.run_task_archive(
        _launcher_command(
            project,
            tmp_path / "caller-archive",
            command="task-archive",
            options=MappingProxyType(
                {
                    "task_ref": admitted.task_ref,
                    "revision": result["state_revision"],
                }
            ),
        )
    )

    assert archived["lifecycle_status"] == "archived"
    assert not (project / admitted.task_ref).exists()
    assert (
        project
        / f".trellis/tasks/archive/example--{admitted.task_id}/integration.yaml"
    ).is_file()


def test_production_task_recover_resumes_exact_unfinished_journal(
    tmp_path: Path, monkeypatch
) -> None:
    import agent_stack.runtime.task_service as task_service_module

    data_root = _installed_data_tree(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    monkeypatch.setattr(commands, "_data_root", lambda: data_root)
    monkeypatch.setattr(commands, "_authorize_running_release", _verified_release)
    commands.run_init(_command(project, dry_run=False))
    manifest = json.loads(
        (project / ".agent-workflow/manifest.json").read_text(encoding="utf-8")
    )
    workspace = json.loads(
        (project / ".agent-workflow/local/workspace.json").read_text(encoding="utf-8")
    )
    release = _verified_release()
    registered_release = VerifiedRelease(
        identity=release.identity,
        manifest_digest=release.manifest_digest,
        source_commit=release.source_commit,
        bundles={
            **dict(release.bundles),
            "artifact": manifest["artifact_bundle_digest"],
            "workflow_lock": manifest["lock_digest"],
            "trust_policy": manifest["release_trust_policy_digest"],
        },
        assets=release.assets,
        immutable_release=True,
    )
    monkeypatch.setattr(
        runtime_commands, "_authorize_running_release", lambda: registered_release
    )
    monkeypatch.setattr(runtime_commands, "_data_root", lambda: data_root)
    request = admission_request(project)
    request = replace(
        request,
        project_id=manifest["project_id"],
        workspace_instance_id=workspace["workspace_instance_id"],
        approval_proof={
            **dict(request.approval_proof),
            "workspace_instance_id": workspace["workspace_instance_id"],
        },
        current_authorities={
            "workspace_instance_id": workspace["workspace_instance_id"]
        },
        recovery_runtime={
            "runtime_role": "committed",
            "release_id": registered_release.identity.release_id,
            "release_manifest_digest": registered_release.manifest_digest,
        },
    )

    def crash(point: str) -> None:
        if point == "after_staged":
            raise RuntimeError("simulated crash")

    monkeypatch.setattr(task_service_module, "_crash_at", crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        admit_task(request)
    monkeypatch.setattr(task_service_module, "_crash_at", lambda point: None)

    result = runtime_commands.run_task_recover(
        _launcher_command(
            project,
            tmp_path / "caller-recover",
            command="task-recover",
            options=MappingProxyType(
                {
                    "transaction_id": request.transaction_id,
                    "recovery_action": "resume",
                }
            ),
        )
    )

    assert result["outcome"] == "committed"
    assert result["lifecycle_status"] == "active"


def test_production_runtime_load_uses_packaged_registry_and_installed_paths(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = _installed_data_tree(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    monkeypatch.setattr(commands, "_data_root", lambda: data_root)
    monkeypatch.setattr(commands, "_authorize_running_release", _verified_release)
    commands.run_init(_command(project, dry_run=False))
    manifest = json.loads(
        (project / ".agent-workflow/manifest.json").read_text(encoding="utf-8")
    )
    release = _verified_release()
    registered_release = VerifiedRelease(
        identity=release.identity,
        manifest_digest=release.manifest_digest,
        source_commit=release.source_commit,
        bundles={
            **dict(release.bundles),
            "artifact": manifest["artifact_bundle_digest"],
            "workflow_lock": manifest["lock_digest"],
            "trust_policy": manifest["release_trust_policy_digest"],
        },
        assets=release.assets,
        immutable_release=True,
    )
    monkeypatch.setattr(
        runtime_commands, "_authorize_running_release", lambda: registered_release
    )
    monkeypatch.setattr(runtime_commands, "_data_root", lambda: data_root)

    bundle = load_production_bundle(data_root)
    registry = validate_surface_registry(
        bundle.surface_registry, bundle.runtime_unit_inventory
    )
    pins = compute_surface_digests(
        registry, runtime_commands._runtime_evidence(bundle, project)
    )
    task_source = tmp_path / "runtime-source"
    initialize_project(task_source)
    admitted = admit_task(admission_request(task_source))
    integration = json.loads(
        (task_source / admitted.task_ref / "integration.yaml").read_text(encoding="utf-8")
    )
    integration["workflow_contract"]["task_contract_surfaces"] = [
        {"surface_id": surface_id, "surface_digest": pins[surface_id]}
        for surface_id in sorted(pins)
    ]
    target = project / admitted.task_ref
    target.mkdir(parents=True)
    (target / "README.md").write_text("# Task\n", encoding="utf-8")
    (target / "integration.yaml").write_bytes(canonical_json_bytes(integration))
    (target / "integration.yaml").chmod(0o640)

    result = runtime_commands.run_task_runtime_load(
        _launcher_command(
            project,
            tmp_path / "caller-runtime-load",
            command="task-runtime-load",
            options=MappingProxyType(
                {
                    "task_ref": admitted.task_ref,
                    "task_id": admitted.task_id,
                    "revision": admitted.state_revision,
                    "phase": "none",
                    "claim": "none",
                    "surface": "platform-adapter:codex",
                    "entry": "codex-wrapper",
                }
            ),
        )
    )

    assert result["runtime_entry_id"] == "codex-wrapper"
    assert "render-unit:codex-wrapper" in result["unit_ids"]


def test_public_task_admit_fails_at_missing_platform_approval_not_placeholder(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = _installed_data_tree(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    monkeypatch.setattr(commands, "_data_root", lambda: data_root)
    monkeypatch.setattr(commands, "_authorize_running_release", _verified_release)
    commands.run_init(_command(project, dry_run=False))
    manifest = json.loads(
        (project / ".agent-workflow/manifest.json").read_text(encoding="utf-8")
    )
    release = _verified_release()
    registered_release = VerifiedRelease(
        identity=release.identity,
        manifest_digest=release.manifest_digest,
        source_commit=release.source_commit,
        bundles={
            **dict(release.bundles),
            "artifact": manifest["artifact_bundle_digest"],
            "workflow_lock": manifest["lock_digest"],
            "trust_policy": manifest["release_trust_policy_digest"],
        },
        assets=release.assets,
        immutable_release=True,
    )
    monkeypatch.setattr(
        runtime_commands, "_authorize_running_release", lambda: registered_release
    )
    monkeypatch.setattr(runtime_commands, "_data_root", lambda: data_root)

    with pytest.raises(RuntimeFailure) as captured:
        runtime_commands.run_task_admit(
            _launcher_command(
                project,
                tmp_path / "caller-admit",
                command="task-admit",
                options=MappingProxyType({"task_ref": ".trellis/tasks/new"}),
            )
        )

    assert captured.value.code == "AWP_ROUTE_APPROVAL_INVALID"
