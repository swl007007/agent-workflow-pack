from __future__ import annotations

import json
import os
import subprocess
import venv
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _installed_console(tmp_path: Path) -> Path:
    wheel_dir = tmp_path / "wheel"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", wheel_dir],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(wheel_dir.glob("agent_workflow_pack-*.whl"))
    assert len(wheels) == 1

    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = environment / "bin/python"
    subprocess.run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-index",
            wheels[0],
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return environment / "bin/agent-stack"


@pytest.fixture(scope="module")
def installed_console(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _installed_console(tmp_path_factory.mktemp("installed-console"))


@pytest.mark.parametrize("command", [["bootstrap"], ["init", "--dry-run"]])
def test_unpublished_installed_console_reaches_release_gate_without_project_writes(
    tmp_path: Path, installed_console: Path,
    command: list[str],
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"}
    }

    completed = subprocess.run(
        [installed_console, *command, "--json"],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    document = json.loads(completed.stdout)

    assert completed.returncode == 30, completed.stderr
    assert document["status"] == "error"
    assert document["errors"][0]["code"] == "AWP_RELEASE_MANIFEST_INVALID"
    assert sorted(project.iterdir()) == []


def test_installed_console_test_routing_uses_production_owner_without_release_fetch(
    tmp_path: Path, installed_console: Path
) -> None:
    project = tmp_path / "test-routing"
    project.mkdir()

    completed = subprocess.run(
        [installed_console, "test-routing", "--json"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    document = json.loads(completed.stdout)

    assert completed.returncode == 0, document
    assert document["status"] == "success"
    assert all(
        error["code"] != "AWP_CLI_OWNER_UNAVAILABLE"
        for error in document["errors"]
    )


@pytest.mark.parametrize("command", [["doctor"], ["sync", "--dry-run"]])
def test_unpublished_release_dependent_commands_fail_closed_without_writes(
    tmp_path: Path, installed_console: Path, command: list[str]
) -> None:
    project = tmp_path / command[0]
    project.mkdir()
    sentinel = project / "user.txt"
    sentinel.write_text("preserve me\n", encoding="utf-8")

    completed = subprocess.run(
        [installed_console, *command, "--json"],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )
    document = json.loads(completed.stdout)

    assert completed.returncode == 30, document
    assert document["status"] == "error"
    assert document["errors"][0]["code"] == "AWP_RELEASE_MANIFEST_INVALID"
    assert sentinel.read_text(encoding="utf-8") == "preserve me\n"
    assert sorted(path.name for path in project.iterdir()) == ["user.txt"]
