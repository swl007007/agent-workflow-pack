"""First-init local-state candidate construction without Runtime import cycles."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping

from agent_stack.core.api import VerifiedTrellisTaskLayout, canonical_json_bytes

from .errors import RendererFailure


_CONTRACT_FIELDS = {
    "release_id",
    "release_version",
    "workspace_schema",
    "approval_replay_schema",
    "task_outbox_schema",
    "trellis_task_layout_digest",
    "contract_digest",
}


def _failure(message: str) -> RendererFailure:
    return RendererFailure("AWP_RECONCILE_RECOVERY_REQUIRED", message)


def _uuid(value: str) -> str:
    try:
        normalized = str(uuid.UUID(value))
    except ValueError as error:
        raise _failure("first-init workspace identity is invalid") from error
    if normalized != value:
        raise _failure("first-init workspace identity is not canonical")
    return value


def _digest(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _failure("first-init local-state digest is invalid")
    return value


def build_first_init_local_state(
    manifest: Mapping[str, object],
    layout: VerifiedTrellisTaskLayout,
    workspace_instance_id: str,
    expected_replay_digest: str,
) -> tuple[dict[str, object], dict[str, object]]:
    contract = manifest.get("local_state_contract")
    if not isinstance(contract, Mapping) or set(contract) != _CONTRACT_FIELDS:
        raise _failure("first-init local-state contract is invalid")
    projection = dict(contract)
    claimed_contract_digest = projection.pop("contract_digest", None)
    if claimed_contract_digest != hashlib.sha256(
        canonical_json_bytes(projection)
    ).hexdigest():
        raise _failure("first-init local-state contract digest is stale")
    if contract.get("trellis_task_layout_digest") != layout.layout_digest:
        raise _failure("first-init Trellis layout differs from local-state contract")
    project_id = _uuid(str(manifest.get("project_id")))
    workspace_id = _uuid(workspace_instance_id)
    if (
        manifest.get("release_id") != contract.get("release_id")
        or manifest.get("pack_version") != contract.get("release_version")
    ):
        raise _failure("first-init Manifest differs from local-state contract")
    workspace = {
        "schema_id": "agent-workflow.workspace-local",
        "schema_version": 1,
        "project_id": project_id,
        "workspace_instance_id": workspace_id,
        "local_state_release_id": contract["release_id"],
        "local_state_release_version": contract["release_version"],
        "local_state_release_manifest_digest": manifest["release_manifest_digest"],
        "local_state_contract_digest": contract["contract_digest"],
        "trellis_task_layout": {
            "layout_digest": layout.layout_digest,
            **dict(layout.normalized),
        },
        "local_state_schemas": {
            "workspace": contract["workspace_schema"],
            "approval_replay": contract["approval_replay_schema"],
            "task_outbox": contract["task_outbox_schema"],
        },
    }
    replay = {
        "schema_id": "agent-workflow.approval-replay",
        "schema_version": 1,
        "project_id": project_id,
        "workspace_instance_id": workspace_id,
        "entries": {},
    }
    if hashlib.sha256(canonical_json_bytes(replay)).hexdigest() != _digest(
        expected_replay_digest
    ):
        raise _failure("first-init empty replay candidate digest changed")
    return workspace, replay
