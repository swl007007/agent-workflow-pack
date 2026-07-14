from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.gates import _require_production_integration


ROOT = Path(__file__).resolve().parents[3]


def test_component_gates_cannot_pass_without_production_integration_evidence() -> None:
    with pytest.raises(LifecycleFailure, match="production integration prerequisite"):
        _require_production_integration(ROOT, "a" * 64)
