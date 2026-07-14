"""Post-wheel validation of the Reconciler-owned maintenance marker."""

from __future__ import annotations

from collections.abc import Mapping

from .errors import RuntimeFailure


_MARKER_FIELDS = {
    "schema_id",
    "schema_version",
    "transaction_id",
    "journal_binding_digest",
    "plan_digest",
    "task_quiescence_digest",
    "candidate_manifest_generation",
}


def validate_maintenance_marker(
    marker: Mapping[str, object], journal: object
) -> None:
    """Require the marker to bind the exact immutable transaction evidence."""

    if set(marker) != _MARKER_FIELDS:
        raise RuntimeFailure("AWP_RUNTIME_BINDING_MISMATCH", "maintenance fields are not closed")
    expected = {
        "schema_id": "agent-workflow.maintenance-marker",
        "schema_version": 1,
        "transaction_id": getattr(journal, "transaction_id", None),
        "journal_binding_digest": getattr(journal, "journal_binding_digest", None),
        "plan_digest": getattr(journal, "plan_digest", None),
        "task_quiescence_digest": getattr(journal, "task_quiescence_digest", None),
        "candidate_manifest_generation": getattr(
            journal, "candidate_manifest_generation", None
        ),
    }
    if dict(marker) != expected:
        raise RuntimeFailure(
            "AWP_RUNTIME_BINDING_MISMATCH",
            "maintenance marker does not bind the unfinished transaction",
        )
