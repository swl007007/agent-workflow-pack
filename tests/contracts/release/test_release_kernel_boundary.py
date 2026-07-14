from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RELEASE_ROOT = ROOT / "src/agent_stack/release"
FORBIDDEN = (
    "agent_stack.cli",
    "agent_stack.renderer",
    "agent_stack.runtime",
    "agent_stack.route",
)


def test_release_kernel_is_a_leaf_boundary() -> None:
    kernel = RELEASE_ROOT / "kernel.py"
    assert kernel.is_file()
    tree = ast.parse(kernel.read_text(encoding="utf-8"), filename=kernel.as_posix())
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imports.append(node.module or "")
    assert not any(name.startswith(FORBIDDEN) for name in imports)


def test_release_kernel_does_not_import_late_composition_transitively() -> None:
    from agent_stack.release import kernel

    exported_modules = {value.__module__ for value in kernel.PUBLIC_MODELS}
    assert not any(module.startswith(FORBIDDEN) for module in exported_modules)
