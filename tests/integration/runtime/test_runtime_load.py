from __future__ import annotations

import dataclasses
import hashlib
import os
from pathlib import Path

import pytest

from agent_stack.core.api import canonical_json_bytes, compute_surface_digests, validate_surface_registry
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.runtime_load import (
    RuntimeEntryDescriptor,
    TaskRuntimeLoadRequest,
    load_task_runtime,
)
from tests.contracts.runtime.test_integration import integration_document


TASK_ID = "5f477c7f-a1dc-4a16-8f75-39f153170222"
TASK_REF = ".trellis/tasks/example"


def surface(surface_id: str, kind: str, unit_id: str, references: list[str]):
    return {
        "surface_id": surface_id,
        "surface_kind": kind,
        "descriptor_version": 1,
        "digest_recipe_id": "surface-content-v1",
        "owned_unit_ids": [unit_id],
        "references": references,
        "contract_change_class": "runtime-visible",
    }


def unit(unit_id: str, owner: str, path: str, scope: str):
    return {
        "unit_id": unit_id,
        "unit_kind": unit_id.split(":", 1)[0],
        "distribution_scope": scope,
        "normalized_path": path,
        "owning_surface_id": owner,
        "leaf_recipe_id": "bytes-mode-contract-v1",
        "runtime_visible": True,
    }


def write_file(path: Path, payload: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    os.chmod(path, mode)


def load_case(tmp_path: Path):
    package_root = tmp_path / "package"
    project_root = tmp_path / "project"
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
        write_file(path, payload)
    registry_document = {
        "schema_id": "agent-workflow.runtime-surface-registry",
        "schema_version": 1,
        "surfaces": [
            surface(
                "runtime-control-plane",
                "runtime-control-plane",
                "module:runtime-control",
                ["surface-registry"],
            ),
            surface(
                "runtime-entry:trellis-implement",
                "runtime-entry",
                "runtime-entry:trellis-implement",
                ["runtime-control-plane"],
            ),
            surface(
                "surface-registry",
                "surface-registry",
                "schema:surface-registry",
                [],
            ),
        ],
    }
    inventory_document = {
        "schema_id": "agent-workflow.runtime-unit-inventory",
        "schema_version": 1,
        "units": [
            unit(
                unit_id,
                owner,
                path.relative_to(package_root if scope == "runtime-package" else project_root).as_posix(),
                scope,
            )
            for unit_id, (path, _, scope, owner) in units.items()
        ],
    }
    registry = validate_surface_registry(registry_document, inventory_document)
    evidence = [
        {
            "unit_id": unit_id,
            "byte_hash": hashlib.sha256(payload).hexdigest(),
            "mode": "0644",
            "contract_digest": hashlib.sha256((unit_id + "-contract").encode()).hexdigest(),
            "distributions": (
                ["git-checkout", "sdist", "wheel"]
                if scope == "runtime-package"
                else ["rendered-project"]
            ),
        }
        for unit_id, (_, payload, scope, _) in units.items()
    ]
    digests = compute_surface_digests(registry, evidence)
    document = integration_document()
    workflow = document["workflow_contract"]
    assert isinstance(workflow, dict)
    workflow["task_contract_surfaces"] = [
        {"surface_id": surface_id, "surface_digest": digests[surface_id]}
        for surface_id in sorted(digests)
    ]
    task = project_root / TASK_REF
    task.mkdir(parents=True)
    integration = task / "integration.yaml"
    integration.write_bytes(canonical_json_bytes(document))
    os.chmod(integration, 0o640)
    entry = RuntimeEntryDescriptor(
        entry_id="trellis-implement",
        owning_surface_id="runtime-entry:trellis-implement",
        allowed_modes=("trellis-native",),
        allowed_lifecycle_statuses=("active", "blocked", "completed"),
        allowed_phases=(),
        claim_policy="forbidden",
    )
    request = TaskRuntimeLoadRequest(
        project_root=project_root,
        package_root=package_root,
        task_ref=TASK_REF,
        task_id=TASK_ID,
        expected_state_revision=2,
        expected_lifecycle_status="active",
        expected_phase=None,
        expected_claim=None,
        surface_id="runtime-entry:trellis-implement",
        runtime_entry_id="trellis-implement",
        registry=registry,
        contract_evidence=tuple(evidence),
        runtime_entries={"trellis-implement": entry},
    )
    return request, units, integration


def test_request_has_no_create_decision_and_dispatch_is_an_immutable_in_memory_bundle(
    tmp_path: Path,
) -> None:
    request, units, _ = load_case(tmp_path)

    bundle = load_task_runtime(request)

    assert "decision" not in {field.name for field in dataclasses.fields(TaskRuntimeLoadRequest)}
    assert bundle.task_id == TASK_ID
    assert bundle.runtime_entry_id == "trellis-implement"
    assert set(bundle.units) == set(units)
    assert bundle.units["runtime-entry:trellis-implement"].content == b"run trellis\n"
    with pytest.raises(TypeError):
        bundle.units["new"] = bundle.units["runtime-entry:trellis-implement"]  # type: ignore[index]
    for path, _, _, _ in units.values():
        path.unlink()
    assert bundle.units["module:runtime-control"].content == b"CONTROL = 1\n"


def test_owner_membership_transitive_pins_and_observed_current_equality_are_required(
    tmp_path: Path,
) -> None:
    request, units, _ = load_case(tmp_path)

    with pytest.raises(RuntimeFailure, match="AWP_TASK_RUNTIME_LOAD_DENIED"):
        load_task_runtime(dataclasses.replace(request, surface_id="runtime-control-plane"))

    document_path = request.project_root / TASK_REF / "integration.yaml"
    document = __import__("json").loads(document_path.read_text())
    workflow = document["workflow_contract"]
    workflow["task_contract_surfaces"] = workflow["task_contract_surfaces"][1:]
    document_path.write_bytes(canonical_json_bytes(document))
    with pytest.raises(RuntimeFailure, match="AWP_TASK_SURFACE_MISMATCH"):
        load_task_runtime(request)

    request, units, _ = load_case(tmp_path / "drift")
    entry_path = units["runtime-entry:trellis-implement"][0]
    entry_path.write_bytes(b"drifted\n")
    with pytest.raises(RuntimeFailure, match="AWP_TASK_SURFACE_MISMATCH"):
        load_task_runtime(request)


def test_state_phase_claim_and_entry_tokens_fail_closed(tmp_path: Path) -> None:
    request, _, _ = load_case(tmp_path)

    for changed in (
        dataclasses.replace(request, expected_state_revision=3),
        dataclasses.replace(request, expected_lifecycle_status="completed"),
        dataclasses.replace(request, expected_phase="implementing"),
        dataclasses.replace(request, expected_claim={"claim_id": "unexpected"}),
    ):
        with pytest.raises(RuntimeFailure, match="AWP_TASK_STATE_STALE"):
            load_task_runtime(changed)
    with pytest.raises(RuntimeFailure, match="AWP_TASK_RUNTIME_LOAD_DENIED"):
        load_task_runtime(dataclasses.replace(request, runtime_entry_id="../../shell"))


def test_restorative_repair_to_the_same_pinned_contract_allows_resume(tmp_path: Path) -> None:
    request, units, _ = load_case(tmp_path)
    path, expected, _, _ = units["runtime-entry:trellis-implement"]
    path.unlink()
    with pytest.raises(RuntimeFailure, match="AWP_TASK_SURFACE_MISMATCH"):
        load_task_runtime(request)

    write_file(path, expected)
    bundle = load_task_runtime(request)

    assert bundle.units["runtime-entry:trellis-implement"].content == expected
