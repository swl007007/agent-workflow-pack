"""Pure authority, runtime-surface, and restorative-repair impact derivation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .canonical import CANONICAL_NULL, digest
from .errors import CoreFailure


AUTHORITY_IDS = (
    "artifact-bundle",
    "profile",
    "release-identity",
    "route-policy",
    "router-contract",
    "surface-registry",
    "trellis-layout",
    "workflow-lock",
)

_AUTHORITY_ID_SET = frozenset(AUTHORITY_IDS)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_OPERATIONS = frozenset({"init", "sync", "repair", "upgrade"})


@dataclass(frozen=True)
class AuthorityChange:
    authority_id: str
    before_digest: str
    after_digest: str

    def to_document(self) -> dict[str, str]:
        return {
            "authority_id": self.authority_id,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
        }


@dataclass(frozen=True)
class SurfaceChange:
    surface_id: str
    change_kind: str
    contract_before_digest: str
    observed_before_digest: str
    after_digest: str

    def to_document(self) -> dict[str, str]:
        return {
            "surface_id": self.surface_id,
            "change_kind": self.change_kind,
            "contract_before_digest": self.contract_before_digest,
            "observed_before_digest": self.observed_before_digest,
            "after_digest": self.after_digest,
        }


@dataclass(frozen=True)
class CandidateImpact:
    impact_kind: str
    authority_changes: tuple[AuthorityChange, ...]
    surface_changes: tuple[SurfaceChange, ...]
    contract_changing: bool
    candidate_impact_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.candidate-impact",
            "schema_version": 1,
            "impact_kind": self.impact_kind,
            "authority_changes": [change.to_document() for change in self.authority_changes],
            "surface_changes": [change.to_document() for change in self.surface_changes],
            "candidate_impact_digest": self.candidate_impact_digest,
        }


def _failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_CANDIDATE_IMPACT_INVALID", message, details=details)


def _coverage_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_SURFACE_COVERAGE_INVALID", message, details=details)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure(f"{label} must be a string-keyed object")
    return value


def _digest_value(value: object, label: str) -> str:
    if value == CANONICAL_NULL:
        return CANONICAL_NULL
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise _failure(f"{label} must be lowercase SHA-256 or canonical-null")
    return value


def _authority_map(value: object, label: str) -> dict[str, str]:
    raw = _mapping(value, label)
    unknown = sorted(set(raw) - _AUTHORITY_ID_SET)
    if unknown:
        raise _failure("authority vector contains unknown ids", authority_ids=unknown)
    return {
        authority_id: _digest_value(raw_value, f"{label}.{authority_id}")
        for authority_id, raw_value in raw.items()
    }


def _surface_map(value: object, label: str) -> dict[str, str]:
    raw = _mapping(value, label)
    normalized: dict[str, str] = {}
    for surface_id, raw_value in raw.items():
        if not surface_id or surface_id != surface_id.strip():
            raise _failure(f"{label} contains an invalid surface id", surface_id=surface_id)
        normalized[surface_id] = _digest_value(raw_value, f"{label}.{surface_id}")
    return normalized


def _string_set(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _failure(f"{label} must be a string array")
    if not all(isinstance(item, str) and item for item in value):
        raise _failure(f"{label} must contain nonempty strings")
    normalized = tuple(sorted(value))
    if len(set(normalized)) != len(normalized):
        raise _failure(f"{label} contains duplicates")
    return normalized


def _value_at(values: Mapping[str, str], identity: str) -> str:
    return values.get(identity, CANONICAL_NULL)


def _authority_changes(
    current: Mapping[str, str], candidate: Mapping[str, str]
) -> tuple[AuthorityChange, ...]:
    changes: list[AuthorityChange] = []
    for authority_id in AUTHORITY_IDS:
        before = _value_at(current, authority_id)
        after = _value_at(candidate, authority_id)
        if before != after:
            changes.append(AuthorityChange(authority_id, before, after))
    return tuple(changes)


def _contract_changes(
    current: Mapping[str, str],
    observed: Mapping[str, str],
    candidate: Mapping[str, str],
) -> tuple[SurfaceChange, ...]:
    surface_ids = sorted(set(current) | set(candidate) | set(observed))
    changes: list[SurfaceChange] = []
    for surface_id in surface_ids:
        before = _value_at(current, surface_id)
        observed_before = _value_at(observed, surface_id)
        after = _value_at(candidate, surface_id)
        if observed_before != before:
            raise _failure(
                "ordinary candidate impact cannot absorb observed runtime drift",
                surface_id=surface_id,
            )
        if after != before:
            changes.append(
                SurfaceChange(
                    surface_id=surface_id,
                    change_kind="contract-change",
                    contract_before_digest=before,
                    observed_before_digest=observed_before,
                    after_digest=after,
                )
            )
    return tuple(changes)


def _repair_changes(
    current: Mapping[str, str],
    observed: Mapping[str, str],
    candidate: Mapping[str, str],
    selected_surface_ids: tuple[str, ...],
) -> tuple[SurfaceChange, ...]:
    if current != candidate:
        raise _failure("repair must preserve the complete surface contract")
    if not selected_surface_ids:
        raise _failure("repair requires an explicit nonempty surface selection")

    known_surface_ids = set(current)
    unknown = sorted(set(selected_surface_ids) - known_surface_ids)
    if unknown:
        raise _failure("repair selects an unknown contract surface", surface_ids=unknown)

    drifted = {
        surface_id
        for surface_id in set(current) | set(observed)
        if _value_at(observed, surface_id) != _value_at(current, surface_id)
    }
    if drifted != set(selected_surface_ids):
        raise _failure(
            "repair selection must exactly cover observed runtime drift",
            selected_surface_ids=list(selected_surface_ids),
            drifted_surface_ids=sorted(drifted),
        )

    return tuple(
        SurfaceChange(
            surface_id=surface_id,
            change_kind="repair",
            contract_before_digest=current[surface_id],
            observed_before_digest=_value_at(observed, surface_id),
            after_digest=candidate[surface_id],
        )
        for surface_id in selected_surface_ids
    )


def _impact_projection(
    impact_kind: str,
    authority_changes: tuple[AuthorityChange, ...],
    surface_changes: tuple[SurfaceChange, ...],
) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.candidate-impact",
        "schema_version": 1,
        "impact_kind": impact_kind,
        "authority_changes": [change.to_document() for change in authority_changes],
        "surface_changes": [change.to_document() for change in surface_changes],
    }


def compute_candidate_impact(
    current_contract: Mapping[str, object],
    observed_state: Mapping[str, object],
    candidate_ir: Mapping[str, object],
) -> CandidateImpact:
    """Derive the complete normalized impact from contract, observation, and candidate IR."""

    operation = candidate_ir.get("operation")
    if operation not in _OPERATIONS:
        raise _failure("candidate operation is unsupported", operation=operation)

    current_authorities = _authority_map(
        current_contract.get("authority_digests"), "current_contract.authority_digests"
    )
    candidate_authorities = _authority_map(
        candidate_ir.get("authority_digests"), "candidate_ir.authority_digests"
    )
    current_surfaces = _surface_map(
        current_contract.get("surface_digests"), "current_contract.surface_digests"
    )
    observed_surfaces = _surface_map(
        observed_state.get("surface_digests"), "observed_state.surface_digests"
    )
    candidate_surfaces = _surface_map(
        candidate_ir.get("surface_digests"), "candidate_ir.surface_digests"
    )

    unclassified = _string_set(
        observed_state.get("unclassified_runtime_units", []),
        "observed_state.unclassified_runtime_units",
    )
    if unclassified:
        raise _coverage_failure(
            "runtime-visible units are absent from the frozen surface inventory",
            unit_ids=list(unclassified),
        )

    current_graph = _digest_value(
        current_contract.get("registry_graph_digest"),
        "current_contract.registry_graph_digest",
    )
    candidate_graph = _digest_value(
        candidate_ir.get("registry_graph_digest"),
        "candidate_ir.registry_graph_digest",
    )
    authority_changes = _authority_changes(current_authorities, candidate_authorities)

    if operation == "repair":
        if authority_changes:
            raise _failure("repair must preserve every authority digest")
        if current_graph != candidate_graph:
            raise _failure("repair must preserve the registry graph")
        selected = _string_set(
            candidate_ir.get("repair_surface_ids"), "candidate_ir.repair_surface_ids"
        )
        surface_changes = _repair_changes(
            current_surfaces, observed_surfaces, candidate_surfaces, selected
        )
    else:
        selected = _string_set(
            candidate_ir.get("repair_surface_ids", []), "candidate_ir.repair_surface_ids"
        )
        if selected:
            raise _failure("non-repair operation may not select repair surfaces")
        surface_changes = _contract_changes(
            current_surfaces, observed_surfaces, candidate_surfaces
        )

    if operation == "upgrade":
        release_change = next(
            (
                change
                for change in authority_changes
                if change.authority_id == "release-identity"
            ),
            None,
        )
        if release_change is None:
            raise _failure("upgrade must change release-identity")

    impact_kind = "none" if not authority_changes and not surface_changes else "runtime-visible"
    contract_changing = bool(authority_changes) or any(
        change.change_kind == "contract-change" for change in surface_changes
    )
    projection = _impact_projection(impact_kind, authority_changes, surface_changes)
    return CandidateImpact(
        impact_kind=impact_kind,
        authority_changes=authority_changes,
        surface_changes=surface_changes,
        contract_changing=contract_changing,
        candidate_impact_digest=digest("agent-workflow.candidate-impact.v1", projection),
    )
