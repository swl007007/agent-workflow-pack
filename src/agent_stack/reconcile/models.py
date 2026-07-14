"""Immutable render and lifecycle transaction models."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from agent_stack.core.api import CANONICAL_NULL, digest, normalize_mode, normalize_path

from .errors import RendererFailure


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PHASES = {
    "planned",
    "probing",
    "prepared",
    "applying",
    "files_applied",
    "manifest_committed",
    "cleanup_pending",
    "complete",
}


def _failure(message: str, **details: object) -> RendererFailure:
    return RendererFailure("AWP_RECONCILE_RECOVERY_REQUIRED", message, details=details)


def _sha256(value: object, field: str, *, allow_null: bool = False) -> str:
    if allow_null and value == CANONICAL_NULL:
        return CANONICAL_NULL
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise _failure("reconcile digest is invalid", field=field)
    return value


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("reconcile object is invalid", field=field)
    return value


@dataclass(frozen=True)
class FileState:
    path: str
    exists: bool
    file_type: str
    byte_hash: str
    mode: str
    non_symlink: bool
    managed_block_hash: str = CANONICAL_NULL

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> FileState:
        expected = {
            "schema_id",
            "schema_version",
            "path",
            "exists",
            "file_type",
            "byte_hash",
            "mode",
            "non_symlink",
            "managed_block_hash",
        }
        if set(document) != expected:
            raise _failure("FileState fields are not closed")
        if (
            document.get("schema_id") != "agent-workflow.file-state"
            or document.get("schema_version") != 1
        ):
            raise _failure("FileState schema identity/version is invalid")
        exists = document.get("exists")
        non_symlink = document.get("non_symlink")
        if not isinstance(exists, bool) or not isinstance(non_symlink, bool):
            raise _failure("FileState boolean field is invalid")
        file_type = document.get("file_type")
        if file_type not in {"regular", "directory", "absent"}:
            raise _failure("FileState type is invalid")
        byte_hash = _sha256(document.get("byte_hash"), "byte_hash", allow_null=True)
        mode = document.get("mode")
        if mode == CANONICAL_NULL:
            normalized_mode = CANONICAL_NULL
        else:
            try:
                normalized_mode = normalize_mode(mode)  # type: ignore[arg-type]
            except Exception as error:
                raise _failure("FileState mode is invalid") from error
        if exists and file_type == "absent":
            raise _failure("existing FileState cannot have absent type")
        if not exists and (file_type != "absent" or byte_hash != CANONICAL_NULL):
            raise _failure("absent FileState has candidate bytes or type")
        return cls(
            path=normalize_path(str(document.get("path"))),
            exists=exists,
            file_type=str(file_type),
            byte_hash=byte_hash,
            mode=normalized_mode,
            non_symlink=non_symlink,
            managed_block_hash=_sha256(
                document.get("managed_block_hash"),
                "managed_block_hash",
                allow_null=True,
            ),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.file-state",
            "schema_version": 1,
            "path": self.path,
            "exists": self.exists,
            "file_type": self.file_type,
            "byte_hash": self.byte_hash,
            "mode": self.mode,
            "non_symlink": self.non_symlink,
            "managed_block_hash": self.managed_block_hash,
        }


@dataclass(frozen=True)
class StagedFile:
    path: str
    definition_id: str
    surface_id: str
    ownership: str
    merge_strategy: str
    source_digest: str
    render_digest: str
    candidate_byte_hash: str
    mode_policy: str
    candidate_mode: str
    validator_results: tuple[Mapping[str, object], ...] = ()

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> StagedFile:
        expected = {
            "schema_id",
            "schema_version",
            "path",
            "definition_id",
            "surface_id",
            "ownership",
            "merge_strategy",
            "source_digest",
            "render_digest",
            "candidate_byte_hash",
            "mode_policy",
            "candidate_mode",
            "validator_results",
        }
        if set(document) != expected:
            raise _failure("StagedFile fields are not closed")
        results = document.get("validator_results")
        if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
            raise _failure("StagedFile validator results are invalid")
        return cls(
            path=normalize_path(str(document.get("path"))),
            definition_id=str(document.get("definition_id")),
            surface_id=str(document.get("surface_id")),
            ownership=str(document.get("ownership")),
            merge_strategy=str(document.get("merge_strategy")),
            source_digest=_sha256(document.get("source_digest"), "source_digest"),
            render_digest=_sha256(document.get("render_digest"), "render_digest"),
            candidate_byte_hash=_sha256(
                document.get("candidate_byte_hash"), "candidate_byte_hash"
            ),
            mode_policy=str(document.get("mode_policy")),
            candidate_mode=normalize_mode(document.get("candidate_mode")),  # type: ignore[arg-type]
            validator_results=tuple(
                MappingProxyType(dict(_mapping(value, "validator_result")))
                for value in results
            ),
        )


@dataclass(frozen=True)
class StagedRenderTree:
    files: tuple[StagedFile, ...]
    content_root_digest: str


@dataclass(frozen=True)
class LifecycleJournal:
    immutable_header: Mapping[str, object]
    journal_binding_digest: str
    task_quiescence_snapshot: Mapping[str, object]
    plan_digest: str
    candidate_manifest_digest: str
    candidate_manifest: Mapping[str, object]
    phase: str
    file_records: tuple[Mapping[str, object], ...]
    created_directories: tuple[str, ...]
    diagnostics: tuple[Mapping[str, object], ...]
    rollback_state: Mapping[str, object]

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> LifecycleJournal:
        expected = {
            "schema_id",
            "schema_version",
            "immutable_header",
            "journal_binding_digest",
            "task_quiescence_snapshot",
            "plan_digest",
            "candidate_manifest_digest",
            "candidate_manifest",
            "phase",
            "file_records",
            "created_directories",
            "diagnostics",
            "rollback_state",
        }
        if set(document) != expected:
            raise _failure("lifecycle journal fields are not closed")
        header = _mapping(document.get("immutable_header"), "immutable_header")
        claimed = _sha256(document.get("journal_binding_digest"), "journal_binding_digest")
        actual = digest("agent-workflow.lifecycle-transaction.v1", header)
        if claimed != actual:
            raise _failure("lifecycle journal immutable binding changed")
        phase = document.get("phase")
        if phase not in _PHASES:
            raise _failure("lifecycle journal phase is invalid")
        def array(field: str) -> Sequence[object]:
            value = document.get(field)
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                raise _failure("lifecycle journal array is invalid", field=field)
            return value
        return cls(
            immutable_header=MappingProxyType(dict(header)),
            journal_binding_digest=claimed,
            task_quiescence_snapshot=MappingProxyType(
                dict(_mapping(document.get("task_quiescence_snapshot"), "snapshot"))
            ),
            plan_digest=_sha256(document.get("plan_digest"), "plan_digest"),
            candidate_manifest_digest=_sha256(
                document.get("candidate_manifest_digest"), "candidate_manifest_digest"
            ),
            candidate_manifest=MappingProxyType(
                dict(_mapping(document.get("candidate_manifest"), "candidate_manifest"))
            ),
            phase=str(phase),
            file_records=tuple(
                MappingProxyType(dict(_mapping(value, "file_record")))
                for value in array("file_records")
            ),
            created_directories=tuple(str(value) for value in array("created_directories")),
            diagnostics=tuple(
                MappingProxyType(dict(_mapping(value, "diagnostic")))
                for value in array("diagnostics")
            ),
            rollback_state=MappingProxyType(
                dict(_mapping(document.get("rollback_state"), "rollback_state"))
            ),
        )
