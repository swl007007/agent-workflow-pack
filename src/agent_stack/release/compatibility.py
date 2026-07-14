"""Exact directed release compatibility and static source-metadata inspection."""

from __future__ import annotations

import hashlib
import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import SchemaCatalog, canonical_json_bytes

from .errors import LifecycleFailure
from .identity import ReleaseIdentity
from .manifest import VerifiedRelease


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_FIELDS = {
    "manifest",
    "workflow_lock",
    "integration",
    "task_transaction",
    "workspace",
    "approval_replay",
    "task_outbox",
}
_TARGET_BUNDLE_FIELDS = {
    "trust_policy",
    "workflow_lock",
    "artifact",
    "schema",
    "migration",
    "launcher",
}
_EDGE_FIELDS = {
    "from_release_id",
    "to_release_id",
    "from_version",
    "to_version",
    "trust_policy_digest",
    "target_bundles",
    "schema_transitions",
    "local_state_contracts",
    "trellis_task_layouts",
    "migrations",
}
_STATIC_MEMBER = "agent_workflow_pack/release-static.json"


def _compatibility_failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_RELEASE_COMPATIBILITY_INVALID", message, exit_code=30, details=details
    )


def _source_failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_RELEASE_SOURCE_METADATA_INVALID", message, exit_code=30, details=details
    )


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise _compatibility_failure("compatibility digest is invalid", field=field)
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _compatibility_failure("compatibility string is invalid", field=field)
    return value


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _compatibility_failure("compatibility object is invalid", field=field)
    return value


@dataclass(frozen=True)
class LocalStateContract:
    contract_digest: str
    trellis_task_layout_digest: str
    schema_versions: Mapping[str, int]

    def __post_init__(self) -> None:
        _sha256(self.contract_digest, "local_state_contract.contract_digest")
        _sha256(
            self.trellis_task_layout_digest,
            "local_state_contract.trellis_task_layout_digest",
        )
        if set(self.schema_versions) != _SCHEMA_FIELDS or not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in self.schema_versions.values()
        ):
            raise _compatibility_failure("local-state schema versions are invalid")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.local-state-contract",
            "schema_version": 1,
            "contract_digest": self.contract_digest,
            "trellis_task_layout_digest": self.trellis_task_layout_digest,
            "schema_versions": dict(sorted(self.schema_versions.items())),
        }


@dataclass(frozen=True)
class RuntimeJournalReference:
    runtime_role: str
    release_id: str
    release_manifest_digest: str

    def __post_init__(self) -> None:
        if self.runtime_role not in {"committed", "candidate"}:
            raise LifecycleFailure(
                "AWP_RELEASE_RUNTIME_NOT_ALLOWED",
                "journal runtime role is invalid",
                exit_code=30,
            )
        _sha256(self.release_id, "runtime_reference.release_id")
        _sha256(
            self.release_manifest_digest, "runtime_reference.release_manifest_digest"
        )

    def to_document(self) -> dict[str, object]:
        return {
            "runtime_role": self.runtime_role,
            "release_id": self.release_id,
            "release_manifest_digest": self.release_manifest_digest,
        }


@dataclass(frozen=True)
class CompatibilityResult:
    relationship: str
    edge_owner: str | None = None
    edge: Mapping[str, object] | None = None
    target_local_state_contract_digest: str | None = None
    target_trellis_task_layout_digest: str | None = None


@dataclass(frozen=True)
class StaticReleaseMetadata:
    identity: ReleaseIdentity
    local_state_contract: LocalStateContract
    compatibility: Mapping[str, object]


def _schema_transition(value: object, field: str) -> dict[str, int]:
    transition = _mapping(value, field)
    if set(transition) != {"from", "to"}:
        raise _compatibility_failure("schema transition fields are not closed", field=field)
    normalized: dict[str, int] = {}
    for side in ("from", "to"):
        version = transition.get(side)
        if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
            raise _compatibility_failure("schema transition version is invalid", field=field)
        normalized[side] = version
    return normalized


def _digest_pair(value: object, field: str) -> dict[str, str]:
    pair = _mapping(value, field)
    if set(pair) != {"from", "to"}:
        raise _compatibility_failure("digest transition fields are not closed", field=field)
    return {
        side: _sha256(pair.get(side), f"{field}.{side}") for side in ("from", "to")
    }


