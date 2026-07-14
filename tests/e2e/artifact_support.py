from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_SET_PATH = ROOT / "dist/release-artifact-set.json"
PROBE_PATH = ROOT / "tests/e2e/scenario_probe.py"


def extracted_distribution_roots(tmp_path: Path) -> dict[str, Path]:
    tmp_path.mkdir(parents=True)
    document = json.loads(ARTIFACT_SET_PATH.read_text(encoding="utf-8"))
    records = {
        str(record["kind"]): ROOT / str(record["path"])
        for record in document["artifacts"]
    }

    wheel_root = tmp_path / "wheel"
    wheel_root.mkdir()
    with zipfile.ZipFile(records["wheel"]) as archive:
        archive.extractall(wheel_root)

    sdist_container = tmp_path / "sdist"
    sdist_container.mkdir()
    with tarfile.open(records["sdist"], "r:gz") as archive:
        archive.extractall(sdist_container, filter="data")
    sdist_roots = [path for path in sdist_container.iterdir() if path.is_dir()]
    assert len(sdist_roots) == 1

    return {
        "git-checkout": ROOT / "src",
        "sdist": sdist_roots[0] / "src",
        "wheel": wheel_root,
    }


def run_scenario_probe(
    package_root: Path,
    scenario: str,
    workspace: Path,
) -> dict[str, object]:
    environment = os.environ.copy()
    environment["AWP_EXPECT_AGENT_STACK_ROOT"] = str(package_root)
    environment["PYTHONPATH"] = str(package_root)
    completed = subprocess.run(
        [sys.executable, str(PROBE_PATH), scenario, str(workspace)],
        cwd=workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert isinstance(value, dict)
    return value
