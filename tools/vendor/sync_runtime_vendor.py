#!/usr/bin/env python3
"""Reproduce or verify the exact private runtime-vendor tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


LOCK_RELATIVE_PATH = Path("vendor/runtime-vendor-lock.json")
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


class VendorError(RuntimeError):
    """The frozen vendor contract or generated tree is invalid."""


@dataclass(frozen=True)
class VendorSpec:
    name: str
    version: str
    archive_name: str
    archive_root: str
    url: str
    archive_sha256: str
    spdx: str
    license_upstream_path: str
    license_installed_path: str
    license_sha256: str
    upstream_root: str
    target_root: str
    exclusions: tuple[str, ...]
    excluded_python_files: tuple[str, ...] = ()


SPECS = (
    VendorSpec(
        name="PyYAML",
        version="6.0.2",
        archive_name="pyyaml-6.0.2.tar.gz",
        archive_root="pyyaml-6.0.2",
        url=(
            "https://files.pythonhosted.org/packages/54/ed/"
            "79a089b6be93607fa5cdaedf301d7dfb23af5f25c398d5ead2525b063e17/"
            "pyyaml-6.0.2.tar.gz"
        ),
        archive_sha256="d584d9ec91ad65861cc08d42e834324ef890a082e591037abe114850ff7bbc3e",
        spdx="MIT",
        license_upstream_path="LICENSE",
        license_installed_path="vendor/licenses/PyYAML-6.0.2.txt",
        license_sha256="8d3928f9dc4490fd635707cb88eb26bd764102a7282954307d3e5167a577e8a4",
        upstream_root="lib/yaml",
        target_root="src/agent_stack/_vendor/yaml",
        exclusions=("lib/yaml/cyaml.py", "ext/**", "tests/**", "examples/**"),
        excluded_python_files=("cyaml.py",),
    ),
    VendorSpec(
        name="fastjsonschema",
        version="2.21.1",
        archive_name="fastjsonschema-2.21.1.tar.gz",
        archive_root="fastjsonschema-2.21.1",
        url=(
            "https://files.pythonhosted.org/packages/8b/50/"
            "4b769ce1ac4071a1ef6d86b1a3fb56cdc3a37615e8c5519e1af96cdac366/"
            "fastjsonschema-2.21.1.tar.gz"
        ),
        archive_sha256="794d4f0a58f848961ba16af7b9c85a3e88cd360df008c59aac6fc5ae9323b5d4",
        spdx="BSD-3-Clause",
        license_upstream_path="LICENSE",
        license_installed_path="vendor/licenses/fastjsonschema-2.21.1.txt",
        license_sha256="9ccddf69eb3998a60148debe85b94c5afed53691b6474692e78abcc0a0e544f1",
        upstream_root="fastjsonschema",
        target_root="src/agent_stack/_vendor/fastjsonschema",
        exclusions=("tests/**", "docs/**", "benchmarks/**"),
    ),
)


@dataclass(frozen=True)
class ArchiveContents:
    files: dict[str, bytes]
    license_bytes: bytes


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise VendorError(
            f"{label} fields differ: missing={sorted(expected - actual)} "
            f"unknown={sorted(actual - expected)}"
        )


def _load_lock(root: Path) -> dict[str, Any]:
    path = root / LOCK_RELATIVE_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VendorError(f"cannot read runtime vendor lock: {error}") from error
    if not isinstance(value, dict):
        raise VendorError("runtime vendor lock must be an object")
    return value


def _validate_lock(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _require_keys(lock, TOP_LEVEL_KEYS, "runtime vendor lock")
    if lock["schema_id"] != "agent-workflow.runtime-vendor-lock":
        raise VendorError("unexpected runtime vendor lock schema_id")
    if lock["schema_version"] != 1:
        raise VendorError("unexpected runtime vendor lock schema_version")
    if lock["namespace"] != "agent_stack._vendor":
        raise VendorError("runtime vendors must use agent_stack._vendor")
    if not isinstance(lock["components"], list):
        raise VendorError("runtime vendor components must be an array")

    names = [component.get("name") for component in lock["components"]]
    expected_names = sorted(spec.name for spec in SPECS)
    if names != expected_names:
        raise VendorError(f"runtime vendor component set/order must be {expected_names}")

    components: dict[str, dict[str, Any]] = {}
    for component in lock["components"]:
        if not isinstance(component, dict):
            raise VendorError("runtime vendor component must be an object")
        _require_keys(component, COMPONENT_KEYS, f"component {component.get('name')}")
        components[component["name"]] = component

    for spec in SPECS:
        component = components[spec.name]
        _require_keys(component["source"], SOURCE_KEYS, f"{spec.name} source")
        _require_keys(component["license"], LICENSE_KEYS, f"{spec.name} license")
        _require_keys(component["install"], INSTALL_KEYS, f"{spec.name} install")
        expected_source = {
            "archive_name": spec.archive_name,
            "url": spec.url,
            "sha256": spec.archive_sha256,
        }
        expected_license = {
            "upstream_path": spec.license_upstream_path,
            "installed_path": spec.license_installed_path,
            "sha256": spec.license_sha256,
        }
        expected_install = {
            "upstream_root": spec.upstream_root,
            "target_root": spec.target_root,
            "modification": "namespace-relocation-only",
        }
        if component["version"] != spec.version:
            raise VendorError(f"{spec.name} version is not frozen at {spec.version}")
        if component["source"] != expected_source:
            raise VendorError(f"{spec.name} source URL/hash is not the frozen source")
        if component["spdx"] != spec.spdx:
            raise VendorError(f"{spec.name} SPDX expression is not {spec.spdx}")
        if component["license"] != expected_license:
            raise VendorError(f"{spec.name} full-license record is not frozen")
        if component["install"] != expected_install:
            raise VendorError(f"{spec.name} private namespace relocation is not frozen")
        if component["exclusions"] != list(spec.exclusions):
            raise VendorError(f"{spec.name} exclusion rules are not frozen")
        if not isinstance(component["files"], list) or not component["files"]:
            raise VendorError(f"{spec.name} file inventory must be nonempty")
        installed_paths: list[str] = []
        for row in component["files"]:
            if not isinstance(row, dict):
                raise VendorError(f"{spec.name} file inventory row must be an object")
            _require_keys(row, FILE_KEYS, f"{spec.name} file inventory row")
            installed_paths.append(row["installed_path"])
        if installed_paths != sorted(installed_paths) or len(installed_paths) != len(
            set(installed_paths)
        ):
            raise VendorError(f"{spec.name} installed paths must be unique and sorted")
    return components


def _default_cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "agent-workflow-pack" / "runtime-vendors"


def _obtain_archive(spec: VendorSpec, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = cache_dir / spec.archive_name
    if archive.exists():
        actual = _sha256_file(archive)
        if actual != spec.archive_sha256:
            raise VendorError(
                f"cached archive hash mismatch for {spec.name}: "
                f"expected {spec.archive_sha256}, got {actual}"
            )
        return archive

    temporary = cache_dir / f".{spec.archive_name}.{uuid.uuid4().hex}.tmp"
    request = urllib.request.Request(spec.url, headers={"User-Agent": "agent-workflow-pack/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = _sha256_file(temporary)
        if actual != spec.archive_sha256:
            raise VendorError(
                f"downloaded archive hash mismatch for {spec.name}: "
                f"expected {spec.archive_sha256}, got {actual}"
            )
        os.replace(temporary, archive)
    except (OSError, urllib.error.URLError) as error:
        raise VendorError(f"cannot acquire frozen archive for {spec.name}: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _validate_member_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise VendorError(f"unsafe archive member path: {name}")
    return path


def _read_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    if not member.isfile():
        raise VendorError(f"selected archive member is not a regular file: {member.name}")
    extracted = archive.extractfile(member)
    if extracted is None:
        raise VendorError(f"cannot read selected archive member: {member.name}")
    return extracted.read()


def _read_archive(spec: VendorSpec, path: Path) -> ArchiveContents:
    if _sha256_file(path) != spec.archive_sha256:
        raise VendorError(f"archive hash changed before extraction for {spec.name}")
    selected_prefix = PurePosixPath(spec.archive_root) / spec.upstream_root
    license_name = (PurePosixPath(spec.archive_root) / spec.license_upstream_path).as_posix()
    selected: dict[str, bytes] = {}
    license_bytes: bytes | None = None

    try:
        with tarfile.open(path, mode="r:gz") as archive:
            for member in archive.getmembers():
                member_path = _validate_member_name(member.name)
                if member.name == license_name:
                    if license_bytes is not None:
                        raise VendorError(f"duplicate license member for {spec.name}")
                    license_bytes = _read_member(archive, member)
                    continue
                if member_path.parent != selected_prefix:
                    continue
                if member_path.suffix != ".py" or member_path.name in spec.excluded_python_files:
                    continue
                upstream_path = (PurePosixPath(spec.upstream_root) / member_path.name).as_posix()
                if upstream_path in selected:
                    raise VendorError(f"duplicate selected member: {upstream_path}")
                selected[upstream_path] = _read_member(archive, member)
    except (OSError, tarfile.TarError) as error:
        raise VendorError(f"cannot parse frozen archive for {spec.name}: {error}") from error

    if not selected:
        raise VendorError(f"frozen archive contains no selected files for {spec.name}")
    if license_bytes is None:
        raise VendorError(f"frozen archive has no full license for {spec.name}")
    if _sha256_bytes(license_bytes) != spec.license_sha256:
        raise VendorError(f"full license hash mismatch for {spec.name}")
    return ArchiveContents(files=selected, license_bytes=license_bytes)


def _validate_inventory_against_archive(
    spec: VendorSpec, component: dict[str, Any], contents: ArchiveContents
) -> None:
    rows = {row["upstream_path"]: row for row in component["files"]}
    if set(rows) != set(contents.files):
        raise VendorError(
            f"{spec.name} selected upstream inventory differs: "
            f"missing={sorted(set(contents.files) - set(rows))} "
            f"extra={sorted(set(rows) - set(contents.files))}"
        )
    for upstream_path, source_bytes in contents.files.items():
        row = rows[upstream_path]
        relative = PurePosixPath(upstream_path).relative_to(spec.upstream_root)
        installed_path = (PurePosixPath(spec.target_root) / relative).as_posix()
        source_hash = _sha256_bytes(source_bytes)
        if row["installed_path"] != installed_path:
            raise VendorError(f"{spec.name} installed path is not a namespace relocation")
        if row["upstream_sha256"] != source_hash:
            raise VendorError(f"{spec.name} upstream file hash mismatch: {upstream_path}")
        if row["installed_sha256"] != source_hash:
            raise VendorError(f"{spec.name} installed bytes are not relocation-only: {installed_path}")


def _validate_installed_tree(root: Path, components: dict[str, dict[str, Any]]) -> None:
    for spec in SPECS:
        component = components[spec.name]
        target_root = root / spec.target_root
        if not target_root.is_dir() or target_root.is_symlink():
            raise VendorError(f"missing private vendor root: {spec.target_root}")
        expected = {row["installed_path"] for row in component["files"]}
        actual: set[str] = set()
        for path in target_root.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.is_symlink():
                raise VendorError(f"vendor tree contains symlink: {relative}")
            if path.is_file():
                actual.add(relative)
            elif not path.is_dir():
                raise VendorError(f"vendor tree contains non-file entry: {relative}")
        unregistered = sorted(actual - expected)
        if unregistered:
            raise VendorError(f"unregistered vendor file: {unregistered[0]}")
        missing = sorted(expected - actual)
        if missing:
            raise VendorError(f"missing registered vendor file: {missing[0]}")
        for row in component["files"]:
            installed = root / row["installed_path"]
            actual_hash = _sha256_file(installed)
            if actual_hash != row["installed_sha256"]:
                raise VendorError(f"installed vendor hash mismatch: {row['installed_path']}")

        license_record = component["license"]
        license_path = root / license_record["installed_path"]
        if not license_path.is_file() or license_path.is_symlink():
            raise VendorError(f"missing full license: {license_record['installed_path']}")
        if _sha256_file(license_path) != license_record["sha256"]:
            raise VendorError(f"full license hash mismatch: {license_record['installed_path']}")


def _write_file(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    path.chmod(0o644)


def _replace_directory(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        os.replace(staged, target)
        return
    if target.is_symlink() or not target.is_dir():
        raise VendorError(f"refusing to replace non-directory vendor root: {target}")
    backup = target.with_name(f".{target.name}.vendor-backup-{uuid.uuid4().hex}")
    os.replace(target, backup)
    try:
        os.replace(staged, target)
    except BaseException:
        os.replace(backup, target)
        raise
    shutil.rmtree(backup)


def _synchronize(
    root: Path,
    components: dict[str, dict[str, Any]],
    archives: dict[str, ArchiveContents],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vendor-staging-", dir=root) as temporary:
        stage = Path(temporary)
        for spec in SPECS:
            component = components[spec.name]
            contents = archives[spec.name]
            for row in component["files"]:
                _write_file(stage / row["installed_path"], contents.files[row["upstream_path"]])
            _write_file(stage / spec.license_installed_path, contents.license_bytes)

        for spec in SPECS:
            _replace_directory(stage / spec.target_root, root / spec.target_root)
        for spec in SPECS:
            staged_license = stage / spec.license_installed_path
            installed_license = root / spec.license_installed_path
            installed_license.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_license, installed_license)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root containing vendor/runtime-vendor-lock.json",
    )
    parser.add_argument("--cache-dir", type=Path, default=_default_cache_dir())
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--sync", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()
    try:
        components = _validate_lock(_load_lock(root))
        archives: dict[str, ArchiveContents] = {}
        for spec in SPECS:
            archive_path = _obtain_archive(spec, args.cache_dir.resolve())
            contents = _read_archive(spec, archive_path)
            _validate_inventory_against_archive(spec, components[spec.name], contents)
            archives[spec.name] = contents
        if args.sync:
            _synchronize(root, components, archives)
            _validate_installed_tree(root, components)
            print("runtime vendor tree synchronized")
        else:
            _validate_installed_tree(root, components)
            print("runtime vendor tree verified")
    except VendorError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
