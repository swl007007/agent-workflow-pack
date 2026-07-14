from __future__ import annotations

import pytest

from agent_stack.core.errors import CoreFailure
from agent_stack.core.models import CapabilityLevel
from agent_stack.core.profile import resolve_profile


def _profile(profile_id: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_id": "agent-workflow.profile",
        "schema_version": 1,
        "id": profile_id,
    }
    value.update(overrides)
    return value


def test_profile_single_inheritance_uses_exact_field_merge_rules() -> None:
    parent = _profile(
        "base",
        route_admission={"default_route": "native-light", "explicit_only": True},
        bindings={"trellis-native": {"codex": "entry:base"}},
        skills={"enable": ["skill:a"], "disable": ["skill:z"]},
        artifact_policy="strict",
        default_platforms=["codex", "claude"],
        required_capabilities={"project_skills": "instruction-only"},
        approval_policy={"task_creation": "required"},
        provider_security_policy={"initializer": "required"},
    )
    child = _profile(
        "child",
        extends="base",
        route_admission={"default_route": "trellis-native"},
        bindings={"trellis-native": {"codex": "entry:child"}},
        skills={"enable": ["skill:b"], "disable": []},
        default_platforms=["codex"],
        required_capabilities={"maintenance_gate": "enforced"},
    )

    resolved = resolve_profile([child, parent], "child")

    assert resolved.profile_id == "child"
    assert resolved.route_admission == {
        "default_route": "trellis-native",
        "explicit_only": True,
    }
    assert resolved.bindings == {"trellis-native": {"codex": "entry:child"}}
    assert resolved.skills_enable == ("skill:a", "skill:b")
    assert resolved.skills_disable == ("skill:z",)
    assert resolved.default_platforms == ("codex",)
    assert resolved.required_capabilities == {
        "maintenance_gate": CapabilityLevel.ENFORCED,
        "project_skills": CapabilityLevel.INSTRUCTION_ONLY,
    }
    assert resolved.artifact_policy == "strict"
    assert resolved.approval_policy == {"task_creation": "required"}
    assert resolved.provider_security_policy == {"initializer": "required"}


def test_profile_cycle_is_rejected() -> None:
    with pytest.raises(CoreFailure, match="AWP_PROFILE_INVALID"):
        resolve_profile([_profile("a", extends="b"), _profile("b", extends="a")], "a")


def test_enabled_and_disabled_skill_conflict_is_rejected() -> None:
    parent = _profile("base", skills={"enable": ["skill:a"], "disable": []})
    child = _profile(
        "child", extends="base", skills={"enable": [], "disable": ["skill:a"]}
    )

    with pytest.raises(CoreFailure, match="AWP_PROFILE_INVALID"):
        resolve_profile([parent, child], "child")


def test_profile_unknown_fields_and_schema_version_mismatch_fail_closed() -> None:
    with pytest.raises(CoreFailure, match="AWP_PROFILE_INVALID"):
        resolve_profile([_profile("bad", executable_expression="latest()")], "bad")
    with pytest.raises(CoreFailure, match="AWP_PROFILE_INVALID"):
        resolve_profile(
            [_profile("base"), {**_profile("child", extends="base"), "schema_version": 2}],
            "child",
        )
