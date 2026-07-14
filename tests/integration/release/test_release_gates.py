from __future__ import annotations

import hashlib
from pathlib import Path

from agent_stack.release.gates import build_release_artifacts, run_release_gates


ROOT = Path(__file__).resolve().parents[3]


def file_hash(path: object) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def test_all_thirteen_release_gates_pass_on_the_exact_final_bytes(
) -> None:
    release_artifact_set = build_release_artifacts(ROOT, ROOT / "dist", rebuild=False)
    before = {
        "wheel": file_hash(release_artifact_set.wheel.path),
        "sdist": file_hash(release_artifact_set.sdist.path),
    }

    result = run_release_gates(release_artifact_set)

    assert result["status"] == "passed"
    assert len(result["gates"]) == 13
    assert len({gate["gate_id"] for gate in result["gates"]}) == 13
    assert all(gate["status"] == "passed" for gate in result["gates"])
    assert result["artifact_set_digest"] == release_artifact_set.artifact_set_digest
    assert before == {
        "wheel": file_hash(release_artifact_set.wheel.path),
        "sdist": file_hash(release_artifact_set.sdist.path),
    }
