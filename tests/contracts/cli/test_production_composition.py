from __future__ import annotations

import importlib

import agent_stack.cli as cli

from agent_stack.cli.dispatch import OWNER_MATRIX
from agent_stack.cli.production import _IMPLEMENTATIONS


def test_production_owner_bindings_cover_the_closed_command_matrix() -> None:
    production_owner_bindings = getattr(cli, "production_owner_bindings", None)

    assert callable(production_owner_bindings)
    bindings = production_owner_bindings()

    assert set(bindings) == set(OWNER_MATRIX)
    assert all(bindings[command].owner == OWNER_MATRIX[command] for command in OWNER_MATRIX)


def test_every_lazy_production_owner_target_is_importable() -> None:
    for implementation in _IMPLEMENTATIONS.values():
        closure = implementation.__closure__
        if closure is None:
            continue
        captured = [cell.cell_contents for cell in closure]
        module_names = [value for value in captured if isinstance(value, str) and ".commands" in value]
        for module_name in module_names:
            importlib.import_module(module_name)
