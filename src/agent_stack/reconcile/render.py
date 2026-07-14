"""Pure deterministic rendering from Core IR and verified provider output roots."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from agent_stack.core.api import DesiredStateIR, digest, normalize_mode, normalize_path
from agent_stack.providers.api import ProviderExecutionResult
from agent_stack.providers.archive import content_root_digest

from .errors import RendererFailure
from .models import StagedFile, StagedRenderTree


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER = re.compile(r"\{\{[a-z0-9._-]+\}\}")
_UNIT_FIELDS = {
    "schema_id",
    "schema_version",
    "unit_id",
    "definition_id",
    "source",
    "target",
    "surface_id",
    "validator_ids",
    "candidate_leaf_digest",
}
_SOURCE_FIELDS = {"source_id", "source_digest"}
_TARGET_COMMON_FIELDS = {"path", "ownership", "merge_strategy", "mode_policy"}
_MANAGED_TARGET_FIELDS = _TARGET_COMMON_FIELDS | {"mode"}
_OVERLAY_TARGET_FIELDS = _TARGET_COMMON_FIELDS | {"markers"}


def _render_failure(message: str, **details: object) -> RendererFailure:
    return RendererFailure("AWP_RENDER_NONDETERMINISTIC", message, details=details)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _render_failure("render projection object is invalid", field=field)
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _render_failure("render projection string is invalid", field=field)
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise _render_failure("render projection digest is invalid", field=field)
    return value


def _provider_roots(
    verified_provider_results: Sequence[ProviderExecutionResult],
) -> tuple[Path, ...]:
    roots: list[Path] = []
    for result in verified_provider_results:
        if result.terminal_state != "succeeded" or result.result_category != "validated":
            raise _render_failure("provider result is not a validated terminal candidate")
        root = Path(result.candidate_output_path)
        if root.is_symlink() or not root.is_dir():
            raise _render_failure("provider candidate root is unavailable")
        if content_root_digest(root) != result.candidate_output_root_digest:
            raise _render_failure("provider candidate root changed after validation")
        roots.append(root.resolve(strict=True))
    return tuple(roots)


def _source_bytes(roots: Sequence[Path], relative_path: str, expected_digest: str) -> bytes:
    matches: list[bytes] = []
    relative = Path(normalize_path(relative_path))
    for root in roots:
        candidate = root / relative
        current = root
        unsafe = False
        for segment in relative.parts:
            current /= segment
            if current.is_symlink():
                unsafe = True
                break
        if unsafe or not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if not resolved.is_relative_to(root):
            continue
        payload = resolved.read_bytes()
        if hashlib.sha256(payload).hexdigest() == expected_digest:
            matches.append(payload)
    if len(matches) != 1:
        raise _render_failure(
            "render source is missing, ambiguous, or differs from its verified digest",
            source_id=relative_path,
        )
    return matches[0]


def _definitions(ir: DesiredStateIR) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for raw in ir.artifact_definitions:
        definition_id = _string(raw.get("id"), "artifact_definition.id")
        if definition_id in result:
            raise _render_failure("artifact definition repeats", definition_id=definition_id)
        result[definition_id] = raw
    return result


def _definition_target(
    definition: Mapping[str, object], target_path: str
) -> Mapping[str, object]:
    targets = definition.get("targets")
    if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)):
        raise _render_failure("artifact definition targets are invalid")
    matches = [
        _mapping(raw, "artifact_definition.target")
        for raw in targets
        if isinstance(raw, Mapping) and raw.get("path") == target_path
    ]
    if len(matches) != 1:
        raise _render_failure("render target is not owned by exactly one artifact definition")
    return matches[0]


def _candidate_mode(
    target: Mapping[str, object], defined_target: Mapping[str, object]
) -> str:
    ownership = target.get("ownership")
    if ownership == "managed":
        if set(target) != _MANAGED_TARGET_FIELDS:
            raise _render_failure("managed render target fields are not closed")
        if (
            target.get("merge_strategy") != "whole-file"
            or target.get("mode_policy") != "exact"
        ):
            raise _render_failure("managed render target contract is invalid")
        mode_value = target.get("mode")
        if not isinstance(mode_value, (int, str)) or isinstance(mode_value, bool):
            raise _render_failure("render target mode is invalid")
        candidate_mode = normalize_mode(mode_value)
    elif ownership == "overlay-managed":
        if set(target) != _OVERLAY_TARGET_FIELDS:
            raise _render_failure("overlay render target fields are not closed")
        if (
            target.get("merge_strategy") != "marked-block"
            or target.get("mode_policy") != "preserve"
        ):
            raise _render_failure("overlay render target contract is invalid")
        markers = _mapping(target.get("markers"), "target.markers")
        if set(markers) != {"begin", "end"}:
            raise _render_failure("overlay marker fields are not closed")
        _string(markers.get("begin"), "target.markers.begin")
        _string(markers.get("end"), "target.markers.end")
        candidate_mode = "canonical-null"
    else:
        raise _render_failure("render target ownership is unsupported")
    for field in target:
        if target.get(field) != defined_target.get(field):
            raise _render_failure(
                "render target contract disagrees with artifact definition", field=field
            )
    return candidate_mode


def _substitutions(ir: DesiredStateIR) -> dict[str, str]:
    values = {
        "release_id": ir.release_contract.get("release_id"),
        "release_manifest_digest": ir.release_contract.get("release_manifest_digest"),
        "profile_digest": ir.authority_digests.get("profile"),
    }
    if not all(isinstance(value, str) and _SHA256.fullmatch(value) for value in values.values()):
        raise _render_failure("fixed render substitutions are incomplete")
    return {key: str(value) for key, value in values.items()}


def _render_text(source_bytes: bytes, substitutions: Mapping[str, str]) -> bytes:
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _render_failure("binary or non-UTF-8 render sources are unsupported") from error
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    for key, value in substitutions.items():
        normalized = normalized.replace(f"{{{{{key}}}}}", value)
    unresolved = sorted(set(_PLACEHOLDER.findall(normalized)))
    if unresolved:
        raise _render_failure("render source contains unresolved substitutions", values=unresolved)
    return normalized.encode("utf-8")


def _validator_results(candidate: bytes, validator_ids: Sequence[object]) -> tuple[Mapping[str, object], ...]:
    results: list[Mapping[str, object]] = []
    for raw_id in validator_ids:
        validator_id = _string(raw_id, "validator_id")
        if validator_id == "utf8-text-v1":
            candidate.decode("utf-8")
        elif validator_id == "newline-v1":
            if b"\r" in candidate or (candidate and not candidate.endswith(b"\n")):
                raise _render_failure("rendered text violates the newline policy")
        elif validator_id == "nonempty-v1":
            if not candidate:
                raise _render_failure("rendered text is empty")
        else:
            raise _render_failure("render validator is unsupported", validator_id=validator_id)
        results.append(
            MappingProxyType(
                {
                    "validator_id": validator_id,
                    "validator_version": 1,
                    "status": "passed",
                }
            )
        )
    return tuple(results)


def render(
    ir: DesiredStateIR,
    verified_provider_results: Sequence[ProviderExecutionResult],
) -> StagedRenderTree:
    roots = _provider_roots(verified_provider_results)
    definitions = _definitions(ir)
    substitutions = _substitutions(ir)
    staged: list[StagedFile] = []
    seen_paths: set[str] = set()
    for raw_unit in ir.render_units:
        if set(raw_unit) != _UNIT_FIELDS:
            raise _render_failure("render-unit fields are not closed")
        if (
            raw_unit.get("schema_id") != "agent-workflow.render-unit"
            or raw_unit.get("schema_version") != 1
        ):
            raise _render_failure("render-unit schema identity/version is invalid")
        definition_id = _string(raw_unit.get("definition_id"), "definition_id")
        try:
            definition = definitions[definition_id]
        except KeyError as error:
            raise _render_failure("render-unit references an unknown definition") from error
        source = _mapping(raw_unit.get("source"), "source")
        target = _mapping(raw_unit.get("target"), "target")
        if set(source) != _SOURCE_FIELDS:
            raise _render_failure("render-unit source fields are not closed")
        source_id = normalize_path(_string(source.get("source_id"), "source_id"))
        if definition.get("source") != source_id:
            raise _render_failure("render-unit source disagrees with artifact definition")
        target_path = normalize_path(_string(target.get("path"), "target.path"))
        if target_path in seen_paths:
            raise _render_failure("render target path repeats", path=target_path)
        seen_paths.add(target_path)
        defined_target = _definition_target(definition, target_path)
        candidate_mode = _candidate_mode(target, defined_target)
        source_digest = _sha256(source.get("source_digest"), "source_digest")
        neutral_bytes = _source_bytes(roots, source_id, source_digest)
        candidate = _render_text(neutral_bytes, substitutions)
        candidate_hash = hashlib.sha256(candidate).hexdigest()
        if candidate_hash != _sha256(
            raw_unit.get("candidate_leaf_digest"), "candidate_leaf_digest"
        ):
            raise _render_failure("rendered candidate differs from its frozen leaf digest")
        validator_ids = raw_unit.get("validator_ids")
        if not isinstance(validator_ids, Sequence) or isinstance(
            validator_ids, (str, bytes)
        ):
            raise _render_failure("render validator IDs are invalid")
        validators = _validator_results(candidate, validator_ids)
        render_digest = digest(
            "agent-workflow.rendered-file.v1",
            {
                "path": target_path,
                "definition_id": definition_id,
                "surface_id": _string(raw_unit.get("surface_id"), "surface_id"),
                "source_digest": source_digest,
                "candidate_byte_hash": candidate_hash,
                "candidate_mode": candidate_mode,
                "renderer_version": 1,
                "validator_ids": list(validator_ids),
            },
        )
        staged.append(
            StagedFile(
                path=target_path,
                definition_id=definition_id,
                surface_id=_string(raw_unit.get("surface_id"), "surface_id"),
                ownership=_string(target.get("ownership"), "ownership"),
                merge_strategy=_string(target.get("merge_strategy"), "merge_strategy"),
                source_digest=source_digest,
                render_digest=render_digest,
                candidate_byte_hash=candidate_hash,
                mode_policy=_string(target.get("mode_policy"), "mode_policy"),
                candidate_mode=candidate_mode,
                validator_results=validators,
                candidate_bytes=candidate,
                neutral_source_bytes=neutral_bytes,
            )
        )
    ordered = tuple(sorted(staged, key=lambda record: record.path))
    file_projection = [
        {
            "path": record.path,
            "candidate_byte_hash": record.candidate_byte_hash,
            "candidate_mode": record.candidate_mode,
            "render_digest": record.render_digest,
        }
        for record in ordered
    ]
    launcher_projection = [
        {
            "path": record.path,
            "neutral_source_hash": hashlib.sha256(record.neutral_source_bytes).hexdigest(),
            "mode": record.candidate_mode,
        }
        for record in ordered
        if record.surface_id.startswith("launcher:")
    ]
    return StagedRenderTree(
        files=ordered,
        content_root_digest=digest("agent-workflow.staged-render-tree.v1", file_projection),
        launcher_bundle_digest=digest(
            "agent-workflow.launcher-bundle.v1", launcher_projection
        ),
        distribution_render_digest=digest(
            "agent-workflow.distribution-render.v1",
            {
                "release_contract": dict(ir.release_contract),
                "files": file_projection,
            },
        ),
    )
