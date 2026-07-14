"""Pure artifact ownership and Trellis task-layout validation."""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .canonical import canonical_json_bytes, normalize_mode, normalize_path, normalize_string_set
from .errors import CoreFailure


_DEFINITION_FIELDS = {
    "schema_id",
    "schema_version",
    "id",
    "source",
    "targets",
    "forbidden_paths",
    "validators",
}
_TARGET_FIELDS = {"path", "ownership", "merge_strategy", "mode_policy", "mode", "markers"}
_VALIDATOR_FIELDS = {"id", "version"}
_LAYOUT_FIELDS = {
    "schema_id",
    "schema_version",
    "adapter_id",
    "adapter_version",
    "runtime_namespace",
    "active_root",
    "archive_root",
    "task_discovery",
    "metadata_contracts",
    "task_transaction_discovery",
}
_TASK_DISCOVERY_FIELDS = {
    "hierarchy",
    "segment_grammar_id",
    "integration_relative_path",
    "integration_schema_id",
    "integration_schema_versions",
    "unknown_root_entry_policy",
    "allowed_non_task_entries",
    "max_scan_depth",
    "max_tasks",
    "max_root_entries",
    "max_integration_bytes",
}
_METADATA_COMMON_FIELDS = {
    "kind",
    "contract_id",
    "schema_id",
    "schema_versions",
    "parser_id",
    "parser_version",
    "classifier_id",
    "classifier_version",
    "semantic_role",
    "task_ref_fields",
    "max_bytes",
    "absence_is_empty",
    "canonical_empty_state_id",
}
_METADATA_EXACT_FIELDS = _METADATA_COMMON_FIELDS | {"path"}
_METADATA_BOUNDED_FIELDS = _METADATA_COMMON_FIELDS | {
    "root",
    "segment_grammar_id",
    "max_depth",
    "max_matches",
}
_TASK_TRANSACTION_FIELDS = {
    "root",
    "filename_grammar_id",
    "schema_id",
    "schema_versions",
    "phase_classifier_id",
    "phase_classifier_version",
    "task_id_field",
    "task_ref_fields",
    "terminal_phases",
    "max_journals",
    "max_journal_bytes",
}
_STABLE_TOKEN = re.compile(r"^[a-z][a-z0-9._-]*$")
_UUID_JSON = re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.json$")

_CONTROL_PATHS = (
    ".agent-workflow/manifest.json",
    ".agent-workflow/workflow.lock",
    ".agent-workflow/reconcile.lock",
    ".agent-workflow/runtime-state.lock",
    ".agent-workflow/maintenance.json",
    ".agent-workflow/runtime",
)


@dataclass(frozen=True)
class ArtifactTarget:
    path: str
    ownership: str
    merge_strategy: str
    mode_policy: str
    mode: str | None
    markers: tuple[str, str] | None


@dataclass(frozen=True)
class ArtifactDefinition:
    definition_id: str
    source: str
    targets: tuple[ArtifactTarget, ...]
    forbidden_paths: tuple[str, ...]
    validators: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class MetadataContract:
    kind: str
    contract_id: str
    location: str
    normalized: Mapping[str, Any]


@dataclass(frozen=True)
class VerifiedTrellisTaskLayout:
    adapter_id: str
    adapter_version: str
    runtime_namespace: str
    active_root: str
    archive_root: str
    metadata_contracts: tuple[MetadataContract, ...]
    task_transaction_root: str
    normalized: Mapping[str, Any]
    layout_digest: str


def _artifact_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_ARTIFACT_POLICY_INVALID", message, details=details)


def _protected_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_PROTECTED_PATH_VIOLATION", message, exit_code=20, details=details)


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _artifact_failure(f"{label} must be an object")
    return value


def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _artifact_failure(f"{label} must be a positive integer")
    return value


def _require_stable_token(value: object, label: str) -> str:
    if not isinstance(value, str) or not _STABLE_TOKEN.fullmatch(value):
        raise _artifact_failure(f"{label} must be a stable id")
    return value


def _path_key(path: str) -> str:
    return path.casefold()


def _same_or_descendant(path: str, root: str) -> bool:
    path_key = _path_key(path)
    root_key = _path_key(root.rstrip("/"))
    return path_key == root_key or path_key.startswith(root_key + "/")


def _paths_overlap(first: str, second: str) -> bool:
    return _same_or_descendant(first, second) or _same_or_descendant(second, first)


