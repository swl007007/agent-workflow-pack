"""Codex platform binding."""

from pathlib import Path

from ..capabilities import LockedPlatformBinding, _load_platform_binding


def load_codex_contract(root: Path) -> LockedPlatformBinding:
    return _load_platform_binding(root, "codex")
