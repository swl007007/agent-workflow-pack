"""Pure ownership observation and reconcile-decision planning."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from agent_stack.core.api import CANONICAL_NULL, normalize_path

from .errors import RendererFailure
from .models import FileState, StagedFile, StagedRenderTree


@dataclass(frozen=True)
class OwnershipPlan:
    decisions: tuple[Mapping[str, object], ...]
    observations: tuple[Mapping[str, object], ...]
    preconditions: tuple[Mapping[str, object], ...]
    candidate_file_states: tuple[FileState, ...]
    candidate_contents: Mapping[str, bytes]
    manifest_file_records: tuple[Mapping[str, object], ...]
    has_file_changes: bool
    has_manifest_changes: bool


def _failure(code: str, message: str, **details: object) -> RendererFailure:
    return RendererFailure(code, message, details=details)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("AWP_OWNERSHIP_CONFLICT", "ownership object is invalid", field=field)
    return value


def _absent(path: str) -> FileState:
    return FileState(path, False, "absent", CANONICAL_NULL, CANONICAL_NULL, True)


def _candidate_state(record: StagedFile) -> FileState:
    return FileState(
        path=record.path,
        exists=True,
        file_type="regular",
        byte_hash=record.candidate_byte_hash,
        mode=record.candidate_mode,
        non_symlink=True,
    )


def _observed(
    path: str, raw: object
) -> tuple[FileState, bytes | None, Mapping[str, object]]:
    item = _mapping(raw, f"observed_files.{path}")
    if set(item) != {"state", "content"}:
        raise _failure(
            "AWP_OWNERSHIP_CONFLICT",
            "ownership observation fields are not closed",
            path=path,
        )
    state = FileState.from_document(_mapping(item.get("state"), "observed state"))
    if state.path != path:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "observed path identity differs", path=path)
    raw_content = item.get("content")
    if raw_content is None:
        content = None
    elif isinstance(raw_content, str):
        content = raw_content.encode("utf-8")
    else:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "observed content is not UTF-8 text", path=path)
    if not state.exists and content is not None:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "absent observation has content", path=path)
    if content is not None and hashlib.sha256(content).hexdigest() != state.byte_hash:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "observed bytes differ from FileState", path=path)
    observation = MappingProxyType(
        {
            "schema_id": "agent-workflow.ownership-observation",
            "schema_version": 1,
            "path": path,
            "file_state": state.to_document(),
            "marker_state": "not-applicable",
            "managed_block_hash": CANONICAL_NULL,
        }
    )
    return state, content, observation


def _definitions(
    artifact_definitions: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    targets: dict[str, Mapping[str, object]] = {}
    for raw_definition in artifact_definitions:
        definition_id = raw_definition.get("id")
        raw_targets = raw_definition.get("targets")
        if not isinstance(definition_id, str) or not isinstance(raw_targets, Sequence):
            raise _failure("AWP_OWNERSHIP_CONFLICT", "artifact definition is invalid")
        for raw_target in raw_targets:
            target = _mapping(raw_target, "artifact target")
            path_value = target.get("path")
            if not isinstance(path_value, str):
                raise _failure("AWP_OWNERSHIP_CONFLICT", "artifact target path is invalid")
            path = normalize_path(path_value)
            if path in targets:
                raise _failure("AWP_OWNERSHIP_CONFLICT", "artifact target repeats", path=path)
            targets[path] = MappingProxyType({**dict(target), "definition_id": definition_id})
    return targets


def _manifest_records(
    records: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for raw_record in records:
        path_value = raw_record.get("path")
        if not isinstance(path_value, str):
            raise _failure("AWP_OWNERSHIP_CONFLICT", "Manifest file path is invalid")
        path = normalize_path(path_value)
        if path in indexed:
            raise _failure("AWP_OWNERSHIP_CONFLICT", "Manifest file path repeats", path=path)
        indexed[path] = MappingProxyType(dict(raw_record))
    return indexed


def _record_state(record: Mapping[str, object]) -> FileState:
    return FileState.from_document(_mapping(record.get("file_state"), "Manifest file state"))


def _markers(value: object, *, path: str) -> tuple[str, str]:
    marker_map = _mapping(value, "markers")
    if set(marker_map) != {"begin", "end"}:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "marker fields are not closed", path=path)
    begin = marker_map.get("begin")
    end = marker_map.get("end")
    if not isinstance(begin, str) or not isinstance(end, str) or not begin or not end:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "marker pair is invalid", path=path)
    return begin, end


def _overlay_parts(
    content: bytes | None, marker_value: object, *, path: str
) -> tuple[bytes, bytes, bytes, dict[str, str]]:
    if content is None:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "overlay target is absent", path=path)
    begin, end = _markers(marker_value, path=path)
    begin_token = begin.encode("utf-8") + b"\n"
    end_token = end.encode("utf-8") + b"\n"
    if content.count(begin_token) != 1 or content.count(end_token) != 1:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "overlay markers are missing or duplicated", path=path)
    begin_at = content.index(begin_token)
    block_at = begin_at + len(begin_token)
    end_at = content.index(end_token)
    if end_at < block_at:
        raise _failure("AWP_OWNERSHIP_CONFLICT", "overlay markers are nested or reversed", path=path)
    return (
        content[:begin_at],
        content[block_at:end_at],
        content[end_at + len(end_token) :],
        {"begin": begin, "end": end},
    )


def _manifest_record(
    staged: StagedFile,
    state: FileState,
    *,
    ownership: str | None = None,
    managed_block_hash: str = CANONICAL_NULL,
    created_once: bool = False,
    markers: Mapping[str, str] | None = None,
) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "path": staged.path,
            "definition_id": staged.definition_id,
            "ownership": ownership or staged.ownership,
            "file_state": state.to_document(),
            "managed_block_hash": managed_block_hash,
            "created_once": created_once,
            "markers": None if markers is None else dict(markers),
        }
    )


def _decision(
    staged: StagedFile,
    observed: FileState,
    baseline: FileState,
    candidate: FileState,
    action: str,
    reason_code: str,
) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.ownership-decision",
            "schema_version": 1,
            "path": staged.path,
            "definition_id": staged.definition_id,
            "ownership": staged.ownership,
            "observed_file_state": observed.to_document(),
            "baseline_file_state": baseline.to_document(),
            "candidate_file_state": candidate.to_document(),
            "action": action,
            "reason_code": reason_code,
        }
    )


def _state_matches(left: FileState, right: FileState) -> bool:
    return left.to_document() == right.to_document()


def plan_ownership(
    staged_tree: StagedRenderTree,
    artifact_definitions: Sequence[Mapping[str, object]],
    manifest_files: Sequence[Mapping[str, object]],
    observed_files: Mapping[str, object],
    *,
    operation: str,
) -> OwnershipPlan:
    """Produce deterministic ownership decisions without reading or writing targets."""

    targets = _definitions(artifact_definitions)
    previous = _manifest_records(manifest_files)
    staged_by_path = {record.path: record for record in staged_tree.files}
    all_paths = sorted(set(staged_by_path) | set(previous))
    if set(observed_files) != set(all_paths):
        raise _failure(
            "AWP_OWNERSHIP_CONFLICT",
            "observed file set differs from staged/Manifest authority",
        )

    decisions: list[Mapping[str, object]] = []
    observations: list[Mapping[str, object]] = []
    preconditions: list[Mapping[str, object]] = []
    candidate_states: list[FileState] = []
    candidate_contents: dict[str, bytes] = {}
    next_manifest: list[Mapping[str, object]] = []

    for path in all_paths:
        observed, content, observation = _observed(path, observed_files[path])
        observations.append(observation)
        old_record = previous.get(path)
        baseline = _record_state(old_record) if old_record is not None else _absent(path)
        record = staged_by_path.get(path)

        if record is None:
            if old_record is None:
                raise AssertionError("unreachable ownership path")
            ownership = old_record.get("ownership")
            retired = StagedFile(
                path=path,
                definition_id=str(old_record.get("definition_id")),
                surface_id="retired",
                ownership=str(ownership),
                merge_strategy="marked-block" if ownership == "overlay-managed" else "whole-file",
                source_digest="0" * 64,
                render_digest="0" * 64,
                candidate_byte_hash=CANONICAL_NULL,
                mode_policy="preserve" if ownership == "overlay-managed" else "exact",
                candidate_mode=CANONICAL_NULL,
            )
            if ownership == "overlay-managed":
                if not _state_matches(observed, baseline):
                    baseline_block = old_record.get("managed_block_hash")
                    if not isinstance(baseline_block, str):
                        raise _failure("AWP_OWNERSHIP_CONFLICT", "overlay baseline is invalid", path=path)
                prefix, block, suffix, _ = _overlay_parts(content, old_record.get("markers"), path=path)
                block_hash = hashlib.sha256(block).hexdigest()
                if block_hash != old_record.get("managed_block_hash"):
                    raise _failure("AWP_OWNERSHIP_DRIFT", "managed overlay block drifted", path=path)
                candidate_bytes = prefix + suffix
                candidate = FileState(
                    path,
                    True,
                    "regular",
                    hashlib.sha256(candidate_bytes).hexdigest(),
                    observed.mode,
                    True,
                )
                reason = "retire-managed-block"
                candidate_contents[path] = candidate_bytes
            elif ownership == "managed":
                if not _state_matches(observed, baseline):
                    raise _failure("AWP_OWNERSHIP_DRIFT", "managed retirement preimage drifted", path=path)
                candidate = _absent(path)
                reason = "retire-managed-file"
            else:
                candidate = observed
                reason = "retire-ownership-record"
            decision = _decision(retired, observed, baseline, candidate, "replace", reason)
            decisions.append(decision)
            preconditions.append(decision)
            if not _state_matches(candidate, observed):
                candidate_states.append(candidate)
            continue

        target = targets.get(path)
        if target is None or target.get("definition_id") != record.definition_id:
            raise _failure("AWP_OWNERSHIP_CONFLICT", "staged target lacks its definition", path=path)
        for field in ("ownership", "merge_strategy", "mode_policy"):
            if target.get(field) != getattr(record, field):
                raise _failure("AWP_OWNERSHIP_CONFLICT", "staged ownership contract differs", path=path)

        candidate = _candidate_state(record)
        action = "no-op"
        reason = "already-current"
        manifest_candidate: Mapping[str, object] | None = old_record

        if record.ownership == "managed":
            if old_record is None:
                if not observed.exists:
                    action, reason = "create", "managed-target-absent"
                    candidate_states.append(candidate)
                    candidate_contents[path] = record.candidate_bytes
                elif _state_matches(observed, candidate):
                    reason = "enroll-matching-candidate"
                else:
                    raise _failure("AWP_OWNERSHIP_CONFLICT", "unmanaged target differs", path=path)
            elif not _state_matches(observed, baseline):
                if operation == "repair" and _state_matches(candidate, baseline):
                    action, reason = "restorative-repair", "restore-managed-contract"
                    candidate_states.append(candidate)
                    candidate_contents[path] = record.candidate_bytes
                else:
                    raise _failure("AWP_OWNERSHIP_DRIFT", "managed target drifted", path=path)
            elif not _state_matches(candidate, observed):
                action, reason = "replace", "managed-candidate-changed"
                candidate_states.append(candidate)
                candidate_contents[path] = record.candidate_bytes
            manifest_candidate = _manifest_record(record, candidate)
        elif record.ownership == "overlay-managed":
            marker_map_raw = target.get("markers")
            begin, end = _markers(marker_map_raw, path=path)
            marker_map = {"begin": begin, "end": end}
            begin_token = begin.encode("utf-8") + b"\n"
            end_token = end.encode("utf-8") + b"\n"
            if (
                old_record is None
                and content is not None
                and content.count(begin_token) == 0
                and content.count(end_token) == 0
            ):
                prefix = content + (b"" if not content or content.endswith(b"\n") else b"\n")
                block = b""
                suffix = b""
                initial_overlay_insert = True
            else:
                prefix, block, suffix, marker_map = _overlay_parts(
                    content, marker_map_raw, path=path
                )
                initial_overlay_insert = False
            observed_block_hash = hashlib.sha256(block).hexdigest()
            candidate_block_hash = hashlib.sha256(record.candidate_bytes).hexdigest()
            observation = MappingProxyType(
                {
                    **dict(observation),
                    "marker_state": "unique",
                    "managed_block_hash": observed_block_hash,
                }
            )
            observations[-1] = observation
            if old_record is None:
                if initial_overlay_insert:
                    action, reason = "create", "insert-managed-block"
                elif observed_block_hash != candidate_block_hash:
                    raise _failure("AWP_OWNERSHIP_CONFLICT", "unmanaged overlay block differs", path=path)
                else:
                    reason = "enroll-matching-overlay"
            elif observed_block_hash != old_record.get("managed_block_hash"):
                if not (
                    operation == "repair"
                    and candidate_block_hash == old_record.get("managed_block_hash")
                ):
                    raise _failure("AWP_OWNERSHIP_DRIFT", "managed overlay block drifted", path=path)
                action, reason = "restorative-repair", "restore-managed-block"
            elif candidate_block_hash != observed_block_hash:
                action, reason = "update-managed-block", "managed-block-candidate-changed"
            candidate_bytes = (
                prefix
                + marker_map["begin"].encode("utf-8")
                + b"\n"
                + record.candidate_bytes
                + marker_map["end"].encode("utf-8")
                + b"\n"
                + suffix
            )
            candidate = FileState(
                path,
                True,
                "regular",
                hashlib.sha256(candidate_bytes).hexdigest(),
                observed.mode,
                True,
                candidate_block_hash,
            )
            if action != "no-op":
                candidate_states.append(candidate)
                candidate_contents[path] = candidate_bytes
            manifest_candidate = (
                old_record
                if action == "no-op" and old_record is not None
                else _manifest_record(
                    record,
                    candidate,
                    managed_block_hash=candidate_block_hash,
                    markers=marker_map,
                )
            )
        elif record.ownership == "adopted":
            candidate = observed
            if old_record is None:
                action, reason = "adopt-baseline", "record-observed-baseline"
            else:
                reason = "adopted-drift-is-observed"
            manifest_candidate = _manifest_record(record, baseline if old_record else observed)
        elif record.ownership == "create-once-then-user-owned":
            if old_record is not None and old_record.get("created_once") is True:
                candidate = observed
                reason = "create-once-already-consumed"
                manifest_candidate = old_record
            elif observed.exists or baseline.exists:
                raise _failure("AWP_OWNERSHIP_CONFLICT", "create-once target lacks historical absence", path=path)
            else:
                action, reason = "create", "create-once-original-absence"
                candidate_states.append(candidate)
                candidate_contents[path] = record.candidate_bytes
                manifest_candidate = _manifest_record(
                    record, candidate, ownership="user-owned", created_once=True
                )
        elif record.ownership == "user-owned":
            candidate = observed
            reason = "user-owned-no-write-authority"
            manifest_candidate = old_record
        else:
            raise _failure("AWP_OWNERSHIP_CONFLICT", "ownership class is unsupported", path=path)

        decision = _decision(record, observed, baseline, candidate, action, reason)
        decisions.append(decision)
        preconditions.append(decision)
        if manifest_candidate is not None:
            next_manifest.append(manifest_candidate)

    previous_projection = [dict(previous[path]) for path in sorted(previous)]
    next_manifest.sort(key=lambda item: str(item["path"]))
    return OwnershipPlan(
        decisions=tuple(decisions),
        observations=tuple(observations),
        preconditions=tuple(preconditions),
        candidate_file_states=tuple(sorted(candidate_states, key=lambda item: item.path)),
        candidate_contents=MappingProxyType(dict(sorted(candidate_contents.items()))),
        manifest_file_records=tuple(next_manifest),
        has_file_changes=bool(candidate_states),
        has_manifest_changes=[dict(item) for item in next_manifest] != previous_projection,
    )