def derive_protected_paths(active_root: str, archive_root: str) -> tuple[str, ...]:
    """Return the minimum protected paths plus both locked task partitions."""

    active = normalize_path(active_root)
    archive = normalize_path(archive_root)
    return (
        ".git/**",
        f"{active}/**",
        f"{archive}/**",
        ".trellis/workspace/**",
        "specs/**",
        ".agent-workflow/local/**",
        ".agent-workflow/task-transactions/**",
        ".agent-workflow/transactions/**",
    )


def _protected_roots(active_root: str, archive_root: str) -> tuple[str, ...]:
    return tuple(pattern.removesuffix("/**") for pattern in derive_protected_paths(active_root, archive_root))


def _assert_artifact_target_allowed(path: str, ownership: str, forbidden: Sequence[str]) -> None:
    protected = _protected_roots(".trellis/tasks", ".trellis/tasks/archive")
    for root in (*protected, *_CONTROL_PATHS, *forbidden):
        if _same_or_descendant(path, root):
            raise _protected_failure("artifact target overlaps a protected authority", path=path, root=root)
    if _same_or_descendant(path, ".trellis/spec") and ownership != "create-once-then-user-owned":
        raise _protected_failure(
            ".trellis/spec may only be seeded as create-once-then-user-owned", path=path
        )


def _validate_target(raw: Mapping[str, object], forbidden: Sequence[str]) -> ArtifactTarget:
    unknown = set(raw) - _TARGET_FIELDS
    if unknown:
        raise _artifact_failure("unknown artifact target fields", fields=sorted(unknown))
    path_value = raw.get("path")
    if not isinstance(path_value, str):
        raise _artifact_failure("artifact target path must be a string")
    path = normalize_path(path_value)
    ownership = raw.get("ownership")
    merge_strategy = raw.get("merge_strategy")
    mode_policy = raw.get("mode_policy")
    if not isinstance(ownership, str):
        raise _artifact_failure("ownership must be a string")
    if not isinstance(merge_strategy, str):
        raise _artifact_failure("merge strategy must be a string")
    if not isinstance(mode_policy, str):
        raise _artifact_failure("ownership, merge strategy, and mode policy must be strings")

    legal = {
        "managed": ("whole-file", "exact"),
        "overlay-managed": ("marked-block", "preserve"),
        "create-once-then-user-owned": ("whole-file", "exact"),
        "adopted": ("observe-baseline", "preserve"),
        "user-owned": ("none", "preserve"),
    }
    expected = legal.get(ownership)
    if expected is None or (merge_strategy, mode_policy) != expected:
        raise _artifact_failure(
            "illegal ownership/merge/mode combination",
            path=path,
            ownership=ownership,
            merge_strategy=merge_strategy,
            mode_policy=mode_policy,
        )

    raw_mode = raw.get("mode")
    mode: str | None = None
    if mode_policy == "exact":
        if raw_mode is None:
            raise _artifact_failure("exact mode policy requires mode", path=path)
        mode = normalize_mode(raw_mode)  # type: ignore[arg-type]
    elif raw_mode is not None:
        raise _artifact_failure("preserve mode policy forbids a candidate mode", path=path)

    raw_markers = raw.get("markers")
    markers: tuple[str, str] | None = None
    if ownership == "overlay-managed":
        marker_mapping = _require_mapping(raw_markers, "markers")
        if set(marker_mapping) != {"begin", "end"}:
            raise _artifact_failure("marker pair must contain only begin and end", path=path)
        begin = marker_mapping["begin"]
        end = marker_mapping["end"]
        if not isinstance(begin, str) or not isinstance(end, str) or not begin or not end or begin == end:
            raise _artifact_failure("marker pair is invalid", path=path)
        if begin in end or end in begin:
            raise _artifact_failure("marker pair may not nest or overlap", path=path)
        markers = (begin, end)
    elif raw_markers is not None:
        raise _artifact_failure("markers are legal only for overlay-managed targets", path=path)

    _assert_artifact_target_allowed(path, ownership, forbidden)
    return ArtifactTarget(
        path=path,
        ownership=ownership,
        merge_strategy=merge_strategy,
        mode_policy=mode_policy,
        mode=mode,
        markers=markers,
    )


