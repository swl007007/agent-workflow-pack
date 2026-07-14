from __future__ import annotations

import hashlib

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


def test_recorded_launcher_descriptor_preimage_candidate_mixes_are_recoverable() -> None:
    from agent_stack.runtime.authority import (
        RuntimeAuthorityInputs,
        RuntimeJournalEvidence,
        verify_runtime_authority,
    )

    committed = _release("a", "0.1.0")
    candidate = _release("c", "0.1.1")
    old_launcher = b"#!/bin/sh\n# old\n"
    new_launcher = b"#!/bin/sh\n# new\n"
    old_contract, old_control = _launcher(committed, old_launcher)
    new_contract, new_control = _launcher(candidate, new_launcher)
    old_descriptor = canonical_json_bytes(old_control)
    new_descriptor = canonical_json_bytes(new_control)
    transaction_id = "33333333-3333-4333-8333-333333333333"
    transitions = {
        ".agent-workflow/bin/agent-stack": (
            hashlib.sha256(old_launcher).hexdigest(),
            hashlib.sha256(new_launcher).hexdigest(),
        ),
        ".agent-workflow/runtime-control.json": (
            hashlib.sha256(old_descriptor).hexdigest(),
            hashlib.sha256(new_descriptor).hexdigest(),
        ),
    }

    for packaged, contract, launcher, descriptor, role in (
        (candidate, new_contract, new_launcher, old_descriptor, "candidate"),
        (committed, old_contract, old_launcher, new_descriptor, "committed"),
    ):
        journal = RuntimeJournalEvidence(
            transaction_id=transaction_id,
            journal_kind="lifecycle",
            phase="applying",
            recovery_runtime=RuntimeJournalReference(
                role, packaged.identity.release_id, packaged.manifest_digest
            ),
            file_transitions=transitions,
        )
        verified = verify_runtime_authority(
            RuntimeAuthorityInputs(
                packaged_release=packaged,
                committed_release=committed,
                candidate_release=candidate,
                committed_manifest=_manifest(committed),
                candidate_manifest=_manifest(candidate),
                workflow_lock_digest="8" * 64,
                launcher_contract=contract,
                launcher_bytes=launcher,
                runtime_control_bytes=descriptor,
                journal=journal,
                maintenance_marker=None,
                command="recover",
                recovery_transaction_id=transaction_id,
            )
        )
        assert verified.runtime_role == role


def test_unrecorded_third_launcher_state_fails_before_recovery_dispatch() -> None:
    from agent_stack.runtime.authority import (
        RuntimeAuthorityInputs,
        RuntimeJournalEvidence,
        verify_runtime_authority,
    )
    from agent_stack.runtime.errors import RuntimeFailure

    committed = _release("a", "0.1.0")
    candidate = _release("c", "0.1.1")
    old_launcher = b"#!/bin/sh\n# old\n"
    new_launcher = b"#!/bin/sh\n# new\n"
    third_launcher = b"#!/bin/sh\n# third\n"
    new_contract, new_control = _launcher(candidate, new_launcher)
    descriptor = canonical_json_bytes(new_control)
    transaction_id = "33333333-3333-4333-8333-333333333333"
    journal = RuntimeJournalEvidence(
        transaction_id=transaction_id,
        journal_kind="lifecycle",
        phase="applying",
        recovery_runtime=RuntimeJournalReference(
            "candidate", candidate.identity.release_id, candidate.manifest_digest
        ),
        file_transitions={
            ".agent-workflow/bin/agent-stack": (
                hashlib.sha256(old_launcher).hexdigest(),
                hashlib.sha256(new_launcher).hexdigest(),
            ),
            ".agent-workflow/runtime-control.json": (
                hashlib.sha256(descriptor).hexdigest(),
                hashlib.sha256(descriptor).hexdigest(),
            ),
        },
    )

    with pytest.raises(RuntimeFailure, match="AWP_RUNTIME_BINDING_MISMATCH"):
        verify_runtime_authority(
            RuntimeAuthorityInputs(
                packaged_release=candidate,
                committed_release=committed,
                candidate_release=candidate,
                committed_manifest=_manifest(committed),
                candidate_manifest=_manifest(candidate),
                workflow_lock_digest="8" * 64,
                launcher_contract=new_contract,
                launcher_bytes=third_launcher,
                runtime_control_bytes=descriptor,
                journal=journal,
                maintenance_marker=None,
                command="recover",
                recovery_transaction_id=transaction_id,
            )
        )


def test_old_task_journal_after_pull_cannot_authorize_old_runtime() -> None:
    from agent_stack.runtime.authority import RuntimeJournalEvidence, select_recovery_runtime
    from agent_stack.runtime.errors import RuntimeFailure

    old = _release("a", "0.1.0")
    current = _release("c", "0.1.1")
    journal = RuntimeJournalEvidence(
        transaction_id="33333333-3333-4333-8333-333333333333",
        journal_kind="task",
        phase="planned",
        recovery_runtime=RuntimeJournalReference(
            "committed", old.identity.release_id, old.manifest_digest
        ),
        file_transitions={},
    )

    with pytest.raises(RuntimeFailure, match="AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED"):
        select_recovery_runtime(current, None, journal)
