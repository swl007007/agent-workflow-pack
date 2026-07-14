"""Existing-task runtime authorization and immutable in-memory dispatch."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import (
    VerifiedSurfaceRegistry,
    canonical_json_bytes,
    compute_surface_digests,
    normalize_mode,
    normalize_path,
)
from agent_stack.core.errors import CoreFailure
from agent_stack.reconcile.locks import acquire_runtime_state_gate

from .errors import RuntimeFailure
from .integration import VerifiedIntegration, validate_integration
from .task_journal import unfinished_task_journals


_ENTRY_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _race_check(point: str) -> None:
    """Test seam; production code never injects a concurrent mutation."""


@dataclass(frozen=True)
class RuntimeEntryDescriptor:
    entry_id: str
    owning_surface_id: str
    allowed_modes: tuple[str, ...]
    allowed_lifecycle_statuses: tuple[str, ...]
    allowed_phases: tuple[str, ...]
    claim_policy: str


@dataclass(frozen=True)
class TaskRuntimeLoadRequest:
    project_root: Path
    package_root: Path
    task_ref: str
    task_id: str
    expected_state_revision: int
    expected_lifecycle_status: str
    expected_phase: str | None
    expected_claim: Mapping[str, object] | None
    surface_id: str
    runtime_entry_id: str
    registry: VerifiedSurfaceRegistry
    contract_evidence: tuple[Mapping[str, object], ...]
    runtime_entries: Mapping[str, RuntimeEntryDescriptor]


@dataclass(frozen=True)
class DispatchUnit:
    unit_id: str
    owning_surface_id: str
    distribution_scope: str
    normalized_path: str
    mode: str
    byte_hash: str
    content: bytes


@dataclass(frozen=True)
class ImmutableDispatchBundle:
    task_id: str
    task_ref: str
    state_revision: int
    mode: str
    lifecycle_status: str
    phase: str | None
    surface_id: str
    runtime_entry_id: str
    authorized_surface_ids: tuple[str, ...]
    units: Mapping[str, DispatchUnit]


def _failure(code: str, message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure(code, message, details=details)


def _task_ref(value: str) -> str:
    try:
        return normalize_path(value)
    except CoreFailure as error:
        raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "task ref is invalid") from error


def _read_integration(root: Path, task_ref: str) -> tuple[bytes, Mapping[str, object]]:
    path = root / task_ref / "integration.yaml"
    if path.is_symlink() or not path.is_file():
        raise _failure("AWP_TASK_STATE_STALE", "integration is missing or has invalid type")
    information = path.stat()
    if normalize_mode(information.st_mode) != "0640":
        raise _failure("AWP_TASK_STATE_STALE", "integration mode changed")
    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _failure("AWP_TASK_STATE_STALE", "integration is corrupt") from error
    if not isinstance(document, Mapping) or canonical_json_bytes(document) != payload:
        raise _failure("AWP_TASK_STATE_STALE", "integration is not canonical")
    return payload, cast(Mapping[str, object], document)


def _closure(registry: VerifiedSurfaceRegistry, surface_id: str) -> tuple[str, ...]:
    if surface_id not in registry.surfaces:
        raise _failure("AWP_TASK_SURFACE_MISMATCH", "requested surface is unknown")
    result: set[str] = set()
    pending = [surface_id]
    while pending:
        current = pending.pop()
        if current in result:
            continue
        result.add(current)
        pending.extend(registry.surfaces[current].references)
    missing = {"runtime-control-plane", "surface-registry"} - result
    if missing:
        raise _failure(
            "AWP_TASK_SURFACE_MISMATCH",
            "runtime surface closure omits mandatory meta-surfaces",
            missing=sorted(missing),
        )
    return tuple(surface for surface in registry.topological_surface_ids if surface in result)


def _evidence_map(
    evidence: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for item in evidence:
        unit_id = item.get("unit_id")
        if not isinstance(unit_id, str) or unit_id in result:
            raise _failure("AWP_TASK_SURFACE_MISMATCH", "contract evidence identity is invalid")
        result[unit_id] = item
    return result


def _real_root(root: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(root))
    if absolute.is_symlink() or not absolute.is_dir():
        raise _failure("AWP_TASK_SURFACE_MISMATCH", f"{label} root is unavailable")
    return absolute


def _unit_path(root: Path, relative: str) -> Path:
    normalized = normalize_path(relative)
    current = root
    for segment in Path(normalized).parts[:-1]:
        current /= segment
        if current.is_symlink() or not current.is_dir():
            raise _failure(
                "AWP_TASK_SURFACE_MISMATCH", "runtime unit parent changed type", path=normalized
            )
    return root / normalized


def _read_unit(
    request: TaskRuntimeLoadRequest,
    unit_id: str,
) -> DispatchUnit:
    descriptor = request.registry.units[unit_id]
    root = _real_root(
        request.package_root if descriptor.distribution_scope == "runtime-package" else request.project_root,
        descriptor.distribution_scope,
    )
    path = _unit_path(root, descriptor.normalized_path)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        file_descriptor = os.open(path, flags)
    except OSError as error:
        raise _failure(
            "AWP_TASK_SURFACE_MISMATCH", "runtime unit is missing or unreadable", unit_id=unit_id
        ) from error
    try:
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise _failure(
                "AWP_TASK_SURFACE_MISMATCH", "runtime unit is not a regular file", unit_id=unit_id
            )
        chunks: list[bytes] = []
        while chunk := os.read(file_descriptor, 1024 * 1024):
            chunks.append(chunk)
        after = os.fstat(file_descriptor)
    finally:
        os.close(file_descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise _failure("AWP_TASK_SURFACE_MISMATCH", "runtime unit changed while reading")
    content = b"".join(chunks)
    return DispatchUnit(
        unit_id,
        descriptor.owning_surface_id,
        descriptor.distribution_scope,
        descriptor.normalized_path,
        normalize_mode(after.st_mode),
        hashlib.sha256(content).hexdigest(),
        content,
    )


def _observed_evidence(
    request: TaskRuntimeLoadRequest,
    expected: Mapping[str, Mapping[str, object]],
    units: Mapping[str, DispatchUnit],
) -> tuple[Mapping[str, object], ...]:
    observed: list[Mapping[str, object]] = []
    for unit_id in request.registry.units:
        contract = expected.get(unit_id)
        if contract is None:
            raise _failure("AWP_TASK_SURFACE_MISMATCH", "contract evidence is incomplete")
        unit = units.get(unit_id)
        if unit is None:
            observed.append(contract)
            continue
        observed.append(
            {
                "unit_id": unit_id,
                "byte_hash": unit.byte_hash,
                "mode": unit.mode,
                "contract_digest": contract.get("contract_digest"),
                "distributions": contract.get("distributions"),
            }
        )
    return tuple(observed)


def _entry(request: TaskRuntimeLoadRequest) -> RuntimeEntryDescriptor:
    if _ENTRY_ID.fullmatch(request.runtime_entry_id) is None:
        raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry ID is invalid")
    entry = request.runtime_entries.get(request.runtime_entry_id)
    if entry is None or entry.entry_id != request.runtime_entry_id:
        raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry is not registered")
    if entry.owning_surface_id != request.surface_id:
        raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry owner differs from request")
    if entry.claim_policy not in {"forbidden", "optional", "required"}:
        raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry claim policy is invalid")
    return entry


def _validate_state(
    request: TaskRuntimeLoadRequest, document: Mapping[str, object]
) -> VerifiedIntegration:
    try:
        verified = validate_integration(document)
    except RuntimeFailure as error:
        code = (
            "AWP_TASK_SURFACE_MISMATCH"
            if "surface" in error.message
            else "AWP_TASK_STATE_STALE"
        )
        raise _failure(code, "integration contract is invalid") from error
    if verified.task_id != request.task_id:
        raise _failure("AWP_TASK_STATE_STALE", "task identity differs")
    if verified.state_revision != request.expected_state_revision:
        raise _failure("AWP_TASK_STATE_STALE", "task revision changed")
    if verified.lifecycle_status != request.expected_lifecycle_status:
        raise _failure("AWP_TASK_STATE_STALE", "task lifecycle changed")
    if verified.lifecycle_status in {"admitting", "archiving", "archived"}:
        raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "task lifecycle is not runnable")
    if verified.phase != request.expected_phase:
        raise _failure("AWP_TASK_STATE_STALE", "task phase changed")
    actual_claim = None if verified.executor_claim is None else dict(verified.executor_claim)
    expected_claim = None if request.expected_claim is None else dict(request.expected_claim)
    if canonical_json_bytes(actual_claim) != canonical_json_bytes(expected_claim):
        raise _failure("AWP_TASK_STATE_STALE", "task executor claim changed")
    return verified


def load_task_runtime(request: TaskRuntimeLoadRequest) -> ImmutableDispatchBundle:
    """Authorize one existing-task entry and return only immutable in-memory bytes."""

    task_ref = _task_ref(request.task_ref)
    with acquire_runtime_state_gate(request.project_root):
        maintenance = request.project_root / ".agent-workflow/maintenance.json"
        if maintenance.exists() or maintenance.is_symlink():
            raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "maintenance blocks runtime load")
        try:
            unfinished = unfinished_task_journals(request.project_root)
        except RuntimeFailure as error:
            raise _failure(
                "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED",
                "task transaction state blocks runtime load",
            ) from error
        if unfinished:
            raise _failure(
                "AWP_TASK_TRANSACTION_RECOVERY_REQUIRED",
                "unfinished task transaction blocks runtime load",
            )
        integration_bytes, document = _read_integration(request.project_root, task_ref)
        verified = _validate_state(request, document)
        entry = _entry(request)
        if verified.mode not in entry.allowed_modes:
            raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry rejects task mode")
        if verified.lifecycle_status not in entry.allowed_lifecycle_statuses:
            raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry rejects lifecycle")
        if entry.allowed_phases and (verified.phase is None or verified.phase not in entry.allowed_phases):
            raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry rejects phase")
        if entry.claim_policy == "forbidden" and verified.executor_claim is not None:
            raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry forbids claims")
        if entry.claim_policy == "required" and verified.executor_claim is None:
            raise _failure("AWP_TASK_RUNTIME_LOAD_DENIED", "runtime entry requires a claim")

        closure = _closure(request.registry, request.surface_id)
        pinned = {pin.surface_id: pin.surface_digest for pin in verified.task_contract_surfaces}
        missing_pins = set(closure) - set(pinned)
        if missing_pins:
            raise _failure(
                "AWP_TASK_SURFACE_MISMATCH",
                "task does not pin the complete runtime surface closure",
                missing=sorted(missing_pins),
            )
        expected_evidence = _evidence_map(request.contract_evidence)
        try:
            current_digests = compute_surface_digests(
                request.registry, request.contract_evidence
            )
        except CoreFailure as error:
            raise _failure("AWP_TASK_SURFACE_MISMATCH", "current surface contract is invalid") from error
        for surface_id in closure:
            if current_digests[surface_id] != pinned[surface_id]:
                raise _failure(
                    "AWP_TASK_SURFACE_MISMATCH",
                    "current surface contract differs from task pin",
                    surface_id=surface_id,
                )

        unit_ids = tuple(
            unit_id
            for surface_id in closure
            for unit_id in request.registry.surfaces[surface_id].owned_unit_ids
        )
        loaded = {unit_id: _read_unit(request, unit_id) for unit_id in unit_ids}
        observed_evidence = _observed_evidence(request, expected_evidence, loaded)
        try:
            observed_digests = compute_surface_digests(request.registry, observed_evidence)
        except CoreFailure as error:
            raise _failure("AWP_TASK_SURFACE_MISMATCH", "observed runtime surface is invalid") from error
        for surface_id in closure:
            if observed_digests[surface_id] != current_digests[surface_id]:
                raise _failure(
                    "AWP_TASK_SURFACE_MISMATCH",
                    "observed runtime surface differs from current contract",
                    surface_id=surface_id,
                )

        _race_check("after-unit-reads")
        current_integration, current_document = _read_integration(request.project_root, task_ref)
        if current_integration != integration_bytes:
            raise _failure("AWP_TASK_STATE_STALE", "task integration changed during load")
        _validate_state(request, current_document)
        for unit_id, first in loaded.items():
            second = _read_unit(request, unit_id)
            if (second.byte_hash, second.mode) != (first.byte_hash, first.mode):
                raise _failure(
                    "AWP_TASK_SURFACE_MISMATCH", "runtime unit changed during load", unit_id=unit_id
                )

        return ImmutableDispatchBundle(
            verified.task_id,
            task_ref,
            verified.state_revision,
            verified.mode,
            verified.lifecycle_status,
            verified.phase,
            request.surface_id,
            request.runtime_entry_id,
            closure,
            MappingProxyType(dict(loaded)),
        )
