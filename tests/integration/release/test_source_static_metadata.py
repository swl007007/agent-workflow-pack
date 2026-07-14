from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from agent_stack.core.api import canonical_json_bytes
from agent_stack.release.compatibility import inspect_source_static_metadata
from agent_stack.release.errors import LifecycleFailure
from tests.unit.release.test_compatibility import (
    SOURCE_CONTRACT,
    SOURCE_LAYOUT,
    bundle,
    local_contract,
    release,
)


def _archive(tmp_path: Path) -> tuple[Path, str]:
    source = release("0.1.0", bundle_seed=1)
    metadata = {
        "schema_id": "agent-workflow.release-static-metadata",
        "schema_version": 1,
        "release_identity": source.identity.to_document(),
        "local_state_contract": local_contract().to_document(),
        "compatibility": bundle(source),
    }
    archive = tmp_path / "source.whl"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "agent_workflow_pack/release-static.json", canonical_json_bytes(metadata)
        )
        output.writestr(
            "agent_workflow_pack/__init__.py",
            "raise RuntimeError('source code must never execute')\n",
        )
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_static_source_metadata_is_read_without_import_or_execution(tmp_path: Path) -> None:
    archive, archive_digest = _archive(tmp_path)

    metadata = inspect_source_static_metadata(archive, archive_digest)

    assert metadata.identity.version == "0.1.0"
    assert metadata.local_state_contract.contract_digest == SOURCE_CONTRACT
    assert metadata.local_state_contract.trellis_task_layout_digest == SOURCE_LAYOUT


def test_complete_archive_hash_precedes_zip_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, _ = _archive(tmp_path)

    def parser_must_not_run(*args: object, **kwargs: object) -> object:
        raise AssertionError("zip parser ran before the complete archive hash matched")

    monkeypatch.setattr(zipfile, "ZipFile", parser_must_not_run)
    with pytest.raises(LifecycleFailure, match="AWP_RELEASE_SOURCE_METADATA_INVALID"):
        inspect_source_static_metadata(archive, "f" * 64)


def test_invalid_authenticated_static_schema_is_supply_chain_failure(tmp_path: Path) -> None:
    archive, _ = _archive(tmp_path)
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "agent_workflow_pack/release-static.json",
            canonical_json_bytes(
                {
                    "schema_id": "agent-workflow.release-static-metadata",
                    "schema_version": 1,
                    "unknown": True,
                }
            ),
        )
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(LifecycleFailure) as captured:
        inspect_source_static_metadata(archive, digest)
    assert captured.value.code == "AWP_RELEASE_SOURCE_METADATA_INVALID"
    assert captured.value.exit_code == 30
