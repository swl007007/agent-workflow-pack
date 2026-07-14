#!/usr/bin/env python3
"""Print the render digest recorded by an exact final artifact set."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_stack.release.gates import verify_release_artifact_set


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_set", type=Path)
    arguments = parser.parse_args()
    artifact_set = verify_release_artifact_set(arguments.artifact_set)
    print(artifact_set.distribution_render_digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
