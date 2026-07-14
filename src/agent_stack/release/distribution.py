"""Directed upgrade/rollback composition over frozen subsystem ports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from agent_stack.core.api import TaskSnapshotAndFindings

from .compatibility import (
    CompatibilityResult,
    LocalStateContract,
    RuntimeJournalReference,
    select_candidate_runtime,
)
from .errors import LifecycleFailure
from .manifest import ReleaseLocator, VerifiedRelease


@dataclass(frozen=True)
class UpgradeRequest:
    installed_release: VerifiedRelease
    running_release: VerifiedRelease
    local_state_contract: LocalStateContract
    target_version: str | None = None


@dataclass(frozen=True)
class UpgradeResult:
    transaction_id: str | None
    target_release_id: str
    recovery_runtime: RuntimeJournalReference
    committed: bool
    no_op: bool

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.upgrade-result",
            "schema_version": 1,
            "transaction_id": self.transaction_id,
            "target_release_id": self.target_release_id,
            "recovery_runtime": self.recovery_runtime.to_document(),
            "committed": self.committed,
            "no_op": self.no_op,
        }


@dataclass(frozen=True)
class UpgradePorts:
    locate_exact_release: Callable[[str], ReleaseLocator]
    verify_candidate_release: Callable[[ReleaseLocator], VerifiedRelease]
    acquire_candidate_wheel: Callable[[VerifiedRelease], object]
    inspect_candidate_static: Callable[[object, VerifiedRelease], VerifiedRelease]
    classify_compatibility: Callable[
        [VerifiedRelease, VerifiedRelease, LocalStateContract], CompatibilityResult
    ]
    resolve_candidate: Callable[[VerifiedRelease, CompatibilityResult], object]
    scan_task_quiescence: Callable[[object], TaskSnapshotAndFindings]
    assert_task_gate: Callable[[object, TaskSnapshotAndFindings], None]
    plan_reconcile: Callable[
        [object, TaskSnapshotAndFindings, CompatibilityResult, RuntimeJournalReference],
        object,
    ]
    approve_plan: Callable[[object], Mapping[str, object] | None]
    apply_plan: Callable[
        [object, Mapping[str, object], Callable[[], TaskSnapshotAndFindings]],
        Mapping[str, object],
    ]


@dataclass(frozen=True)
class UpgradeRecoveryRequest:
    transaction_id: str
    action: str
    committed_release: VerifiedRelease
    running_release: VerifiedRelease


@dataclass(frozen=True)
class UpgradeRecoveryPorts:
    load_runtime_reference: Callable[[str], RuntimeJournalReference]
    load_verified_candidate: Callable[
        [RuntimeJournalReference], VerifiedRelease | None
    ]
    recover_transaction: Callable[
        [str, str, VerifiedRelease], Mapping[str, object]
    ]


def _failure(code: str, message: str, *, exit_code: int, **details: object) -> LifecycleFailure:
    return LifecycleFailure(code, message, exit_code=exit_code, details=details)


def _locator(request: UpgradeRequest, ports: UpgradePorts) -> ReleaseLocator:
    if request.target_version is None:
        return ReleaseLocator(
            version=request.running_release.identity.version,
            release_manifest_digest=request.running_release.manifest_digest,
        )
    return ports.locate_exact_release(request.target_version)


def _same_verified_claims(before: VerifiedRelease, after: VerifiedRelease) -> bool:
    return (
        before.identity == after.identity
        and before.manifest_digest == after.manifest_digest
        and before.source_commit == after.source_commit
        and dict(before.bundles) == dict(after.bundles)
        and {key: dict(value) for key, value in before.assets.items()}
        == {key: dict(value) for key, value in after.assets.items()}
        and before.immutable_release == after.immutable_release
    )


def _recovery_runtime(
    request: UpgradeRequest,
    candidate: VerifiedRelease,
    compatibility: CompatibilityResult,
) -> RuntimeJournalReference:
    if compatibility.edge_owner == "target":
        selected = candidate
        role = "candidate"
    elif compatibility.edge_owner == "current":
        selected = request.installed_release
        role = "committed"
    else:
        raise _failure(
            "AWP_RELEASE_TARGET_NOT_REACHABLE",
            "target lacks one exact directed compatibility edge",
            exit_code=30,
            relationship=compatibility.relationship,
        )
    if request.running_release.identity != selected.identity or (
        request.running_release.manifest_digest != selected.manifest_digest
    ):
        raise _failure(
            "AWP_RELEASE_RUNTIME_NOT_ALLOWED",
            "the running CLI is not the directed edge owner",
            exit_code=30,
            edge_owner=compatibility.edge_owner,
        )
    return RuntimeJournalReference(
        runtime_role=role,
        release_id=selected.identity.release_id,
        release_manifest_digest=selected.manifest_digest,
    )


def orchestrate_upgrade(request: UpgradeRequest, ports: UpgradePorts) -> UpgradeResult:
    """Compose one exact upgrade or supported rollback without owning domain policy."""

    locator = _locator(request, ports)
    verified = ports.verify_candidate_release(locator)
    if verified.identity.version != locator.version or (
        verified.manifest_digest != locator.release_manifest_digest
    ):
        raise _failure(
            "AWP_RELEASE_MANIFEST_INVALID",
            "verified candidate does not match the exact locator",
            exit_code=30,
        )
    artifact = ports.acquire_candidate_wheel(verified)
    candidate = ports.inspect_candidate_static(artifact, verified)
    if not _same_verified_claims(verified, candidate):
        raise _failure(
            "AWP_RELEASE_SOURCE_METADATA_INVALID",
            "static inspection changed verified candidate claims",
            exit_code=30,
        )
    compatibility = ports.classify_compatibility(
        request.installed_release, candidate, request.local_state_contract
    )
    if compatibility.relationship == "equal":
        reference = RuntimeJournalReference(
            runtime_role="committed",
            release_id=request.installed_release.identity.release_id,
            release_manifest_digest=request.installed_release.manifest_digest,
        )
        return UpgradeResult(None, candidate.identity.release_id, reference, False, True)
    if compatibility.relationship != "migration-required":
        raise _failure(
            "AWP_RELEASE_TARGET_NOT_REACHABLE",
            "target is not reachable by an exact directed compatibility edge",
            exit_code=30,
            relationship=compatibility.relationship,
        )
    recovery_runtime = _recovery_runtime(request, candidate, compatibility)
    resolved = ports.resolve_candidate(candidate, compatibility)
    snapshot = ports.scan_task_quiescence(resolved)
    ports.assert_task_gate(resolved, snapshot)
    saved_plan = ports.plan_reconcile(
        resolved, snapshot, compatibility, recovery_runtime
    )
    approval = ports.approve_plan(saved_plan)
    if approval is None:
        raise _failure(
            "AWP_UPGRADE_APPROVAL_REQUIRED",
            "upgrade requires explicit approval of the exact saved plan",
            exit_code=22,
        )
    applied = ports.apply_plan(
        saved_plan,
        approval,
        lambda: ports.scan_task_quiescence(resolved),
    )
    transaction_id = applied.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id:
        raise _failure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "Reconciler result lacks its transaction identity",
            exit_code=21,
        )
    return UpgradeResult(
        transaction_id=transaction_id,
        target_release_id=candidate.identity.release_id,
        recovery_runtime=recovery_runtime,
        committed=applied.get("committed") is True,
        no_op=applied.get("no_op") is True,
    )


def recover_upgrade(
    request: UpgradeRecoveryRequest, ports: UpgradeRecoveryPorts
) -> Mapping[str, object]:
    """Recover only with the runtime identity already authorized by the journal."""

    if request.action not in {"resume", "rollback"}:
        raise _failure(
            "AWP_RECONCILE_RECOVERY_REQUIRED",
            "recovery action must be explicit",
            exit_code=21,
        )
    reference = ports.load_runtime_reference(request.transaction_id)
    candidate = (
        ports.load_verified_candidate(reference)
        if reference.runtime_role == "candidate"
        else None
    )
    selected = select_candidate_runtime(
        request.committed_release, candidate, reference
    )
    if request.running_release.identity != selected.identity or (
        request.running_release.manifest_digest != selected.manifest_digest
    ):
        raise _failure(
            "AWP_RELEASE_RUNTIME_NOT_ALLOWED",
            "recovery is not running under the journal-selected runtime",
            exit_code=30,
        )
    return ports.recover_transaction(
        request.transaction_id, request.action, selected
    )


__all__ = [
    "UpgradePorts",
    "UpgradeRecoveryPorts",
    "UpgradeRecoveryRequest",
    "UpgradeRequest",
    "UpgradeResult",
    "orchestrate_upgrade",
    "recover_upgrade",
]
