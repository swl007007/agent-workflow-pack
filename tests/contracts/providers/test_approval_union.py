from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.core.api import CoreFailure, SchemaCatalog
from tests.unit.providers.test_approval import _plan, _proof


ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "task_field",
    [
        {"task_id": "11111111-1111-4111-8111-111111111111"},
        {"decision_digest": "a" * 64},
        {"task_ref": "task-a"},
        {"route": "speckit-superpowers"},
        {"terminal_confirmation": True},
    ],
)
def test_provider_approval_is_a_closed_non_task_union(task_field: dict[str, object]) -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    proof = _proof(_plan())
    proof.update(task_field)
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate(proof)


def test_provider_approval_schema_accepts_only_the_direct_human_branch() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    proof = _proof(_plan())
    catalog.load_and_validate(proof)
    model = dict(proof)
    model["actor"] = {"id": "assistant", "kind": "model"}
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate(model)
