"""Frozen public entry point for all Core/Resolver consumers."""

from typing import Final

from .artifact_policy import (
    ArtifactDefinition,
    VerifiedTrellisTaskLayout,
    derive_protected_paths,
    validate_artifact_definitions,
    validate_trellis_layout,
)
from .canonical import (
    CANONICAL_NULL,
    canonical_json_bytes,
    digest,
    normalize_mode,
    normalize_path,
)
from .catalog import (
    evaluate_capabilities,
    normalize_workflow_lock,
    resolve_catalog_closure,
)
from .diagnostics import WorkspaceDiagnostic, build_workspace_diagnostic
from .errors import CoreFailure
from .impact import CandidateImpact, compute_candidate_impact
from .profile import resolve_profile
from .resolver import DesiredStateIR, ResolverInputs, resolve
from .saved_plan import (
    SavedPlanEnvelope,
    compute_candidate_manifest_digest,
    compute_journal_binding_digest,
    compute_plan_core_digest,
    compute_plan_digest,
    validate_plan_core,
    validate_saved_plan_envelope,
)
from .schema_catalog import SchemaCatalog
from .surfaces import (
    SurfaceCoverageProof,
    VerifiedSurfaceRegistry,
    compute_surface_digests,
    prove_surface_coverage,
    validate_surface_registry,
)
from .task_policy import (
    TaskGateResult,
    WorkspaceTaskState,
    evaluate_task_gate,
    evaluate_workspace_state_quiescence,
)


CORE_INTERFACE_VERSION: Final = 1

__all__ = [
    "ArtifactDefinition",
    "CANONICAL_NULL",
    "CORE_INTERFACE_VERSION",
    "CandidateImpact",
    "CoreFailure",
    "DesiredStateIR",
    "ResolverInputs",
    "SavedPlanEnvelope",
    "SchemaCatalog",
    "SurfaceCoverageProof",
    "TaskGateResult",
    "VerifiedSurfaceRegistry",
    "VerifiedTrellisTaskLayout",
    "WorkspaceDiagnostic",
    "WorkspaceTaskState",
    "build_workspace_diagnostic",
    "canonical_json_bytes",
    "compute_candidate_impact",
    "compute_candidate_manifest_digest",
    "compute_journal_binding_digest",
    "compute_plan_core_digest",
    "compute_plan_digest",
    "compute_surface_digests",
    "derive_protected_paths",
    "digest",
    "evaluate_capabilities",
    "evaluate_task_gate",
    "evaluate_workspace_state_quiescence",
    "normalize_mode",
    "normalize_path",
    "normalize_workflow_lock",
    "prove_surface_coverage",
    "resolve",
    "resolve_catalog_closure",
    "resolve_profile",
    "validate_artifact_definitions",
    "validate_plan_core",
    "validate_saved_plan_envelope",
    "validate_surface_registry",
    "validate_trellis_layout",
]
