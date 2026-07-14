from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

from agent_stack.core.api import SchemaCatalog
from agent_stack.release.compatibility import (
    LocalStateContract,
    RuntimeJournalReference,
    classify_compatibility,
    select_candidate_runtime,
)
from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.identity import ReleaseIdentity
from agent_stack.release.manifest import VerifiedRelease


TRUST = "a" * 64
SOURCE_CONTRACT = "b" * 64
TARGET_CONTRACT = "c" * 64
SOURCE_LAYOUT = "d" * 64
TARGET_LAYOUT = "e" * 64
ROOT = Path(__file__).resolve().parents[3]


def bundles(seed: int) -> dict[str, str]:
    values = "abcdef0123456789"
    result = {
        field: values[(seed + index) % len(values)] * 64
        for index, field in enumerate(
            (
                "trust_policy",
                "workflow_lock",
                "artifact",
                "schema",
                "migration",
                "compatibility",
                "launcher",
            )
        )
    }
    result["trust_policy"] = TRUST
    return result


def release(
    version: str,
    *,
    bundle_seed: int,
    compatibility: dict[str, object] | None = None,
) -> VerifiedRelease:
    identity = ReleaseIdentity(
        "github.com/pinned-owner/agent-workflow-pack",
        "agent-workflow-pack",
        version,
    )
    return VerifiedRelease(
        identity=identity,
        manifest_digest=str(bundle_seed) * 64,
        source_commit=str(bundle_seed) * 40,
        bundles=MappingProxyType(bundles(bundle_seed)),
        assets=MappingProxyType({}),
        immutable_release=True,
        compatibility=compatibility,
    )


def edge(source: VerifiedRelease, target: VerifiedRelease) -> dict[str, object]:
    target_bundles = {
        field: value for field, value in target.bundles.items() if field != "compatibility"
    }
    return {
        "from_release_id": source.identity.release_id,
        "to_release_id": target.identity.release_id,
        "from_version": source.identity.version,
        "to_version": target.identity.version,
        "trust_policy_digest": TRUST,
        "target_bundles": target_bundles,
        "schema_transitions": {
            field: {"from": 1, "to": 1}
            for field in (
                "manifest",
                "workflow_lock",
                "integration",
                "task_transaction",
                "workspace",
                "approval_replay",
                "task_outbox",
            )
        },
        "local_state_contracts": {"from": SOURCE_CONTRACT, "to": TARGET_CONTRACT},
        "trellis_task_layouts": {"from": SOURCE_LAYOUT, "to": TARGET_LAYOUT},
        "migrations": [
            {"migration_id": "local-state-v1", "migration_digest": "f" * 64}
        ],
    }


def bundle(owner: VerifiedRelease, *edges: dict[str, object]) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.release-compatibility",
        "schema_version": 1,
        "release_id": owner.identity.release_id,
        "edges": list(edges),
    }


def local_contract() -> LocalStateContract:
    return LocalStateContract(
        contract_digest=SOURCE_CONTRACT,
        trellis_task_layout_digest=SOURCE_LAYOUT,
        schema_versions={
            field: 1
            for field in (
                "manifest",
                "workflow_lock",
                "integration",
                "task_transaction",
                "workspace",
                "approval_replay",
                "task_outbox",
            )
        },
    )


def test_candidate_owned_forward_edge_is_migration_required() -> None:
    current = release("0.1.0", bundle_seed=1)
    candidate = release("0.2.0", bundle_seed=2)
    candidate = replace(candidate, compatibility=bundle(candidate, edge(current, candidate)))

    result = classify_compatibility(current, candidate, local_contract())

    assert result.relationship == "migration-required"
    assert result.edge_owner == "target"
    assert result.target_local_state_contract_digest == TARGET_CONTRACT


def test_current_owned_edge_authorizes_supported_rollback() -> None:
    current = release("0.2.0", bundle_seed=2)
    target = release("0.1.0", bundle_seed=1)
    current = replace(current, compatibility=bundle(current, edge(current, target)))

    result = classify_compatibility(current, target, local_contract())

    assert result.relationship == "migration-required"
    assert result.edge_owner == "current"


