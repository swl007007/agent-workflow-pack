"""Workspace-state and command-admission diagnostic projection."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import digest
from .errors import CoreFailure
from .task_policy import TaskGateResult, WorkspaceTaskState


_RELATIONSHIPS = frozenset(
    {"matching", "migration-required", "ahead", "diverged", "unknown"}
)
_RELATIONSHIP_EVIDENCE = frozenset({"verified", "missing", "invalid"})
_DISCOVERY_EVIDENCE = frozenset({"verified", "missing", "unsupported", "invalid"})


@dataclass(frozen=True)
class WorkspaceStateDiagnostic:
    relationship: str
    relationship_evidence: str
    discovery_evidence: str
    task_quiescence: str
    primary_state_blocker: str | None

    def to_document(self) -> dict[str, object]:
        return {
            "relationship": self.relationship,
            "relationship_evidence": self.relationship_evidence,
            "discovery_evidence": self.discovery_evidence,
            "task_quiescence": self.task_quiescence,
            "primary_state_blocker": self.primary_state_blocker,
        }


@dataclass(frozen=True)
class CommandAdmission:
    command: str
    allowed: bool
    blocker: str | None

    def to_document(self) -> dict[str, object]:
        return {"command": self.command, "allowed": self.allowed, "blocker": self.blocker}


@dataclass(frozen=True)
class WorkspaceDiagnostic:
    workspace_state: WorkspaceStateDiagnostic
    command_admission: CommandAdmission
    secondary_diagnostics: tuple[str, ...]
    workspace_diagnostic_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.workspace-diagnostic",
            "schema_version": 1,
            "workspace_state": self.workspace_state.to_document(),
            "command_admission": self.command_admission.to_document(),
            "secondary_diagnostics": list(self.secondary_diagnostics),
            "workspace_diagnostic_digest": self.workspace_diagnostic_digest,
        }


def _failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_SCHEMA_INVALID", message, details=details)


def _state_blocker(
    relationship: str,
    relationship_evidence: str,
    discovery_evidence: str,
    task_state: WorkspaceTaskState,
    task_gate: TaskGateResult,
) -> tuple[str, str | None]:
    if relationship_evidence == "invalid":
        return "unknown", "AWP_SOURCE_RELEASE_VERIFICATION_FAILED"
    if relationship_evidence == "missing":
        return "unknown", "AWP_WORKSPACE_SOURCE_METADATA_REQUIRED"
    if relationship == "ahead":
        return relationship, "AWP_WORKSPACE_CONTRACT_AHEAD"
    if relationship == "diverged":
        return relationship, "AWP_WORKSPACE_CONTRACT_DIVERGED"
    if relationship == "migration-required":
        if discovery_evidence == "missing":
            return relationship, "AWP_WORKSPACE_SOURCE_METADATA_REQUIRED"
        if discovery_evidence in {"unsupported", "invalid"} or task_state.task_quiescence == "ambiguous":
            return relationship, "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS"
        if task_gate.primary_evaluator_blocker is not None:
            return relationship, task_gate.primary_evaluator_blocker
        return relationship, "AWP_WORKSPACE_MIGRATION_REQUIRED"
    if relationship != "matching":
        return "unknown", "AWP_WORKSPACE_SOURCE_METADATA_REQUIRED"
    if discovery_evidence in {"unsupported", "invalid"} or task_state.task_quiescence == "ambiguous":
        return relationship, "AWP_WORKSPACE_TASK_LAYOUT_AMBIGUOUS"
    if "unfinished-task-transaction" in task_state.evidence_kinds:
        return relationship, "AWP_WORKSPACE_TASK_RECOVERY_BLOCK"
    return relationship, None


def _command_admission(
    command: str,
    relationship: str,
    relationship_evidence: str,
    discovery_evidence: str,
    state_blocker: str | None,
    task_gate: TaskGateResult,
) -> CommandAdmission:
    if command == "doctor":
        return CommandAdmission(command, True, None)
    if relationship_evidence == "invalid":
        return CommandAdmission(command, False, "AWP_SOURCE_RELEASE_VERIFICATION_FAILED")
    if command == "workspace-migrate":
        allowed = (
            relationship == "migration-required"
            and relationship_evidence == "verified"
            and discovery_evidence == "verified"
            and not task_gate.blockers
        )
        blocker = None if allowed else task_gate.primary_evaluator_blocker or state_blocker
        return CommandAdmission(command, allowed, blocker)
    allowed = (
        relationship == "matching"
        and relationship_evidence == "verified"
        and not task_gate.blockers
        and state_blocker is None
    )
    return CommandAdmission(
        command,
        allowed,
        None if allowed else task_gate.primary_evaluator_blocker or state_blocker,
    )


def build_workspace_diagnostic(
    *,
    command: str,
    relationship: str,
    relationship_evidence: str,
    discovery_evidence: str,
    workspace_task_state: WorkspaceTaskState,
    task_gate_result: TaskGateResult,
) -> WorkspaceDiagnostic:
    """Build one state/admission object shared by human and JSON projections."""

    if relationship not in _RELATIONSHIPS:
        raise _failure("workspace relationship is invalid", relationship=relationship)
    if relationship_evidence not in _RELATIONSHIP_EVIDENCE:
        raise _failure("relationship evidence state is invalid")
    if discovery_evidence not in _DISCOVERY_EVIDENCE:
        raise _failure("discovery evidence state is invalid")
    normalized_relationship, state_blocker = _state_blocker(
        relationship,
        relationship_evidence,
        discovery_evidence,
        workspace_task_state,
        task_gate_result,
    )
    workspace_state = WorkspaceStateDiagnostic(
        relationship=normalized_relationship,
        relationship_evidence=relationship_evidence,
        discovery_evidence=discovery_evidence,
        task_quiescence=workspace_task_state.task_quiescence,
        primary_state_blocker=state_blocker,
    )
    admission = _command_admission(
        command,
        normalized_relationship,
        relationship_evidence,
        discovery_evidence,
        state_blocker,
        task_gate_result,
    )
    all_codes = [blocker.code for blocker in task_gate_result.blockers]
    if state_blocker is not None:
        all_codes.append(state_blocker)
    primary_codes = {state_blocker, admission.blocker}
    secondary = tuple(sorted({code for code in all_codes if code not in primary_codes}))
    projection = {
        "schema_id": "agent-workflow.workspace-diagnostic",
        "schema_version": 1,
        "workspace_state": workspace_state.to_document(),
        "command_admission": admission.to_document(),
        "secondary_diagnostics": list(secondary),
    }
    return WorkspaceDiagnostic(
        workspace_state=workspace_state,
        command_admission=admission,
        secondary_diagnostics=secondary,
        workspace_diagnostic_digest=digest("agent-workflow.workspace-diagnostic.v1", projection),
    )
