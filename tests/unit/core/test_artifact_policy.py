from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_stack.core.artifact_policy import (
    derive_protected_paths,
    validate_artifact_definitions,
)
from agent_stack.core.errors import CoreFailure
from agent_stack.core.schema_catalog import SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]


def _target(path: str, ownership: str, merge: str, mode_policy: str, **extra: object):
    value: dict[str, object] = {
        "path": path,
        "ownership": ownership,
        "merge_strategy": merge,
        "mode_policy": mode_policy,
    }
    value.update(extra)
    return value


def _definition(definition_id: str, *targets: dict[str, object]) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.artifact-definition",
        "schema_version": 1,
        "id": definition_id,
        "source": f"overlays/{definition_id}.txt",
        "targets": list(targets),
        "forbidden_paths": [],
        "validators": [{"id": "utf8", "version": 1}],
    }


def test_all_five_ownership_classes_accept_only_their_legal_contracts() -> None:
    definitions = [
        _definition("managed", _target("AGENTS.md", "managed", "whole-file", "exact", mode="0644")),
        _definition(
            "overlay",
            _target(
                "CLAUDE.md",
                "overlay-managed",
                "marked-block",
                "preserve",
                markers={"begin": "<!-- begin -->", "end": "<!-- end -->"},
            ),
        ),
        _definition(
            "seed",
            _target(
                ".trellis/spec/project.md",
                "create-once-then-user-owned",
                "whole-file",
                "exact",
                mode="0644",
            ),
        ),
        _definition("adopted", _target("host.txt", "adopted", "observe-baseline", "preserve")),
        _definition("user", _target("notes.txt", "user-owned", "none", "preserve")),
    ]

    verified = validate_artifact_definitions(definitions)

    assert tuple(target.ownership for item in verified for target in item.targets) == (
        "managed",
        "overlay-managed",
        "create-once-then-user-owned",
        "adopted",
        "user-owned",
    )


@pytest.mark.parametrize(
    "target",
    [
        _target("a", "managed", "marked-block", "exact", mode="0644"),
        _target("a", "overlay-managed", "whole-file", "preserve"),
        _target("a", "overlay-managed", "marked-block", "exact", mode="0644"),
        _target("a", "adopted", "observe-baseline", "exact", mode="0644"),
        _target("a", "user-owned", "whole-file", "preserve"),
    ],
)
def test_illegal_ownership_merge_and_mode_pairs_fail(target: dict[str, object]) -> None:
    with pytest.raises(CoreFailure, match="AWP_ARTIFACT_POLICY_INVALID"):
        validate_artifact_definitions([_definition("bad", target)])


@pytest.mark.parametrize(
    "path",
    [
        ".git/config",
        ".trellis/tasks/task-a/integration.yaml",
        ".trellis/workspace/state.json",
        "specs/feature/spec.md",
        ".agent-workflow/local/workspace.json",
        ".agent-workflow/manifest.json",
        ".agent-workflow/runtime-state.lock",
    ],
)
def test_global_protected_paths_cannot_be_targeted(path: str) -> None:
    with pytest.raises(CoreFailure, match="AWP_PROTECTED_PATH_VIOLATION"):
        validate_artifact_definitions(
            [_definition("protected", _target(path, "managed", "whole-file", "exact", mode="0644"))]
        )


def test_target_collisions_and_duplicate_marker_pairs_fail() -> None:
    first = _definition(
        "first",
        _target(
            "AGENTS.md",
            "overlay-managed",
            "marked-block",
            "preserve",
            markers={"begin": "<!-- begin -->", "end": "<!-- end -->"},
        ),
    )
    second = _definition(
        "second",
        _target(
            "AGENTS.md",
            "overlay-managed",
            "marked-block",
            "preserve",
            markers={"begin": "<!-- begin -->", "end": "<!-- end -->"},
        ),
    )

    with pytest.raises(CoreFailure, match="AWP_ARTIFACT_POLICY_INVALID"):
        validate_artifact_definitions([first, second])


def test_protected_paths_are_derived_from_the_locked_layout() -> None:
    assert derive_protected_paths(".trellis/tasks", ".trellis/tasks/archive") == (
        ".git/**",
        ".trellis/tasks/**",
        ".trellis/tasks/archive/**",
        ".trellis/workspace/**",
        "specs/**",
        ".agent-workflow/local/**",
        ".agent-workflow/task-transactions/**",
        ".agent-workflow/transactions/**",
    )


def test_task4_schemas_are_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.supported_versions("agent-workflow.artifact-definition") == (1,)
    assert catalog.supported_versions("agent-workflow.trellis-task-layout") == (1,)

    definition = _definition(
        "managed", _target("AGENTS.md", "managed", "whole-file", "exact", mode="0644")
    )
    layout = json.loads(
        (ROOT / "tests/fixtures/core/trellis_layouts/valid.json").read_text(encoding="utf-8")
    )
    catalog.load_and_validate(definition)
    catalog.load_and_validate(layout)
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**definition, "unknown": True})
