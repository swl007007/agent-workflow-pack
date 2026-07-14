from __future__ import annotations

import pytest

from agent_stack.core.api import canonical_json_bytes
from agent_stack.release.compatibility import RuntimeJournalReference
from agent_stack.release.identity import ReleaseIdentity
from agent_stack.release.manifest import VerifiedRelease
from agent_stack.runtime.bootstrap import LauncherContract


def _release(character: str, version: str) -> VerifiedRelease:
    identity = ReleaseIdentity(
        "github.com/example/agent-workflow-pack", "agent-workflow-pack", version
    )
    return VerifiedRelease(
        identity=identity,
        manifest_digest=character * 64,
        source_commit=character * 40,
        bundles={
            name: value * 64
            for name, value in zip(
                (
                    "trust_policy",
                    "workflow_lock",
                    "artifact",
                    "schema",
                    "migration",
                    "compatibility",
                    "launcher",
                ),
                "1234567",
                strict=True,
            )
        },
        assets={
            "wheel": {
                "name": f"agent_workflow_pack-{version}-py3-none-any.whl",
                "url": "https://github.com/example/agent-workflow-pack/releases/download/"
                f"v{version}/agent_workflow_pack-{version}-py3-none-any.whl",
                "size": 100,
                "sha256": character * 64,
            },
            "sdist": {
                "name": f"agent_workflow_pack-{version}.tar.gz",
                "url": "https://github.com/example/agent-workflow-pack/releases/download/"
                f"v{version}/agent_workflow_pack-{version}.tar.gz",
                "size": 200,
                "sha256": "f" * 64,
            },
        },
        immutable_release=True,
    )


def _launcher(release: VerifiedRelease, payload: bytes) -> tuple[LauncherContract, dict[str, object]]:
    contract = LauncherContract(
        1,
        "runtime-launcher-v1",
        release.identity.release_id,
        release.manifest_digest,
        str(release.assets["wheel"]["url"]),
        str(release.assets["wheel"]["sha256"]),
    )
    return contract, contract.runtime_control(payload)


def _manifest(release: VerifiedRelease, lock_digest: str = "8" * 64) -> dict[str, object]:
    return {
        "schema_version": 1,
        "project_id": "11111111-1111-4111-8111-111111111111",
        "generation": 3,
        "pack_version": release.identity.version,
        "release_id": release.identity.release_id,
        "release_manifest_digest": release.manifest_digest,
        "release_trust_policy_id": "github-immutable-release-v1",
        "release_trust_policy_digest": release.bundles["trust_policy"],
        "profile": "default",
        "profile_digest": "9" * 64,
        "lock_digest": lock_digest,
        "artifact_bundle_digest": release.bundles["artifact"],
        "local_state_contract": {},
        "platforms": ["codex"],
        "last_transaction_id": "22222222-2222-4222-8222-222222222222",
        "last_transaction_binding_digest": "a" * 64,
        "previous_manifest_digest": "b" * 64,
        "files": [],
    }


def test_ordinary_runtime_requires_exact_package_manifest_descriptor_and_lock() -> None:
    from agent_stack.runtime.authority import RuntimeAuthorityInputs, verify_runtime_authority

    release = _release("a", "0.1.0")
    launcher_bytes = b"#!/bin/sh\n# committed launcher\n"
    contract, control = _launcher(release, launcher_bytes)

    verified = verify_runtime_authority(
        RuntimeAuthorityInputs(
            packaged_release=release,
            committed_release=release,
            candidate_release=None,
            committed_manifest=_manifest(release),
            candidate_manifest=None,
            workflow_lock_digest="8" * 64,
            launcher_contract=contract,
            launcher_bytes=launcher_bytes,
            runtime_control_bytes=canonical_json_bytes(control),
            journal=None,
            maintenance_marker=None,
            command="doctor",
            recovery_transaction_id=None,
        )
    )

    assert verified.runtime_role == "committed"
    assert verified.release.identity == release.identity
    assert verified.command == "doctor"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("release_id", "0" * 64),
        ("release_manifest_digest", "0" * 64),
        ("wheel_sha256", "0" * 64),
        ("render_digest", "0" * 64),
    ],
)
def test_descriptor_or_manifest_binding_mismatch_fails_closed(
    field: str, value: str
) -> None:
    from agent_stack.runtime.authority import RuntimeAuthorityInputs, verify_runtime_authority
    from agent_stack.runtime.errors import RuntimeFailure

    release = _release("a", "0.1.0")
    launcher_bytes = b"#!/bin/sh\n# committed launcher\n"
    contract, control = _launcher(release, launcher_bytes)
    control[field] = value

    with pytest.raises(RuntimeFailure, match="AWP_RUNTIME_BINDING_MISMATCH"):
        verify_runtime_authority(
            RuntimeAuthorityInputs(
                packaged_release=release,
                committed_release=release,
                candidate_release=None,
                committed_manifest=_manifest(release),
                candidate_manifest=None,
                workflow_lock_digest="8" * 64,
                launcher_contract=contract,
                launcher_bytes=launcher_bytes,
                runtime_control_bytes=canonical_json_bytes(control),
                journal=None,
                maintenance_marker=None,
                command="doctor",
                recovery_transaction_id=None,
            )
        )


