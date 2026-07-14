from __future__ import annotations

from agent_stack.release.gates import (
    ReleaseArtifactSet,
    compute_distribution_render_digest,
)


def test_distribution_render_digest_matches_git_wheel_and_sdist(
    release_artifact_set: ReleaseArtifactSet,
) -> None:
    expected = release_artifact_set.distribution_render_digest

    assert compute_distribution_render_digest(release_artifact_set.git_inventory) == expected
    assert compute_distribution_render_digest(release_artifact_set.wheel_inventory) == expected
    assert compute_distribution_render_digest(release_artifact_set.sdist_inventory) == expected
    assert compute_distribution_render_digest(release_artifact_set.git_inventory) == expected


def test_container_hashes_are_not_inputs_to_render_digest(
    release_artifact_set: ReleaseArtifactSet,
) -> None:
    changed_container_claims = release_artifact_set.to_document()
    changed_container_claims["artifacts"][0]["sha256"] = "f" * 64

    assert release_artifact_set.distribution_render_digest == compute_distribution_render_digest(
        release_artifact_set.git_inventory
    )
