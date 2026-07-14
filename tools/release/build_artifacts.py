#!/usr/bin/env python3
"""Build, record, or verify the final wheel/sdist byte set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_stack.release.gates import (
    build_release_artifacts,
    run_release_gates,
    verify_release_artifact_set,
)
from agent_stack.release.errors import LifecycleFailure


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
    try:
        result = run_release_gates(artifact_set)
    except LifecycleFailure as error:
        print(
            json.dumps(
                {
                    "failure": error.to_document(),
                    "actual_artifact_set": artifact_set.to_document(),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
