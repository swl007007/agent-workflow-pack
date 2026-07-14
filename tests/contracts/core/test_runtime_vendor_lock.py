from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = ROOT / "vendor" / "runtime-vendor-lock.json"
SCHEMA_PATH = ROOT / "schemas" / "core" / "runtime-vendor-lock.v1.json"
SYNC_TOOL = ROOT / "tools" / "vendor" / "sync_runtime_vendor.py"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_COMPONENTS = {
    "PyYAML": {
        "version": "6.0.2",
        "url": "https://files.pythonhosted.org/packages/54/ed/79a089b6be93607fa5cdaedf301d7dfb23af5f25c398d5ead2525b063e17/pyyaml-6.0.2.tar.gz",
        "archive_sha256": "d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e",
        "spdx": "MIT",
        "license_sha256": "8d3928f9dc4490fd635707cb88eb26bd764102a7282954307d3e5167a577e8a4",
        "target_root": "src/agent_stack/_vendor/yaml",
    },
    "fastjsonschema": {
        "version": "2.21.1",
        "url": "https://files.pythonhosted.org/packages/8b/50/4b769ce1ac4071a1ef6d86b1a3fb56cdc3a37615e8c5519e1af96cdac366/fastjsonschema-2.21.1.tar.gz",
        "archive_sha256": "794d4f0a58f848961ba16af7b9c85a3e88cd360df008c59aac6fc5ae9323b5d4",
        "spdx": "BSD-3-Clause",
        "license_sha256": "9ccddf69eb3998a60148debe85b94c5afed53691b6474692e78abcc0a0e544f1",
        "target_root": "src/agent_stack/_vendor/fastjsonschema",
    },
}

TOP_LEVEL_KEYS = {"schema_id", "schema_version", "namespace", "components"}
COMPONENT_KEYS = {
    "name",
    "version",
    "source",
    "spdx",
    "license",
    "install",
    "exclusions",
    "files",
}
SOURCE_KEYS = {"archive_name", "url", "sha256"}
LICENSE_KEYS = {"upstream_path", "installed_path", "sha256"}
INSTALL_KEYS = {"upstream_root", "target_root", "modification"}
FILE_KEYS = {
    "upstream_path",
    "upstream_sha256",
    "installed_path",
    "installed_sha256",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_lock(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / "vendor" / "runtime-vendor-lock.json").read_text(encoding="utf-8"))


def _component_map(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {component["name"]: component for component in lock["components"]}


def _run_sync(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SYNC_TOOL), *args],
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=True,
    )


def test_vendor_lock_schema_and_object_are_closed() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    lock = _load_lock()

    assert schema["$id"] == "agent-workflow.runtime-vendor-lock"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["components"]["items"]["additionalProperties"] is False
    assert set(lock) == TOP_LEVEL_KEYS
    assert lock["schema_id"] == "agent-workflow.runtime-vendor-lock"
    assert lock["schema_version"] == 1
    assert lock["namespace"] == "agent_stack._vendor"


def test_vendor_lock_freezes_exact_sources_licenses_and_namespace() -> None:
    lock = _load_lock()
    components = _component_map(lock)

    assert set(components) == set(EXPECTED_COMPONENTS)
    assert [component["name"] for component in lock["components"]] == sorted(components)

    for name, expected in EXPECTED_COMPONENTS.items():
        component = components[name]
        assert set(component) == COMPONENT_KEYS
        assert set(component["source"]) == SOURCE_KEYS
        assert set(component["license"]) == LICENSE_KEYS
        assert set(component["install"]) == INSTALL_KEYS
        assert component["version"] == expected["version"]
        assert component["source"]["url"] == expected["url"]
        assert component["source"]["sha256"] == expected["archive_sha256"]
        assert component["spdx"] == expected["spdx"]
        assert component["license"]["sha256"] == expected["license_sha256"]
        assert component["install"]["target_root"] == expected["target_root"]
        assert component["install"]["modification"] == "namespace-relocation-only"
        assert component["exclusions"]


def test_every_locked_file_and_full_license_matches_the_installed_bytes() -> None:
    lock = _load_lock()
    installed_inventory: set[str] = set()

    for component in lock["components"]:
        license_record = component["license"]
        license_path = ROOT / license_record["installed_path"]
        assert license_path.is_file()
        assert _sha256(license_path) == license_record["sha256"]
        assert len(license_path.read_text(encoding="utf-8").strip()) > 100

        rows = component["files"]
        assert rows
        assert [row["installed_path"] for row in rows] == sorted(
            row["installed_path"] for row in rows
        )
        for row in rows:
            assert set(row) == FILE_KEYS
            assert HEX64.fullmatch(row["upstream_sha256"])
            assert HEX64.fullmatch(row["installed_sha256"])
            assert row["upstream_sha256"] == row["installed_sha256"]
            installed_path = ROOT / row["installed_path"]
            assert installed_path.is_file()
            assert _sha256(installed_path) == row["installed_sha256"]
            assert row["installed_path"] not in installed_inventory
            installed_inventory.add(row["installed_path"])

    actual_inventory = {
        path.relative_to(ROOT).as_posix()
        for component in lock["components"]
        for path in (ROOT / component["install"]["target_root"]).rglob("*")
        if path.is_file()
    }
    assert actual_inventory == installed_inventory


def test_exact_archives_reproduce_the_same_private_tree(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    generated_roots: list[Path] = []

    for name in ("first", "second"):
        root = tmp_path / name
        (root / "vendor").mkdir(parents=True)
        shutil.copy2(LOCK_PATH, root / "vendor" / LOCK_PATH.name)
        result = _run_sync("--root", str(root), "--cache-dir", str(cache), "--sync")
        assert result.stdout.strip() == "runtime vendor tree synchronized"
        generated_roots.append(root)

    first_lock = _load_lock(generated_roots[0])
    second_lock = _load_lock(generated_roots[1])
    assert first_lock == second_lock == _load_lock()
    for component in first_lock["components"]:
        for row in component["files"]:
            first = generated_roots[0] / row["installed_path"]
            second = generated_roots[1] / row["installed_path"]
            assert first.read_bytes() == second.read_bytes()
        license_path = component["license"]["installed_path"]
        assert (generated_roots[0] / license_path).read_bytes() == (
            generated_roots[1] / license_path
        ).read_bytes()


def test_check_rejects_an_unregistered_vendor_file(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "vendor", root / "vendor")
    shutil.copytree(ROOT / "src", root / "src")
    rogue = root / "src" / "agent_stack" / "_vendor" / "yaml" / "rogue.py"
    rogue.write_text("raise RuntimeError('unregistered')\n", encoding="utf-8")

    result = _run_sync("--root", str(root), "--check", check=False)

    assert result.returncode != 0
    assert "unregistered vendor file" in result.stderr


def test_checked_in_vendor_tree_passes_the_reproducibility_check() -> None:
    first = _run_sync("--check")
    second = _run_sync("--check")

    assert first.stdout.strip() == "runtime vendor tree verified"
    assert second.stdout == first.stdout