def test_reverse_only_is_ahead_and_no_direction_is_diverged() -> None:
    source = release("0.2.0", bundle_seed=2)
    target = release("0.1.0", bundle_seed=1)
    source = replace(source, compatibility=bundle(source, edge(target, source)))
    ahead = classify_compatibility(source, target, local_contract())
    assert ahead.relationship == "ahead"

    source = replace(source, compatibility=bundle(source))
    target = replace(target, compatibility=bundle(target))
    diverged = classify_compatibility(source, target, local_contract())
    assert diverged.relationship == "diverged"


def test_missing_compatibility_evidence_is_distinct() -> None:
    result = classify_compatibility(
        release("0.1.0", bundle_seed=1),
        release("0.2.0", bundle_seed=2),
        local_contract(),
    )
    assert result.relationship == "missing"


@pytest.mark.parametrize(
    "forbidden",
    [
        {"wheel_url": "https://attacker.invalid/wheel"},
        {"wheel_sha256": "1" * 64},
        {"source_commit": "1" * 40},
        {"compatibility_bundle_digest": "1" * 64},
        {"retained_runtime": {}},
        {"resume_compatibility": True},
    ],
)
def test_authenticated_edge_rejects_forbidden_authority_fields(
    forbidden: dict[str, object],
) -> None:
    current = release("0.1.0", bundle_seed=1)
    target = release("0.2.0", bundle_seed=2)
    invalid_edge = {**edge(current, target), **forbidden}
    target = replace(target, compatibility=bundle(target, invalid_edge))

    with pytest.raises(LifecycleFailure) as captured:
        classify_compatibility(current, target, local_contract())
    assert captured.value.code == "AWP_RELEASE_COMPATIBILITY_INVALID"
    assert captured.value.exit_code == 30


def test_target_bundle_or_source_contract_mismatch_fails_closed() -> None:
    current = release("0.1.0", bundle_seed=1)
    target = release("0.2.0", bundle_seed=2)
    invalid = edge(current, target)
    invalid["target_bundles"] = {**invalid["target_bundles"], "schema": "0" * 64}
    target = replace(target, compatibility=bundle(target, invalid))
    with pytest.raises(LifecycleFailure, match="AWP_RELEASE_COMPATIBILITY_INVALID"):
        classify_compatibility(current, target, local_contract())

    target = release("0.2.0", bundle_seed=2)
    target = replace(target, compatibility=bundle(target, edge(current, target)))
    wrong_local = replace(local_contract(), contract_digest="0" * 64)
    with pytest.raises(LifecycleFailure, match="AWP_RELEASE_COMPATIBILITY_INVALID"):
        classify_compatibility(current, target, wrong_local)


def test_runtime_selection_accepts_only_exact_committed_or_candidate_reference() -> None:
    committed = release("0.1.0", bundle_seed=1)
    candidate = release("0.2.0", bundle_seed=2)
    committed_ref = RuntimeJournalReference(
        runtime_role="committed",
        release_id=committed.identity.release_id,
        release_manifest_digest=committed.manifest_digest,
    )
    candidate_ref = RuntimeJournalReference(
        runtime_role="candidate",
        release_id=candidate.identity.release_id,
        release_manifest_digest=candidate.manifest_digest,
    )

    assert select_candidate_runtime(committed, candidate, committed_ref) is committed
    assert select_candidate_runtime(committed, candidate, candidate_ref) is candidate

    with pytest.raises(LifecycleFailure, match="AWP_RELEASE_RUNTIME_NOT_ALLOWED"):
        select_candidate_runtime(
            committed,
            candidate,
            replace(candidate_ref, release_manifest_digest="f" * 64),
        )


def test_runtime_journal_reference_has_no_url_hash_or_trust_override() -> None:
    reference = RuntimeJournalReference(
        runtime_role="committed",
        release_id="a" * 64,
        release_manifest_digest="b" * 64,
    )
    assert set(reference.to_document()) == {
        "runtime_role",
        "release_id",
        "release_manifest_digest",
    }


def test_packaged_compatibility_bundle_satisfies_the_closed_schema() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    parsed = SchemaCatalog.parse_yaml(
        (ROOT / "compatibility/releases.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(parsed, dict)
    catalog.load_and_validate(parsed)
