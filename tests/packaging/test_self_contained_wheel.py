from __future__ import annotations

import zipfile
from email.parser import BytesParser

from agent_stack.release.gates import ReleaseArtifactSet


def test_wheel_has_no_runtime_requires_dist_and_exposes_cli(
    release_artifact_set: ReleaseArtifactSet,
) -> None:
    with zipfile.ZipFile(release_artifact_set.wheel.path) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        entry_points = archive.read(
            next(name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt"))
        ).decode("utf-8")

    assert metadata.get_all("Requires-Dist") in (None, [])
    assert set(metadata["Requires-Python"].split(",")) == {">=3.11", "<3.15"}
    assert "agent-stack = agent_stack.__main__:main" in entry_points


def test_detached_manifest_is_absent_from_final_distributions(
    release_artifact_set: ReleaseArtifactSet,
) -> None:
    assert "release-manifest.json" not in release_artifact_set.wheel_names
    assert "release-manifest.json" not in release_artifact_set.sdist_names
