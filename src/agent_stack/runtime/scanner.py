"""Bounded, fact-only Trellis task quiescence scanner."""

from __future__ import annotations

import hashlib
import os
import stat
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from agent_stack._vendor import fastjsonschema
from agent_stack.core.api import (
    TaskSnapshotAndFindings,
    VerifiedDiscoverySchemas,
    VerifiedTrellisTaskLayout,
)
from agent_stack.core.artifact_policy import (
    MetadataContract,
    validate_task_journal_name,
    validate_task_segment,
)
from agent_stack.core.canonical import (
    canonical_json_bytes,
    digest,
    normalize_mode,
    normalize_nfc,
    normalize_path,
)
from agent_stack.core.errors import CoreFailure
from agent_stack.core.schema_catalog import SchemaCatalog


_TASK_STATUS = frozenset(
    {"admitting", "active", "blocked", "completed", "archiving", "archived"}
)
_TASK_MODES = frozenset({"trellis-native", "speckit-superpowers"})


@dataclass(frozen=True)
class _SchemaEntry:
    schema_id: str
    schema_version: int
    document_format: str
    schema: Mapping[str, object]


@dataclass(frozen=True)
class _TaskObservation:
    path: str
    role: str
    task_id: str
    admission_task_ref: str
    integration_byte_hash: str
    integration_mode: str
    integration_schema_id: str
    integration_schema_version: int
    lifecycle_status: str
    revision: int
    mode: str
    task_contract_digest: str
    task_contract_surfaces: tuple[dict[str, str], ...]

    def semantic_projection(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "admission_task_ref": self.admission_task_ref,
            "integration_byte_hash": self.integration_byte_hash,
            "integration_mode": self.integration_mode,
            "integration_schema_id": self.integration_schema_id,
            "integration_schema_version": self.integration_schema_version,
            "lifecycle_status": self.lifecycle_status,
            "revision": self.revision,
            "mode": self.mode,
            "task_contract_digest": self.task_contract_digest,
            "task_contract_surfaces": list(self.task_contract_surfaces),
        }


@dataclass(frozen=True)
class _MetadataObservation:
    path: str
    byte_hash: str
    mode: str
    parser_id: str
    parser_version: int
    classifier_id: str
    classifier_version: int
    parsed_task_refs: tuple[str, ...]
    semantic_role: str
    classification: str

    def document(self) -> dict[str, object]:
        return {
            "path": self.path,
            "byte_hash": self.byte_hash,
            "mode": self.mode,
            "parser_id": self.parser_id,
            "parser_version": self.parser_version,
            "classifier_id": self.classifier_id,
            "classifier_version": self.classifier_version,
            "parsed_task_refs": list(self.parsed_task_refs),
            "semantic_role": self.semantic_role,
            "classification": self.classification,
        }


@dataclass(frozen=True)
class _JournalObservation:
    path: str
    byte_hash: str
    mode: str
    schema_id: str
    schema_version: int
    operation: str
    phase: str
    task_id: str
    task_ref: str
    terminal: bool

    def document(self) -> dict[str, object]:
        return {
            "journal_path": self.path,
            "byte_hash": self.byte_hash,
            "mode": self.mode,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "operation": self.operation,
            "phase": self.phase,
            "task_id": self.task_id,
            "task_ref": self.task_ref,
            "terminal": self.terminal,
        }


class _BundleError(ValueError):
    pass


