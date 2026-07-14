#!/usr/bin/env python3
"""Generate or verify pre-build provenance, full licenses, and notices."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_stack.core.api import canonical_json_bytes
from agent_stack.release.provenance import (
    build_frozen_provenance_inventory,
    render_third_party_notices,
)


def _root(value: str | None) -> Path:
    return Path(value).resolve() if value is not None else Path(__file__).resolve().parents[2]


def _expected(root: Path) -> dict[Path, bytes]:
    inventory = build_frozen_provenance_inventory(root)
    return {
        root / "release/provenance-lock.json": canonical_json_bytes(inventory.to_document())
        + b"\n",
        root / "THIRD_PARTY_NOTICES.md": render_third_party_notices(inventory).encode("utf-8"),
        root / "LICENSES/PyYAML-6.0.2.txt": (
            root / "vendor/licenses/PyYAML-6.0.2.txt"
        ).read_bytes(),
        root / "LICENSES/fastjsonschema-2.21.1.txt": (
            root / "vendor/licenses/fastjsonschema-2.21.1.txt"
        ).read_bytes(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root")
    arguments = parser.parse_args(argv)
    root = _root(arguments.root)
    expected = _expected(root)
    stale: list[str] = []
    for path, body in expected.items():
        if arguments.check:
            try:
                actual = path.read_bytes()
            except OSError:
                actual = b""
            if actual != body:
                stale.append(path.relative_to(root).as_posix())
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    if stale:
        sys.stderr.write("stale generated provenance inputs: " + ", ".join(stale) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
