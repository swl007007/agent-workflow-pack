"""Candidate Manifest bytes and Manifest-last compare-and-swap."""

from __future__ import annotations

from pathlib import Path

from agent_stack.core.api import CANONICAL_NULL, SavedPlanEnvelope, canonical_json_bytes

from .cas import compare_and_swap
from .models import FileState
from .plan import render_candidate_manifest


def manifest_precondition(envelope: SavedPlanEnvelope) -> FileState:
    if envelope.operation == "init":
        return FileState(
            ".agent-workflow/manifest.json",
            False,
            "absent",
            CANONICAL_NULL,
            CANONICAL_NULL,
            True,
        )
    return FileState(
        ".agent-workflow/manifest.json",
        True,
        "regular",
        str(envelope.plan_core["manifest_digest"]),
        "0644",
        True,
    )


def apply_candidate_manifest(root: Path, envelope: SavedPlanEnvelope) -> FileState:
    candidate_manifest = render_candidate_manifest(envelope)
    candidate_bytes = canonical_json_bytes(candidate_manifest)
    candidate = FileState(
        ".agent-workflow/manifest.json",
        True,
        "regular",
        envelope.candidate_manifest_digest,
        "0644",
        True,
    )
    return compare_and_swap(
        root,
        manifest_precondition(envelope),
        candidate,
        candidate_bytes,
    )
