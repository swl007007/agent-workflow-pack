from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import agent_stack


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "tests/fixtures/e2e/acceptance-matrix.json"
ARTIFACT_SET_PATH = ROOT / "dist/release-artifact-set.json"


def _frozen_acceptance_nodes() -> tuple[str, ...]:
    document = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = document["criteria"]
    nodes: list[str] = []
    for row in rows:
        nodes.append(str(row["primary_node"]))
        nodes.extend(str(node) for node in row["supporting_nodes"])
    return tuple(dict.fromkeys(nodes))


def _absolute_acceptance_nodes() -> tuple[str, ...]:
    resolved: list[str] = []
    for node in _frozen_acceptance_nodes():
        relative, separator, selector = node.partition("::")
        assert separator
        resolved.append(f"{(ROOT / relative).resolve()}::{selector}")
    return tuple(resolved)


def _artifact_paths(tmp_path: Path) -> dict[str, Path]:
    document = json.loads(ARTIFACT_SET_PATH.read_text(encoding="utf-8"))
    records = {str(record["kind"]): ROOT / str(record["path"]) for record in document["artifacts"]}

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


def run_frozen_acceptance_suite(tmp_path: Path) -> dict[str, int]:
    nodes = _absolute_acceptance_nodes()
    assert len(nodes) == 68
    executed: dict[str, int] = {}
    for distribution, package_root in _artifact_paths(tmp_path).items():
        child_cwd = tmp_path / "child-cwds" / distribution
        child_cwd.mkdir(parents=True)
        environment = os.environ.copy()
        environment["AWP_EXPECT_AGENT_STACK_ROOT"] = str(package_root)
        environment["PYTHONPATH"] = str(package_root)
        environment.pop("PYTEST_ADDOPTS", None)
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                f"{Path(__file__).resolve()}::test_agent_stack_origin_matches_requested_distribution",
                *nodes,
                "-q",
            ],
            cwd=child_cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, (
            f"{distribution} acceptance failed\n{completed.stdout}\n{completed.stderr}"
        )
        executed[distribution] = len(nodes)
    return executed


def test_agent_stack_origin_matches_requested_distribution() -> None:
    expected_root = Path(os.environ.get("AWP_EXPECT_AGENT_STACK_ROOT", ROOT / "src"))
    package_path = Path(agent_stack.__file__).resolve()

    assert package_path.is_relative_to(expected_root.resolve())


def test_frozen_nodes_are_absolute_for_isolated_child_execution() -> None:
    nodes = _absolute_acceptance_nodes()

    assert nodes
    assert all(Path(node.partition("::")[0]).is_absolute() for node in nodes)
    assert all(str(ROOT) in node for node in nodes)


def test_frozen_acceptance_suite_executes_from_git_wheel_and_sdist(
    tmp_path: Path,
) -> None:
    executed = run_frozen_acceptance_suite(tmp_path)

    assert executed == {"git-checkout": 68, "sdist": 68, "wheel": 68}
