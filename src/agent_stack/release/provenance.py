"""Deterministic pre-build provenance, license, and notice inventory."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from agent_stack._vendor import yaml
from agent_stack.core.api import CANONICAL_NULL, canonical_json_bytes, digest

from .errors import LifecycleFailure


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_BUILD_KEYS = frozenset(
    {"wheel_sha256", "sdist_sha256", "container_sha256", "distribution_sha256"}
)


def _failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_PROVENANCE_INCOMPLETE", message, exit_code=30, details=details
    )


def _file_sha256(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise _failure("provenance input is unreadable", path=path.as_posix()) from error


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _failure("provenance JSON input is invalid", path=path.as_posix()) from error
    if not isinstance(value, dict):
        raise _failure("provenance JSON input must be an object", path=path.as_posix())
    return cast(dict[str, object], value)


def _load_platform_catalog(path: Path) -> Mapping[str, object]:
    try:
        value = yaml.safe_load(  # type: ignore[no-untyped-call]
            path.read_text(encoding="utf-8")
        )
    except Exception as error:
        raise _failure("platform catalog provenance input is invalid") from error
    if not isinstance(value, Mapping):
        raise _failure("platform catalog provenance input must be an object")
    return cast(Mapping[str, object], value)


def _component_id(name: str) -> str:
    return f"vendor:{name.casefold()}"


def _notice(name: str, version: str, target_root: str) -> dict[str, str]:
    namespace = target_root.removeprefix("src/").replace("/", ".")
    text = (
        f"{name} {version} is installed under the private namespace {namespace}; "
        "only that private namespace changed, and the registered source file bytes are "
        "unchanged."
    )
    return {
        "text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _vendor_components(root: Path) -> list[dict[str, object]]:
    lock = _load_json(root / "vendor/runtime-vendor-lock.json")
    raw_components = lock.get("components")
    if lock.get("namespace") != "agent_stack._vendor" or not isinstance(
        raw_components, list
    ):
        raise _failure("runtime vendor lock identity is invalid")
    result: list[dict[str, object]] = []
    for raw in raw_components:
        if not isinstance(raw, Mapping):
            raise _failure("runtime vendor component is invalid")
        name = raw.get("name")
        version = raw.get("version")
        source = raw.get("source")
        license_record = raw.get("license")
        install = raw.get("install")
        files = raw.get("files")
        spdx = raw.get("spdx")
        if not isinstance(name, str) or not isinstance(version, str):
            raise _failure("runtime vendor identity is incomplete")
        if not isinstance(source, Mapping) or set(source) != {
            "archive_name",
            "url",
            "sha256",
        }:
            raise _failure("runtime vendor source is incomplete", component=name)
        if not isinstance(source.get("sha256"), str) or not _SHA256.fullmatch(
            str(source.get("sha256"))
        ):
            raise _failure("runtime vendor source hash is invalid", component=name)
        if not isinstance(license_record, Mapping) or set(license_record) != {
            "upstream_path",
            "installed_path",
            "sha256",
        }:
            raise _failure("runtime vendor license record is incomplete", component=name)
        if not isinstance(install, Mapping) or set(install) != {
            "upstream_root",
            "target_root",
            "modification",
        }:
            raise _failure("runtime vendor install record is incomplete", component=name)
        target_root = install.get("target_root")
        if (
            not isinstance(target_root, str)
            or not target_root.startswith("src/agent_stack/_vendor/")
            or install.get("modification") != "namespace-relocation-only"
        ):
            raise _failure("runtime vendor namespace is not private", component=name)
        if not isinstance(files, list) or not files:
            raise _failure("runtime vendor file inventory is empty", component=name)
        normalized_files: list[dict[str, str]] = []
        registered: set[str] = set()
        for row in files:
            if not isinstance(row, Mapping) or set(row) != {
                "upstream_path",
                "upstream_sha256",
                "installed_path",
                "installed_sha256",
            }:
                raise _failure("runtime vendor file record is incomplete", component=name)
            normalized = {key: str(row[key]) for key in sorted(row)}
            installed_path = normalized["installed_path"]
            if installed_path in registered:
                raise _failure("runtime vendor file repeats", path=installed_path)
            registered.add(installed_path)
            actual = _file_sha256(root / installed_path)
            if actual != normalized["installed_sha256"]:
                raise _failure("runtime vendor file hash changed", path=installed_path)
            if normalized["upstream_sha256"] != normalized["installed_sha256"]:
                raise _failure("namespace relocation changed source bytes", path=installed_path)
            normalized_files.append(normalized)
        actual_paths = {
            path.relative_to(root).as_posix()
            for path in (root / target_root).rglob("*.py")
            if path.is_file() and not path.is_symlink()
        }
        unregistered = sorted(actual_paths - registered)
        missing = sorted(registered - actual_paths)
        if unregistered:
            raise _failure(
                "unregistered vendor file is present", component=name, paths=unregistered
            )
        if missing:
            raise _failure("registered vendor file is missing", component=name, paths=missing)
        license_source_path = str(license_record.get("installed_path"))
        license_sha256 = str(license_record.get("sha256"))
        if _file_sha256(root / license_source_path) != license_sha256:
            raise _failure("runtime vendor license bytes changed", component=name)
        distribution_path = f"LICENSES/{name}-{version}.txt"
        result.append(
            {
                "component_id": _component_id(name),
                "kind": "vendored-runtime",
                "name": name,
                "version": version,
                "source": dict(source),
                "license_expression": spdx,
                "license_file": {
                    "source_path": license_source_path,
                    "distribution_path": distribution_path,
                    "sha256": license_sha256,
                },
                "install": dict(install),
                "modification_notice": _notice(name, version, target_root),
                "files": sorted(normalized_files, key=lambda item: item["installed_path"]),
            }
        )
    return sorted(result, key=lambda item: str(item["component_id"]))


def _first_party_component(root: Path) -> dict[str, object]:
    pyproject_path = root / "pyproject.toml"
    try:
        project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, KeyError) as error:
        raise _failure("first-party project metadata is invalid") from error
    version = project.get("version")
    license_expression = project.get("license")
    if not isinstance(version, str) or not isinstance(license_expression, str):
        raise _failure("first-party version/license metadata is missing")
    return {
        "component_id": "first-party:agent-workflow-pack",
        "kind": "first-party",
        "name": "agent-workflow-pack",
        "version": version,
        "source": {
            "type": "git-release",
            "repository": "github.com/swl007007/agent-workflow-pack",
            "release_binding": "detached-manifest-source-commit",
            "version_source": "pyproject.toml",
        },
        "license_expression": license_expression,
        "license_file": None,
        "install": {
            "target_root": "src/agent_stack",
            "modification": "first-party",
        },
        "modification_notice": {"text": "", "sha256": CANONICAL_NULL},
        "files": [],
    }


def _projected_units(root: Path) -> list[dict[str, object]]:
    catalog = _load_platform_catalog(root / "catalog/platforms.yaml")
    platforms = catalog.get("platforms")
    if not isinstance(platforms, Sequence) or isinstance(platforms, (str, bytes)):
        raise _failure("platform catalog lacks its closed platform array")
    units: list[dict[str, object]] = []
    seen: set[str] = set()
    for platform in platforms:
        if not isinstance(platform, Mapping) or not isinstance(
            platform.get("adapter"), Mapping
        ):
            raise _failure("platform provenance record is invalid")
        adapter = cast(Mapping[str, object], platform["adapter"])
        adapter_id = adapter.get("adapter_id")
        projections = adapter.get("render_projections")
        if not isinstance(adapter_id, str) or not isinstance(projections, Sequence):
            raise _failure("platform provenance adapter is incomplete")
        for raw in projections:
            if not isinstance(raw, Mapping) or not isinstance(raw.get("unit_id"), str):
                raise _failure("projected provenance unit is invalid", adapter=adapter_id)
            unit_id = cast(str, raw["unit_id"])
            if unit_id in seen:
                raise _failure("projected provenance unit is ambiguous", unit_id=unit_id)
            seen.add(unit_id)
            projection: dict[str, object] = {
                "unit_id": unit_id,
                "platform_adapter": adapter_id,
                "definition_path": "catalog/platforms.yaml",
                "definition_digest": digest(
                    "agent-workflow.projected-unit-provenance.v1",
                    {"platform_adapter": adapter_id, "projection": dict(raw)},
                ),
                "source_component_id": "first-party:agent-workflow-pack",
                "license_expression": "Apache-2.0",
            }
            units.append(projection)
    return sorted(units, key=lambda item: str(item["unit_id"]))


def _projection(root: Path) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.provenance-lock",
        "schema_version": 1,
        "components": [_first_party_component(root), *_vendor_components(root)],
        "projected_units": _projected_units(root),
        "provider_records": [],
    }


@dataclass(frozen=True)
class FrozenProvenanceInventory:
    document: Mapping[str, object]

    @property
    def provenance_lock_digest(self) -> str:
        return cast(str, self.document["provenance_lock_digest"])

    def to_document(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(canonical_json_bytes(self.document)))


def build_frozen_provenance_inventory(root: Path) -> FrozenProvenanceInventory:
    projection = _projection(root)
    document = {
        **projection,
        "provenance_lock_digest": digest(
            "agent-workflow.provenance-lock.v1", projection
        ),
    }
    return FrozenProvenanceInventory(document=document)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return {str(key) for key in value} | {
            nested for child in value.values() for nested in _all_keys(child)
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {nested for child in value for nested in _all_keys(child)}
    return set()


def validate_provenance_inventory(
    document: Mapping[str, object], root: Path
) -> FrozenProvenanceInventory:
    if _FORBIDDEN_BUILD_KEYS & _all_keys(document):
        raise _failure("distribution container hash creates a provenance build cycle")
    expected = build_frozen_provenance_inventory(root).to_document()
    supplied = cast(dict[str, Any], json.loads(canonical_json_bytes(document)))
    if supplied != expected:
        raise _failure("frozen provenance inventory differs from authoritative inputs")
    for component in cast(list[dict[str, object]], supplied["components"]):
        license_file = component.get("license_file")
        if not isinstance(license_file, Mapping):
            continue
        distribution_path = license_file.get("distribution_path")
        expected_hash = license_file.get("sha256")
        if not isinstance(distribution_path, str) or not isinstance(expected_hash, str):
            raise _failure("frozen license record is invalid")
        if _file_sha256(root / distribution_path) != expected_hash:
            raise _failure("distributed full-license bytes differ", path=distribution_path)
    return FrozenProvenanceInventory(document=supplied)


def load_frozen_provenance(root: Path) -> FrozenProvenanceInventory:
    return validate_provenance_inventory(
        _load_json(root / "release/provenance-lock.json"), root
    )


def render_third_party_notices(inventory: FrozenProvenanceInventory) -> str:
    components = [
        component
        for component in cast(Sequence[Mapping[str, object]], inventory.document["components"])
        if component.get("kind") == "vendored-runtime"
    ]
    lines = ["# Third-Party Notices", ""]
    for component in sorted(components, key=lambda item: str(item["name"]).casefold()):
        source = cast(Mapping[str, object], component["source"])
        install = cast(Mapping[str, object], component["install"])
        license_file = cast(Mapping[str, object], component["license_file"])
        notice = cast(Mapping[str, object], component["modification_notice"])
        namespace = str(install["target_root"]).removeprefix("src/").replace("/", ".")
        lines.extend(
            [
                f"## {component['name']} {component['version']}",
                "",
                f"- SPDX license: `{component['license_expression']}`",
                f"- Source archive: `{source['archive_name']}`",
                f"- Source SHA-256: `{source['sha256']}`",
                f"- Installed namespace: `{namespace}`",
                f"- Modification: `{install['modification']}`",
                f"- Full license: `{license_file['distribution_path']}`",
                "",
                str(notice["text"]),
                "",
            ]
        )
    return "\n".join(lines)


__all__ = [
    "FrozenProvenanceInventory",
    "build_frozen_provenance_inventory",
    "load_frozen_provenance",
    "render_third_party_notices",
    "validate_provenance_inventory",
]
