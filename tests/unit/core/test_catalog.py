from __future__ import annotations

import pytest

from agent_stack.core.catalog import evaluate_capabilities, resolve_catalog_closure
from agent_stack.core.errors import CoreFailure
from agent_stack.core.models import CapabilityLevel
from agent_stack.core.profile import resolve_profile


def _profile(**overrides: object):
    value: dict[str, object] = {
        "schema_id": "agent-workflow.profile",
        "schema_version": 1,
        "id": "test",
        "skills": {"enable": ["skill:a"], "disable": []},
        "default_platforms": ["codex"],
    }
    value.update(overrides)
    return resolve_profile([value], "test")


def _entry(entry_id: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": entry_id,
        "kind": entry_id.split(":", 1)[0],
        "dependencies": [],
        "conflicts": [],
        "references": [],
        "platforms": [],
        "required_capabilities": {},
        "mandatory": False,
        "discoverable": True,
    }
    value.update(overrides)
    return value


def _catalog(*entries: dict[str, object]) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.catalog",
        "schema_version": 1,
        "entries": list(entries),
    }


def _manifest(**capabilities: str) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.capability-manifest",
        "schema_version": 1,
        "platform": "codex",
        "adapter_id": "codex",
        "adapter_version": "1.0.0",
        "harness_id": "codex-cli",
        "harness_version": "1.0.0",
        "probe_suite_id": "codex-capability-probes",
        "probe_suite_version": 1,
        "capabilities": capabilities,
        "approval_verifiers": {},
        "evidence_digest": "a" * 64,
    }


def test_disabled_dependency_blocks_resolution() -> None:
    profile = _profile(skills={"enable": ["skill:a"], "disable": ["skill:b"]})
    catalog = _catalog(_entry("skill:a", dependencies=["skill:b"]), _entry("skill:b"))

    with pytest.raises(CoreFailure, match="AWP_CATALOG_CLOSURE_BLOCKED"):
        resolve_catalog_closure(profile, catalog, [_manifest()])


def test_dependency_and_reference_closure_has_stable_topological_order() -> None:
    catalog = _catalog(
        _entry("skill:a", dependencies=["component:b"], references=["command:c"]),
        _entry("component:b", dependencies=["component:d"]),
        _entry("command:c"),
        _entry("component:d"),
        _entry("platform:codex", mandatory=True),
    )

    closure = resolve_catalog_closure(_profile(), catalog, [_manifest()])

    assert closure.ordered_ids == (
        "command:c",
        "component:d",
        "component:b",
        "platform:codex",
        "skill:a",
    )
    assert closure.reference_ids == ("command:c",)
    assert closure.discoverable_ids == tuple(sorted(closure.ordered_ids))


@pytest.mark.parametrize(
    "catalog",
    [
        _catalog(_entry("skill:a", dependencies=["missing:x"])),
        _catalog(_entry("skill:a", conflicts=["component:b"]), _entry("component:b", mandatory=True)),
        _catalog(_entry("skill:a", references=["command:c"]), _entry("command:c", references=["skill:a"])),
        _catalog(_entry("skill:a", platforms=["claude"])),
    ],
)
def test_missing_conflicting_cyclic_or_platform_incompatible_closure_fails(
    catalog: dict[str, object],
) -> None:
    with pytest.raises(CoreFailure, match="AWP_CATALOG_CLOSURE_BLOCKED"):
        resolve_catalog_closure(_profile(), catalog, [_manifest()])


def test_capability_ordering_and_missing_capability_normalization() -> None:
    profile = _profile(
        required_capabilities={
            "project_skills": "instruction-only",
            "maintenance_gate": "enforced",
        }
    )
    results = evaluate_capabilities(
        profile,
        [_manifest(project_skills="enforced", maintenance_gate="enforced")],
    )

    assert [(result.capability_id, result.observed) for result in results] == [
        ("maintenance_gate", CapabilityLevel.ENFORCED),
        ("project_skills", CapabilityLevel.ENFORCED),
    ]
    with pytest.raises(CoreFailure, match="AWP_CAPABILITY_INSUFFICIENT"):
        evaluate_capabilities(profile, [_manifest(project_skills="instruction-only")])


def test_entry_capability_requirement_is_enforced() -> None:
    catalog = _catalog(
        _entry("skill:a", required_capabilities={"project_skills": "enforced"})
    )

    with pytest.raises(CoreFailure, match="AWP_CATALOG_CLOSURE_BLOCKED"):
        resolve_catalog_closure(
            _profile(), catalog, [_manifest(project_skills="instruction-only")]
        )
