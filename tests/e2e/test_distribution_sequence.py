from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

from agent_stack.release.gates import (
    compute_distribution_render_digest,
    run_release_gates,
    verify_release_artifact_set,
)
from tests.e2e.artifact_support import (
    extracted_distribution_roots,
    run_scenario_probe,
)
ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "tests/fixtures/e2e/releases/final-artifact-contract.json"


def _contract() -> dict[str, object]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run_distribution_render_cli_matrix(tmp_path: Path) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for distribution, package_root in extracted_distribution_roots(
        tmp_path / "distributions"
    ).items():
        workspace = tmp_path / "workspaces" / distribution
        workspace.mkdir(parents=True)
        results[distribution] = run_scenario_probe(
            package_root, "distribution", workspace
        )
    return results


def test_final_distribution_installs_and_runs_without_mutating_frozen_bytes(
    tmp_path: Path,
) -> None:
    contract = _contract()
    artifact_set = verify_release_artifact_set(ROOT / "dist/release-artifact-set.json")
    before = {
        "wheel": _sha256(artifact_set.wheel.path),
        "sdist": _sha256(artifact_set.sdist.path),
    }

    assert artifact_set.artifact_set_digest == contract["artifact_set_digest"]
    assert before["wheel"] == contract["wheel_sha256"]
    assert before["sdist"] == contract["sdist_sha256"]
    assert artifact_set.distribution_render_digest == contract["render_digest"]
    assert compute_distribution_render_digest(artifact_set.git_inventory) == contract[
        "render_digest"
    ]
    assert compute_distribution_render_digest(artifact_set.wheel_inventory) == contract[
        "render_digest"
    ]
    assert compute_distribution_render_digest(artifact_set.sdist_inventory) == contract[
        "render_digest"
    ]
    assert run_release_gates(artifact_set)["status"] == "passed"

    environment = tmp_path / "wheel-env"
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = environment / "bin/python"
    executable = environment / "bin/agent-stack"
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    clean_env["PATH"] = f"{environment / 'bin'}:/usr/bin:/bin"
    subprocess.run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-index",
            artifact_set.wheel.path,
        ],
        check=True,
        cwd=tmp_path,
        env=clean_env,
        capture_output=True,
        text=True,
    )
    completed = subprocess.run(
        [executable, "--help"],
        check=False,
        cwd=tmp_path,
        env=clean_env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "agent-stack" in completed.stdout
    assert before == {
        "wheel": _sha256(artifact_set.wheel.path),
        "sdist": _sha256(artifact_set.sdist.path),
    }
    assert sys.version_info >= (3, 11)


def test_git_wheel_and_sdist_execute_identical_render_and_cli_flow(
    tmp_path: Path,
) -> None:
    results = run_distribution_render_cli_matrix(tmp_path)

    assert set(results) == {"git-checkout", "sdist", "wheel"}
    assert len({json.dumps(result, sort_keys=True) for result in results.values()}) == 1
    result = results["wheel"]
    assert result["status"] == "success"
    assert result["command"] == "doctor"
    assert result["result"]["rendered_paths"] == [".agent-workflow/probe.txt"]
