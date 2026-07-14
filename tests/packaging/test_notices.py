from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from agent_stack.release.provenance import load_frozen_provenance, render_third_party_notices


ROOT = Path(__file__).resolve().parents[2]


def test_full_license_bytes_are_exact_vendor_sources() -> None:
    pairs = (
        ("vendor/licenses/PyYAML-6.0.2.txt", "LICENSES/PyYAML-6.0.2.txt"),
        (
            "vendor/licenses/fastjsonschema-2.21.1.txt",
            "LICENSES/fastjsonschema-2.21.1.txt",
        ),
    )
    for source, distributed in pairs:
        source_bytes = (ROOT / source).read_bytes()
        distributed_bytes = (ROOT / distributed).read_bytes()
        assert distributed_bytes == source_bytes
        assert hashlib.sha256(distributed_bytes).hexdigest() in {
            "8d3928f9dc4490fd635707cb88eb26bd764102a7282954307d3e5167a577e8a4",
            "9ccddf69eb3998a60148debe85b94c5afed53691b6474692e78abcc0a0e544f1",
        }


def test_notices_are_deterministic_sorted_and_disclose_relocation() -> None:
    inventory = load_frozen_provenance(ROOT)
    expected = render_third_party_notices(inventory)
    actual = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

    assert actual == expected
    assert actual.index("fastjsonschema 2.21.1") < actual.index("PyYAML 6.0.2")
    assert actual.count("namespace-relocation-only") == 2
    assert "agent_stack._vendor.fastjsonschema" in actual
    assert "agent_stack._vendor.yaml" in actual


def test_generator_check_rejects_any_stale_generated_input() -> None:
    completed = subprocess.run(
        [sys.executable, "tools/release/generate_notices.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
