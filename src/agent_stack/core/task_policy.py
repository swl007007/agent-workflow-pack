"""Pure task-quiescence and operation-specific task-gate policies."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .canonical import digest, normalize_mode, normalize_path
from .errors import CoreFailure
from .impact import CandidateImpact, SurfaceChange


WORKSPACE_STATE_EVALUATOR_ID = "agent-workflow.workspace-state-quiescence"
TASK_GATE_EVALUATOR_ID = "agent-workflow.task-gate"
EVALUATOR_VERSION = 1

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_AMBIGUOUS_KINDS = frozenset(
    {
        "layout-ambiguous",
        "unknown-entry",
        "collision",
        "scan-limit",
        "interpretation-conflict",
    }
)
_BLOCKED_KINDS = frozenset(
    {"unfinished-task-transaction", "non-archived-task", "layout-state-stranded"}
)
_OPERATIONS = frozenset({"init", "sync", "repair", "upgrade", "workspace-migrate"})
_NON_ARCHIVED_STATUSES = frozenset(
    {"admitting", "active", "blocked", "completed", "archiving"}
)
_FINDING_FIELDS = {
    "layout-ambiguous": {
        "kind",
        "finding_id",
        "normalized_path",
        "evidence_class",
        "parser_id",
        "parser_version",
        "evidence_schema_id",
        "evidence_schema_version",
    },
    "unknown-entry": {"kind", "finding_id", "normalized_path", "root_contract_id"},
    "collision": {"kind", "finding_id", "normalized_aliases", "collision_class"},
    "scan-limit": {
        "kind",
        "finding_id",
        "contract_id",
        "limit_kind",
        "configured_limit",
    },
    "interpretation-conflict": {
        "kind",
        "finding_id",
        "task_id",
        "task_ref",
        "current_path",
        "conflicting_fields",
    },
    "unfinished-task-transaction": {
        "kind",
        "finding_id",
        "journal_path",
        "task_id",
        "task_ref",
        "operation",
        "phase",
    },
    "non-archived-task": {
        "kind",
        "finding_id",
        "task_id",
        "current_path",
        "lifecycle_status",
        "mode",
        "pinned_surfaces",
    },
    "layout-state-stranded": {
        "kind",
        "finding_id",
        "normalized_path",
        "semantic_role",
        "source_visibility",
        "target_visibility",
    },
}


@dataclass(frozen=True)
class SurfacePin:
    surface_id: str
    surface_digest: str


@dataclass(frozen=True)
class TaskFact:
    task_id: str
    current_path: str
    lifecycle_status: str
    mode: str
    pinned_surfaces: tuple[SurfacePin, ...]


@dataclass(frozen=True)
class FindingFact:
    kind: str
    finding_id: str
    task_id: str | None = None
    path: str | None = None
    lifecycle_status: str | None = None
    mode: str | None = None
    pinned_surfaces: tuple[SurfacePin, ...] = ()


@dataclass(frozen=True)
class WorkspaceTaskState:
    evaluator_id: str
    evaluator_version: int
    task_quiescence: str
    evidence_kinds: tuple[str, ...]


@dataclass(frozen=True)
class TaskGateBlocker:
    code: str
    finding_id: str
    task_id: str | None = None
    path: str | None = None
    surface_id: str | None = None
    authority_id: str | None = None


@dataclass(frozen=True)
class TaskGateResult:
    evaluator_id: str
    evaluator_version: int
    operation: str
    blockers: tuple[TaskGateBlocker, ...]
    primary_evaluator_blocker: str | None


@dataclass(frozen=True)
class VerifiedDiscoverySchemas:
    schema_bundle_digest: str
    normalized: Mapping[str, object]

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.schema_bundle_digest):
            raise ValueError("schema_bundle_digest must be lowercase SHA-256")


@dataclass(frozen=True)
class TaskSnapshotAndFindings:
    snapshot: Mapping[str, object]
    findings: Mapping[str, object]
    task_quiescence_digest: str

    def __post_init__(self) -> None:
        if not _DIGEST.fullmatch(self.task_quiescence_digest):
            raise ValueError("task_quiescence_digest must be lowercase SHA-256")


def _failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_SCHEMA_INVALID", message, details=details)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure(f"{label} must be a string-keyed object")
    return value


def _array(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _failure(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise _failure(f"{label} must be a nonempty string")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise _failure(f"{label} must be lowercase SHA-256")
    return value


def _uuid(value: object, label: str) -> str:
    text = _string(value, label)
    try:
        parsed = str(uuid.UUID(text))
    except ValueError as error:
        raise _failure(f"{label} must be a canonical UUID") from error
    if parsed != text:
        raise _failure(f"{label} must be a canonical UUID")
    return text


def _path(value: object, label: str) -> str:
    try:
        return normalize_path(_string(value, label))
    except CoreFailure as error:
        raise _failure(f"{label} must be a normalized repository path") from error


def _surface_pins(value: object, label: str) -> tuple[SurfacePin, ...]:
    pins: list[SurfacePin] = []
    for index, raw_pin in enumerate(_array(value, label)):
        pin = _mapping(raw_pin, f"{label}[{index}]")
        if set(pin) != {"surface_id", "surface_digest"}:
            raise _failure(f"{label}[{index}] fields are not closed")
        surface_id = _string(pin.get("surface_id"), f"{label}[{index}].surface_id")
        surface_digest = _sha256(
            pin.get("surface_digest"), f"{label}[{index}].surface_digest"
        )
        pins.append(SurfacePin(surface_id, surface_digest))
    ordered = tuple(sorted(pins, key=lambda pin: pin.surface_id))
    if tuple(pins) != ordered or len({pin.surface_id for pin in pins}) != len(pins):
        raise _failure(f"{label} must be unique and sorted by surface_id")
    return ordered


def _task_facts(snapshot: Mapping[str, object]) -> dict[str, TaskFact]:
    tasks: dict[str, TaskFact] = {}
    paths: set[str] = set()
    required_fields = {
        "task_id",
        "admission_task_ref",
        "current_path",
        "source_role",
        "target_role",
        "integration_byte_hash",
        "integration_mode",
        "integration_schema_id",
        "integration_schema_version",
        "lifecycle_status",
        "revision",
        "mode",
        "task_contract_digest",
        "task_contract_surfaces",
    }
    for index, raw_task in enumerate(_array(snapshot.get("tasks"), "snapshot.tasks")):
        task = _mapping(raw_task, f"snapshot.tasks[{index}]")
        if set(task) != required_fields:
            raise _failure("task snapshot record fields are not closed", index=index)
        task_id = _uuid(task.get("task_id"), f"snapshot.tasks[{index}].task_id")
        current_path = _path(
            task.get("current_path"), f"snapshot.tasks[{index}].current_path"
        )
        _string(task.get("admission_task_ref"), "task admission ref")
        if task.get("source_role") not in {"absent", "active", "archive"} or task.get(
            "target_role"
        ) not in {"absent", "active", "archive"}:
            raise _failure("task source/target roles are invalid", task_id=task_id)
        _sha256(task.get("integration_byte_hash"), "integration byte hash")
        try:
            normalize_mode(task.get("integration_mode"))  # type: ignore[arg-type]
        except CoreFailure as error:
            raise _failure("integration mode is invalid", task_id=task_id) from error
        _string(task.get("integration_schema_id"), "integration schema id")
        if not isinstance(task.get("integration_schema_version"), int):
            raise _failure("integration schema version must be an integer")
        status = _string(task.get("lifecycle_status"), "lifecycle status")
        if status not in _NON_ARCHIVED_STATUSES | {"archived"}:
            raise _failure("task lifecycle status is invalid", task_id=task_id)
        revision = task.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise _failure("task revision must be a nonnegative integer", task_id=task_id)
        mode = _string(task.get("mode"), "task mode")
        if mode not in {"trellis-native", "speckit-superpowers"}:
            raise _failure("task mode is invalid", task_id=task_id)
        _sha256(task.get("task_contract_digest"), "task contract digest")
        pins = _surface_pins(task.get("task_contract_surfaces"), "task contract surfaces")
        if task_id in tasks or current_path in paths:
            raise _failure("task identity or current path is duplicated", task_id=task_id)
        paths.add(current_path)
        tasks[task_id] = TaskFact(task_id, current_path, status, mode, pins)
    return tasks


def _validate_snapshot_collections(snapshot: Mapping[str, object]) -> None:
    for label in (
        "source_layout_digest",
        "target_layout_digest",
        "source_schema_bundle_digest",
        "target_schema_bundle_digest",
    ):
        _sha256(snapshot.get(label), f"snapshot.{label}")
    for index, raw in enumerate(_array(snapshot.get("metadata"), "snapshot.metadata")):
        metadata = _mapping(raw, f"snapshot.metadata[{index}]")
        required = {
            "path",
            "byte_hash",
            "mode",
            "parser_id",
            "parser_version",
            "classifier_id",
            "classifier_version",
            "parsed_task_refs",
            "semantic_role",
            "classification",
        }
        if set(metadata) != required:
            raise _failure("metadata snapshot record fields are not closed", index=index)
        _path(metadata.get("path"), "metadata path")
        _sha256(metadata.get("byte_hash"), "metadata byte hash")
    for index, raw in enumerate(
        _array(snapshot.get("task_journals"), "snapshot.task_journals")
    ):
        journal = _mapping(raw, f"snapshot.task_journals[{index}]")
        required = {
            "journal_path",
            "byte_hash",
            "mode",
            "schema_id",
            "schema_version",
            "operation",
            "phase",
            "task_id",
            "task_ref",
            "terminal",
        }
        if set(journal) != required:
            raise _failure("task-journal snapshot record fields are not closed", index=index)
        _path(journal.get("journal_path"), "task journal path")
        _sha256(journal.get("byte_hash"), "task journal byte hash")
        _uuid(journal.get("task_id"), "task journal task_id")
        if not isinstance(journal.get("terminal"), bool):
            raise _failure("task journal terminal flag must be boolean")


def _parse_findings(findings_document: Mapping[str, object]) -> tuple[FindingFact, ...]:
    if set(findings_document) != {"schema_id", "schema_version", "findings"}:
        raise _failure("task findings fields are not closed")
    if findings_document.get("schema_id") != "agent-workflow.task-findings" or findings_document.get(
        "schema_version"
    ) != 1:
        raise _failure("task findings schema identity/version is invalid")
    facts: list[FindingFact] = []
    finding_ids: set[str] = set()
    for index, raw_finding in enumerate(
        _array(findings_document.get("findings"), "findings.findings")
    ):
        finding = _mapping(raw_finding, f"findings.findings[{index}]")
        kind = _string(finding.get("kind"), "finding kind")
        if kind not in _FINDING_FIELDS or set(finding) != _FINDING_FIELDS[kind]:
            raise _failure("finding branch fields are not closed", kind=kind)
        finding_id = _string(finding.get("finding_id"), "finding id")
        if finding_id in finding_ids:
            raise _failure("finding id is duplicated", finding_id=finding_id)
        finding_ids.add(finding_id)
        task_id: str | None = None
        path: str | None = None
        status: str | None = None
        mode: str | None = None
        pins: tuple[SurfacePin, ...] = ()
        if "task_id" in finding:
            task_id = _uuid(finding.get("task_id"), "finding task_id")
        if "current_path" in finding:
            path = _path(finding.get("current_path"), "finding current_path")
        elif "journal_path" in finding:
            path = _path(finding.get("journal_path"), "finding journal_path")
        elif "normalized_path" in finding:
            path = _path(finding.get("normalized_path"), "finding normalized_path")
        if kind == "collision":
            aliases = tuple(
                _path(alias, "collision alias")
                for alias in _array(finding.get("normalized_aliases"), "normalized aliases")
            )
            path = min(aliases) if aliases else None
        if kind == "non-archived-task":
            status = _string(finding.get("lifecycle_status"), "finding lifecycle status")
            if status not in _NON_ARCHIVED_STATUSES:
                raise _failure("non-archived finding has an archived/invalid status")
            mode = _string(finding.get("mode"), "finding task mode")
            pins = _surface_pins(finding.get("pinned_surfaces"), "finding pinned surfaces")
        facts.append(FindingFact(kind, finding_id, task_id, path, status, mode, pins))
    return tuple(facts)


def _validated_evidence(
    snapshot_document: Mapping[str, object], findings_document: Mapping[str, object]
) -> tuple[dict[str, TaskFact], tuple[FindingFact, ...]]:
    required = {
        "schema_id",
        "schema_version",
        "source_layout_digest",
        "target_layout_digest",
        "source_schema_bundle_digest",
        "target_schema_bundle_digest",
        "tasks",
        "metadata",
        "task_journals",
        "finding_ids",
        "task_quiescence_digest",
    }
    if set(snapshot_document) != required:
        raise _failure("task snapshot fields are not closed")
    if snapshot_document.get("schema_id") != "agent-workflow.task-quiescence-snapshot" or snapshot_document.get(
        "schema_version"
    ) != 1:
        raise _failure("task snapshot schema identity/version is invalid")
    expected_digest = _sha256(
        snapshot_document.get("task_quiescence_digest"), "task_quiescence_digest"
    )
    projection = dict(snapshot_document)
    del projection["task_quiescence_digest"]
    if digest("agent-workflow.task-quiescence.v1", projection) != expected_digest:
        raise _failure("task snapshot digest does not match its canonical projection")
    tasks = _task_facts(snapshot_document)
    _validate_snapshot_collections(snapshot_document)
    findings = _parse_findings(findings_document)
    raw_finding_ids = _array(snapshot_document.get("finding_ids"), "snapshot.finding_ids")
    if not all(isinstance(item, str) for item in raw_finding_ids):
        raise _failure("snapshot finding_ids must contain strings")
    finding_ids = tuple(str(item) for item in raw_finding_ids)
    if finding_ids != tuple(sorted(finding_ids)) or finding_ids != tuple(
        sorted(finding.finding_id for finding in findings)
    ):
        raise _failure("snapshot and finding identity sets disagree")

    journals = {
        str(_mapping(raw, "task journal")["journal_path"]): _mapping(raw, "task journal")
        for raw in _array(snapshot_document.get("task_journals"), "snapshot.task_journals")
    }
    for finding in findings:
        if finding.kind == "non-archived-task":
            task = tasks.get(finding.task_id or "")
            if task is None or (
                task.current_path,
                task.lifecycle_status,
                task.mode,
                task.pinned_surfaces,
            ) != (
                finding.path,
                finding.lifecycle_status,
                finding.mode,
                finding.pinned_surfaces,
            ):
                raise _failure(
                    "non-archived finding disagrees with task snapshot",
                    finding_id=finding.finding_id,
                )
        if finding.kind == "unfinished-task-transaction":
            journal = journals.get(finding.path or "")
            if journal is None or journal.get("terminal") is not False:
                raise _failure(
                    "unfinished transaction finding disagrees with journal snapshot",
                    finding_id=finding.finding_id,
                )
    return tasks, findings


def evaluate_workspace_state_quiescence(
    snapshot: Mapping[str, object], findings: Mapping[str, object]
) -> WorkspaceTaskState:
    """Evaluate command-independent workspace task state from canonical facts only."""

    _, facts = _validated_evidence(snapshot, findings)
    evidence_kinds = tuple(sorted({fact.kind for fact in facts}))
    if any(fact.kind in _AMBIGUOUS_KINDS for fact in facts):
        state = "ambiguous"
    elif any(fact.kind in _BLOCKED_KINDS for fact in facts):
        state = "blocked"
    else:
        state = "quiescent"
    return WorkspaceTaskState(
        evaluator_id=WORKSPACE_STATE_EVALUATOR_ID,
        evaluator_version=EVALUATOR_VERSION,
        task_quiescence=state,
        evidence_kinds=evidence_kinds,
    )


def _blocker(
    code: str, finding: FindingFact, *, surface_id: str | None = None
) -> TaskGateBlocker:
    return TaskGateBlocker(
        code=code,
        finding_id=finding.finding_id,
        task_id=finding.task_id,
        path=finding.path,
        surface_id=surface_id,
    )


def _surface_changes_by_id(impact: CandidateImpact) -> dict[str, SurfaceChange]:
    return {change.surface_id: change for change in impact.surface_changes}


def _task_blocker(finding: FindingFact, impact: CandidateImpact) -> TaskGateBlocker | None:
    changes = _surface_changes_by_id(impact)
    pin_by_id = {pin.surface_id: pin.surface_digest for pin in finding.pinned_surfaces}
    matching_ids = sorted(set(changes) & set(pin_by_id))
    for surface_id in matching_ids:
        change = changes[surface_id]
        pinned_digest = pin_by_id[surface_id]
        if change.contract_before_digest != pinned_digest:
            return _blocker(
                "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS", finding, surface_id=surface_id
            )
        if change.change_kind == "repair":
            if not (
                change.contract_before_digest
                == change.after_digest
                == pinned_digest
                and not impact.authority_changes
            ):
                return _blocker(
                    "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS", finding, surface_id=surface_id
                )
            continue
        if change.change_kind == "contract-change" and change.after_digest != pinned_digest:
            return _blocker("AWP_WORKSPACE_ACTIVE_TASK_BLOCK", finding, surface_id=surface_id)
    if finding.mode == "speckit-superpowers" and impact.contract_changing:
        return _blocker("AWP_WORKSPACE_ACTIVE_TASK_BLOCK", finding)
    return None


def _blocker_sort_key(blocker: TaskGateBlocker) -> tuple[object, ...]:
    class_order = {
        "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS": 0,
        "AWP_WORKSPACE_TASK_RECOVERY_BLOCK": 1,
        "AWP_WORKSPACE_ACTIVE_TASK_BLOCK": 2,
        "AWP_WORKSPACE_LAYOUT_STATE_STRANDED": 3,
    }
    return (
        class_order[blocker.code],
        blocker.task_id or "",
        blocker.path or "",
        blocker.surface_id or "",
        blocker.authority_id or "",
        blocker.finding_id,
    )


def evaluate_task_gate(
    operation: str,
    candidate_impact: CandidateImpact,
    snapshot: Mapping[str, object],
    findings: Mapping[str, object],
) -> TaskGateResult:
    """Apply operation policy to facts without changing the fixed workspace state."""

    if operation not in _OPERATIONS:
        raise _failure("task-gate operation is unsupported", operation=operation)
    _, facts = _validated_evidence(snapshot, findings)
    if (
        operation == "sync"
        and candidate_impact.impact_kind == "none"
        and not candidate_impact.authority_changes
        and not candidate_impact.surface_changes
    ):
        return TaskGateResult(TASK_GATE_EVALUATOR_ID, 1, operation, (), None)

    layout_changing = any(
        change.authority_id == "trellis-layout"
        for change in candidate_impact.authority_changes
    )
    blockers: list[TaskGateBlocker] = []
    for finding in facts:
        if finding.kind in _AMBIGUOUS_KINDS:
            blockers.append(_blocker("AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS", finding))
        elif finding.kind == "unfinished-task-transaction":
            blockers.append(_blocker("AWP_WORKSPACE_TASK_RECOVERY_BLOCK", finding))
        elif finding.kind == "non-archived-task":
            if operation in {"init", "workspace-migrate"}:
                blockers.append(_blocker("AWP_WORKSPACE_ACTIVE_TASK_BLOCK", finding))
            else:
                task_blocker = _task_blocker(finding, candidate_impact)
                if task_blocker is not None:
                    blockers.append(task_blocker)
        elif finding.kind == "layout-state-stranded" and (
            operation in {"init", "workspace-migrate"} or layout_changing
        ):
            blockers.append(_blocker("AWP_WORKSPACE_LAYOUT_STATE_STRANDED", finding))
    ordered = tuple(sorted(blockers, key=_blocker_sort_key))
    return TaskGateResult(
        evaluator_id=TASK_GATE_EVALUATOR_ID,
        evaluator_version=EVALUATOR_VERSION,
        operation=operation,
        blockers=ordered,
        primary_evaluator_blocker=ordered[0].code if ordered else None,
    )
