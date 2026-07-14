"""Post-wheel project authority and recovery-runtime verification."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import cast

from agent_stack.core.api import SchemaCatalog, canonical_json_bytes
from agent_stack.release.compatibility import RuntimeJournalReference
from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.manifest import VerifiedRelease
from agent_stack.release.compatibility import select_candidate_runtime as _select_candidate_runtime

from .bootstrap import LauncherContract
from .errors import RuntimeFailure
from .maintenance import validate_maintenance_marker


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_FIELDS = {
    "schema_id",
    "schema_version",
    "launcher_contract_version",
    "launcher_renderer_version",
    "release_id",
    "release_manifest_digest",
    "wheel_url",
    "wheel_sha256",
    "uv_version_range",
    "python_version_range",
    "render_digest",
}
_LAUNCHER_PATH = ".agent-workflow/bin/agent-stack"
_CONTROL_PATH = ".agent-workflow/runtime-control.json"


def _failure(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure("AWP_RUNTIME_BINDING_MISMATCH", message, details=details)


def _sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise _failure("runtime authority digest is invalid", field=field_name)
    return value


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class RuntimeJournalEvidence:
    transaction_id: str
    journal_kind: str
    phase: str
    recovery_runtime: RuntimeJournalReference
    file_transitions: Mapping[str, tuple[str, str]]
    journal_binding_digest: str | None = None
    plan_digest: str | None = None
    task_quiescence_digest: str | None = None
    candidate_manifest_generation: int | None = None

    def __post_init__(self) -> None:
        if self.journal_kind not in {"lifecycle", "workspace", "task", "probe"}:
            raise _failure("runtime journal kind is unsupported")
        if not self.transaction_id or not self.phase or self.phase == "complete":
            raise _failure("runtime journal is not an unfinished transaction")
        normalized: dict[str, tuple[str, str]] = {}
        for path, pair in self.file_transitions.items():
            if path not in {_LAUNCHER_PATH, _CONTROL_PATH} or len(pair) != 2:
                raise _failure("runtime journal file transition is invalid", path=path)
            normalized[path] = (
                _sha256(pair[0], f"{path}.original"),
                _sha256(pair[1], f"{path}.candidate"),
            )
        object.__setattr__(self, "file_transitions", MappingProxyType(normalized))


@dataclass(frozen=True)
class RuntimeAuthorityInputs:
    packaged_release: VerifiedRelease
    committed_release: VerifiedRelease
    candidate_release: VerifiedRelease | None
    committed_manifest: Mapping[str, object]
    candidate_manifest: Mapping[str, object] | None
    workflow_lock_digest: str
    launcher_contract: LauncherContract
    launcher_bytes: bytes
    runtime_control_bytes: bytes
    journal: RuntimeJournalEvidence | None
    maintenance_marker: Mapping[str, object] | None
    command: str
    recovery_transaction_id: str | None


@dataclass(frozen=True)
class VerifiedRuntimeAuthority:
    release: VerifiedRelease | None
    runtime_role: str
    command: str
    recovery_transaction_id: str | None
    release_id: str
    details: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

def select_recovery_runtime(
    committed_release: VerifiedRelease,
    candidate_release: VerifiedRelease | None,
    journal: RuntimeJournalEvidence | None,
) -> VerifiedRelease:
    if journal is not None and (
        journal.journal_kind == "task" and journal.recovery_runtime.runtime_role == "candidate"
    ):
        raise RuntimeFailure(
            "AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED",
            "task journals cannot introduce a candidate recovery runtime",
        )
    try:
        return _select_candidate_runtime(
            committed_release,
            candidate_release,
            None if journal is None else journal.recovery_runtime,
        )
    except LifecycleFailure as error:
        raise RuntimeFailure(
            "AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED",
            "journal runtime is outside the committed/candidate allowlist",
            details={"lifecycle_code": error.code},
        ) from error


def _parse_control(payload: bytes) -> Mapping[str, object]:
    try:
        parsed = SchemaCatalog.parse_json(payload.decode("utf-8"))
    except Exception as error:
        raise _failure("runtime-control descriptor is invalid JSON") from error
    if not isinstance(parsed, dict) or canonical_json_bytes(parsed) != payload:
        raise _failure("runtime-control descriptor is not canonical JSON")
    if set(parsed) != _CONTROL_FIELDS:
        raise _failure("runtime-control descriptor fields are not closed")
    return cast(Mapping[str, object], parsed)


def _release_projection(release: VerifiedRelease) -> dict[str, object]:
    wheel = release.assets.get("wheel")
    if not isinstance(wheel, Mapping):
        raise _failure("verified release has no wheel authority")
    return {
        "release_id": release.identity.release_id,
        "release_manifest_digest": release.manifest_digest,
        "wheel_url": wheel.get("url"),
        "wheel_sha256": wheel.get("sha256"),
    }


def _descriptor_release(
    control: Mapping[str, object],
    committed: VerifiedRelease,
    candidate: VerifiedRelease | None,
) -> VerifiedRelease:
    constants = {
        "launcher_contract_version": 1,
        "launcher_renderer_version": "runtime-launcher-v1",
        "uv_version_range": ">=0.7.0,<1.0.0",
        "python_version_range": ">=3.11,<3.15",
        "schema_id": "agent-workflow.runtime-control",
        "schema_version": 1,
    }
    if any(control.get(name) != value for name, value in constants.items()):
        raise _failure("runtime-control fixed contract changed")
    for release in (committed, candidate):
        if release is not None and all(
            control.get(name) == value
            for name, value in _release_projection(release).items()
        ):
            _sha256(control.get("render_digest"), "render_digest")
            return release
    raise _failure("runtime-control release authority is unrecognized")


def _verify_manifest(
    document: Mapping[str, object], release: VerifiedRelease, lock_digest: str
) -> None:
    expected = {
        "schema_version": 1,
        "pack_version": release.identity.version,
        "release_id": release.identity.release_id,
        "release_manifest_digest": release.manifest_digest,
        "release_trust_policy_digest": release.bundles.get("trust_policy"),
        "artifact_bundle_digest": release.bundles.get("artifact"),
        "lock_digest": lock_digest,
    }
    mismatches = sorted(
        name for name, value in expected.items() if document.get(name) != value
    )
    if mismatches:
        raise _failure("Manifest disagrees with verified release authority", fields=mismatches)


def _verify_launcher_contract(contract: LauncherContract, release: VerifiedRelease) -> None:
    projection = _release_projection(release)
    observed = {
        "release_id": contract.release_id,
        "release_manifest_digest": contract.release_manifest_digest,
        "wheel_url": contract.wheel_url,
        "wheel_sha256": contract.wheel_sha256,
    }
    if observed != projection:
        raise _failure("launcher constants disagree with the running package")


def _authorized_file_state(
    path: str, observed_digest: str, journal: RuntimeJournalEvidence | None
) -> bool:
    if journal is None or path not in journal.file_transitions:
        return False
    return observed_digest in journal.file_transitions[path]


def _verify_command(inputs: RuntimeAuthorityInputs) -> None:
    journal = inputs.journal
    if journal is None and inputs.maintenance_marker is None:
        return
    if journal is None:
        raise _failure("maintenance exists without its transaction journal")
    if inputs.maintenance_marker is not None:
        validate_maintenance_marker(inputs.maintenance_marker, journal)
    if inputs.command == "doctor":
        return
    if (
        inputs.command != "recover"
        or inputs.recovery_transaction_id != journal.transaction_id
    ):
        raise RuntimeFailure(
            "AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED",
            "unfinished runtime state admits only matching recovery or diagnostics",
        )


def verify_runtime_authority(inputs: RuntimeAuthorityInputs) -> VerifiedRuntimeAuthority:
    """Verify package, release, Manifest, descriptor, journal, and command in order."""

    _sha256(inputs.workflow_lock_digest, "workflow_lock_digest")
    _verify_manifest(inputs.committed_manifest, inputs.committed_release, inputs.workflow_lock_digest)
    if inputs.candidate_release is not None:
        if inputs.candidate_manifest is None:
            raise _failure("candidate release has no approved candidate Manifest")
        _verify_manifest(
            inputs.candidate_manifest, inputs.candidate_release, inputs.workflow_lock_digest
        )
    selected = select_recovery_runtime(
        inputs.committed_release, inputs.candidate_release, inputs.journal
    )
    if selected.identity != inputs.packaged_release.identity or (
        selected.manifest_digest != inputs.packaged_release.manifest_digest
    ):
        raise RuntimeFailure(
            "AWP_RUNTIME_RECOVERY_NOT_AUTHORIZED",
            "running package is not the selected recovery runtime",
        )
    _verify_launcher_contract(inputs.launcher_contract, inputs.packaged_release)
    control = _parse_control(inputs.runtime_control_bytes)
    descriptor_release = _descriptor_release(
        control, inputs.committed_release, inputs.candidate_release
    )
    launcher_digest = _hash(inputs.launcher_bytes)
    descriptor_digest = _hash(inputs.runtime_control_bytes)
    if inputs.journal is None:
        if descriptor_release.identity != inputs.packaged_release.identity:
            raise _failure("ordinary descriptor does not match the running package")
        if control.get("render_digest") != launcher_digest:
            raise _failure("ordinary launcher and descriptor digests disagree")
    else:
        launcher_recorded = _authorized_file_state(
            _LAUNCHER_PATH, launcher_digest, inputs.journal
        )
        descriptor_recorded = _authorized_file_state(
            _CONTROL_PATH, descriptor_digest, inputs.journal
        )
        if inputs.journal.file_transitions and not (
            launcher_recorded and descriptor_recorded
        ):
            raise _failure("launcher or descriptor is an unrecorded third state")
        if not inputs.journal.file_transitions and (
            descriptor_release.identity != inputs.packaged_release.identity
            or control.get("render_digest") != launcher_digest
        ):
            raise _failure("unrecorded launcher and descriptor do not match")
        allowed_launcher_digests = inputs.journal.file_transitions.get(_LAUNCHER_PATH)
        if allowed_launcher_digests is not None and control.get(
            "render_digest"
        ) not in allowed_launcher_digests:
            raise _failure("descriptor names a launcher outside the journal transition")
    _verify_command(inputs)
    return VerifiedRuntimeAuthority(
        release=selected,
        runtime_role=(
            "committed" if inputs.journal is None else inputs.journal.recovery_runtime.runtime_role
        ),
        command=inputs.command,
        recovery_transaction_id=inputs.recovery_transaction_id,
        release_id=selected.identity.release_id,
        details=MappingProxyType(
            {
                "descriptor_release_id": descriptor_release.identity.release_id,
                "launcher_digest": launcher_digest,
                "runtime_control_digest": descriptor_digest,
            }
        ),
    )
