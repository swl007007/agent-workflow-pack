from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROVIDER_ROOT = ROOT / "src/agent_stack/providers"
STDLIB = {
    "__future__", "abc", "argparse", "array", "ast", "base64", "collections", "contextlib",
    "dataclasses", "datetime", "enum", "errno", "fcntl", "functools", "hashlib",
    "hmac", "http", "io", "ipaddress", "json", "locale", "logging", "math",
    "mmap", "os", "pathlib", "platform", "queue", "re", "resource", "secrets",
    "select", "shlex", "shutil", "signal", "socket", "stat", "string", "struct",
    "subprocess", "sys", "tarfile", "tempfile", "threading", "time", "types",
    "typing", "unicodedata", "urllib", "uuid", "zipfile",
}


def test_provider_import_graph_uses_only_stdlib_and_public_core() -> None:
    violations: list[str] = []
    for path in sorted(PROVIDER_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                imported = [node.module or ""]
            for name in imported:
                root = name.split(".", 1)[0]
                if name.startswith("agent_stack._vendor"):
                    violations.append(f"{path.name}: private vendor import {name}")
                elif name.startswith("agent_stack.core") and name != "agent_stack.core.api":
                    violations.append(f"{path.name}: non-public Core import {name}")
                elif root not in STDLIB and not name.startswith("agent_stack.providers") and not name.startswith("agent_stack.core"):
                    violations.append(f"{path.name}: external runtime import {name}")
    assert violations == []


def test_provider_package_has_no_local_vendor_tree() -> None:
    assert not (PROVIDER_ROOT / "_vendor").exists()