def _normalize_edge(value: object) -> dict[str, object]:
    edge = _mapping(value, "edge")
    if set(edge) != _EDGE_FIELDS:
        raise _compatibility_failure("compatibility edge fields are not closed")
    target_bundles = _mapping(edge.get("target_bundles"), "target_bundles")
    if set(target_bundles) != _TARGET_BUNDLE_FIELDS:
        raise _compatibility_failure("target bundle identities are not closed")
    normalized_bundles = {
        field: _sha256(target_bundles.get(field), f"target_bundles.{field}")
        for field in sorted(_TARGET_BUNDLE_FIELDS)
    }
    transitions = _mapping(edge.get("schema_transitions"), "schema_transitions")
    if set(transitions) != _SCHEMA_FIELDS:
        raise _compatibility_failure("schema transition domains are not closed")
    normalized_transitions = {
        field: _schema_transition(transitions.get(field), f"schema_transitions.{field}")
        for field in sorted(_SCHEMA_FIELDS)
    }
    local_contracts = _digest_pair(
        edge.get("local_state_contracts"), "local_state_contracts"
    )
    layouts = _digest_pair(edge.get("trellis_task_layouts"), "trellis_task_layouts")
    raw_migrations = edge.get("migrations")
    if not isinstance(raw_migrations, list):
        raise _compatibility_failure("compatibility migrations must be an array")
    migrations: list[dict[str, str]] = []
    migration_ids: set[str] = set()
    for raw in raw_migrations:
        migration = _mapping(raw, "migrations")
        if set(migration) != {"migration_id", "migration_digest"}:
            raise _compatibility_failure("migration fields are not closed")
        migration_id = _string(migration.get("migration_id"), "migration_id")
        if migration_id in migration_ids:
            raise _compatibility_failure("migration ID repeats", migration_id=migration_id)
        migration_ids.add(migration_id)
        migrations.append(
            {
                "migration_id": migration_id,
                "migration_digest": _sha256(
                    migration.get("migration_digest"), "migration_digest"
                ),
            }
        )
    changed = (
        local_contracts["from"] != local_contracts["to"]
        or layouts["from"] != layouts["to"]
        or any(value["from"] != value["to"] for value in normalized_transitions.values())
    )
    if changed and not migrations:
        raise _compatibility_failure("contract-changing edge has no exact migration")
    return {
        "from_release_id": _sha256(edge.get("from_release_id"), "from_release_id"),
        "to_release_id": _sha256(edge.get("to_release_id"), "to_release_id"),
        "from_version": _string(edge.get("from_version"), "from_version"),
        "to_version": _string(edge.get("to_version"), "to_version"),
        "trust_policy_digest": _sha256(
            edge.get("trust_policy_digest"), "trust_policy_digest"
        ),
        "target_bundles": normalized_bundles,
        "schema_transitions": normalized_transitions,
        "local_state_contracts": local_contracts,
        "trellis_task_layouts": layouts,
        "migrations": migrations,
    }


def _compatibility_edges(release: VerifiedRelease) -> list[dict[str, object]] | None:
    document = release.compatibility
    if document is None:
        return None
    if set(document) != {"schema_id", "schema_version", "release_id", "edges"}:
        raise _compatibility_failure("compatibility document fields are not closed")
    if (
        document.get("schema_id") != "agent-workflow.release-compatibility"
        or document.get("schema_version") != 1
        or document.get("release_id") != release.identity.release_id
    ):
        raise _compatibility_failure("compatibility document owner identity is invalid")
    raw_edges = document.get("edges")
    if not isinstance(raw_edges, list):
        raise _compatibility_failure("compatibility edges must be an array")
    normalized = [_normalize_edge(raw) for raw in raw_edges]
    identities = [
        (edge["from_release_id"], edge["to_release_id"]) for edge in normalized
    ]
    if len(identities) != len(set(identities)):
        raise _compatibility_failure("directed compatibility edge repeats")
    return normalized


