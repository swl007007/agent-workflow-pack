"""Catalog closure, capability evaluation, and workflow-lock normalization."""

from __future__ import annotations

import heapq
import re
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .canonical import normalize_string_set
from .errors import CoreFailure
from .models import (
    CapabilityLevel,
    CapabilityResult,
    CatalogClosure,
    CatalogEntry,
    ResolvedProfile,
    WorkflowComponent,
    WorkflowLock,
)


_CATALOG_FIELDS = {"schema_id", "schema_version", "entries"}
_ENTRY_FIELDS = {
    "id",
    "kind",
    "dependencies",
    "conflicts",
    "references",
    "platforms",
    "required_capabilities",
    "mandatory",
    "discoverable",
}
_MANIFEST_FIELDS = {
    "schema_id",
    "schema_version",
    "platform",
    "adapter_id",
    "adapter_version",
    "harness_id",
    "harness_version",
    "probe_suite_id",
    "probe_suite_version",
    "capabilities",
    "approval_verifiers",
    "evidence_digest",
}
_LOCK_FIELDS = {"schema_id", "schema_version", "components"}
_LOCK_COMPONENT_FIELDS = {
    "id",
    "version",
    "source_sha256",
    "content_digest",
    "provider_id",
    "acquisition_id",
}
_STABLE_ID = re.compile(r"^[a-z][a-z0-9-]*:[a-z0-9][a-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _catalog_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_CATALOG_CLOSURE_BLOCKED", message, details=details)


def _capability_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_CAPABILITY_INSUFFICIENT", message, exit_code=23, details=details)


