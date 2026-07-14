from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from types import MappingProxyType

import pytest

from agent_stack.core.api import TaskSnapshotAndFindings
from agent_stack.release.compatibility import (
    CompatibilityResult,
    LocalStateContract,
    classify_compatibility,
)
from agent_stack.release.distribution import UpgradePorts, UpgradeRequest, orchestrate_upgrade
from agent_stack.release.identity import ReleaseIdentity
from agent_stack.release.manifest import ReleaseLocator, VerifiedRelease
from agent_stack.runtime.errors import RuntimeFailure


DIGESTS = {
    "trust_policy": "1" * 64,
    "workflow_lock": "2" * 64,
    "artifact": "3" * 64,
    "schema": "4" * 64,
    "migration": "5" * 64,
    "compatibility": "6" * 64,
    "launcher": "7" * 64,
}


def local_contract() -> LocalStateContract:
    return LocalStateContract(
        contract_digest="8" * 64,
        trellis_task_layout_digest="9" * 64,
        schema_versions={
            "manifest": 1,
            "workflow_lock": 1,
            "integration": 1,
            "task_transaction": 1,
            "workspace": 1,
            "approval_replay": 1,
            "task_outbox": 1,
        },
    )


def release(version: str, marker: str, *, compatibility: Mapping[str, object] | None = None) -> VerifiedRelease:
    identity = ReleaseIdentity("github.com/example/agent-workflow-pack", "agent-workflow-pack", version)
    bundles = dict(DIGESTS)
    bundles["workflow_lock"] = marker * 64
    return VerifiedRelease(
        identity=identity,
        manifest_digest=marker * 64,
        source_commit=marker * 40,
        bundles=MappingProxyType(bundles),
        assets=MappingProxyType(
            {
                "wheel": MappingProxyType(
                    {
                        "name": f"agent_workflow_pack-{version}-py3-none-any.whl",
                        "url": f"https://github.com/example/releases/{version}/wheel.whl",
                        "size": 100,
                        "sha256": marker * 64,
                    }
                ),
                "sdist": MappingProxyType(
                    {
                        "name": f"agent_workflow_pack-{version}.tar.gz",
                        "url": f"https://github.com/example/releases/{version}/source.tar.gz",
                        "size": 200,
                        "sha256": ("f" if marker != "f" else "e") * 64,
                    }
                ),
            }
        ),
        immutable_release=True,
        compatibility=compatibility,
    )


def edge(source: VerifiedRelease, target: VerifiedRelease) -> dict[str, object]:
    contract = local_contract()
    return {
        "from_release_id": source.identity.release_id,
        "to_release_id": target.identity.release_id,
        "from_version": source.identity.version,
        "to_version": target.identity.version,
        "trust_policy_digest": DIGESTS["trust_policy"],
        "target_bundles": {
            key: target.bundles[key]
            for key in ("trust_policy", "workflow_lock", "artifact", "schema", "migration", "launcher")
        },
        "schema_transitions": {
            key: {"from": 1, "to": 1} for key in contract.schema_versions
        },
        "local_state_contracts": {
            "from": contract.contract_digest,
            "to": contract.contract_digest,
        },
        "trellis_task_layouts": {
            "from": contract.trellis_task_layout_digest,
            "to": contract.trellis_task_layout_digest,
        },
        "migrations": [],
    }


def with_edges(owner: VerifiedRelease, edges: list[dict[str, object]]) -> VerifiedRelease:
    return replace(
        owner,
        compatibility=MappingProxyType(
            {
                "schema_id": "agent-workflow.release-compatibility",
                "schema_version": 1,
                "release_id": owner.identity.release_id,
                "edges": edges,
            }
        ),
    )


def quiet() -> TaskSnapshotAndFindings:
    return TaskSnapshotAndFindings(snapshot={}, findings={}, task_quiescence_digest="a" * 64)


