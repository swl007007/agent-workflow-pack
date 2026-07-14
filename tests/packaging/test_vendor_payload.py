from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from agent_stack.release.gates import ReleaseArtifactSet


ROOT = Path(__file__).resolve().parents[2]


def test_wheel_vendor_payload_exactly_matches_frozen_lock(
    release_artifact_set: ReleaseArtifactSet,
) -> None:
    lock = json.loads((ROOT / "vendor/runtime-vendor-lock.json").read_text(encoding="utf-8"))
    expected = {
        row["installed_path"].removeprefix("src/"): row["installed_sha256"]
        for component in lock["components"]
        for row in component["files"]
    }
    with zipfile.ZipFile(release_artifact_set.wheel.path) as archive:
        actual = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith("agent_stack/_vendor/")
            and name.endswith(".py")
            and name != "agent_stack/_vendor/__init__.py"
        }

    assert actual == expected
    assert not any(name.startswith(("yaml/", "fastjsonschema/")) for name in archive.namelist())
