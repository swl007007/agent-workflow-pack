from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.gates import _require_production_integration


ROOT = Path(__file__).resolve().parents[3]


def test_component_gates_cannot_pass_without_production_integration_evidence() -> None:
    with pytest.raises(
        LifecycleFailure, match="production integration prerequisite"
    ) as captured:
        _require_production_integration(ROOT, "a" * 64)

    assert captured.value.details == {
        "expected_artifact_set_digest": json.loads(
            ROOT.joinpath("release/production-integration.json").read_text(
                encoding="utf-8"
            )
        )["artifact_set_digest"],
        "actual_artifact_set_digest": "a" * 64,
    }
