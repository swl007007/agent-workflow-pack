from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from agent_stack.cli.parser import CommandInvocation
from agent_stack.cli.production import ProductionCommand
from agent_stack.reconcile import commands
from agent_stack.reconcile.production_bundle import load_production_bundle


ROOT = Path(__file__).resolve().parents[3]


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
    command = ProductionCommand(
        invocation=CommandInvocation(
            command="init",
            options=MappingProxyType({"dry_run": True}),
            json_output=True,
            debug=False,
        ),
        repository_root=tmp_path,
    )

    result = commands.run_init(command)

    assert loaded == [ROOT]
    assert result["planned_paths"] == [
        ".agent-workflow/bin/codex-wrapper",
        ".agents/skills/agent-workflow/SKILL.md",
        "AGENTS.md",
    ]
    assert result["writes_performed"] == 0
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before