class _DiscoveryBundle:
    def __init__(self, verified: VerifiedDiscoverySchemas) -> None:
        normalized = _mapping(verified.normalized, "discovery schema bundle")
        if set(normalized) != {"schemas", "parsers", "classifiers", "phase_classifiers"}:
            raise _BundleError("discovery schema bundle fields are not closed")
        self.digest = verified.schema_bundle_digest
        self.schemas: dict[tuple[str, int], _SchemaEntry] = {}
        for raw in _array(normalized.get("schemas"), "schemas"):
            item = _mapping(raw, "schema entry")
            if set(item) != {"schema_id", "schema_version", "format", "schema"}:
                raise _BundleError("schema entry fields are not closed")
            schema_id = _nonempty(item.get("schema_id"), "schema id")
            schema_version = _positive_int(item.get("schema_version"), "schema version")
            document_format = _nonempty(item.get("format"), "schema format")
            if document_format not in {"json", "yaml"}:
                raise _BundleError("schema format is not allowlisted")
            schema = _mapping(item.get("schema"), "JSON schema")
            key = (schema_id, schema_version)
            if key in self.schemas:
                raise _BundleError("schema identity/version is duplicated")
            self.schemas[key] = _SchemaEntry(
                schema_id, schema_version, document_format, schema
            )

        self.parsers: dict[tuple[str, int], str] = {}
        for raw in _array(normalized.get("parsers"), "parsers"):
            item = _mapping(raw, "parser entry")
            if set(item) != {"parser_id", "parser_version", "format"}:
                raise _BundleError("parser entry fields are not closed")
            key = (
                _nonempty(item.get("parser_id"), "parser id"),
                _positive_int(item.get("parser_version"), "parser version"),
            )
            parser_format = _nonempty(item.get("format"), "parser format")
            if parser_format != "json" or key in self.parsers:
                raise _BundleError("parser entry is unsupported or duplicated")
            self.parsers[key] = parser_format

        self.classifiers: dict[tuple[str, int], Mapping[str, object]] = {}
        for raw in _array(normalized.get("classifiers"), "classifiers"):
            item = _mapping(raw, "classifier entry")
            if set(item) != {
                "classifier_id",
                "classifier_version",
                "strategy",
                "canonical_empty_state_id",
            }:
                raise _BundleError("classifier entry fields are not closed")
            key = (
                _nonempty(item.get("classifier_id"), "classifier id"),
                _positive_int(item.get("classifier_version"), "classifier version"),
            )
            if item.get("strategy") not in {"task-refs-empty", "always-nonempty"}:
                raise _BundleError("classifier strategy is unsupported")
            _nonempty(item.get("canonical_empty_state_id"), "canonical empty state id")
            if key in self.classifiers:
                raise _BundleError("classifier entry is duplicated")
            self.classifiers[key] = item

        self.phase_classifiers: dict[tuple[str, int], Mapping[str, object]] = {}
        for raw in _array(normalized.get("phase_classifiers"), "phase classifiers"):
            item = _mapping(raw, "phase classifier entry")
            if set(item) != {
                "classifier_id",
                "classifier_version",
                "operations",
                "terminal_phases",
            }:
                raise _BundleError("phase classifier entry fields are not closed")
            key = (
                _nonempty(item.get("classifier_id"), "phase classifier id"),
                _positive_int(item.get("classifier_version"), "phase classifier version"),
            )
            operations = _mapping(item.get("operations"), "phase operations")
            for operation, phases in operations.items():
                _nonempty(operation, "phase operation")
                normalized_phases = tuple(
                    _nonempty(phase, "phase") for phase in _array(phases, "operation phases")
                )
                if not normalized_phases or len(set(normalized_phases)) != len(
                    normalized_phases
                ):
                    raise _BundleError("operation phases are empty or duplicated")
            terminals = tuple(
                _nonempty(phase, "terminal phase")
                for phase in _array(item.get("terminal_phases"), "terminal phases")
            )
            if not terminals or len(set(terminals)) != len(terminals):
                raise _BundleError("terminal phases are empty or duplicated")
            if key in self.phase_classifiers:
                raise _BundleError("phase classifier is duplicated")
            self.phase_classifiers[key] = item

    def parse_and_validate(
        self,
        payload: bytes,
        *,
        schema_id: str,
        allowed_versions: Sequence[int],
        parser: tuple[str, int] | None = None,
    ) -> tuple[Mapping[str, object], _SchemaEntry]:
        if parser is not None and parser not in self.parsers:
            raise _BundleError("metadata parser is not in the verified bundle")
        candidates = [
            self.schemas[(schema_id, version)]
            for version in allowed_versions
            if (schema_id, version) in self.schemas
        ]
        if not candidates:
            raise _BundleError("schema identity/version is not in the verified bundle")
        formats = {candidate.document_format for candidate in candidates}
        if parser is not None and formats != {self.parsers[parser]}:
            raise _BundleError("parser and schema formats disagree")
        try:
            text = payload.decode("utf-8", errors="strict")
            if formats == {"yaml"}:
                parsed = SchemaCatalog.parse_yaml(text)
            elif formats == {"json"}:
                parsed = SchemaCatalog.parse_json(text)
            else:
                raise _BundleError("schema versions disagree on document format")
        except (UnicodeError, CoreFailure) as error:
            raise _BundleError("document parsing failed") from error
        document = _mapping(parsed, "parsed document")
        version = document.get("schema_version")
        if isinstance(version, bool) or not isinstance(version, int):
            raise _BundleError("document schema_version is invalid")
        entry = self.schemas.get((schema_id, version))
        if entry is None or version not in allowed_versions:
            raise _BundleError("document schema version is unsupported")
        try:
            validated = fastjsonschema.compile(entry.schema)(dict(document))  # type: ignore[no-untyped-call]
        except Exception as error:
            raise _BundleError("document does not satisfy its verified schema") from error
        return _mapping(validated, "validated document"), entry


class _Findings:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, object]] = {}

    def add(self, kind: str, **fields: object) -> None:
        projection = {"kind": kind, **fields}
        identifier = f"finding-{hashlib.sha256(canonical_json_bytes(projection)).hexdigest()}"
        self._records[identifier] = {"kind": kind, "finding_id": identifier, **fields}

    def documents(self) -> list[dict[str, object]]:
        return [self._records[key] for key in sorted(self._records)]


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _BundleError(f"{label} must be a string-keyed object")
    return value


