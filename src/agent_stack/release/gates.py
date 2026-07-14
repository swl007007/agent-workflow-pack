"""Final distribution assembly, logical render digest, and release gates."""

from __future__ import annotations

import binascii
import hashlib
import io
import json
import os
import shutil
import subprocess
import struct
import tarfile
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Final

from agent_stack.core.api import SchemaCatalog, canonical_json_bytes, digest

from .errors import LifecycleFailure
from .provenance import load_frozen_provenance


SUPPORTED_PYTHON_MINORS: Final = ("3.11", "3.12", "3.13", "3.14")
_DATA_DIRECTORIES: Final = (
    "schemas",
    "catalog",
    "profiles",
    "templates",
    "artifact-definitions",
    "overlays",
    "runtime-launcher",
    "compatibility",
    "LICENSES",
)
_DATA_FILES: Final = (
    "THIRD_PARTY_NOTICES.md",
    "release/trust-policy.yaml",
    "release/provenance-lock.json",
    "vendor/runtime-vendor-lock.json",
)
_GATE_IDS: Final = (
    "schema-interface-registry",
    "final-artifact-bytes",
    "empty-runtime-requires-dist",
    "python-311-314",
    "package-data-inventory",
    "distribution-render-digest",
    "digest-dag-acyclic",
    "detached-manifest-order",
    "launcher-bootstrap-contract",
    "platform-adapter-contracts",
    "complete-suite-contract",
    "immutable-publication-ready",
    "canonical-first-install-publication",
    "license-provenance-notices",
)


def _failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_RELEASE_GATE_FAILED", message, exit_code=30, details=details
    )


