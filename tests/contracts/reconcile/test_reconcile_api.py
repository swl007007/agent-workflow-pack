from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from agent_stack.core.api import CoreFailure, SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]


def _file_state() -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.file-state",
        "schema_version": 1,
        "path": "generated/config.yaml",
        "exists": True,
        "file_type": "regular",
        "byte_hash": "a" * 64,
        "mode": "0644",
        "non_symlink": True,
        "managed_block_hash": "canonical-null",
    }


def _staged_file() -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.staged-file",
        "schema_version": 1,
        "path": "generated/config.yaml",
        "definition_id": "generated-config",
        "surface_id": "runtime-entry:generated-config",
        "ownership": "managed",
        "merge_strategy": "whole-file",
        "source_digest": "b" * 64,
        "render_digest": "c" * 64,
        "candidate_byte_hash": "a" * 64,
        "mode_policy": "exact",
        "candidate_mode": "0644",
        "validator_results": [],
    }


def test_reconcile_api_exports_frozen_callables_and_models() -> None:
    from agent_stack.reconcile import api
    from agent_stack.reconcile.models import FileState, LifecycleJournal, StagedFile

    assert callable(api.render)
    assert callable(api.plan_reconcile)
    assert callable(api.apply_plan)
    assert callable(api.recover_transaction)
    assert {FileState, LifecycleJournal, StagedFile} <= set(api.PUBLIC_MODELS)
    assert tuple(inspect.signature(api.render).parameters) == (
        "ir",
        "verified_provider_results",
    )


def test_reconcile_schemas_are_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    for schema_id in (
        "agent-workflow.file-state",
        "agent-workflow.staged-file",
        "agent-workflow.lifecycle-transaction",
    ):
        assert catalog.supported_versions(schema_id) == (1,)
    catalog.load_and_validate(_file_state())
    catalog.load_and_validate(_staged_file())
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**_file_state(), "target_path": "/tmp/escape"})


def test_file_state_binds_type_bytes_mode_and_non_symlink() -> None:
    from agent_stack.reconcile.models import FileState

    state = FileState.from_document(_file_state())
    assert state.path == "generated/config.yaml"
    assert state.byte_hash == "a" * 64
    assert state.mode == "0644"
    assert state.non_symlink is True