def validate_artifact_definitions(
    definitions: Sequence[Mapping[str, object]],
) -> tuple[ArtifactDefinition, ...]:
    """Validate closed definitions and finite ownership/path collisions."""

    verified: list[ArtifactDefinition] = []
    definition_ids: set[str] = set()
    target_paths: dict[str, str] = {}
    marker_pairs: dict[tuple[str, str], str] = {}

    for raw in definitions:
        unknown = set(raw) - _DEFINITION_FIELDS
        if unknown:
            raise _artifact_failure("unknown artifact definition fields", fields=sorted(unknown))
        if raw.get("schema_id") != "agent-workflow.artifact-definition" or raw.get(
            "schema_version"
        ) != 1:
            raise _artifact_failure("artifact definition schema identity/version is invalid")
        definition_id = _require_stable_token(raw.get("id"), "definition id")
        if definition_id in definition_ids:
            raise _artifact_failure("duplicate artifact definition id", definition_id=definition_id)
        definition_ids.add(definition_id)
        source_value = raw.get("source")
        if not isinstance(source_value, str):
            raise _artifact_failure("artifact source must be a path")
        source = normalize_path(source_value)
        forbidden_raw = raw.get("forbidden_paths", [])
        if not isinstance(forbidden_raw, list) or not all(
            isinstance(path, str) for path in forbidden_raw
        ):
            raise _artifact_failure("forbidden_paths must be a string array")
        forbidden = tuple(normalize_path(path) for path in forbidden_raw)
        raw_targets = raw.get("targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            raise _artifact_failure("artifact definition requires at least one target")
        targets = tuple(
            _validate_target(_require_mapping(target, "artifact target"), forbidden)
            for target in raw_targets
        )
        for target in targets:
            key = _path_key(target.path)
            if key in target_paths:
                raise _artifact_failure(
                    "multiple definitions manage the same normalized target",
                    path=target.path,
                    first_definition=target_paths[key],
                    second_definition=definition_id,
                )
            target_paths[key] = definition_id
            if target.markers is not None:
                if target.markers in marker_pairs:
                    raise _artifact_failure(
                        "marker pair must be globally unique",
                        first_path=marker_pairs[target.markers],
                        second_path=target.path,
                    )
                marker_pairs[target.markers] = target.path

        raw_validators = raw.get("validators", [])
        if not isinstance(raw_validators, list):
            raise _artifact_failure("validators must be an array")
        validators: list[tuple[str, int]] = []
        for raw_validator in raw_validators:
            validator = _require_mapping(raw_validator, "validator")
            if set(validator) != _VALIDATOR_FIELDS:
                raise _artifact_failure("validator must contain only id and version")
            validator_id = _require_stable_token(validator.get("id"), "validator id")
            version = _require_positive_int(validator.get("version"), "validator version")
            validators.append((validator_id, version))
        if len(validators) != len(set(validators)):
            raise _artifact_failure("duplicate artifact validator")
        verified.append(
            ArtifactDefinition(
                definition_id=definition_id,
                source=source,
                targets=targets,
                forbidden_paths=forbidden,
                validators=tuple(sorted(validators)),
            )
        )
    return tuple(verified)


def validate_task_segment(segment: str) -> str:
    """Validate the safe-nfc-segment-v1 grammar."""

    from .canonical import normalize_nfc

    normalized = normalize_nfc(segment)
    encoded = normalized.encode("utf-8")
    if not 1 <= len(encoded) <= 128:
        raise _artifact_failure("task segment must contain 1 through 128 UTF-8 bytes")
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized or "\0" in normalized:
        raise _artifact_failure("task segment contains a path alias or separator")
    if normalized != normalized.strip() or normalized.endswith("."):
        raise _artifact_failure("task segment has forbidden edge whitespace or trailing dot")
    if any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in normalized):
        raise _artifact_failure("task segment contains a control character")
    return normalized


def validate_task_journal_name(filename: str) -> str:
    """Validate uuid-json-v1 and return the canonical UUID."""

    match = _UUID_JSON.fullmatch(filename)
    if match is None:
        raise _artifact_failure("task journal filename does not match uuid-json-v1")
    candidate = match.group(1)
    try:
        parsed = uuid.UUID(candidate)
    except ValueError as error:
        raise _artifact_failure("task journal UUID is invalid") from error
    if str(parsed) != candidate:
        raise _artifact_failure("task journal UUID is not canonical lowercase form")
    return candidate