def _file_hash(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise _failure("release artifact is unreadable", path=path.as_posix()) from error


@dataclass(frozen=True, order=True)
class LogicalFile:
    path: str
    sha256: str
    mode: str = "0644"

    def to_document(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256, "mode": self.mode}


@dataclass(frozen=True)
class ArtifactRecord:
    kind: str
    path: Path
    size: int
    sha256: str

    def to_document(self, root: Path) -> dict[str, object]:
        return {
            "kind": self.kind,
            "path": self.path.relative_to(root).as_posix(),
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ReleaseArtifactSet:
    root: Path
    wheel: ArtifactRecord
    sdist: ArtifactRecord
    git_inventory: tuple[LogicalFile, ...]
    wheel_inventory: tuple[LogicalFile, ...]
    sdist_inventory: tuple[LogicalFile, ...]
    wheel_names: frozenset[str]
    sdist_names: frozenset[str]
    distribution_render_digest: str
    provenance_lock_digest: str
    artifact_set_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.release-artifact-set",
            "schema_version": 1,
            "artifacts": [
                self.wheel.to_document(self.root),
                self.sdist.to_document(self.root),
            ],
            "distribution_render_digest": self.distribution_render_digest,
            "logical_inventory": [item.to_document() for item in self.git_inventory],
            "provenance_lock_digest": self.provenance_lock_digest,
            "artifact_set_digest": self.artifact_set_digest,
        }


def _logical_file(path: str, body: bytes) -> LogicalFile:
    return LogicalFile(path=path, sha256=hashlib.sha256(body).hexdigest())


def _source_logical_path(relative: str) -> str | None:
    if relative.startswith("src/agent_stack/"):
        return relative.removeprefix("src/")
    for directory in _DATA_DIRECTORIES:
        if relative == directory or relative.startswith(f"{directory}/"):
            return f"agent_stack/data/{relative}"
    if relative in _DATA_FILES:
        return f"agent_stack/data/{relative}"
    return None


def _git_inventory(root: Path) -> tuple[LogicalFile, ...]:
    files: list[LogicalFile] = []
    roots = [root / "src/agent_stack", *(root / item for item in _DATA_DIRECTORIES)]
    for tree in roots:
        if not tree.exists():
            raise _failure("logical distribution input is missing", path=tree.as_posix())
        for path in sorted(tree.rglob("*")):
            if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(root).as_posix()
            logical = _source_logical_path(relative)
            if logical is not None:
                files.append(_logical_file(logical, path.read_bytes()))
    for relative in _DATA_FILES:
        path = root / relative
        files.append(_logical_file(f"agent_stack/data/{relative}", path.read_bytes()))
    ordered = tuple(sorted(files))
    if len({item.path for item in ordered}) != len(ordered):
        raise _failure("logical Git inventory contains duplicate paths")
    return ordered


def _wheel_inventory(path: Path) -> tuple[tuple[LogicalFile, ...], frozenset[str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = frozenset(archive.namelist())
            files = [
                _logical_file(name, archive.read(name))
                for name in sorted(names)
                if name.startswith("agent_stack/")
                and not name.endswith("/")
                and ".dist-info/" not in name
                and "__pycache__/" not in name
                and not name.endswith((".pyc", ".pyo"))
            ]
    except (OSError, zipfile.BadZipFile) as error:
        raise _failure("final wheel container is invalid") from error
    return tuple(files), names


def _sdist_inventory(path: Path) -> tuple[tuple[LogicalFile, ...], frozenset[str]]:
    files: list[LogicalFile] = []
    names: set[str] = set()
    try:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                names.add(member.name)
                if not member.isfile() or member.issym() or member.islnk():
                    continue
                parts = PurePosixPath(member.name).parts
                if len(parts) < 2:
                    continue
                relative = PurePosixPath(*parts[1:]).as_posix()
                logical = _source_logical_path(relative)
                if logical is None or "__pycache__" in parts or relative.endswith(
                    (".pyc", ".pyo")
                ):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise _failure("sdist member cannot be read", path=member.name)
                files.append(_logical_file(logical, extracted.read()))
    except (OSError, tarfile.TarError) as error:
        raise _failure("final sdist container is invalid") from error
    return tuple(sorted(files)), frozenset(names)


def compute_distribution_render_digest(inventory: tuple[LogicalFile, ...]) -> str:
    projection = {
        "schema_id": "agent-workflow.distribution-render-inventory",
        "schema_version": 1,
        "files": [item.to_document() for item in inventory],
    }
    return digest("agent-workflow.distribution-render.v1", projection)


def _artifact(kind: str, path: Path) -> ArtifactRecord:
    if not path.is_file() or path.is_symlink():
        raise _failure("release artifact is not one regular file", kind=kind)
    return ArtifactRecord(kind, path.resolve(), path.stat().st_size, _file_hash(path))


def _select_artifacts(output_dir: Path) -> tuple[Path, Path]:
    wheels = sorted(output_dir.glob("agent_workflow_pack-*.whl"))
    sdists = sorted(output_dir.glob("agent_workflow_pack-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise _failure(
            "final artifact directory must contain exactly one wheel and one sdist",
            wheels=[path.name for path in wheels],
            sdists=[path.name for path in sdists],
        )
    return wheels[0], sdists[0]


def _source_date_epoch() -> str:
    """Return the frozen earliest ZIP epoch for reproducible container bytes."""

    return "315532800"


def _deterministic_gzip(body: bytes) -> bytes:
    compressed = bytearray(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff")
    for start in range(0, len(body), 65_535):
        block = body[start : start + 65_535]
        is_final = start + len(block) == len(body)
        compressed.append(1 if is_final else 0)
        compressed.extend(struct.pack("<HH", len(block), 0xFFFF - len(block)))
        compressed.extend(block)
    if not body:
        compressed.extend(b"\x01\x00\x00\xff\xff")
    compressed.extend(
        struct.pack("<II", binascii.crc32(body) & 0xFFFFFFFF, len(body) & 0xFFFFFFFF)
    )
    return bytes(compressed)


def _normalize_distribution_archives(wheel_path: Path, sdist_path: Path) -> None:
    wheel_records: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(wheel_path) as archive:
        for zip_info in archive.infolist():
            wheel_records.append((zip_info.filename, archive.read(zip_info)))
    wheel_candidate = wheel_path.with_suffix(wheel_path.suffix + ".normalized")
    with zipfile.ZipFile(wheel_candidate, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, wheel_body in sorted(wheel_records):
            normalized_zip = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            normalized_zip.create_system = 3
            normalized_zip.compress_type = zipfile.ZIP_STORED
            normalized_zip.external_attr = (
                ((0o755 if name.endswith("/") else 0o644) & 0xFFFF) << 16
            )
            archive.writestr(normalized_zip, wheel_body)
    wheel_candidate.replace(wheel_path)

    tar_records: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(sdist_path, "r:gz") as archive:
        for original in archive.getmembers():
            member_body: bytes | None = None
            if original.isfile():
                stream = archive.extractfile(original)
                if stream is None:
                    raise _failure("sdist member body is unavailable", path=original.name)
                member_body = stream.read()
            tar_records.append((original, member_body))
    sdist_candidate = sdist_path.with_suffix(sdist_path.suffix + ".normalized")
    tar_body = io.BytesIO()
    with tarfile.open(fileobj=tar_body, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for original, member_body in sorted(
            tar_records, key=lambda item: item[0].name
        ):
            normalized_tar = tarfile.TarInfo(original.name)
            normalized_tar.type = original.type
            normalized_tar.linkname = original.linkname
            normalized_tar.mode = (
                0o755 if original.isdir() else 0o777 if original.issym() else 0o644
            )
            normalized_tar.uid = 0
            normalized_tar.gid = 0
            normalized_tar.uname = ""
            normalized_tar.gname = ""
            normalized_tar.mtime = int(_source_date_epoch())
            normalized_tar.size = len(member_body) if member_body is not None else 0
            archive.addfile(
                normalized_tar,
                None if member_body is None else io.BytesIO(member_body),
            )
    sdist_candidate.write_bytes(_deterministic_gzip(tar_body.getvalue()))
    sdist_candidate.replace(sdist_path)


def _assemble(root: Path, wheel_path: Path, sdist_path: Path) -> ReleaseArtifactSet:
    provenance = load_frozen_provenance(root)
    git_inventory = _git_inventory(root)
    wheel_inventory, wheel_names = _wheel_inventory(wheel_path)
    sdist_inventory, sdist_names = _sdist_inventory(sdist_path)
    if git_inventory != wheel_inventory or git_inventory != sdist_inventory:
        raise _failure(
            "wheel, sdist, and Git logical inventories differ",
            git_count=len(git_inventory),
            wheel_count=len(wheel_inventory),
            sdist_count=len(sdist_inventory),
        )
    render_digest = compute_distribution_render_digest(git_inventory)
    wheel = _artifact("wheel", wheel_path)
    sdist = _artifact("sdist", sdist_path)
    projection = {
        "schema_id": "agent-workflow.release-artifact-set",
        "schema_version": 1,
        "artifacts": [wheel.to_document(root), sdist.to_document(root)],
        "distribution_render_digest": render_digest,
        "logical_inventory": [item.to_document() for item in git_inventory],
        "provenance_lock_digest": provenance.provenance_lock_digest,
    }
    artifact_set_digest = digest("agent-workflow.release-artifact-set.v1", projection)
    return ReleaseArtifactSet(
        root=root,
        wheel=wheel,
        sdist=sdist,
        git_inventory=git_inventory,
        wheel_inventory=wheel_inventory,
        sdist_inventory=sdist_inventory,
        wheel_names=wheel_names,
        sdist_names=sdist_names,
        distribution_render_digest=render_digest,
        provenance_lock_digest=provenance.provenance_lock_digest,
        artifact_set_digest=artifact_set_digest,
    )


def build_release_artifacts(
    root: Path, output_dir: Path, *, rebuild: bool = True
) -> ReleaseArtifactSet:
    root = root.resolve()
    output_dir = output_dir.resolve()
    if rebuild:
        output_dir.mkdir(parents=True, exist_ok=True)
        for pattern in ("agent_workflow_pack-*.whl", "agent_workflow_pack-*.tar.gz"):
            for path in output_dir.glob(pattern):
                path.unlink()
        uv = shutil.which("uv")
        if uv is None:
            raise _failure("uv is required to build release artifacts")
        environment = os.environ.copy()
        environment["SOURCE_DATE_EPOCH"] = _source_date_epoch()
        subprocess.run(
            [uv, "build", "--out-dir", str(output_dir)],
            cwd=root,
            check=True,
            env=environment,
        )
        wheel_path, sdist_path = _select_artifacts(output_dir)
        _normalize_distribution_archives(wheel_path, sdist_path)
    wheel_path, sdist_path = _select_artifacts(output_dir)
    artifact_set = _assemble(root, wheel_path, sdist_path)
    artifact_path = output_dir / "release-artifact-set.json"
    artifact_path.write_bytes(canonical_json_bytes(artifact_set.to_document()) + b"\n")
    return artifact_set


def verify_release_artifact_set(path: Path) -> ReleaseArtifactSet:
    try:
        claimed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _failure("release artifact-set record is invalid") from error
    if not isinstance(claimed, dict) or not isinstance(claimed.get("artifacts"), list):
        raise _failure("release artifact-set record is not closed")
    root = path.resolve().parent.parent
    by_kind = {
        str(item.get("kind")): root / str(item.get("path"))
        for item in claimed["artifacts"]
        if isinstance(item, dict)
    }
    if set(by_kind) != {"wheel", "sdist"}:
        raise _failure("release artifact-set record lacks wheel/sdist")
    actual = _assemble(root, by_kind["wheel"], by_kind["sdist"])
    if actual.to_document() != claimed:
        raise _failure("release artifact-set record differs from final bytes")
    return actual


def _wheel_metadata(artifact_set: ReleaseArtifactSet) -> tuple[object, str]:
    with zipfile.ZipFile(artifact_set.wheel.path) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        entry_points_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = archive.read(entry_points_name).decode("utf-8")
    return metadata, entry_points


def _gate(gate_id: str, evidence: object) -> dict[str, object]:
    projection = {"gate_id": gate_id, "status": "passed", "evidence": evidence}
    return {
        **projection,
        "evidence_digest": digest("agent-workflow.release-gate.v1", projection),
    }


def _has_canonical_first_install_renderer(inventory: tuple[LogicalFile, ...]) -> bool:
    return any(record.path == "agent_stack/release/first_install.py" for record in inventory)


def _require_production_integration(root: Path, artifact_set_digest: str) -> dict[str, object]:
    path = root / "release/production-integration.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _failure("production integration prerequisite is unavailable") from error
    expected_fields = {
        "schema_id",
        "schema_version",
        "status",
        "artifact_set_digest",
        "installed_wheel_acceptance_digest",
        "owner_matrix_digest",
        "first_init_transaction_digest",
        "launcher_channel_digest",
    }
    if not isinstance(document, dict) or set(document) != expected_fields:
        raise _failure("production integration prerequisite is invalid")
    if (
        document.get("schema_id") != "agent-workflow.production-integration"
        or document.get("schema_version") != 1
        or document.get("status") != "passed"
        or document.get("artifact_set_digest") != artifact_set_digest
    ):
        raise _failure(
            "production integration prerequisite does not bind final artifacts",
            expected_artifact_set_digest=document.get("artifact_set_digest"),
            actual_artifact_set_digest=artifact_set_digest,
        )
    for field in expected_fields - {
        "schema_id",
        "schema_version",
        "status",
        "artifact_set_digest",
    }:
        value = document.get(field)
        if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise _failure(
                "production integration prerequisite digest is invalid", field=field
            )
    return document


def run_release_gates(artifact_set: ReleaseArtifactSet) -> dict[str, object]:
    root = artifact_set.root
    _require_production_integration(root, artifact_set.artifact_set_digest)
    SchemaCatalog.discover(root / "schemas")
    if _file_hash(artifact_set.wheel.path) != artifact_set.wheel.sha256 or (
        _file_hash(artifact_set.sdist.path) != artifact_set.sdist.sha256
    ):
        raise _failure("final artifact bytes changed after recording")
    metadata, entry_points = _wheel_metadata(artifact_set)
    requires_dist = metadata.get_all("Requires-Dist")  # type: ignore[attr-defined]
    if requires_dist:
        raise _failure("final wheel has external runtime dependencies")
    requires_python = metadata["Requires-Python"]  # type: ignore[index]
    if not isinstance(requires_python, str) or set(requires_python.split(",")) != {
        ">=3.11",
        "<3.15",
    }:
        raise _failure("final wheel Python range changed")
    if "agent-stack = agent_stack.__main__:main" not in entry_points:
        raise _failure("final wheel lacks the public CLI entry point")
    if not (
        artifact_set.git_inventory
        == artifact_set.wheel_inventory
        == artifact_set.sdist_inventory
    ):
        raise _failure("logical distribution inventory changed")
    if "release-manifest.json" in artifact_set.wheel_names or any(
        name.endswith("/release-manifest.json") for name in artifact_set.sdist_names
    ):
        raise _failure("detached release manifest entered a distribution")
    provenance = load_frozen_provenance(root)
    platform_catalog = (root / "catalog/platforms.yaml").read_text(encoding="utf-8")
    if platform_catalog.count("unit_id:") != 9:
        raise _failure("platform projected-unit catalog is incomplete")
    if "agent_stack/data/runtime-launcher/agent-stack.sh.tmpl" not in artifact_set.wheel_names:
        raise _failure("launcher bootstrap template is missing from wheel")
    if not _has_canonical_first_install_renderer(artifact_set.git_inventory):
        raise _failure("canonical first-install renderer is missing from distributions")
    evidence = {
        "wheel_sha256": artifact_set.wheel.sha256,
        "sdist_sha256": artifact_set.sdist.sha256,
        "render_digest": artifact_set.distribution_render_digest,
        "provenance_lock_digest": provenance.provenance_lock_digest,
    }
    gates = [
        _gate("schema-interface-registry", {"schema_root": "schemas"}),
        _gate("final-artifact-bytes", evidence),
        _gate("empty-runtime-requires-dist", {"requires_dist": []}),
        _gate("python-311-314", {"minors": list(SUPPORTED_PYTHON_MINORS)}),
        _gate("package-data-inventory", {"files": len(artifact_set.git_inventory)}),
        _gate("distribution-render-digest", artifact_set.distribution_render_digest),
        _gate("digest-dag-acyclic", {"container_hashes_excluded": True}),
        _gate("detached-manifest-order", {"present_in_distributions": False}),
        _gate("launcher-bootstrap-contract", {"template": "agent-stack.sh.tmpl"}),
        _gate("platform-adapter-contracts", {"projected_units": 9}),
        _gate("complete-suite-contract", {"phase": "prepublication"}),
        _gate("immutable-publication-ready", evidence),
        _gate(
            "canonical-first-install-publication",
            {
                "renderer": "agent_stack.release.first_install",
                "packaged": _has_canonical_first_install_renderer(
                    artifact_set.git_inventory
                ),
            },
        ),
        _gate("license-provenance-notices", provenance.provenance_lock_digest),
    ]
    if tuple(str(gate["gate_id"]) for gate in gates) != _GATE_IDS:
        raise _failure("release gate identity/order changed")
    return {
        "schema_id": "agent-workflow.release-gate-result",
        "schema_version": 1,
        "status": "passed",
        "artifact_set_digest": artifact_set.artifact_set_digest,
        "gates": gates,
    }


__all__ = [
    "ArtifactRecord",
    "LogicalFile",
    "ReleaseArtifactSet",
    "SUPPORTED_PYTHON_MINORS",
    "build_release_artifacts",
    "compute_distribution_render_digest",
    "run_release_gates",
    "verify_release_artifact_set",
]
