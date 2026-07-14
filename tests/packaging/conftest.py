from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.release.gates import ReleaseArtifactSet, build_release_artifacts


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def release_artifact_set() -> ReleaseArtifactSet:
    return build_release_artifacts(ROOT, ROOT / "dist", rebuild=False)
