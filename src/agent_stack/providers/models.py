"""Immutable provider/cache public contract models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from agent_stack.core.api import CANONICAL_NULL, digest


@dataclass(frozen=True)
class AcquisitionRequest:
    component_id: str
    source_url: str
    expected_sha256: str
    max_download_bytes: int
    cache_namespace: str
    archive_policy: Mapping[str, object] | None = None
    extract: bool = False


@dataclass(frozen=True)
class AcquisitionResult:
    component_id: str
    source_digest: str
    cache_object_path: str
    archive_evidence_digest: str | None
    content_root_digest: str | None
    diagnostics_digest: str
    provenance_records: tuple[Mapping[str, object], ...]


@dataclass(frozen=True)
class ProviderPlan:
    provider_id: str
    provider_version: str
    provider_artifact_digest: str
    command_digest: str
    command: Mapping[str, object]
    project_id: str
    workspace_instance_id: str
    workflow_lock_digest: str
    input_digests: tuple[str, ...]
    requested_controls: Mapping[str, object]
    measured_isolation_gaps: tuple[str, ...]
    approval_challenge: str
    prospective_transaction_id: str
    deterministic_output_contract: Mapping[str, object]

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.provider-plan",
            "schema_version": 1,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "provider_artifact_digest": self.provider_artifact_digest,
            "command_digest": self.command_digest,
            "command": dict(self.command),
            "project_id": self.project_id,
            "workspace_instance_id": self.workspace_instance_id,
            "workflow_lock_digest": self.workflow_lock_digest,
            "input_digests": list(self.input_digests),
            "requested_controls": dict(self.requested_controls),
            "measured_isolation_gaps": list(self.measured_isolation_gaps),
            "approval_challenge": self.approval_challenge,
            "prospective_transaction_id": self.prospective_transaction_id,
            "deterministic_output_contract": dict(self.deterministic_output_contract),
        }

    @property
    def provider_plan_digest(self) -> str:
        return digest("agent-workflow.provider-plan.v1", self.to_document())


@dataclass(frozen=True)
class ProviderExecutionResult:
    provider_plan_digest: str
    approval_digest: str
    attempt_id: str
    terminal_state: str
    containment_evidence_digest: str
    result_category: str
    candidate_output_root_digest: str
    diagnostics_digest: str
    provenance_records: tuple[Mapping[str, object], ...]

    @classmethod
    def without_approval(
        cls,
        *,
        provider_plan_digest: str,
        attempt_id: str,
        terminal_state: str,
        containment_evidence_digest: str,
        result_category: str,
        candidate_output_root_digest: str,
        diagnostics_digest: str,
        provenance_records: tuple[Mapping[str, object], ...],
    ) -> ProviderExecutionResult:
        return cls(
            provider_plan_digest=provider_plan_digest,
            approval_digest=CANONICAL_NULL,
            attempt_id=attempt_id,
            terminal_state=terminal_state,
            containment_evidence_digest=containment_evidence_digest,
            result_category=result_category,
            candidate_output_root_digest=candidate_output_root_digest,
            diagnostics_digest=diagnostics_digest,
            provenance_records=provenance_records,
        )