def test_candidate_recovery_runtime_is_exactly_allowlisted() -> None:
    from agent_stack.runtime.authority import (
        RuntimeAuthorityInputs,
        RuntimeJournalEvidence,
        select_recovery_runtime,
        verify_runtime_authority,
    )
    from agent_stack.runtime.errors import RuntimeFailure

    committed = _release("a", "0.1.0")
    candidate = _release("c", "0.1.1")
    launcher_bytes = b"#!/bin/sh\n# candidate launcher\n"
    contract, control = _launcher(candidate, launcher_bytes)
    journal = RuntimeJournalEvidence(
        transaction_id="33333333-3333-4333-8333-333333333333",
        journal_kind="lifecycle",
        phase="applying",
        recovery_runtime=RuntimeJournalReference(
            "candidate", candidate.identity.release_id, candidate.manifest_digest
        ),
        file_transitions={},
    )

    assert select_recovery_runtime(committed, candidate, journal) == candidate
    verified = verify_runtime_authority(
        RuntimeAuthorityInputs(
            packaged_release=candidate,
            committed_release=committed,
            candidate_release=candidate,
            committed_manifest=_manifest(committed),
            candidate_manifest=_manifest(candidate),
            workflow_lock_digest="8" * 64,
            launcher_contract=contract,
            launcher_bytes=launcher_bytes,
            runtime_control_bytes=canonical_json_bytes(control),
            journal=journal,
            maintenance_marker=None,
            command="recover",
            recovery_transaction_id=journal.transaction_id,
        )
    )
    assert verified.runtime_role == "candidate"

    third = RuntimeJournalEvidence(
        transaction_id=journal.transaction_id,
        journal_kind="lifecycle",
        phase="applying",
        recovery_runtime=RuntimeJournalReference("candidate", "d" * 64, "e" * 64),
        file_transitions={},
    )
    with pytest.raises(RuntimeFailure, match="AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED"):
        select_recovery_runtime(committed, candidate, third)


def test_maintenance_blocks_ordinary_dispatch_and_requires_exact_recovery() -> None:
    from agent_stack.runtime.authority import (
        RuntimeAuthorityInputs,
        RuntimeJournalEvidence,
        verify_runtime_authority,
    )
    from agent_stack.runtime.errors import RuntimeFailure

    release = _release("a", "0.1.0")
    launcher_bytes = b"#!/bin/sh\n"
    contract, control = _launcher(release, launcher_bytes)
    transaction_id = "33333333-3333-4333-8333-333333333333"
    journal = RuntimeJournalEvidence(
        transaction_id=transaction_id,
        journal_kind="lifecycle",
        phase="applying",
        recovery_runtime=RuntimeJournalReference(
            "committed", release.identity.release_id, release.manifest_digest
        ),
        file_transitions={},
        journal_binding_digest="1" * 64,
        plan_digest="2" * 64,
        task_quiescence_digest="3" * 64,
        candidate_manifest_generation=4,
    )
    marker = {
        "schema_id": "agent-workflow.maintenance-marker",
        "schema_version": 1,
        "transaction_id": transaction_id,
        "journal_binding_digest": "1" * 64,
        "plan_digest": "2" * 64,
        "task_quiescence_digest": "3" * 64,
        "candidate_manifest_generation": 4,
    }
    common = dict(
        packaged_release=release,
        committed_release=release,
        candidate_release=None,
        committed_manifest=_manifest(release),
        candidate_manifest=None,
        workflow_lock_digest="8" * 64,
        launcher_contract=contract,
        launcher_bytes=launcher_bytes,
        runtime_control_bytes=canonical_json_bytes(control),
        journal=journal,
        maintenance_marker=marker,
    )

    with pytest.raises(RuntimeFailure, match="AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED"):
        verify_runtime_authority(
            RuntimeAuthorityInputs(
                **common, command="workspace register", recovery_transaction_id=None
            )
        )
    recovered = verify_runtime_authority(
        RuntimeAuthorityInputs(
            **common, command="recover", recovery_transaction_id=transaction_id
        )
    )
    assert recovered.recovery_transaction_id == transaction_id
