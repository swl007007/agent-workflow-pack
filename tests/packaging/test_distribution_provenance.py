from __future__ import annotations

import json
import zipfile

from agent_stack.release.gates import ReleaseArtifactSet


def test_final_wheel_contains_frozen_provenance_licenses_and_notices(
    release_artifact_set: ReleaseArtifactSet,
) -> None:
    with zipfile.ZipFile(release_artifact_set.wheel.path) as archive:
        provenance = json.loads(
            archive.read("agent_stack/data/release/provenance-lock.json")
        )
        notices = archive.read("agent_stack/data/THIRD_PARTY_NOTICES.md")
        pyyaml_license = archive.read(
            "agent_stack/data/LICENSES/PyYAML-6.0.2.txt"
        )
        fast_license = archive.read(
            "agent_stack/data/LICENSES/fastjsonschema-2.21.1.txt"
        )

    assert (
        provenance["provenance_lock_digest"]
        == release_artifact_set.provenance_lock_digest
    )
    assert notices
    assert pyyaml_license
    assert fast_license
    assert "wheel_sha256" not in repr(provenance)
    assert "sdist_sha256" not in repr(provenance)
