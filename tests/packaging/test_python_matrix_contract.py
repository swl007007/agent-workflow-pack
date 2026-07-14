from __future__ import annotations

import tomllib
from pathlib import Path

from agent_stack.release.gates import SUPPORTED_PYTHON_MINORS


ROOT = Path(__file__).resolve().parents[2]


def test_python_contract_is_exactly_311_through_314() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["requires-python"] == ">=3.11,<3.15"
    assert SUPPORTED_PYTHON_MINORS == ("3.11", "3.12", "3.13", "3.14")
