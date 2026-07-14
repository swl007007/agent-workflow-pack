"""Pure Core/Resolver facade composing the frozen validation pipeline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from .artifact_policy import validate_artifact_definitions, validate_trellis_layout
from .canonical import canonical_json_bytes, digest, normalize_json_value
from .catalog import (
    evaluate_capabilities,
    normalize_workflow_lock,
    resolve_catalog_closure,
)
from .errors import CoreFailure
from .impact import CandidateImpact, compute_candidate_impact
from .profile import resolve_profile
from .surfaces import (
    compute_surface_digests,
    prove_surface_coverage,
    validate_surface_registry,
)
from .task_policy import evaluate_task_gate, evaluate_workspace_state_quiescence


@dataclass(frozen=True)
class ResolverInputs:
    operation: str
    release_contract: Mapping[str, object]
    profile_sources: Sequence[Mapping[str, object]]
    selected_profile_id: str
    catalog_document: Mapping[str, object]
    workflow_lock_document: Mapping[str, object]
    capability_manifests: Sequence[Mapping[str, object]]
    artifact_definition_documents: Sequence[Mapping[str, object]]
    trellis_layout_document: Mapping[str, object]
    surface_registry_document: Mapping[str, object]
    runtime_unit_inventory_document: Mapping[str, object]
    runtime_unit_evidence: Sequence[Mapping[str, object]]
    route_policy_document: Mapping[str, object]
    router_contract_document: Mapping[str, object]
    entry_ownership: Sequence[Mapping[str, object]]
    render_units: Sequence[Mapping[str, object]]
    current_contract: Mapping[str, object]
    observed_state: Mapping[str, object]
    repair_surface_ids: Sequence[str]
    diagnostics: Sequence[Mapping[str, object]]
    task_snapshot: Mapping[str, object]
    task_findings: Mapping[str, object]


@dataclass(frozen=True)
class DesiredStateIR:
    operation: str
    release_contract: Mapping[str, object]
    resolved_profile: Mapping[str, object]
    authority_digests: Mapping[str, str]
    workflow_lock_projection: Mapping[str, object]
    selected_platforms: tuple[str, ...]
    capability_results: tuple[Mapping[str, object], ...]
    catalog_closure: tuple[str, ...]
    reference_closure: tuple[str, ...]
    route_policy: Mapping[str, object]
    entry_ownership: tuple[Mapping[str, object], ...]
    discoverable_leaf_ids: tuple[str, ...]
    runtime_catalog_entry_ids: tuple[str, ...]
    trellis_task_layout: Mapping[str, object]
    surface_registry: Mapping[str, object]
    surface_digests: Mapping[str, str]
    coverage_result: Mapping[str, object]
    render_units: tuple[Mapping[str, object], ...]
    artifact_definitions: tuple[Mapping[str, object], ...]
    candidate_impact: CandidateImpact
    workspace_state_evaluation: Mapping[str, object]
    task_gate_evaluation: Mapping[str, object]
    diagnostics: tuple[Mapping[str, object], ...]
    desired_state_ir_digest: str

    def _projection(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.desired-state-ir",
            "schema_version": 1,
            "operation": self.operation,
            "release_contract": dict(self.release_contract),
            "resolved_profile": dict(self.resolved_profile),
            "authority_digests": dict(self.authority_digests),
            "workflow_lock_projection": dict(self.workflow_lock_projection),
            "selected_platforms": list(self.selected_platforms),
            "capability_results": [dict(item) for item in self.capability_results],
            "catalog_closure": list(self.catalog_closure),
            "reference_closure": list(self.reference_closure),
            "route_policy": dict(self.route_policy),
            "entry_ownership": [dict(item) for item in self.entry_ownership],
            "discoverable_leaf_ids": list(self.discoverable_leaf_ids),
            "runtime_catalog_entry_ids": list(self.runtime_catalog_entry_ids),
            "trellis_task_layout": dict(self.trellis_task_layout),
            "surface_registry": dict(self.surface_registry),
            "surface_digests": [
                {"surface_id": surface_id, "surface_digest": surface_digest}
                for surface_id, surface_digest in self.surface_digests.items()
            ],
            "coverage_result": dict(self.coverage_result),
            "render_units": [dict(item) for item in self.render_units],
            "artifact_definitions": [dict(item) for item in self.artifact_definitions],
            "candidate_impact": self.candidate_impact.to_document(),
            "workspace_state_evaluation": dict(self.workspace_state_evaluation),
            "task_gate_evaluation": dict(self.task_gate_evaluation),
        }

    def to_document(self) -> dict[str, object]:
        return {
            **self._projection(),
            "diagnostics": [dict(item) for item in self.diagnostics],
            "desired_state_ir_digest": self.desired_state_ir_digest,
        }


def _failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_SCHEMA_INVALID", message, details=details)


def _json_mapping(value: object, label: str) -> Mapping[str, object]:
    normalized = normalize_json_value(value)
    if not isinstance(normalized, dict):
        raise _failure(f"{label} must be an object")
    return MappingProxyType(cast(dict[str, object], normalized))


def _sorted_mappings(
    values: Sequence[Mapping[str, object]], label: str
) -> tuple[Mapping[str, object], ...]:
    normalized = [_json_mapping(value, label) for value in values]
    return tuple(sorted(normalized, key=canonical_json_bytes))


def _validate_release_contract(value: Mapping[str, object]) -> Mapping[str, object]:
    release = _json_mapping(value, "release contract")
    expected = {
        "release_id",
        "release_manifest_digest",
        "release_trust_policy_id",
        "release_trust_policy_digest",
        "version",
    }
    if set(release) != expected:
        raise _failure("release contract fields are not closed")
    for field in (
        "release_id",
        "release_manifest_digest",
        "release_trust_policy_digest",
    ):
        candidate = release.get(field)
        if (
            not isinstance(candidate, str)
            or len(candidate) != 64
            or any(character not in "0123456789abcdef" for character in candidate)
        ):
            raise _failure("release contract digest is invalid", field=field)
    for field in ("release_trust_policy_id", "version"):
        candidate = release.get(field)
        if not isinstance(candidate, str) or not candidate or candidate != candidate.strip():
            raise _failure("release contract string is invalid", field=field)
    return release


def _profile_projection(profile: Any) -> Mapping[str, object]:
    return _json_mapping(
        {
            "schema_version": profile.schema_version,
            "profile_id": profile.profile_id,
            "route_admission": dict(profile.route_admission),
            "bindings": {
                mode: dict(platforms) for mode, platforms in profile.bindings.items()
            },
            "skills_enable": list(profile.skills_enable),
            "skills_disable": list(profile.skills_disable),
            "artifact_policy": profile.artifact_policy,
            "default_platforms": list(profile.default_platforms),
            "required_capabilities": {
                capability_id: level.value
                for capability_id, level in profile.required_capabilities.items()
            },
            "approval_policy": dict(profile.approval_policy),
            "provider_security_policy": dict(profile.provider_security_policy),
        },
        "resolved profile",
    )


def _workflow_lock_projection(workflow_lock: Any) -> Mapping[str, object]:
    return _json_mapping(
        {
            "schema_id": "agent-workflow.workflow-lock",
            "schema_version": workflow_lock.schema_version,
            "components": [
                {
                    "id": component.component_id,
                    "version": component.version,
                    "source_sha256": component.source_sha256,
                    "content_digest": component.content_digest,
                    "provider_id": component.provider_id,
                    "acquisition_id": component.acquisition_id,
                }
                for component in workflow_lock.components
            ],
        },
        "workflow lock",
    )


def _artifact_projection(definitions: Sequence[Any]) -> tuple[Mapping[str, object], ...]:
    result: list[Mapping[str, object]] = []
    for definition in definitions:
        result.append(
            _json_mapping(
                {
                    "id": definition.definition_id,
                    "source": definition.source,
                    "targets": [
                        {
                            "path": target.path,
                            "ownership": target.ownership,
                            "merge_strategy": target.merge_strategy,
                            "mode_policy": target.mode_policy,
                            "mode": target.mode,
                            "markers": (
                                None
                                if target.markers is None
                                else {"begin": target.markers[0], "end": target.markers[1]}
                            ),
                        }
                        for target in definition.targets
                    ],
                    "forbidden_paths": list(definition.forbidden_paths),
                    "validators": [
                        {"id": validator_id, "version": version}
                        for validator_id, version in definition.validators
                    ],
                },
                "artifact definition",
            )
        )
    return tuple(sorted(result, key=lambda item: str(item["id"])))


def compute_workflow_lock_digest(document: Mapping[str, object]) -> str:
    """Return the exact Resolver authority digest for one workflow lock."""

    return digest(
        "agent-workflow.workflow-lock.v1",
        _workflow_lock_projection(normalize_workflow_lock(document)),
    )


def compute_artifact_bundle_digest(
    documents: Sequence[Mapping[str, object]],
) -> str:
    """Return the exact Resolver authority digest for artifact definitions."""

    return digest(
        "agent-workflow.artifact-bundle.v1",
        list(_artifact_projection(validate_artifact_definitions(documents))),
    )


def _gate_blocker_exit(code: str) -> int:
    if code == "AWP_WORKSPACE_TASK_RECOVERY_BLOCK":
        return 21
    return 22


def resolve(inputs: ResolverInputs) -> DesiredStateIR:
    """Resolve raw verified inputs into one complete, non-authoritative DesiredStateIR."""

    if inputs.operation not in {"init", "sync", "repair", "upgrade"}:
        raise _failure("Resolver operation is unsupported", operation=inputs.operation)

    release_contract = _validate_release_contract(inputs.release_contract)
    workflow_lock = normalize_workflow_lock(inputs.workflow_lock_document)
    workflow_lock_projection = _workflow_lock_projection(workflow_lock)
    profile = resolve_profile(inputs.profile_sources, inputs.selected_profile_id)
    resolved_profile = _profile_projection(profile)
    catalog = resolve_catalog_closure(
        profile, inputs.catalog_document, inputs.capability_manifests
    )
    capability_results_raw = evaluate_capabilities(profile, inputs.capability_manifests)
    capability_results = tuple(
        _json_mapping(
            {
                "capability_id": result.capability_id,
                "required": result.required.value,
                "observed": result.observed.value,
                "platform": result.platform,
            },
            "capability result",
        )
        for result in capability_results_raw
    )

    artifact_definitions = validate_artifact_definitions(
        inputs.artifact_definition_documents
    )
    artifact_projection = _artifact_projection(artifact_definitions)
    artifact_targets = tuple(
        target.path for definition in artifact_definitions for target in definition.targets
    )
    layout = validate_trellis_layout(
        inputs.trellis_layout_document, artifact_targets=artifact_targets
    )
    registry = validate_surface_registry(
        inputs.surface_registry_document, inputs.runtime_unit_inventory_document
    )
    surface_digests = compute_surface_digests(registry, inputs.runtime_unit_evidence)
    coverage = prove_surface_coverage(registry, inputs.runtime_unit_evidence)

    route_policy = _json_mapping(inputs.route_policy_document, "route policy")
    router_contract = _json_mapping(inputs.router_contract_document, "router contract")
    authority_digests = MappingProxyType(
        {
            "artifact-bundle": digest(
                "agent-workflow.artifact-bundle.v1", list(artifact_projection)
            ),
            "profile": digest("agent-workflow.profile.v1", resolved_profile),
            "release-identity": digest(
                "agent-workflow.release-identity.v1", release_contract
            ),
            "route-policy": digest("agent-workflow.route-policy.v1", route_policy),
            "router-contract": digest(
                "agent-workflow.router-contract.v1", router_contract
            ),
            "surface-registry": registry.registry_digest,
            "trellis-layout": layout.layout_digest,
            "workflow-lock": digest(
                "agent-workflow.workflow-lock.v1", workflow_lock_projection
            ),
        }
    )
    candidate_view: dict[str, object] = {
        "operation": inputs.operation,
        "authority_digests": dict(authority_digests),
        "surface_digests": dict(surface_digests),
        "registry_graph_digest": registry.registry_digest,
        "repair_surface_ids": list(inputs.repair_surface_ids),
    }
    candidate_impact = compute_candidate_impact(
        inputs.current_contract, inputs.observed_state, candidate_view
    )
    workspace_state = evaluate_workspace_state_quiescence(
        inputs.task_snapshot, inputs.task_findings
    )
    task_gate = evaluate_task_gate(
        inputs.operation,
        candidate_impact,
        inputs.task_snapshot,
        inputs.task_findings,
    )
    if task_gate.blockers:
        blocker = task_gate.blockers[0]
        raise CoreFailure(
            blocker.code,
            "task gate blocks the requested Resolver operation",
            exit_code=_gate_blocker_exit(blocker.code),
            details={"finding_id": blocker.finding_id},
        )

    entry_ownership = _sorted_mappings(inputs.entry_ownership, "entry ownership")
    render_units = _sorted_mappings(inputs.render_units, "render unit")
    diagnostics = _sorted_mappings(inputs.diagnostics, "diagnostic")
    workspace_evaluation = MappingProxyType(
        {
            "evaluator_id": workspace_state.evaluator_id,
            "evaluator_version": workspace_state.evaluator_version,
            "task_quiescence": workspace_state.task_quiescence,
            "blockers": list(workspace_state.evidence_kinds),
        }
    )
    gate_evaluation: Mapping[str, object] = MappingProxyType(
        {
            "evaluator_id": task_gate.evaluator_id,
            "evaluator_version": task_gate.evaluator_version,
            "blockers": [],
            "primary_evaluator_blocker": None,
        }
    )
    coverage_result = MappingProxyType(
        {
            "covered_unit_ids": list(coverage.covered_unit_ids),
            "surface_ids": list(coverage.surface_ids),
            "registry_digest": coverage.registry_digest,
            "proof_digest": coverage.proof_digest,
        }
    )
    ir_without_digest = DesiredStateIR(
        operation=inputs.operation,
        release_contract=release_contract,
        resolved_profile=resolved_profile,
        authority_digests=authority_digests,
        workflow_lock_projection=workflow_lock_projection,
        selected_platforms=profile.default_platforms,
        capability_results=capability_results,
        catalog_closure=catalog.ordered_ids,
        reference_closure=catalog.reference_ids,
        route_policy=route_policy,
        entry_ownership=entry_ownership,
        discoverable_leaf_ids=catalog.discoverable_ids,
        runtime_catalog_entry_ids=catalog.ordered_ids,
        trellis_task_layout=layout.normalized,
        surface_registry=_json_mapping(
            inputs.surface_registry_document, "surface registry"
        ),
        surface_digests=surface_digests,
        coverage_result=coverage_result,
        render_units=render_units,
        artifact_definitions=artifact_projection,
        candidate_impact=candidate_impact,
        workspace_state_evaluation=workspace_evaluation,
        task_gate_evaluation=gate_evaluation,
        diagnostics=diagnostics,
        desired_state_ir_digest="",
    )
    desired_state_ir_digest = digest(
        "agent-workflow.desired-state-ir.v1", ir_without_digest._projection()
    )
    return DesiredStateIR(
        **{
            **ir_without_digest.__dict__,
            "desired_state_ir_digest": desired_state_ir_digest,
        }
    )