def _matching(
    edges: Sequence[Mapping[str, object]] | None,
    source: VerifiedRelease,
    target: VerifiedRelease,
) -> list[Mapping[str, object]]:
    if edges is None:
        return []
    return [
        edge
        for edge in edges
        if edge.get("from_release_id") == source.identity.release_id
        and edge.get("to_release_id") == target.identity.release_id
        and edge.get("from_version") == source.identity.version
        and edge.get("to_version") == target.identity.version
    ]


def _validate_binding(
    edge: Mapping[str, object],
    source: VerifiedRelease,
    target: VerifiedRelease,
    local_state: LocalStateContract | None,
) -> None:
    target_bundles = cast(Mapping[str, str], edge["target_bundles"])
    actual_target = {
        field: target.bundles.get(field) for field in sorted(_TARGET_BUNDLE_FIELDS)
    }
    if dict(target_bundles) != actual_target:
        raise _compatibility_failure("edge target bundle identities do not match release")
    trust = edge.get("trust_policy_digest")
    if (
        trust != source.bundles.get("trust_policy")
        or trust != target.bundles.get("trust_policy")
        or trust != target_bundles.get("trust_policy")
    ):
        raise _compatibility_failure("ordinary edge changes the trust root")
    if local_state is None:
        return
    contracts = cast(Mapping[str, str], edge["local_state_contracts"])
    layouts = cast(Mapping[str, str], edge["trellis_task_layouts"])
    transitions = cast(Mapping[str, Mapping[str, int]], edge["schema_transitions"])
    if contracts["from"] != local_state.contract_digest:
        raise _compatibility_failure("source local-state contract does not match edge")
    if layouts["from"] != local_state.trellis_task_layout_digest:
        raise _compatibility_failure("source Trellis layout does not match edge")
    mismatches = sorted(
        field
        for field, version in local_state.schema_versions.items()
        if transitions[field]["from"] != version
    )
    if mismatches:
        raise _compatibility_failure(
            "source persistent schema versions do not match edge", fields=mismatches
        )


def classify_compatibility(
    current_release: VerifiedRelease,
    target_release: VerifiedRelease,
    local_state_contract: LocalStateContract,
) -> CompatibilityResult:
    if current_release.identity.release_id == target_release.identity.release_id:
        return CompatibilityResult("equal")
    current_edges = _compatibility_edges(current_release)
    target_edges = _compatibility_edges(target_release)
    forward = [
        *(('current', edge) for edge in _matching(current_edges, current_release, target_release)),
        *(('target', edge) for edge in _matching(target_edges, current_release, target_release)),
    ]
    if len(forward) > 1:
        raise _compatibility_failure("multiple owners claim the same directed edge")
    if forward:
        owner, selected = forward[0]
        _validate_binding(selected, current_release, target_release, local_state_contract)
        contracts = cast(Mapping[str, str], selected["local_state_contracts"])
        layouts = cast(Mapping[str, str], selected["trellis_task_layouts"])
        return CompatibilityResult(
            relationship="migration-required",
            edge_owner=owner,
            edge=MappingProxyType(dict(selected)),
            target_local_state_contract_digest=contracts["to"],
            target_trellis_task_layout_digest=layouts["to"],
        )
    reverse = [
        *_matching(current_edges, target_release, current_release),
        *_matching(target_edges, target_release, current_release),
    ]
    if len(reverse) > 1:
        raise _compatibility_failure("multiple owners claim the same reverse edge")
    if reverse:
        _validate_binding(reverse[0], target_release, current_release, None)
        return CompatibilityResult("ahead")
    if current_edges is None or target_edges is None:
        return CompatibilityResult("missing")
    return CompatibilityResult("diverged")


def select_candidate_runtime(
    committed_release: VerifiedRelease,
    candidate_release: VerifiedRelease | None,
    journal_reference: RuntimeJournalReference | None = None,
) -> VerifiedRelease:
    if journal_reference is None:
        return committed_release
    selected = (
        committed_release
        if journal_reference.runtime_role == "committed"
        else candidate_release
    )
    if (
        selected is None
        or journal_reference.release_id != selected.identity.release_id
        or journal_reference.release_manifest_digest != selected.manifest_digest
    ):
        raise LifecycleFailure(
            "AWP_RELEASE_RUNTIME_NOT_ALLOWED",
            "journal runtime is outside the committed/candidate allowlist",
            exit_code=30,
        )
    return selected