def _array(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _BundleError(f"{label} must be an array")
    return value


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise _BundleError(f"{label} must be a nonempty string")
    return value


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _BundleError(f"{label} must be a positive integer")
    return value


def _safe_relative(path: str) -> str:
    try:
        return normalize_path(path)
    except CoreFailure:
        parent = path.rsplit("/", 1)[0] if "/" in path else "invalid"
        try:
            parent = normalize_path(parent)
        except CoreFailure:
            parent = "invalid"
        token = hashlib.sha256(os.fsencode(path)).hexdigest()[:24]
        return f"{parent}/invalid-{token}"


def _relative_join(root: str, name: str) -> str:
    return _safe_relative(f"{root}/{name}")


def _path_kind(project_root: Path, relative: str) -> tuple[str, os.stat_result | None]:
    current = project_root
    for segment in relative.split("/"):
        current = current / segment
        try:
            status = current.lstat()
        except FileNotFoundError:
            return "missing", None
        except OSError:
            return "io-error", None
        if stat.S_ISLNK(status.st_mode):
            return "symlink", status
    if stat.S_ISDIR(status.st_mode):
        return "directory", status
    if stat.S_ISREG(status.st_mode):
        return "regular", status
    return "other", status


def _read_regular(
    project_root: Path, relative: str, maximum: int
) -> tuple[bytes, str, str] | str:
    kind, _ = _path_kind(project_root, relative)
    if kind != "regular":
        return kind
    path = project_root / relative
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return "io-error"
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return "wrong-type"
        if before.st_size > maximum:
            return "oversized"
        payload = bytearray()
        while len(payload) <= maximum:
            block = os.read(descriptor, min(65536, maximum + 1 - len(payload)))
            if not block:
                break
            payload.extend(block)
        after = os.fstat(descriptor)
        if len(payload) > maximum:
            return "oversized"
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            return "raced"
        return (
            bytes(payload),
            hashlib.sha256(payload).hexdigest(),
            normalize_mode(stat.S_IMODE(after.st_mode)),
        )
    except OSError:
        return "io-error"
    finally:
        os.close(descriptor)


def _json_pointer(document: Mapping[str, object], pointer: str) -> object:
    current: object = document
    for raw_segment in pointer.removeprefix("/").split("/") if pointer != "/" else [""]:
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or segment not in current:
            return None
        current = current[segment]
    return current


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise _BundleError("task identity is not a string")
    try:
        parsed = str(uuid.UUID(value))
    except ValueError as error:
        raise _BundleError("task identity is not a UUID") from error
    if parsed != value:
        raise _BundleError("task identity is not canonical")
    return parsed


def _layout_ambiguous(
    findings: _Findings,
    *,
    path: str,
    evidence_class: str,
    parser_id: str,
    parser_version: int,
    schema_id: str,
    schema_version: int,
) -> None:
    findings.add(
        "layout-ambiguous",
        normalized_path=_safe_relative(path),
        evidence_class=evidence_class,
        parser_id=parser_id,
        parser_version=parser_version,
        evidence_schema_id=schema_id,
        evidence_schema_version=schema_version,
    )


def _collision(findings: _Findings, paths: Sequence[str], collision_class: str) -> None:
    normalized = sorted({_safe_relative(path) for path in paths})
    if len(normalized) < 2:
        marker = hashlib.sha256(os.fsencode(paths[0])).hexdigest()[:16]
        normalized.append(f"{normalized[0]}.alias-{marker}")
    findings.add(
        "collision", normalized_aliases=normalized, collision_class=collision_class
    )


class NormativeTaskScanner:
    """Bind the frozen four-argument scanner port to one verified project root."""

    def __init__(self, project_root: str | Path) -> None:
        root = Path(project_root)
        if not root.is_absolute():
            root = root.absolute()
        self.project_root = root

    def __call__(
        self,
        source_layout: VerifiedTrellisTaskLayout,
        target_layout: VerifiedTrellisTaskLayout,
        source_schemas: VerifiedDiscoverySchemas,
        target_schemas: VerifiedDiscoverySchemas,
    ) -> TaskSnapshotAndFindings:
        findings = _Findings()
        try:
            source_bundle = _DiscoveryBundle(source_schemas)
        except _BundleError:
            source_bundle = None
        try:
            target_bundle = _DiscoveryBundle(target_schemas)
        except _BundleError:
            target_bundle = None

        task_views: dict[str, dict[str, _TaskObservation]] = defaultdict(dict)
        metadata_views: dict[str, dict[str, _MetadataObservation]] = defaultdict(dict)
        journal_views: dict[str, dict[str, _JournalObservation]] = defaultdict(dict)

        self._scan_layout_tasks(
            "source", source_layout, source_bundle, task_views, findings
        )
        self._scan_layout_tasks(
            "target", target_layout, target_bundle, task_views, findings
        )
        self._scan_layout_metadata(
            "source", source_layout, source_bundle, metadata_views, findings
        )
        self._scan_layout_metadata(
            "target", target_layout, target_bundle, metadata_views, findings
        )
        self._scan_layout_journals(
            "source", source_layout, source_bundle, journal_views, findings
        )
        self._scan_layout_journals(
            "target", target_layout, target_bundle, journal_views, findings
        )

        tasks = self._merge_tasks(task_views, findings)
        metadata = self._merge_metadata(metadata_views, findings)
        journals = self._merge_journals(journal_views, tasks, findings)
        finding_documents = findings.documents()
        projection: dict[str, object] = {
            "schema_id": "agent-workflow.task-quiescence-snapshot",
            "schema_version": 1,
            "source_layout_digest": source_layout.layout_digest,
            "target_layout_digest": target_layout.layout_digest,
            "source_schema_bundle_digest": source_schemas.schema_bundle_digest,
            "target_schema_bundle_digest": target_schemas.schema_bundle_digest,
            "tasks": tasks,
            "metadata": metadata,
            "task_journals": journals,
            "finding_ids": sorted(str(item["finding_id"]) for item in finding_documents),
        }
        task_quiescence_digest = digest("agent-workflow.task-quiescence.v1", projection)
        snapshot = {**projection, "task_quiescence_digest": task_quiescence_digest}
        finding_envelope = {
            "schema_id": "agent-workflow.task-findings",
            "schema_version": 1,
            "findings": finding_documents,
        }
        return TaskSnapshotAndFindings(
            snapshot=MappingProxyType(snapshot),
            findings=MappingProxyType(finding_envelope),
            task_quiescence_digest=task_quiescence_digest,
        )

    def _scan_layout_tasks(
        self,
        side: str,
        layout: VerifiedTrellisTaskLayout,
        bundle: _DiscoveryBundle | None,
        views: dict[str, dict[str, _TaskObservation]],
        findings: _Findings,
    ) -> None:
        discovery = _mapping(layout.normalized.get("task_discovery"), "task discovery")
        for role, root in (("active", layout.active_root), ("archive", layout.archive_root)):
            self._scan_task_partition(
                side, role, root, layout, discovery, bundle, views, findings
            )

    def _scan_task_partition(
        self,
        side: str,
        role: str,
        root: str,
        layout: VerifiedTrellisTaskLayout,
        discovery: Mapping[str, object],
        bundle: _DiscoveryBundle | None,
        views: dict[str, dict[str, _TaskObservation]],
        findings: _Findings,
    ) -> None:
        schema_id = str(discovery["integration_schema_id"])
        versions = tuple(
            _positive_int(value, "integration schema version")
            for value in _array(discovery["integration_schema_versions"], "versions")
        )
        root_kind, _ = _path_kind(self.project_root, root)
        if root_kind == "missing":
            return
        if root_kind != "directory":
            _layout_ambiguous(
                findings,
                path=root,
                evidence_class=f"task-root-{root_kind}",
                parser_id="yaml-json-object-v1",
                parser_version=1,
                schema_id=schema_id,
                schema_version=versions[0],
            )
            return
        try:
            entries = sorted(os.scandir(self.project_root / root), key=lambda item: os.fsencode(item.name))
        except OSError:
            _layout_ambiguous(
                findings,
                path=root,
                evidence_class="task-root-io-error",
                parser_id="yaml-json-object-v1",
                parser_version=1,
                schema_id=schema_id,
                schema_version=versions[0],
            )
            return
        max_entries = _positive_int(discovery["max_root_entries"], "max root entries")
        if len(entries) > max_entries:
            findings.add(
                "scan-limit",
                contract_id=f"{layout.adapter_id}:{role}-root",
                limit_kind="max_root_entries",
                configured_limit=max_entries,
            )

        allowed = {str(value).casefold() for value in _array(discovery["allowed_non_task_entries"], "allowed entries")}
        partition_segment: str | None = None
        if role == "active" and layout.archive_root.startswith(root.rstrip("/") + "/"):
            partition_segment = layout.archive_root[len(root.rstrip("/")) + 1 :].split("/", 1)[0]

        aliases: dict[str, list[str]] = defaultdict(list)
        candidates: list[tuple[os.DirEntry[str], str]] = []
        for entry in entries:
            path = _relative_join(root, entry.name)
            if entry.name.casefold() in allowed or entry.name == partition_segment:
                continue
            try:
                normalized_segment = validate_task_segment(entry.name)
            except CoreFailure:
                findings.add(
                    "unknown-entry",
                    normalized_path=_safe_relative(path),
                    root_contract_id=f"{layout.adapter_id}:{role}-root",
                )
                continue
            aliases[normalize_nfc(normalized_segment).casefold()].append(path)
            if entry.name != normalized_segment:
                _collision(findings, [path, f"{root}/{normalized_segment}"], "unicode-alias")
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                findings.add(
                    "unknown-entry",
                    normalized_path=_safe_relative(path),
                    root_contract_id=f"{layout.adapter_id}:{role}-root",
                )
                continue
            candidates.append((entry, path))
        for paths in aliases.values():
            if len(paths) > 1:
                _collision(findings, paths, "case-unicode-alias")
        max_tasks = _positive_int(discovery["max_tasks"], "max tasks")
        if len(candidates) > max_tasks:
            findings.add(
                "scan-limit",
                contract_id=f"{layout.adapter_id}:{role}-root",
                limit_kind="max_tasks",
                configured_limit=max_tasks,
            )

        integration_name = str(discovery["integration_relative_path"])
        maximum = _positive_int(discovery["max_integration_bytes"], "integration bytes")
        for _, path in candidates:
            integration_path = f"{path}/{integration_name}"
            read = _read_regular(self.project_root, integration_path, maximum)
            if isinstance(read, str):
                _layout_ambiguous(
                    findings,
                    path=integration_path,
                    evidence_class=f"integration-{read}",
                    parser_id="yaml-json-object-v1",
                    parser_version=1,
                    schema_id=schema_id,
                    schema_version=versions[0],
                )
                continue
            payload, byte_hash, mode = read
            if bundle is None:
                _layout_ambiguous(
                    findings,
                    path=integration_path,
                    evidence_class="discovery-schema-bundle-unsupported",
                    parser_id="yaml-json-object-v1",
                    parser_version=1,
                    schema_id=schema_id,
                    schema_version=versions[0],
                )
                continue
            try:
                document, schema = bundle.parse_and_validate(
                    payload, schema_id=schema_id, allowed_versions=versions
                )
                observation = self._task_observation(
                    path, role, document, schema, byte_hash, mode
                )
            except (_BundleError, CoreFailure):
                _layout_ambiguous(
                    findings,
                    path=integration_path,
                    evidence_class="integration-invalid",
                    parser_id="yaml-json-object-v1",
                    parser_version=1,
                    schema_id=schema_id,
                    schema_version=versions[0],
                )
                continue
            existing = views[path].get(side)
            if existing is not None and existing.role != observation.role:
                findings.add(
                    "interpretation-conflict",
                    task_id=observation.task_id,
                    task_ref=observation.admission_task_ref,
                    current_path=path,
                    conflicting_fields=["source_role" if side == "source" else "target_role"],
                )
            views[path][side] = observation

    def _task_observation(
        self,
        path: str,
        role: str,
        document: Mapping[str, object],
        schema: _SchemaEntry,
        byte_hash: str,
        mode: str,
    ) -> _TaskObservation:
        admission = _mapping(document.get("admission"), "integration admission")
        lifecycle = _mapping(document.get("lifecycle"), "integration lifecycle")
        workflow = _mapping(document.get("workflow_contract"), "workflow contract")
        task_id = _canonical_uuid(admission.get("task_id"))
        admission_ref = normalize_path(_nonempty(admission.get("task_ref"), "task ref"))
        status = _nonempty(lifecycle.get("status"), "lifecycle status")
        if status not in _TASK_STATUS:
            raise _BundleError("lifecycle status is not closed")
        revision = lifecycle.get("state_revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise _BundleError("state revision is invalid")
        task_mode = _nonempty(document.get("mode"), "task mode")
        if task_mode not in _TASK_MODES:
            raise _BundleError("task mode is not closed")
        raw_surfaces = _array(workflow.get("task_contract_surfaces"), "task surfaces")
        surfaces: list[dict[str, str]] = []
        for raw_surface in raw_surfaces:
            surface = _mapping(raw_surface, "task surface")
            if set(surface) != {"surface_id", "surface_digest"}:
                raise _BundleError("task surface fields are not closed")
            surface_id = _nonempty(surface.get("surface_id"), "surface id")
            surface_digest = _nonempty(surface.get("surface_digest"), "surface digest")
            if len(surface_digest) != 64 or any(character not in "0123456789abcdef" for character in surface_digest):
                raise _BundleError("task surface digest is invalid")
            surfaces.append({"surface_id": surface_id, "surface_digest": surface_digest})
        ordered = sorted(surfaces, key=lambda item: item["surface_id"])
        if surfaces != ordered or len({item["surface_id"] for item in surfaces}) != len(surfaces):
            raise _BundleError("task surfaces are not unique and sorted")
        return _TaskObservation(
            path=path,
            role=role,
            task_id=task_id,
            admission_task_ref=admission_ref,
            integration_byte_hash=byte_hash,
            integration_mode=mode,
            integration_schema_id=schema.schema_id,
            integration_schema_version=schema.schema_version,
            lifecycle_status=status,
            revision=revision,
            mode=task_mode,
            task_contract_digest=digest("agent-workflow.task-contract.v1", workflow),
            task_contract_surfaces=tuple(ordered),
        )

    def _scan_layout_metadata(
        self,
        side: str,
        layout: VerifiedTrellisTaskLayout,
        bundle: _DiscoveryBundle | None,
        views: dict[str, dict[str, _MetadataObservation]],
        findings: _Findings,
    ) -> None:
        for contract in layout.metadata_contracts:
            if contract.kind == "exact":
                self._scan_exact_metadata(side, contract, bundle, views, findings)
            else:
                self._scan_bounded_metadata(side, contract, bundle, views, findings)

    def _scan_exact_metadata(
        self,
        side: str,
        contract: MetadataContract,
        bundle: _DiscoveryBundle | None,
        views: dict[str, dict[str, _MetadataObservation]],
        findings: _Findings,
    ) -> None:
        kind, _ = _path_kind(self.project_root, contract.location)
        normalized = contract.normalized
        if kind == "missing":
            if not bool(normalized["absence_is_empty"]):
                self._metadata_ambiguous(contract, contract.location, "metadata-missing", findings)
            return
        if kind != "regular":
            self._metadata_ambiguous(
                contract, contract.location, f"metadata-{kind}", findings
            )
            return
        observation = self._parse_metadata(contract, contract.location, bundle, findings)
        if observation is not None:
            views[contract.location][side] = observation

    def _scan_bounded_metadata(
        self,
        side: str,
        contract: MetadataContract,
        bundle: _DiscoveryBundle | None,
        views: dict[str, dict[str, _MetadataObservation]],
        findings: _Findings,
    ) -> None:
        normalized = contract.normalized
        root = contract.location
        kind, _ = _path_kind(self.project_root, root)
        if kind == "missing":
            if not bool(normalized["absence_is_empty"]):
                self._metadata_ambiguous(contract, root, "metadata-root-missing", findings)
            return
        if kind != "directory":
            self._metadata_ambiguous(contract, root, f"metadata-root-{kind}", findings)
            return
        try:
            entries = sorted(os.scandir(self.project_root / root), key=lambda item: os.fsencode(item.name))
        except OSError:
            self._metadata_ambiguous(contract, root, "metadata-root-io-error", findings)
            return
        maximum = int(normalized["max_matches"])
        if len(entries) > maximum:
            findings.add(
                "scan-limit",
                contract_id=contract.contract_id,
                limit_kind="max_matches",
                configured_limit=maximum,
            )
        grammar = str(normalized["segment_grammar_id"])
        for entry in entries:
            path = _relative_join(root, entry.name)
            try:
                if grammar == "uuid-json-v1":
                    validate_task_journal_name(entry.name)
                else:
                    validate_task_segment(entry.name)
            except CoreFailure:
                findings.add(
                    "unknown-entry",
                    normalized_path=_safe_relative(path),
                    root_contract_id=contract.contract_id,
                )
                continue
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                findings.add(
                    "unknown-entry",
                    normalized_path=_safe_relative(path),
                    root_contract_id=contract.contract_id,
                )
                continue
            observation = self._parse_metadata(contract, path, bundle, findings)
            if observation is not None:
                views[path][side] = observation

    def _metadata_ambiguous(
        self,
        contract: MetadataContract,
        path: str,
        evidence_class: str,
        findings: _Findings,
    ) -> None:
        normalized = contract.normalized
        versions = _array(normalized["schema_versions"], "metadata schema versions")
        _layout_ambiguous(
            findings,
            path=path,
            evidence_class=evidence_class,
            parser_id=str(normalized["parser_id"]),
            parser_version=_positive_int(normalized["parser_version"], "parser version"),
            schema_id=str(normalized["schema_id"]),
            schema_version=_positive_int(versions[0], "metadata schema version"),
        )

    def _parse_metadata(
        self,
        contract: MetadataContract,
        path: str,
        bundle: _DiscoveryBundle | None,
        findings: _Findings,
    ) -> _MetadataObservation | None:
        normalized = contract.normalized
        read = _read_regular(
            self.project_root,
            path,
            _positive_int(normalized["max_bytes"], "metadata max bytes"),
        )
        if isinstance(read, str):
            self._metadata_ambiguous(contract, path, f"metadata-{read}", findings)
            return None
        payload, byte_hash, mode = read
        if bundle is None:
            self._metadata_ambiguous(
                contract, path, "discovery-schema-bundle-unsupported", findings
            )
            return None
        parser = (
            str(normalized["parser_id"]),
            _positive_int(normalized["parser_version"], "metadata parser version"),
        )
        versions = tuple(
            _positive_int(value, "metadata schema version")
            for value in _array(normalized["schema_versions"], "versions")
        )
        try:
            document, _ = bundle.parse_and_validate(
                payload,
                schema_id=str(normalized["schema_id"]),
                allowed_versions=versions,
                parser=parser,
            )
            refs: list[str] = []
            for pointer in _array(normalized["task_ref_fields"], "task ref fields"):
                value = _json_pointer(document, str(pointer))
                if value is None or value == "":
                    continue
                refs.append(normalize_path(_nonempty(value, "metadata task ref")))
            refs = sorted(set(refs))
            classifier_key = (
                str(normalized["classifier_id"]),
                _positive_int(
                    normalized["classifier_version"], "metadata classifier version"
                ),
            )
            classifier = bundle.classifiers.get(classifier_key)
            if classifier is None or classifier.get("canonical_empty_state_id") != normalized.get(
                "canonical_empty_state_id"
            ):
                raise _BundleError("metadata classifier is unsupported")
            classification = (
                "empty"
                if classifier.get("strategy") == "task-refs-empty" and not refs
                else "nonempty"
            )
        except (_BundleError, CoreFailure):
            self._metadata_ambiguous(contract, path, "metadata-invalid", findings)
            return None
        return _MetadataObservation(
            path=path,
            byte_hash=byte_hash,
            mode=mode,
            parser_id=parser[0],
            parser_version=parser[1],
            classifier_id=classifier_key[0],
            classifier_version=classifier_key[1],
            parsed_task_refs=tuple(refs),
            semantic_role=str(normalized["semantic_role"]),
            classification=classification,
        )

    def _scan_layout_journals(
        self,
        side: str,
        layout: VerifiedTrellisTaskLayout,
        bundle: _DiscoveryBundle | None,
        views: dict[str, dict[str, _JournalObservation]],
        findings: _Findings,
    ) -> None:
        contract = _mapping(
            layout.normalized.get("task_transaction_discovery"),
            "task transaction discovery",
        )
        root = layout.task_transaction_root
        versions = tuple(
            _positive_int(value, "task journal schema version")
            for value in _array(contract["schema_versions"], "versions")
        )
        schema_id = str(contract["schema_id"])
        kind, _ = _path_kind(self.project_root, root)
        if kind == "missing":
            return
        if kind != "directory":
            _layout_ambiguous(
                findings,
                path=root,
                evidence_class=f"task-journal-root-{kind}",
                parser_id="json-object-v1",
                parser_version=1,
                schema_id=schema_id,
                schema_version=versions[0],
            )
            return
        try:
            entries = sorted(os.scandir(self.project_root / root), key=lambda item: os.fsencode(item.name))
        except OSError:
            _layout_ambiguous(
                findings,
                path=root,
                evidence_class="task-journal-root-io-error",
                parser_id="json-object-v1",
                parser_version=1,
                schema_id=schema_id,
                schema_version=versions[0],
            )
            return
        maximum = _positive_int(contract["max_journals"], "max task journals")
        if len(entries) > maximum:
            findings.add(
                "scan-limit",
                contract_id=f"{layout.adapter_id}:task-transactions",
                limit_kind="max_journals",
                configured_limit=maximum,
            )
        for entry in entries:
            path = _relative_join(root, entry.name)
            try:
                validate_task_journal_name(entry.name)
            except CoreFailure:
                findings.add(
                    "unknown-entry",
                    normalized_path=_safe_relative(path),
                    root_contract_id=f"{layout.adapter_id}:task-transactions",
                )
                continue
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                findings.add(
                    "unknown-entry",
                    normalized_path=_safe_relative(path),
                    root_contract_id=f"{layout.adapter_id}:task-transactions",
                )
                continue
            read = _read_regular(
                self.project_root,
                path,
                _positive_int(contract["max_journal_bytes"], "max task journal bytes"),
            )
            if isinstance(read, str):
                _layout_ambiguous(
                    findings,
                    path=path,
                    evidence_class=f"task-journal-{read}",
                    parser_id="json-object-v1",
                    parser_version=1,
                    schema_id=schema_id,
                    schema_version=versions[0],
                )
                continue
            payload, byte_hash, mode = read
            if bundle is None:
                _layout_ambiguous(
                    findings,
                    path=path,
                    evidence_class="discovery-schema-bundle-unsupported",
                    parser_id="json-object-v1",
                    parser_version=1,
                    schema_id=schema_id,
                    schema_version=versions[0],
                )
                continue
            try:
                document, schema = bundle.parse_and_validate(
                    payload,
                    schema_id=schema_id,
                    allowed_versions=versions,
                    parser=("json-object-v1", 1),
                )
                phase_key = (
                    str(contract["phase_classifier_id"]),
                    _positive_int(
                        contract["phase_classifier_version"], "phase classifier version"
                    ),
                )
                classifier = bundle.phase_classifiers.get(phase_key)
                if classifier is None:
                    raise _BundleError("task phase classifier is unsupported")
                operation = _nonempty(document.get("operation"), "task operation")
                phase = _nonempty(document.get("phase"), "task phase")
                operations = _mapping(classifier.get("operations"), "phase operations")
                legal_phases = tuple(
                    str(value) for value in _array(operations.get(operation), "legal phases")
                )
                if phase not in legal_phases:
                    raise _BundleError("task phase is not in the closed operation table")
                classifier_terminals = tuple(
                    str(value)
                    for value in _array(classifier.get("terminal_phases"), "terminal phases")
                )
                layout_terminals = tuple(
                    str(value) for value in _array(contract["terminal_phases"], "layout terminals")
                )
                if set(classifier_terminals) != set(layout_terminals):
                    raise _BundleError("layout and phase classifier terminal phases disagree")
                task_id = _canonical_uuid(_json_pointer(document, str(contract["task_id_field"])))
                refs = [
                    _json_pointer(document, str(pointer))
                    for pointer in _array(contract["task_ref_fields"], "journal task refs")
                ]
                task_ref = next(
                    normalize_path(value) for value in refs if isinstance(value, str) and value
                )
            except (StopIteration, _BundleError, CoreFailure):
                _layout_ambiguous(
                    findings,
                    path=path,
                    evidence_class="task-journal-invalid",
                    parser_id="json-object-v1",
                    parser_version=1,
                    schema_id=schema_id,
                    schema_version=versions[0],
                )
                continue
            views[path][side] = _JournalObservation(
                path=path,
                byte_hash=byte_hash,
                mode=mode,
                schema_id=schema.schema_id,
                schema_version=schema.schema_version,
                operation=operation,
                phase=phase,
                task_id=task_id,
                task_ref=task_ref,
                terminal=phase in classifier_terminals,
            )

    def _merge_tasks(
        self,
        views: Mapping[str, Mapping[str, _TaskObservation]],
        findings: _Findings,
    ) -> list[dict[str, object]]:
        candidates: list[tuple[_TaskObservation, str, str]] = []
        for path in sorted(views):
            source = views[path].get("source")
            target = views[path].get("target")
            chosen = source or target
            if chosen is None:
                continue
            if source is not None and target is not None:
                differing = sorted(
                    key
                    for key in source.semantic_projection()
                    if source.semantic_projection()[key] != target.semantic_projection()[key]
                )
                if differing:
                    findings.add(
                        "interpretation-conflict",
                        task_id=chosen.task_id,
                        task_ref=chosen.admission_task_ref,
                        current_path=path,
                        conflicting_fields=differing,
                    )
            source_role = source.role if source is not None else "absent"
            target_role = target.role if target is not None else "absent"
            if source_role != target_role:
                findings.add(
                    "layout-state-stranded",
                    normalized_path=path,
                    semantic_role=f"task-{source_role if source_role != 'absent' else target_role}",
                    source_visibility="recognized" if source is not None else "unrecognized",
                    target_visibility="recognized" if target is not None else "unrecognized",
                )
            candidates.append((chosen, source_role, target_role))

        paths_by_id: dict[str, list[str]] = defaultdict(list)
        for candidate, _, _ in candidates:
            paths_by_id[candidate.task_id].append(candidate.path)
        duplicate_ids = {task_id for task_id, paths in paths_by_id.items() if len(paths) > 1}
        for candidate, _, _ in candidates:
            if candidate.task_id in duplicate_ids:
                findings.add(
                    "interpretation-conflict",
                    task_id=candidate.task_id,
                    task_ref=candidate.admission_task_ref,
                    current_path=candidate.path,
                    conflicting_fields=["task_id"],
                )

        records: list[dict[str, object]] = []
        emitted_ids: set[str] = set()
        for candidate, source_role, target_role in candidates:
            if candidate.task_id in emitted_ids:
                continue
            emitted_ids.add(candidate.task_id)
            record = {
                "task_id": candidate.task_id,
                "admission_task_ref": candidate.admission_task_ref,
                "current_path": candidate.path,
                "source_role": source_role,
                "target_role": target_role,
                "integration_byte_hash": candidate.integration_byte_hash,
                "integration_mode": candidate.integration_mode,
                "integration_schema_id": candidate.integration_schema_id,
                "integration_schema_version": candidate.integration_schema_version,
                "lifecycle_status": candidate.lifecycle_status,
                "revision": candidate.revision,
                "mode": candidate.mode,
                "task_contract_digest": candidate.task_contract_digest,
                "task_contract_surfaces": list(candidate.task_contract_surfaces),
            }
            records.append(record)
            if candidate.lifecycle_status != "archived":
                findings.add(
                    "non-archived-task",
                    task_id=candidate.task_id,
                    current_path=candidate.path,
                    lifecycle_status=candidate.lifecycle_status,
                    mode=candidate.mode,
                    pinned_surfaces=list(candidate.task_contract_surfaces),
                )
            elif source_role == "active" or target_role == "active":
                findings.add(
                    "interpretation-conflict",
                    task_id=candidate.task_id,
                    task_ref=candidate.admission_task_ref,
                    current_path=candidate.path,
                    conflicting_fields=["current_path", "lifecycle_status"],
                )
        return sorted(records, key=lambda record: str(record["current_path"]))

    def _merge_metadata(
        self,
        views: Mapping[str, Mapping[str, _MetadataObservation]],
        findings: _Findings,
    ) -> list[dict[str, object]]:
        records: list[dict[str, object]] = []
        for path in sorted(views):
            source = views[path].get("source")
            target = views[path].get("target")
            chosen = source or target
            if chosen is None:
                continue
            if source is None or target is None:
                if chosen.classification != "empty":
                    findings.add(
                        "layout-state-stranded",
                        normalized_path=path,
                        semantic_role=chosen.semantic_role,
                        source_visibility="recognized" if source is not None else "unrecognized",
                        target_visibility="recognized" if target is not None else "unrecognized",
                    )
            elif source.document() != target.document():
                findings.add(
                    "layout-state-stranded",
                    normalized_path=path,
                    semantic_role=source.semantic_role,
                    source_visibility="recognized",
                    target_visibility="unrecognized",
                )
            records.append(chosen.document())
        return records

    def _merge_journals(
        self,
        views: Mapping[str, Mapping[str, _JournalObservation]],
        tasks: Sequence[Mapping[str, object]],
        findings: _Findings,
    ) -> list[dict[str, object]]:
        task_by_id = {str(task["task_id"]): task for task in tasks}
        records: list[dict[str, object]] = []
        for path in sorted(views):
            source = views[path].get("source")
            target = views[path].get("target")
            chosen = source or target
            if chosen is None:
                continue
            if source is None or target is None:
                findings.add(
                    "layout-state-stranded",
                    normalized_path=path,
                    semantic_role="task-transaction",
                    source_visibility="recognized" if source is not None else "unrecognized",
                    target_visibility="recognized" if target is not None else "unrecognized",
                )
            elif source.document() != target.document():
                _layout_ambiguous(
                    findings,
                    path=path,
                    evidence_class="task-journal-interpretation-conflict",
                    parser_id="json-object-v1",
                    parser_version=1,
                    schema_id=source.schema_id,
                    schema_version=source.schema_version,
                )
            records.append(chosen.document())
            if not chosen.terminal:
                findings.add(
                    "unfinished-task-transaction",
                    journal_path=path,
                    task_id=chosen.task_id,
                    task_ref=chosen.task_ref,
                    operation=chosen.operation,
                    phase=chosen.phase,
                )
            task = task_by_id.get(chosen.task_id)
            if task is not None and chosen.task_ref not in {
                task["admission_task_ref"],
                task["current_path"],
            }:
                findings.add(
                    "interpretation-conflict",
                    task_id=chosen.task_id,
                    task_ref=chosen.task_ref,
                    current_path=str(task["current_path"]),
                    conflicting_fields=["task_ref"],
                )
        return records


def scan_task_quiescence(
    source_layout: VerifiedTrellisTaskLayout,
    target_layout: VerifiedTrellisTaskLayout,
    source_schemas: VerifiedDiscoverySchemas,
    target_schemas: VerifiedDiscoverySchemas,
) -> TaskSnapshotAndFindings:
    """Scan the current project working directory through the frozen port."""

    return NormativeTaskScanner(Path.cwd())(
        source_layout, target_layout, source_schemas, target_schemas
    )


__all__ = ["NormativeTaskScanner", "scan_task_quiescence"]
