#!/usr/bin/env python3
"""Build, record, or verify the final wheel/sdist byte set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_stack.release.gates import (
    build_release_artifacts,
    run_release_gates,
    verify_release_artifact_set,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-existing", type=Path)
    parser.add_argument("--record-existing", action="store_true")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if arguments.verify_existing is not None:
        artifact_set = verify_release_artifact_set(
            (root / arguments.verify_existing).resolve()
        )
    else:
        artifact_set = build_release_artifacts(
            root, root / "dist", rebuild=not arguments.record_existing
        )
    result = run_release_gates(artifact_set)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
