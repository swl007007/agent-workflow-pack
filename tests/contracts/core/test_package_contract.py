from __future__ import annotations

import ast
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_core_api_is_importable() -> None:
    from agent_stack.core import api

    assert api.CORE_INTERFACE_VERSION == 1


def test_project_metadata_keeps_the_runtime_self_contained() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["requires-python"] == ">=3.11,<3.15"
    assert "dependencies" not in metadata["project"]
    assert metadata["build-system"]["build-backend"]


def test_runtime_vendors_exist_only_below_the_private_namespace() -> None:
    private_root = ROOT / "src" / "agent_stack" / "_vendor"

    assert (private_root / "yaml" / "__init__.py").is_file()
    assert (private_root / "fastjsonschema" / "__init__.py").is_file()
    assert not (ROOT / "src" / "yaml").exists()
    assert not (ROOT / "src" / "fastjsonschema").exists()


def test_source_tree_has_no_top_level_vendor_imports() -> None:
    violations: list[str] = []

    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in {"yaml", "fastjsonschema"}:
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported = node.module
            if imported and imported.split(".", 1)[0] in {"yaml", "fastjsonschema"}:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{imported}")

    assert violations == []
