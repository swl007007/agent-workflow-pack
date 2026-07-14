"""Release-bound single-file launcher rendering and bootstrap invocation validation."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

from agent_stack.release.manifest import VerifiedRelease

from .errors import RuntimeFailure


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER = re.compile(rb"\{\{([a-z][a-z0-9_]*)\}\}")
_EXPECTED_PLACEHOLDERS = {
    "launcher_contract_version",
    "launcher_renderer_version",
    "release_id",
    "release_manifest_digest",
    "wheel_url",
    "wheel_sha256",
}


def _binding_failure(message: str, **details: object) -> RuntimeFailure:
    return RuntimeFailure("AWP_RUNTIME_BINDING_MISMATCH", message, details=details)


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise _binding_failure("launcher digest is invalid", field=field)
    return value


def _closed_https_wheel_url(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise _binding_failure("launcher wheel URL is invalid")
    if any(character in value for character in ("'", '"', "\\", "\r", "\n", "\t")):
        raise _binding_failure("launcher wheel URL is not shell-safe")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise _binding_failure("launcher wheel URL is invalid") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith(".whl")
    ):
        raise _binding_failure("launcher wheel URL violates the immutable HTTPS contract")
    return value


@dataclass(frozen=True)
class LauncherContract:
    launcher_contract_version: int
    launcher_renderer_version: str
    release_id: str
    release_manifest_digest: str
    wheel_url: str
    wheel_sha256: str

    def __post_init__(self) -> None:
        if self.launcher_contract_version != 1:
            raise _binding_failure("launcher contract version is unsupported")
        if self.launcher_renderer_version != "runtime-launcher-v1":
            raise _binding_failure("launcher renderer version is unsupported")
        _digest(self.release_id, "release_id")
        _digest(self.release_manifest_digest, "release_manifest_digest")
        _closed_https_wheel_url(self.wheel_url)
        _digest(self.wheel_sha256, "wheel_sha256")

    def render(self, template: bytes) -> bytes:
        placeholders = {match.decode("ascii") for match in _PLACEHOLDER.findall(template)}
        if placeholders != _EXPECTED_PLACEHOLDERS:
            raise _binding_failure(
                "launcher template substitutions are not closed",
                expected=sorted(_EXPECTED_PLACEHOLDERS),
                observed=sorted(placeholders),
            )
        substitutions = {
            "launcher_contract_version": str(self.launcher_contract_version),
            "launcher_renderer_version": self.launcher_renderer_version,
            "release_id": self.release_id,
            "release_manifest_digest": self.release_manifest_digest,
            "wheel_url": self.wheel_url,
            "wheel_sha256": self.wheel_sha256,
        }
        rendered = template.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        for name, value in substitutions.items():
            rendered = rendered.replace(f"{{{{{name}}}}}".encode(), value.encode("utf-8"))
        if _PLACEHOLDER.search(rendered) or not rendered.endswith(b"\n"):
            raise _binding_failure("rendered launcher is incomplete")
        return rendered

    def runtime_control(self, rendered_launcher: bytes) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.runtime-control",
            "schema_version": 1,
            "launcher_contract_version": self.launcher_contract_version,
            "launcher_renderer_version": self.launcher_renderer_version,
            "release_id": self.release_id,
            "release_manifest_digest": self.release_manifest_digest,
            "wheel_url": self.wheel_url,
            "wheel_sha256": self.wheel_sha256,
            "uv_version_range": ">=0.7.0,<1.0.0",
            "python_version_range": ">=3.11,<3.15",
            "render_digest": hashlib.sha256(rendered_launcher).hexdigest(),
        }


def launcher_contract_from_release(release: VerifiedRelease) -> LauncherContract:
    if not release.immutable_release:
        raise _binding_failure("launcher release is not immutable")
    try:
        wheel = release.assets["wheel"]
        wheel_url = wheel["url"]
        wheel_sha256 = wheel["sha256"]
    except (KeyError, TypeError) as error:
        raise _binding_failure("verified release has no complete wheel authority") from error
    return LauncherContract(
        launcher_contract_version=1,
        launcher_renderer_version="runtime-launcher-v1",
        release_id=release.identity.release_id,
        release_manifest_digest=release.manifest_digest,
        wheel_url=_closed_https_wheel_url(wheel_url),
        wheel_sha256=_digest(wheel_sha256, "wheel_sha256"),
    )


@dataclass(frozen=True)
class LauncherInvocation:
    project_root: Path
    caller_context_version: int
    command: tuple[str, ...]
    caller_fields: Mapping[str, str]


@dataclass(frozen=True)
class VerifiedRuntimeInvocation:
    project_root: Path
    caller_context_version: int
    command: tuple[str, ...]
    caller_fields: Mapping[str, str]


def bootstrap_project_runtime(invocation: LauncherInvocation) -> VerifiedRuntimeInvocation:
    """Validate only the reserved launcher channel before later authority verification."""

    root = invocation.project_root
    if invocation.caller_context_version != 1:
        raise RuntimeFailure("AWP_CALLER_CONTEXT_INVALID", "caller context version is unsupported")
    if not root.is_absolute() or not root.is_dir():
        raise _binding_failure("bootstrap project root is invalid")
    normalized = root.resolve(strict=True)
    if normalized != root:
        raise _binding_failure("bootstrap project root is not normalized")
    if not invocation.command or any(
        argument.startswith(("--bootstrap-", "--caller-")) for argument in invocation.command
    ):
        raise RuntimeFailure(
            "AWP_CALLER_CONTEXT_INVALID", "command contains a reserved launcher argument"
        )
    return VerifiedRuntimeInvocation(
        project_root=normalized,
        caller_context_version=1,
        command=tuple(invocation.command),
        caller_fields=MappingProxyType(dict(invocation.caller_fields)),
    )