def _integer_versions(value: object, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, int) and not isinstance(item, bool) and item >= 1 for item in value
    ):
        raise _artifact_failure(f"{label} must be a nonempty positive-integer array")
    normalized = tuple(sorted(set(value)))
    if len(normalized) != len(value):
        raise _artifact_failure(f"{label} contains duplicate versions")
    return normalized


def _json_pointers(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.startswith("/") and "//" not in item for item in value
    ):
        raise _artifact_failure(f"{label} must contain normalized JSON pointers")
    return normalize_string_set(value)


def _metadata_location_allowed(
    location: str,
    *,
    runtime_namespace: str,
    active_root: str,
    archive_root: str,
    artifact_targets: Sequence[str],
    source_roots: Sequence[str],
) -> None:
    forbidden_roots = (
        ".git",
        ".agent-workflow",
        "specs",
        *artifact_targets,
        *source_roots,
        active_root,
        archive_root,
    )
    if not _same_or_descendant(location, runtime_namespace):
        raise _protected_failure("Trellis metadata must remain in its runtime namespace", path=location)
    for root in forbidden_roots:
        if _paths_overlap(location, root):
            raise _protected_failure("Trellis metadata overlaps another ownership boundary", path=location, root=root)


def _normalize_metadata_contract(
    raw: Mapping[str, object],
    *,
    runtime_namespace: str,
    active_root: str,
    archive_root: str,
    artifact_targets: Sequence[str],
    source_roots: Sequence[str],
) -> MetadataContract:
    kind = raw.get("kind")
    expected_fields = _METADATA_EXACT_FIELDS if kind == "exact" else _METADATA_BOUNDED_FIELDS
    if kind not in {"exact", "bounded"} or set(raw) != expected_fields:
        raise _artifact_failure("metadata contract branch is not closed", kind=kind)
    contract_id = _require_stable_token(raw.get("contract_id"), "metadata contract id")
    location_field = "path" if kind == "exact" else "root"
    location_value = raw.get(location_field)
    if not isinstance(location_value, str):
        raise _artifact_failure("metadata location must be a path", contract_id=contract_id)
    location = normalize_path(location_value)
    _metadata_location_allowed(
        location,
        runtime_namespace=runtime_namespace,
        active_root=active_root,
        archive_root=archive_root,
        artifact_targets=artifact_targets,
        source_roots=source_roots,
    )
    if kind == "bounded":
        grammar = raw.get("segment_grammar_id")
        if grammar not in {"safe-nfc-segment-v1", "uuid-json-v1"}:
            raise _artifact_failure("bounded metadata segment grammar is not allowlisted")
        if raw.get("max_depth") != 1:
            raise _artifact_failure("bounded metadata max_depth must be exactly one")
        _require_positive_int(raw.get("max_matches"), "metadata max_matches")

    normalized: dict[str, Any] = dict(raw)
    normalized[location_field] = location
    normalized["schema_id"] = _require_stable_token(raw.get("schema_id"), "metadata schema id")
    normalized["schema_versions"] = list(
        _integer_versions(raw.get("schema_versions"), "metadata schema_versions")
    )
    normalized["parser_id"] = _require_stable_token(raw.get("parser_id"), "metadata parser id")
    normalized["parser_version"] = _require_positive_int(
        raw.get("parser_version"), "metadata parser version"
    )
    normalized["classifier_id"] = _require_stable_token(
        raw.get("classifier_id"), "metadata classifier id"
    )
    normalized["classifier_version"] = _require_positive_int(
        raw.get("classifier_version"), "metadata classifier version"
    )
    normalized["semantic_role"] = _require_stable_token(
        raw.get("semantic_role"), "metadata semantic role"
    )
    normalized["task_ref_fields"] = list(
        _json_pointers(raw.get("task_ref_fields"), "metadata task_ref_fields")
    )
    normalized["max_bytes"] = _require_positive_int(raw.get("max_bytes"), "metadata max_bytes")
    if not isinstance(raw.get("absence_is_empty"), bool):
        raise _artifact_failure("metadata absence_is_empty must be boolean")
    normalized["canonical_empty_state_id"] = _require_stable_token(
        raw.get("canonical_empty_state_id"), "metadata canonical empty state id"
    )
    return MetadataContract(
        kind=kind,
        contract_id=contract_id,
        location=location,
        normalized=MappingProxyType(normalized),
    )


