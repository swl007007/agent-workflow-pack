from __future__ import annotations

import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "tests/fixtures/e2e/acceptance-matrix.json"
LIFECYCLE_SPEC = (
    ROOT
    / "docs/superpowers/specs/2026-07-13-agent-workflow-pack-lifecycle-release-design.md"
)
EXPECTED_IDS = tuple(f"AC-{index:02d}" for index in range(1, 65))
ROW_FIELDS = {
    "ac_id",
    "primary_owner",
    "scenario_group",
    "primary_node",
    "supporting_nodes",
}
SPEC_OWNER_ROW = re.compile(r"^\| (AC-\d{2}) \| (Task [1-6]) \|")
SCENARIO_NODES = {
    "distribution": (
        "tests/e2e/test_distribution_sequence.py::"
        "test_git_wheel_and_sdist_execute_identical_render_and_cli_flow"
    ),
    "clone-a": (
        "tests/e2e/test_clone_a_lifecycle.py::"
        "test_clone_a_executes_continuous_recovery_and_upgrade_sequence"
    ),
    "clone-b": (
        "tests/e2e/test_clone_b_workspace_migration.py::"
        "test_clone_b_executes_continuous_pull_gate_and_migration_sequence"
    ),
    "clone-c": (
        "tests/e2e/test_clone_c_relationship_diagnostics.py::"
        "test_clone_c_executes_continuous_relationship_diagnostic_sequence"
    ),
}


def _matrix() -> dict[str, object]:
    document = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _criteria() -> list[dict[str, object]]:
    document = _matrix()
    assert set(document) == {"schema_id", "schema_version", "criteria"}
    assert document["schema_id"] == "agent-workflow.acceptance-matrix"
    assert document["schema_version"] == 1
    rows = document["criteria"]
    assert isinstance(rows, list)
    assert all(isinstance(row, dict) for row in rows)
    return rows


def _frozen_owners() -> dict[str, str]:
    owners: dict[str, str] = {}
    for line in LIFECYCLE_SPEC.read_text(encoding="utf-8").splitlines():
        match = SPEC_OWNER_ROW.match(line)
        if match:
            ac_id, owner = match.groups()
            assert ac_id not in owners
            owners[ac_id] = owner
    return owners


def _node_parts(node: str) -> tuple[Path, str, str | None]:
    relative, separator, selector = node.partition("::")
    assert separator and relative.startswith("tests/")
    base_selector, bracket, parameter = selector.partition("[")
    parameter_id = parameter.removesuffix("]") if bracket else None
    return ROOT / relative, base_selector, parameter_id


def _defined_tests(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def test_acceptance_matrix_has_exact_frozen_ids_and_owners() -> None:
    rows = _criteria()
    assert len(rows) == 64
    assert all(set(row) == ROW_FIELDS for row in rows)
    assert tuple(row["ac_id"] for row in rows) == EXPECTED_IDS
    assert len({row["ac_id"] for row in rows}) == 64
    assert _frozen_owners() == {
        str(row["ac_id"]): str(row["primary_owner"]) for row in rows
    }


def test_every_ac_has_one_unique_primary_node_and_real_support() -> None:
    rows = _criteria()
    primary_nodes = [str(row["primary_node"]) for row in rows]
    assert len(primary_nodes) == len(set(primary_nodes)) == 64

    for row in rows:
        assert row["scenario_group"] in {"distribution", "clone-a", "clone-b", "clone-c"}
        primary_path, primary_test, parameter_id = _node_parts(str(row["primary_node"]))
        assert primary_path.is_file(), f"missing primary scenario: {primary_path}"
        assert primary_test in _defined_tests(primary_path)
        assert parameter_id is None

        supporting_nodes = row["supporting_nodes"]
        assert isinstance(supporting_nodes, list) and supporting_nodes
        for support in supporting_nodes:
            assert isinstance(support, str)
            support_path, support_test, support_parameter = _node_parts(support)
            assert support_path.is_file(), f"missing support suite: {support_path}"
            assert support_test in _defined_tests(support_path), support
            assert support_parameter is None


def test_primary_evidence_is_behavioral_and_each_row_references_its_e2e_scenario() -> None:
    for row in _criteria():
        scenario_group = str(row["scenario_group"])
        primary_path, primary_test, parameter_id = _node_parts(str(row["primary_node"]))
        assert parameter_id is None
        assert primary_test != "test_acceptance_evidence"
        assert primary_path != Path(__file__).resolve()

        supporting_nodes = row["supporting_nodes"]
        assert isinstance(supporting_nodes, list)
        assert SCENARIO_NODES[scenario_group] in supporting_nodes
