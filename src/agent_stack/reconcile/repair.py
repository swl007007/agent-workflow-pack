"""Restorative-repair validation and staged-surface selection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from agent_stack.core.api import CandidateImpact, DesiredStateIR, digest
from agent_stack.core.impact import SurfaceChange

from .errors import RendererFailure
from .models import StagedRenderTree


def _failure(message: str, **details: object) -> RendererFailure:
    return RendererFailure("AWP_OWNERSHIP_CONFLICT", message, details=details)


def validate_repair_selection(
    impact: CandidateImpact,
    *,
    selected_surface_ids: Sequence[str],
    pinned_surface_digests: Mapping[str, str],
    registry_graph_before_digest: str,
    registry_graph_after_digest: str,
) -> tuple[SurfaceChange, ...]:
    """Validate the closed restorative branch without authorizing a contract change."""

    if impact.authority_changes:
        raise _failure("restorative repair cannot change an authority")
    if registry_graph_before_digest != registry_graph_after_digest:
        raise _failure("restorative repair cannot change the registry/reference graph")
    changes = tuple(impact.surface_changes)
    if not changes or impact.contract_changing:
        raise _failure("restorative repair requires a non-contract-changing drift set")
    selected = tuple(sorted(selected_surface_ids))
    change_ids = tuple(sorted(change.surface_id for change in changes))
    if selected != change_ids or len(set(selected)) != len(selected):
        raise _failure(
            "repair selection differs from the complete drift set",
            selected=list(selected),
            changes=list(change_ids),
        )
    for change in changes:
        if change.change_kind != "repair":
            raise _failure("repair selection contains a contract-change record")
        if change.contract_before_digest != change.after_digest:
            raise _failure("repair after digest differs from the current contract")
        if change.observed_before_digest == change.contract_before_digest:
            raise _failure("repair record has no observed drift")
        pinned = pinned_surface_digests.get(change.surface_id)
        if pinned is not None and pinned != change.after_digest:
            raise _failure(
                "task pinned surface differs from restorative after digest",
                surface_id=change.surface_id,
            )
    return tuple(sorted(changes, key=lambda item: item.surface_id))


def stage_restorative_repair(
    ir: DesiredStateIR, staged: StagedRenderTree
) -> StagedRenderTree:
    """Select only files owned by the exact frozen repair surface set."""

    if ir.operation != "repair" or ir.candidate_impact.authority_changes:
        raise _failure("restorative staging requires a repair IR with no authority changes")
    changes = tuple(ir.candidate_impact.surface_changes)
    if not changes or any(change.change_kind != "repair" for change in changes):
        raise _failure("restorative staging requires only repair surface changes")
    selected_ids = {change.surface_id for change in changes}
    for change in changes:
        if (
            change.contract_before_digest != change.after_digest
            or ir.surface_digests.get(change.surface_id) != change.after_digest
        ):
            raise _failure(
                "repair staged contract differs from the frozen surface registry",
                surface_id=change.surface_id,
            )
    files = tuple(record for record in staged.files if record.surface_id in selected_ids)
    represented = {record.surface_id for record in files}
    if represented != selected_ids:
        raise _failure(
            "repair staged tree does not exactly represent selected surfaces",
            missing=sorted(selected_ids - represented),
        )
    projection = [
        {
            "path": record.path,
            "surface_id": record.surface_id,
            "candidate_byte_hash": record.candidate_byte_hash,
            "candidate_mode": record.candidate_mode,
            "render_digest": record.render_digest,
        }
        for record in files
    ]
    return StagedRenderTree(
        files=files,
        content_root_digest=digest(
            "agent-workflow.restorative-repair-stage.v1", projection
        ),
        launcher_bundle_digest=staged.launcher_bundle_digest,
        distribution_render_digest=staged.distribution_render_digest,
    )
