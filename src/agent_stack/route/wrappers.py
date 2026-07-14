"""Closed native-light and existing-task wrapper dispatch."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from agent_stack.runtime.ports import (
    RouteDecisionVerifierPort,
    RouteVerifierPorts,
    bind_route_verifier_ports,
)
from agent_stack.runtime.runtime_load import (
    ImmutableDispatchBundle,
    TaskRuntimeLoadRequest,
    load_task_runtime,
)

from .approval import verify_task_creation_approval
from .calculator import VerifiedRouteAuthoritySnapshot
from .errors import RouteFailure
from .verifier import verify_route_decision


NativeLightDispatcher = Callable[["NativeLightDispatch"], object]
IntegratedDispatcher = Callable[[ImmutableDispatchBundle], object]


def _failure(code: str, message: str, **details: object) -> RouteFailure:
    return RouteFailure(code, message, details=details)


def _launcher(path: Path, project_root: Path | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    if not absolute.is_absolute() or absolute.parts[-3:] != (
        ".agent-workflow",
        "bin",
        "agent-stack",
    ):
        raise _failure(
            "AWP_ADAPTER_BYPASS_DETECTED",
            "wrapper does not use the repository launcher",
        )
    if absolute.is_symlink() or not absolute.is_file() or not os.access(absolute, os.X_OK):
        raise _failure(
            "AWP_ADAPTER_BYPASS_DETECTED",
            "repository launcher is unavailable or not executable",
        )
    if project_root is not None:
        expected = Path(os.path.abspath(project_root)) / ".agent-workflow/bin/agent-stack"
        if absolute != expected:
            raise _failure(
                "AWP_ADAPTER_BYPASS_DETECTED",
                "integrated wrapper launcher differs from task project",
            )
    return absolute


@dataclass(frozen=True)
class NativeLightDispatch:
    operation: str
    platform: str
    repository_launcher: Path
    entry_id: str
    decision_digest: str
    intent_digest: str

    def to_document(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "schema_id": "agent-workflow.native-light-dispatch",
                "schema_version": 1,
                "operation": self.operation,
                "platform": self.platform,
                "repository_launcher": str(self.repository_launcher),
                "entry_id": self.entry_id,
                "decision_digest": self.decision_digest,
                "intent_digest": self.intent_digest,
            }
        )


@dataclass(frozen=True)
class ExecuteLightRuntimeContext(Mapping[str, object]):
    platform: str
    repository_launcher: Path
    native_light_entry_id: str
    current_authorities: Mapping[str, object]
    decision_verifier: RouteDecisionVerifierPort
    dispatcher: NativeLightDispatcher

    def _public(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "repository_launcher": str(self.repository_launcher),
            "native_light_entry_id": self.native_light_entry_id,
        }

    def __getitem__(self, key: str) -> object:
        return self._public()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._public())

    def __len__(self) -> int:
        return len(self._public())


@dataclass(frozen=True)
class IntegratedWrapperInvocation:
    repository_launcher: Path
    load_request: TaskRuntimeLoadRequest
    dispatcher: IntegratedDispatcher


class _ProductionDecisionVerifier:
    """Adapt Runtime's frozen Mapping port to Route's typed authority snapshot."""

    def __call__(
        self,
        decision: Mapping[str, object],
        current_authorities: Mapping[str, object],
        consumer: str,
    ) -> Mapping[str, object]:
        expected = {field.name for field in fields(VerifiedRouteAuthoritySnapshot)}
        values = dict(current_authorities)
        if "extra_authorities" not in values:
            values["extra_authorities"] = {}
        if set(values) != expected:
            raise _failure(
                "AWP_ROUTE_POLICY_MISMATCH",
                "Runtime authority snapshot fields are not closed",
                missing=sorted(expected - set(values)),
                unknown=sorted(set(values) - expected),
            )
        try:
            snapshot = VerifiedRouteAuthoritySnapshot(**cast(Any, values))
        except (TypeError, ValueError) as error:
            raise _failure(
                "AWP_ROUTE_POLICY_MISMATCH", "Runtime authority snapshot is invalid"
            ) from error
        return verify_route_decision(decision, snapshot, consumer)


_PRODUCTION_ROUTE_PORTS = bind_route_verifier_ports(
    _ProductionDecisionVerifier(), verify_task_creation_approval
)


def production_route_verifier_ports() -> RouteVerifierPorts:
    """Return the one production binding; Runtime owns no verifier fallback."""

    return _PRODUCTION_ROUTE_PORTS


def invoke_execute_light(
    decision: Mapping[str, object], runtime_context: Mapping[str, object]
) -> object:
    """Reverify and dispatch one native-light Decision without task authority."""

    if not isinstance(runtime_context, ExecuteLightRuntimeContext):
        raise _failure(
            "AWP_ROUTE_OPERATION_MISMATCH", "verified execute-light runtime context is required"
        )
    launcher = _launcher(runtime_context.repository_launcher)
    if not callable(runtime_context.decision_verifier) or not callable(
        runtime_context.dispatcher
    ):
        raise _failure("AWP_ADAPTER_BYPASS_DETECTED", "native-light wrapper ports are invalid")
    verified = runtime_context.decision_verifier(
        decision, runtime_context.current_authorities, "execute-light"
    )
    if (
        verified.get("verification_kind") != "verified-execute-light"
        or verified.get("operation") != "execute-light"
        or verified.get("route") != "native-light"
        or verified.get("platform") != runtime_context.platform
        or verified.get("entry_owner") != runtime_context.native_light_entry_id
    ):
        raise _failure(
            "AWP_ROUTE_OPERATION_MISMATCH", "native-light Decision binding is invalid"
        )
    forbidden = {
        "requested_task_id",
        "requested_task_ref",
        "task_contract_surfaces",
        "approval_challenge",
        "task_creation_approval",
    }
    if forbidden & set(verified):
        raise _failure("AWP_ROUTE_OPERATION_MISMATCH", "native-light Decision carries task fields")
    decision_digest = verified.get("decision_digest")
    intent_digest = verified.get("intent_digest")
    if not isinstance(decision_digest, str) or not isinstance(intent_digest, str):
        raise _failure("AWP_ROUTE_DECISION_INVALID", "native-light Decision digests are absent")
    dispatch = NativeLightDispatch(
        operation="execute-light",
        platform=runtime_context.platform,
        repository_launcher=launcher,
        entry_id=runtime_context.native_light_entry_id,
        decision_digest=decision_digest,
        intent_digest=intent_digest,
    )
    return runtime_context.dispatcher(dispatch)


def _validate_bundle(bundle: ImmutableDispatchBundle) -> None:
    if bundle.mode == "speckit-superpowers":
        if (
            bundle.runtime_entry_id != "heavy-development-router"
            or bundle.surface_id != "runtime-entry:heavy-development-router"
        ):
            raise _failure(
                "AWP_ADAPTER_BYPASS_DETECTED",
                "heavy task bypasses heavy-development-router",
            )
    elif bundle.mode == "trellis-native":
        if bundle.runtime_entry_id == "heavy-development-router":
            raise _failure(
                "AWP_ADAPTER_BYPASS_DETECTED",
                "Trellis-native task entered the heavy router",
            )
    else:
        raise _failure("AWP_ROUTE_OPERATION_MISMATCH", "integrated bundle mode is invalid")


def invoke_integrated_wrapper(invocation: object) -> object:
    """Load current task authority once, then dispatch only the immutable bundle."""

    if not isinstance(invocation, IntegratedWrapperInvocation) or not callable(
        invocation.dispatcher
    ):
        raise _failure("AWP_ADAPTER_BYPASS_DETECTED", "integrated wrapper invocation is invalid")
    _launcher(invocation.repository_launcher, invocation.load_request.project_root)
    bundle = load_task_runtime(invocation.load_request)
    if not isinstance(bundle, ImmutableDispatchBundle):
        raise _failure("AWP_ADAPTER_BYPASS_DETECTED", "Runtime returned an invalid dispatch")
    _validate_bundle(bundle)
    return invocation.dispatcher(bundle)
