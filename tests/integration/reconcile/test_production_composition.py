from __future__ import annotations

from pathlib import Path
import shutil
from types import MappingProxyType

from agent_stack.cli.parser import CommandInvocation
from agent_stack.cli.production import ProductionCommand
from agent_stack.reconcile import commands
from agent_stack.reconcile.production_bundle import load_production_bundle
from agent_stack.release.identity import ReleaseIdentity
from agent_stack.release.manifest import VerifiedRelease


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
        assets={},
        immutable_release=True,
    )


def _command(root: Path, *, dry_run: bool) -> ProductionCommand:
    return ProductionCommand(
        invocation=CommandInvocation(
            command="init",
            options=MappingProxyType({"dry_run": dry_run}),
            json_output=True,
            debug=False,
        ),
        repository_root=root,
    )


def _installed_data_tree(root: Path) -> Path:
    data = root / "installed-data"
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

    result = commands.run_init(_command(project, dry_run=False))

    assert result["committed"] is True
    assert (project / "user.txt").read_text(encoding="utf-8") == "keep me\n"
    assert (project / "AGENTS.md").read_text(encoding="utf-8").startswith(
        "User instructions stay.\n"
    )
    assert (project / ".agents/skills/agent-workflow/SKILL.md").is_file()
    assert (project / ".agent-workflow/bin/codex-wrapper").is_file()
    assert (project / ".agent-workflow/manifest.json").is_file()
    assert (project / ".agent-workflow/local/workspace.json").is_file()
    assert (project / ".agent-workflow/local/approval-replay.json").is_file()
