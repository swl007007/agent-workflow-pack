"""Single-inheritance profile resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

from .canonical import normalize_string_set
from .errors import CoreFailure
from .models import CapabilityLevel, ResolvedProfile


_PROFILE_FIELDS = {
    "schema_id",
    "schema_version",
    "id",
    "extends",
    "route_admission",
    "bindings",
    "skills",
    "artifact_policy",
    "default_platforms",
    "required_capabilities",
    "approval_policy",
    "provider_security_policy",
}


def _profile_failure(message: str, **details: object) -> CoreFailure:
    return CoreFailure("AWP_PROFILE_INVALID", message, details=details)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _profile_failure("profile field must be an object", field=field)
    return value


def _string_array(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _profile_failure("profile field must be a string array", field=field)
    return normalize_string_set(value)


def _validate_source(source: Mapping[str, object]) -> str:
    unknown = set(source) - _PROFILE_FIELDS
    if unknown:
        raise _profile_failure("unknown profile fields", fields=sorted(unknown))
    if source.get("schema_id") != "agent-workflow.profile":
        raise _profile_failure("profile schema_id is invalid")
    if source.get("schema_version") != 1:
        raise _profile_failure("profile schema_version is unsupported")
    profile_id = source.get("id")
    if not isinstance(profile_id, str) or not profile_id:
        raise _profile_failure("profile id is invalid")
    extends = source.get("extends")
    if extends is not None and (not isinstance(extends, str) or not extends):
        raise _profile_failure("profile extends must be a profile id")
    return profile_id


def resolve_profile(
    profile_sources: Sequence[Mapping[str, object]], selected_profile_id: str
) -> ResolvedProfile:
    """Resolve one complete profile chain using the frozen field rules."""

    sources: dict[str, Mapping[str, object]] = {}
    for source in profile_sources:
        profile_id = _validate_source(source)
        if profile_id in sources:
            raise _profile_failure("duplicate profile id", profile_id=profile_id)
        sources[profile_id] = source
    if selected_profile_id not in sources:
        raise _profile_failure("selected profile does not exist", profile_id=selected_profile_id)

    chain: list[Mapping[str, object]] = []
    visiting: set[str] = set()
    current_id: str | None = selected_profile_id
    while current_id is not None:
        if current_id in visiting:
            raise _profile_failure("profile inheritance cycle", profile_id=current_id)
        visiting.add(current_id)
        try:
            current = sources[current_id]
        except KeyError as error:
            raise _profile_failure("profile parent does not exist", profile_id=current_id) from error
        chain.append(current)
        parent = current.get("extends")
        current_id = parent if isinstance(parent, str) else None
    chain.reverse()

    route_admission: dict[str, object] = {}
    bindings: dict[str, dict[str, str]] = {}
    enabled: set[str] = set()
    disabled: set[str] = set()
    artifact_policy = "default"
    default_platforms: tuple[str, ...] = ()
    required_capabilities: dict[str, CapabilityLevel] = {}
    approval_policy: dict[str, object] = {}
    provider_security_policy: dict[str, object] = {}

    for source in chain:
        if "route_admission" in source:
            route_admission.update(_mapping(source["route_admission"], "route_admission"))
        if "bindings" in source:
            raw_bindings = _mapping(source["bindings"], "bindings")
            for mode, raw_platform_bindings in raw_bindings.items():
                platform_bindings = _mapping(raw_platform_bindings, f"bindings.{mode}")
                if not all(isinstance(value, str) for value in platform_bindings.values()):
                    raise _profile_failure("binding values must be entry ids", mode=mode)
                bindings.setdefault(mode, {}).update(
                    {key: str(value) for key, value in platform_bindings.items()}
                )
        if "skills" in source:
            skills = _mapping(source["skills"], "skills")
            unknown = set(skills) - {"enable", "disable"}
            if unknown:
                raise _profile_failure("unknown skills fields", fields=sorted(unknown))
            enabled.update(_string_array(skills.get("enable", []), "skills.enable"))
            disabled.update(_string_array(skills.get("disable", []), "skills.disable"))
        if "artifact_policy" in source:
            value = source["artifact_policy"]
            if not isinstance(value, str) or not value:
                raise _profile_failure("artifact_policy must be a stable id")
            artifact_policy = value
        if "default_platforms" in source:
            default_platforms = _string_array(source["default_platforms"], "default_platforms")
        if "required_capabilities" in source:
            capabilities = _mapping(source["required_capabilities"], "required_capabilities")
            for capability_id, level in capabilities.items():
                try:
                    required_capabilities[capability_id] = CapabilityLevel.parse(level)
                except ValueError as error:
                    raise _profile_failure(
                        "invalid capability minimum", capability_id=capability_id
                    ) from error
        if "approval_policy" in source:
            approval_policy.update(_mapping(source["approval_policy"], "approval_policy"))
        if "provider_security_policy" in source:
            provider_security_policy.update(
                _mapping(source["provider_security_policy"], "provider_security_policy")
            )

    overlap = enabled & disabled
    if overlap:
        raise _profile_failure("skills cannot be both enabled and disabled", skills=sorted(overlap))

    frozen_bindings = MappingProxyType(
        {mode: MappingProxyType(dict(platforms)) for mode, platforms in sorted(bindings.items())}
    )
    return ResolvedProfile(
        schema_version=1,
        profile_id=selected_profile_id,
        route_admission=MappingProxyType(dict(sorted(route_admission.items()))),
        bindings=frozen_bindings,
        skills_enable=tuple(sorted(enabled)),
        skills_disable=tuple(sorted(disabled)),
        artifact_policy=artifact_policy,
        default_platforms=default_platforms,
        required_capabilities=MappingProxyType(dict(sorted(required_capabilities.items()))),
        approval_policy=MappingProxyType(dict(sorted(approval_policy.items()))),
        provider_security_policy=MappingProxyType(dict(sorted(provider_security_policy.items()))),
    )
