"""Immutable maintenance-marker binding and exact cleanup."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from agent_stack.core.api import SavedPlanEnvelope, canonical_json_bytes

from .errors import RendererFailure


def build_maintenance_marker(envelope: SavedPlanEnvelope) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.maintenance-marker",
        "schema_version": 1,
        "transaction_id": envelope.plan_core["transaction_id"],
        "journal_binding_digest": envelope.journal_binding_digest,
        "plan_digest": envelope.plan_digest,
        "task_quiescence_digest": envelope.plan_core["task_quiescence_digest"],
        "candidate_manifest_generation": envelope.plan_core[
            "candidate_manifest_generation"
        ],
    }


def maintenance_path(root: Path) -> Path:
    return root / ".agent-workflow" / "maintenance.json"


def write_maintenance(root: Path, marker: Mapping[str, object]) -> Path:
    path = maintenance_path(root)
    if path.exists() or path.is_symlink():
        raise RendererFailure("AWP_MAINTENANCE_CORRUPT", "maintenance marker already exists")
    descriptor, raw_temporary = tempfile.mkstemp(prefix=".maintenance.", dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(canonical_json_bytes(marker))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()
    return path


def remove_maintenance(root: Path, marker: Mapping[str, object]) -> None:
    path = maintenance_path(root)
    if path.is_symlink() or not path.is_file():
        raise RendererFailure("AWP_MAINTENANCE_CORRUPT", "maintenance marker is missing")
    if path.read_bytes() != canonical_json_bytes(marker):
        raise RendererFailure("AWP_MAINTENANCE_CORRUPT", "maintenance marker binding changed")
    path.unlink()