def _parse_static_json(body: bytes) -> dict[str, object]:
    try:
        parsed = SchemaCatalog.parse_json(body.decode("utf-8"))
    except Exception as error:
        raise _source_failure("static release metadata is invalid JSON") from error
    if not isinstance(parsed, dict) or canonical_json_bytes(parsed) != body:
        raise _source_failure("static release metadata is not canonical JSON")
    return cast(dict[str, object], parsed)


def _local_state_from_document(value: object) -> LocalStateContract:
    document = _mapping(value, "local_state_contract")
    if set(document) != {
        "schema_id",
        "schema_version",
        "contract_digest",
        "trellis_task_layout_digest",
        "schema_versions",
    }:
        raise _source_failure("static local-state contract fields are not closed")
    if (
        document.get("schema_id") != "agent-workflow.local-state-contract"
        or document.get("schema_version") != 1
    ):
        raise _source_failure("static local-state contract identity is invalid")
    versions = _mapping(document.get("schema_versions"), "schema_versions")
    if not all(isinstance(value, int) for value in versions.values()):
        raise _source_failure("static schema versions are invalid")
    return LocalStateContract(
        contract_digest=_sha256(document.get("contract_digest"), "contract_digest"),
        trellis_task_layout_digest=_sha256(
            document.get("trellis_task_layout_digest"), "trellis_task_layout_digest"
        ),
        schema_versions=cast(Mapping[str, int], versions),
    )


def _identity_from_document(value: object) -> ReleaseIdentity:
    document = _mapping(value, "release_identity")
    expected_fields = {
        "schema_id",
        "schema_version",
        "repository_id",
        "distribution_name",
        "version",
        "release_id",
    }
    if set(document) != expected_fields:
        raise _source_failure("static Release Identity fields are not closed")
    identity = ReleaseIdentity(
        _string(document.get("repository_id"), "repository_id"),
        _string(document.get("distribution_name"), "distribution_name"),
        _string(document.get("version"), "version"),
    )
    if (
        document.get("schema_id") != "agent-workflow.release-identity"
        or document.get("schema_version") != 1
        or document.get("release_id") != identity.release_id
    ):
        raise _source_failure("static Release Identity is invalid")
    return identity


def inspect_source_static_metadata(
    archive_path: Path, expected_archive_sha256: str
) -> StaticReleaseMetadata:
    if archive_path.is_symlink() or not archive_path.is_file():
        raise _source_failure("source distribution is not a regular file")
    _sha256(expected_archive_sha256, "expected_archive_sha256")
    try:
        with archive_path.open("rb") as stream:
            actual_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise _source_failure("source distribution cannot be read") from error
    if actual_digest != expected_archive_sha256:
        raise _source_failure("source distribution bytes do not match verified identity")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            matches = [name for name in archive.namelist() if name == _STATIC_MEMBER]
            if matches != [_STATIC_MEMBER]:
                raise _source_failure("source distribution static metadata is missing or repeats")
            info = archive.getinfo(_STATIC_MEMBER)
            if info.file_size > 1024 * 1024:
                raise _source_failure("source static metadata exceeds its size limit")
            body = archive.read(info)
    except LifecycleFailure:
        raise
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise _source_failure("source distribution is not a valid bounded wheel archive") from error
    document = _parse_static_json(body)
    if set(document) != {
        "schema_id",
        "schema_version",
        "release_identity",
        "local_state_contract",
        "compatibility",
    }:
        raise _source_failure("static release metadata fields are not closed")
    if (
        document.get("schema_id") != "agent-workflow.release-static-metadata"
        or document.get("schema_version") != 1
    ):
        raise _source_failure("static release metadata identity is invalid")
    identity = _identity_from_document(document.get("release_identity"))
    local_state = _local_state_from_document(document.get("local_state_contract"))
    compatibility = _mapping(document.get("compatibility"), "compatibility")
    static_release = VerifiedRelease(
        identity=identity,
        manifest_digest="0" * 64,
        source_commit="0" * 40,
        bundles=MappingProxyType({}),
        assets=MappingProxyType({}),
        immutable_release=True,
        compatibility=compatibility,
    )
    _compatibility_edges(static_release)
    return StaticReleaseMetadata(identity, local_state, MappingProxyType(dict(compatibility)))
