"""Claude Code platform binding."""

from pathlib import Path

from ..capabilities import LockedPlatformBinding, _load_platform_binding


def load_claude_code_contract(root: Path) -> LockedPlatformBinding:
    return _load_platform_binding(root, "claude-code")