def ports(
    *,
    events: list[str],
    candidate: VerifiedRelease,
    locate: Callable[[str], ReleaseLocator] | None = None,
    gate: Callable[[object, TaskSnapshotAndFindings], None] | None = None,
) -> UpgradePorts:
    def verify(locator: ReleaseLocator) -> VerifiedRelease:
        events.append(f"verify-manifest:{locator.version}")
        return replace(candidate, compatibility=None)

    def acquire(verified: VerifiedRelease) -> object:
        events.append(f"acquire-wheel:{verified.identity.version}")
        return {"sha256": verified.assets["wheel"]["sha256"]}

    def inspect(artifact: object, verified: VerifiedRelease) -> VerifiedRelease:
        assert artifact == {"sha256": verified.assets["wheel"]["sha256"]}
        events.append(f"inspect-static:{verified.identity.version}")
        return candidate

    def resolve(
        verified: VerifiedRelease, compatibility: CompatibilityResult
    ) -> object:
        events.append(f"resolve:{verified.identity.version}:{compatibility.edge_owner}")
        return {"candidate": verified.identity.version}

    def scan(_: object) -> TaskSnapshotAndFindings:
        events.append("scan")
        return quiet()

    def check(resolved: object, snapshot: TaskSnapshotAndFindings) -> None:
        events.append("task-gate")
        if gate is not None:
            gate(resolved, snapshot)

    def plan(
        resolved: object,
        snapshot: TaskSnapshotAndFindings,
        compatibility: CompatibilityResult,
        recovery_runtime: object,
    ) -> object:
        events.append("plan")
        return {
            "resolved": resolved,
            "snapshot": snapshot.task_quiescence_digest,
            "edge_owner": compatibility.edge_owner,
            "recovery_runtime": recovery_runtime,
            "plan_digest": "b" * 64,
        }

    def approve(plan: object) -> Mapping[str, object]:
        events.append("approve")
        assert isinstance(plan, dict)
        return MappingProxyType({"plan_digest": plan["plan_digest"]})

    def apply(
        plan: object,
        approval: Mapping[str, object],
        scanner: Callable[[], TaskSnapshotAndFindings],
    ) -> Mapping[str, object]:
        events.append("apply-local-state")
        assert scanner().task_quiescence_digest == "a" * 64
        events.append("manifest-commit")
        return MappingProxyType({"transaction_id": "tx-1", "committed": True})

    return UpgradePorts(
        locate_exact_release=locate or (lambda version: (_ for _ in ()).throw(AssertionError(version))),
        verify_candidate_release=verify,
        acquire_candidate_wheel=acquire,
        inspect_candidate_static=inspect,
        classify_compatibility=classify_compatibility,
        resolve_candidate=resolve,
        scan_task_quiescence=scan,
        assert_task_gate=check,
        plan_reconcile=plan,
        approve_plan=approve,
        apply_plan=apply,
    )


def test_default_upgrade_targets_exact_running_release_and_preserves_owner_order() -> None:
    installed = release("0.1.0", "b")
    target_base = release("0.2.0", "c")
    target = with_edges(target_base, [edge(installed, target_base)])
    events: list[str] = []

    result = orchestrate_upgrade(
        UpgradeRequest(
            installed_release=installed,
            running_release=target,
            local_state_contract=local_contract(),
        ),
        ports(events=events, candidate=target),
    )

    assert result.committed is True
    assert result.target_release_id == target.identity.release_id
    assert result.recovery_runtime.runtime_role == "candidate"
    assert events == [
        "verify-manifest:0.2.0",
        "acquire-wheel:0.2.0",
        "inspect-static:0.2.0",
        "resolve:0.2.0:target",
        "scan",
        "task-gate",
        "plan",
        "approve",
        "apply-local-state",
        "scan",
        "manifest-commit",
    ]


def test_exact_to_uses_trust_policy_locator_and_never_latest_lookup() -> None:
    installed = release("0.1.0", "b")
    target_base = release("0.2.0", "c")
    target = with_edges(target_base, [edge(installed, target_base)])
    events: list[str] = []
    located: list[str] = []

    def locate(version: str) -> ReleaseLocator:
        located.append(version)
        return ReleaseLocator(version=version, release_manifest_digest=target.manifest_digest)

    orchestrate_upgrade(
        UpgradeRequest(
            installed_release=installed,
            running_release=target,
            local_state_contract=local_contract(),
            target_version="0.2.0",
        ),
        ports(events=events, candidate=target, locate=locate),
    )

    assert located == ["0.2.0"]
    assert "latest" not in repr(events).casefold()


def test_active_task_gate_blocks_before_plan_and_apply() -> None:
    installed = release("0.1.0", "b")
    target_base = release("0.2.0", "c")
    target = with_edges(target_base, [edge(installed, target_base)])
    events: list[str] = []

    def active(_: object, __: TaskSnapshotAndFindings) -> None:
        raise RuntimeFailure("AWP_WORKSPACE_ACTIVE_TASK_BLOCK", "active task blocks upgrade")

    with pytest.raises(RuntimeFailure, match="AWP_WORKSPACE_ACTIVE_TASK_BLOCK"):
        orchestrate_upgrade(
            UpgradeRequest(
                installed_release=installed,
                running_release=target,
                local_state_contract=local_contract(),
            ),
            ports(events=events, candidate=target, gate=active),
        )

    assert "plan" not in events
    assert "apply-local-state" not in events