def validate_trellis_layout(
    document: Mapping[str, object],
    *,
    artifact_targets: Sequence[str] = (),
    source_roots: Sequence[str] = ("src",),
) -> VerifiedTrellisTaskLayout:
    """Validate one finite, provenance-locked Trellis discovery contract."""

    if set(document) != _LAYOUT_FIELDS:
        raise _artifact_failure("Trellis layout fields are not closed")
    if document.get("schema_id") != "agent-workflow.trellis-task-layout" or document.get(
        "schema_version"
    ) != 1:
        raise _artifact_failure("Trellis layout schema identity/version is invalid")
    adapter_id = _require_stable_token(document.get("adapter_id"), "adapter id")
    adapter_version = document.get("adapter_version")
    if not isinstance(adapter_version, str) or not adapter_version:
        raise _artifact_failure("adapter version must be nonempty")
    raw_runtime = document.get("runtime_namespace")
    raw_active = document.get("active_root")
    raw_archive = document.get("archive_root")
    if not isinstance(raw_runtime, str):
        raise _artifact_failure("runtime_namespace must be a path")
    if not isinstance(raw_active, str):
        raise _artifact_failure("active_root must be a path")
    if not isinstance(raw_archive, str):
        raise _artifact_failure("archive_root must be a path")
    runtime_namespace = normalize_path(raw_runtime)
    active_root = normalize_path(raw_active)
    archive_root = normalize_path(raw_archive)
    if active_root == runtime_namespace or not _same_or_descendant(active_root, runtime_namespace):
        raise _artifact_failure("active_root must be a strict runtime-namespace descendant")
    if archive_root == active_root or not _same_or_descendant(archive_root, active_root):
        raise _artifact_failure("archive_root must be a strict active-root partition")

    task_discovery = _require_mapping(document.get("task_discovery"), "task_discovery")
    if set(task_discovery) != _TASK_DISCOVERY_FIELDS:
        raise _artifact_failure("task_discovery fields are not closed")
    if task_discovery.get("hierarchy") != "one-segment":
        raise _artifact_failure("only one-segment task discovery is supported")
    if task_discovery.get("segment_grammar_id") != "safe-nfc-segment-v1":
        raise _artifact_failure("task segment grammar must be safe-nfc-segment-v1")
    integration_path = task_discovery.get("integration_relative_path")
    if not isinstance(integration_path, str) or "/" in integration_path:
        raise _artifact_failure("integration_relative_path must be one relative filename")
    validate_task_segment(integration_path)
    integration_schema_id = _require_stable_token(
        task_discovery.get("integration_schema_id"), "integration schema id"
    )
    integration_versions = _integer_versions(
        task_discovery.get("integration_schema_versions"), "integration schema versions"
    )
    if task_discovery.get("unknown_root_entry_policy") != "block":
        raise _artifact_failure("unknown task-root entries must block")
    allowed_entries = task_discovery.get("allowed_non_task_entries")
    if not isinstance(allowed_entries, list) or not all(isinstance(item, str) for item in allowed_entries):
        raise _artifact_failure("allowed_non_task_entries must be a string array")
    normalized_allowed = tuple(validate_task_segment(item) for item in allowed_entries)
    if len(normalized_allowed) != len(set(item.casefold() for item in normalized_allowed)):
        raise _artifact_failure("allowed task-root entries have case/Unicode aliases")
    if task_discovery.get("max_scan_depth") != 1:
        raise _artifact_failure("task max_scan_depth must be exactly one")
    max_tasks = _require_positive_int(task_discovery.get("max_tasks"), "max_tasks")
    max_root_entries = _require_positive_int(
        task_discovery.get("max_root_entries"), "max_root_entries"
    )
    max_integration_bytes = _require_positive_int(
        task_discovery.get("max_integration_bytes"), "max_integration_bytes"
    )

    normalized_artifact_targets = tuple(normalize_path(path) for path in artifact_targets)
    normalized_source_roots = tuple(normalize_path(path) for path in source_roots)
    raw_metadata = document.get("metadata_contracts")
    if not isinstance(raw_metadata, list):
        raise _artifact_failure("metadata_contracts must be an array")
    metadata = tuple(
        _normalize_metadata_contract(
            _require_mapping(item, "metadata contract"),
            runtime_namespace=runtime_namespace,
            active_root=active_root,
            archive_root=archive_root,
            artifact_targets=normalized_artifact_targets,
            source_roots=normalized_source_roots,
        )
        for item in raw_metadata
    )
    if len({item.contract_id for item in metadata}) != len(metadata):
        raise _artifact_failure("metadata contract ids must be unique")
    for index, first in enumerate(metadata):
        for second in metadata[index + 1 :]:
            if _paths_overlap(first.location, second.location):
                raise _protected_failure(
                    "metadata contract locations overlap",
                    first=first.contract_id,
                    second=second.contract_id,
                )

    transaction = _require_mapping(
        document.get("task_transaction_discovery"), "task_transaction_discovery"
    )
    if set(transaction) != _TASK_TRANSACTION_FIELDS:
        raise _artifact_failure("task_transaction_discovery fields are not closed")
    transaction_root_value = transaction.get("root")
    if not isinstance(transaction_root_value, str):
        raise _artifact_failure("task transaction root must be a path")
    transaction_root = normalize_path(transaction_root_value)
    if transaction_root != ".agent-workflow/task-transactions":
        raise _protected_failure("task transaction discovery root is not the sole exception")
    if transaction.get("filename_grammar_id") != "uuid-json-v1":
        raise _artifact_failure("task transaction filename grammar must be uuid-json-v1")
    transaction_schema_id = _require_stable_token(
        transaction.get("schema_id"), "task transaction schema id"
    )
    transaction_versions = _integer_versions(
        transaction.get("schema_versions"), "task transaction schema versions"
    )
    phase_classifier = _require_stable_token(
        transaction.get("phase_classifier_id"), "task phase classifier id"
    )
    phase_classifier_version = _require_positive_int(
        transaction.get("phase_classifier_version"), "task phase classifier version"
    )
    if transaction.get("task_id_field") != "/task_id":
        raise _artifact_failure("task transaction task_id_field must be /task_id")
    transaction_task_refs = _json_pointers(
        transaction.get("task_ref_fields"), "task transaction task_ref_fields"
    )
    terminal_phases = transaction.get("terminal_phases")
    if not isinstance(terminal_phases, list) or not terminal_phases or not all(
        isinstance(item, str) for item in terminal_phases
    ):
        raise _artifact_failure("terminal_phases must be a nonempty string array")
    normalized_terminal = normalize_string_set(terminal_phases)
    max_journals = _require_positive_int(transaction.get("max_journals"), "max_journals")
    max_journal_bytes = _require_positive_int(
        transaction.get("max_journal_bytes"), "max_journal_bytes"
    )

    normalized_task_discovery = {
        "hierarchy": "one-segment",
        "segment_grammar_id": "safe-nfc-segment-v1",
        "integration_relative_path": integration_path,
        "integration_schema_id": integration_schema_id,
        "integration_schema_versions": list(integration_versions),
        "unknown_root_entry_policy": "block",
        "allowed_non_task_entries": sorted(normalized_allowed, key=str.casefold),
        "max_scan_depth": 1,
        "max_tasks": max_tasks,
        "max_root_entries": max_root_entries,
        "max_integration_bytes": max_integration_bytes,
    }
    normalized_transaction = {
        "root": transaction_root,
        "filename_grammar_id": "uuid-json-v1",
        "schema_id": transaction_schema_id,
        "schema_versions": list(transaction_versions),
        "phase_classifier_id": phase_classifier,
        "phase_classifier_version": phase_classifier_version,
        "task_id_field": "/task_id",
        "task_ref_fields": list(transaction_task_refs),
        "terminal_phases": list(normalized_terminal),
        "max_journals": max_journals,
        "max_journal_bytes": max_journal_bytes,
    }
    normalized_document = {
        "schema_id": "agent-workflow.trellis-task-layout",
        "schema_version": 1,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "runtime_namespace": runtime_namespace,
        "active_root": active_root,
        "archive_root": archive_root,
        "task_discovery": normalized_task_discovery,
        "metadata_contracts": [
            dict(item.normalized) for item in sorted(metadata, key=lambda item: item.contract_id)
        ],
        "task_transaction_discovery": normalized_transaction,
    }
    layout_digest = hashlib.sha256(canonical_json_bytes(normalized_document)).hexdigest()
    return VerifiedTrellisTaskLayout(
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        runtime_namespace=runtime_namespace,
        active_root=active_root,
        archive_root=archive_root,
        metadata_contracts=tuple(sorted(metadata, key=lambda item: item.contract_id)),
        task_transaction_root=transaction_root,
        normalized=MappingProxyType(normalized_document),
        layout_digest=layout_digest,
    )