def _string_array(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _catalog_failure("catalog field must be a string array", field=field)
    return normalize_string_set(value)


def _capability_mapping(value: object, field: str) -> Mapping[str, CapabilityLevel]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _catalog_failure("capability field must be an object", field=field)
    result: dict[str, CapabilityLevel] = {}
    for capability_id, raw_level in value.items():
        try:
            result[capability_id] = CapabilityLevel.parse(raw_level)
        except ValueError as error:
            raise _catalog_failure(
                "invalid capability level", field=field, capability_id=capability_id
            ) from error
    return MappingProxyType(dict(sorted(result.items())))


def _required_string(value: Mapping[str, object], field: str) -> str:
    candidate = value.get(field)
    if not isinstance(candidate, str) or not candidate:
        raise _catalog_failure("workflow-lock component field must be a nonempty string", field=field)
    return candidate


def _parse_manifests(
    manifests: Sequence[Mapping[str, object]],
) -> Mapping[str, Mapping[str, CapabilityLevel]]:
    result: dict[str, Mapping[str, CapabilityLevel]] = {}
    for manifest in manifests:
        unknown = set(manifest) - _MANIFEST_FIELDS
        if unknown:
            raise _capability_failure("unknown CapabilityManifest fields", fields=sorted(unknown))
        if manifest.get("schema_id") != "agent-workflow.capability-manifest":
            raise _capability_failure("CapabilityManifest schema_id is invalid")
        if manifest.get("schema_version") != 1:
            raise _capability_failure("CapabilityManifest schema_version is unsupported")
        platform = manifest.get("platform")
        if not isinstance(platform, str) or not platform:
            raise _capability_failure("CapabilityManifest platform is invalid")
        if platform in result:
            raise _capability_failure("duplicate CapabilityManifest platform", platform=platform)
        evidence_digest = manifest.get("evidence_digest")
        if not isinstance(evidence_digest, str) or not _SHA256.fullmatch(evidence_digest):
            raise _capability_failure("CapabilityManifest evidence digest is invalid", platform=platform)
        capabilities = manifest.get("capabilities")
        try:
            result[platform] = _capability_mapping(capabilities, "capabilities")
        except CoreFailure as error:
            raise _capability_failure(error.message, platform=platform, **dict(error.details)) from error
    return MappingProxyType(result)


def evaluate_capabilities(
    profile: ResolvedProfile,
    manifests: Sequence[Mapping[str, object]],
) -> tuple[CapabilityResult, ...]:
    """Compare verified observations with the selected profile minima."""

    by_platform = _parse_manifests(manifests)
    if profile.required_capabilities and not profile.default_platforms:
        raise _capability_failure("profile requires capabilities but selects no platform")
    results: list[CapabilityResult] = []
    for capability_id, required in sorted(profile.required_capabilities.items()):
        for platform in profile.default_platforms:
            observed = by_platform.get(platform, {}).get(
                capability_id, CapabilityLevel.UNSUPPORTED
            )
            if observed.rank < required.rank:
                raise _capability_failure(
                    "platform capability is below the profile minimum",
                    platform=platform,
                    capability_id=capability_id,
                    required=required.value,
                    observed=observed.value,
                )
            results.append(
                CapabilityResult(
                    capability_id=capability_id,
                    required=required,
                    observed=observed,
                    platform=platform,
                )
            )
    return tuple(results)


def _parse_catalog(document: Mapping[str, object]) -> dict[str, CatalogEntry]:
    unknown = set(document) - _CATALOG_FIELDS
    if unknown:
        raise _catalog_failure("unknown catalog fields", fields=sorted(unknown))
    if document.get("schema_id") != "agent-workflow.catalog" or document.get(
        "schema_version"
    ) != 1:
        raise _catalog_failure("catalog schema identity/version is invalid")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise _catalog_failure("catalog entries must be an array")

    entries: dict[str, CatalogEntry] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            raise _catalog_failure("catalog entry must be an object")
        unknown_entry = set(raw_entry) - _ENTRY_FIELDS
        if unknown_entry:
            raise _catalog_failure("unknown catalog entry fields", fields=sorted(unknown_entry))
        entry_id = raw_entry.get("id")
        kind = raw_entry.get("kind")
        if not isinstance(entry_id, str) or not _STABLE_ID.fullmatch(entry_id):
            raise _catalog_failure("catalog entry id is invalid", entry_id=entry_id)
        if not isinstance(kind, str) or entry_id.split(":", 1)[0] != kind:
            raise _catalog_failure("catalog entry kind disagrees with its id", entry_id=entry_id)
        if entry_id in entries:
            raise _catalog_failure("duplicate catalog entry id", entry_id=entry_id)
        mandatory = raw_entry.get("mandatory", False)
        discoverable = raw_entry.get("discoverable", True)
        if not isinstance(mandatory, bool) or not isinstance(discoverable, bool):
            raise _catalog_failure("catalog entry flags must be booleans", entry_id=entry_id)
        entries[entry_id] = CatalogEntry(
            entry_id=entry_id,
            kind=kind,
            dependencies=_string_array(raw_entry.get("dependencies", []), "dependencies"),
            conflicts=_string_array(raw_entry.get("conflicts", []), "conflicts"),
            references=_string_array(raw_entry.get("references", []), "references"),
            platforms=_string_array(raw_entry.get("platforms", []), "platforms"),
            required_capabilities=_capability_mapping(
                raw_entry.get("required_capabilities", {}), "required_capabilities"
            ),
            mandatory=mandatory,
            discoverable=discoverable,
        )
    return entries


def _entry_is_supported(
    entry: CatalogEntry,
    selected_platforms: tuple[str, ...],
    capability_by_platform: Mapping[str, Mapping[str, CapabilityLevel]],
) -> bool:
    candidate_platforms = tuple(
        platform
        for platform in selected_platforms
        if not entry.platforms or platform in entry.platforms
    )
    if entry.platforms and not candidate_platforms:
        return False
    if not entry.required_capabilities:
        return True
    for platform in candidate_platforms:
        observed = capability_by_platform.get(platform, {})
        if all(
            observed.get(capability_id, CapabilityLevel.UNSUPPORTED).rank >= required.rank
            for capability_id, required in entry.required_capabilities.items()
        ):
            return True
    return False


def _stable_topological_order(
    selected: set[str], entries: Mapping[str, CatalogEntry]
) -> tuple[str, ...]:
    consumers: dict[str, set[str]] = {entry_id: set() for entry_id in selected}
    indegree = {entry_id: 0 for entry_id in selected}
    for entry_id in selected:
        entry = entries[entry_id]
        for prerequisite in set(entry.dependencies) | set(entry.references):
            if prerequisite not in selected:
                raise _catalog_failure(
                    "closure prerequisite was not selected",
                    entry_id=entry_id,
                    prerequisite=prerequisite,
                )
            if entry_id not in consumers[prerequisite]:
                consumers[prerequisite].add(entry_id)
                indegree[entry_id] += 1

    ready = [entry_id for entry_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        entry_id = heapq.heappop(ready)
        ordered.append(entry_id)
        for consumer in sorted(consumers[entry_id]):
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                heapq.heappush(ready, consumer)
    if len(ordered) != len(selected):
        cyclic = sorted(entry_id for entry_id, count in indegree.items() if count > 0)
        raise _catalog_failure("catalog dependency/reference cycle", entries=cyclic)
    return tuple(ordered)


def resolve_catalog_closure(
    profile: ResolvedProfile,
    catalog_document: Mapping[str, object],
    manifests: Sequence[Mapping[str, object]],
) -> CatalogClosure:
    """Resolve dependencies, conflicts, references, platforms, and capabilities."""

    evaluate_capabilities(profile, manifests)
    capability_by_platform = _parse_manifests(manifests)
    entries = _parse_catalog(catalog_document)
    disabled = set(profile.skills_disable)
    selected: set[str] = set()
    reference_ids: set[str] = set()

    seeds = set(profile.skills_enable)
    seeds.update(entry_id for entry_id, entry in entries.items() if entry.mandatory)
    seeds.update(
        platform_id
        for platform in profile.default_platforms
        if (platform_id := f"platform:{platform}") in entries
    )

    def add(entry_id: str, *, via_reference: bool = False) -> None:
        if entry_id in selected:
            if via_reference:
                reference_ids.add(entry_id)
            return
        if entry_id in disabled:
            raise _catalog_failure("disabled entry cannot enter closure", entry_id=entry_id)
        try:
            entry = entries[entry_id]
        except KeyError as error:
            raise _catalog_failure("catalog dependency/reference is missing", entry_id=entry_id) from error
        if not _entry_is_supported(entry, profile.default_platforms, capability_by_platform):
            raise _catalog_failure("catalog entry is platform/capability incompatible", entry_id=entry_id)
        selected.add(entry_id)
        if via_reference:
            reference_ids.add(entry_id)
        for dependency in entry.dependencies:
            add(dependency)
        for reference in entry.references:
            add(reference, via_reference=True)

    for seed in sorted(seeds):
        add(seed)

    for entry_id in sorted(selected):
        conflicts = set(entries[entry_id].conflicts) & selected
        if conflicts:
            raise _catalog_failure(
                "catalog conflict in complete closure",
                entry_id=entry_id,
                conflicts=sorted(conflicts),
            )

    ordered = _stable_topological_order(selected, entries)
    selected_entries = MappingProxyType({entry_id: entries[entry_id] for entry_id in sorted(selected)})
    return CatalogClosure(
        ordered_ids=ordered,
        reference_ids=tuple(sorted(reference_ids)),
        discoverable_ids=tuple(
            sorted(entry_id for entry_id in selected if entries[entry_id].discoverable)
        ),
        entries=selected_entries,
    )


def normalize_workflow_lock(document: Mapping[str, object]) -> WorkflowLock:
    """Validate exact locked identities without performing version resolution."""

    unknown = set(document) - _LOCK_FIELDS
    if unknown:
        raise _catalog_failure("unknown workflow-lock fields", fields=sorted(unknown))
    if document.get("schema_id") != "agent-workflow.workflow-lock" or document.get(
        "schema_version"
    ) != 1:
        raise _catalog_failure("workflow-lock schema identity/version is invalid")
    raw_components = document.get("components")
    if not isinstance(raw_components, list):
        raise _catalog_failure("workflow-lock components must be an array")

    components: dict[str, WorkflowComponent] = {}
    for raw in raw_components:
        if not isinstance(raw, Mapping):
            raise _catalog_failure("workflow-lock component must be an object")
        unknown_component = set(raw) - _LOCK_COMPONENT_FIELDS
        if unknown_component:
            raise _catalog_failure(
                "unknown workflow-lock component fields", fields=sorted(unknown_component)
            )
        component_id = raw.get("id")
        if not isinstance(component_id, str) or not _STABLE_ID.fullmatch(component_id):
            raise _catalog_failure("workflow-lock component id is invalid", component_id=component_id)
        if component_id in components:
            raise _catalog_failure("duplicate workflow-lock component id", component_id=component_id)
        version = _required_string(raw, "version")
        source_sha = _required_string(raw, "source_sha256")
        content_digest = _required_string(raw, "content_digest")
        provider_id = _required_string(raw, "provider_id")
        acquisition_id = _required_string(raw, "acquisition_id")
        if not _SHA256.fullmatch(source_sha) or not _SHA256.fullmatch(content_digest):
            raise _catalog_failure("workflow-lock component hashes must be lowercase SHA-256")
        components[component_id] = WorkflowComponent(
            component_id=component_id,
            version=version,
            source_sha256=source_sha,
            content_digest=content_digest,
            provider_id=provider_id,
            acquisition_id=acquisition_id,
        )
    return WorkflowLock(schema_version=1, components=tuple(components[key] for key in sorted(components)))
