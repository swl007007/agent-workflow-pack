from __future__ import annotations

from agent_stack.release.gates import ReleaseArtifactSet


def test_wheel_contains_all_frozen_runtime_and_release_data(
    release_artifact_set: ReleaseArtifactSet,
) -> None:
    names = release_artifact_set.wheel_names
    required = {
        "agent_stack/data/LICENSES/PyYAML-6.0.2.txt",
        "agent_stack/data/LICENSES/fastjsonschema-2.21.1.txt",
        "agent_stack/data/THIRD_PARTY_NOTICES.md",
        "agent_stack/data/release/provenance-lock.json",
        "agent_stack/data/release/trust-policy.yaml",
        "agent_stack/data/vendor/runtime-vendor-lock.json",
        "agent_stack/data/catalog/platforms.yaml",
        "agent_stack/data/catalog/route-policy.yaml",
        "agent_stack/data/compatibility/releases.yaml",
        "agent_stack/data/runtime-launcher/agent-stack.sh.tmpl",
    }
    assert required <= names
    assert any(name.startswith("agent_stack/data/schemas/") for name in names)
    assert any(name.startswith("agent_stack/data/artifact-definitions/") for name in names)
    assert any(name.startswith("agent_stack/data/overlays/") for name in names)


def test_wheel_sdist_and_git_have_identical_logical_runtime_inventory(
    release_artifact_set: ReleaseArtifactSet,
) -> None:
    assert release_artifact_set.git_inventory == release_artifact_set.wheel_inventory
    assert release_artifact_set.git_inventory == release_artifact_set.sdist_inventory
