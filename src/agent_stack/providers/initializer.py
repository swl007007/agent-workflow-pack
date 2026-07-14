"""Provider initializer orchestration and deterministic output validation."""

from __future__ import annotations

import os
import secrets
import tempfile
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_stack.core.api import CANONICAL_NULL, CoreFailure, digest, normalize_path

from .approval import VerifiedProviderApproval
from .archive import content_root_digest
from .attempts import AttemptStore
from .broker import TrustedBroker
from .errors import ProviderFailure
from .models import ProviderExecutionResult, ProviderPlan
from .sandbox import run_sandboxed


_OUTPUT_FIELDS = {
    "schema_id",
    "schema_version",
    "provider_id",
    "provider_version",
    "command_digest",
    "input_digests",
    "locale",
    "timezone",
    "environment",
    "umask",
    "mode_policy_id",
    "file_order_policy_id",
    "renderer_id",
    "renderer_version",
    "expected_content_root_digest",
    "timeout_seconds",
    "max_output_bytes",
    "max_memory_bytes",
    "max_cpu_seconds",
}
_SECRET_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "PRIVATE_KEY", "PROXY")


def provider_cache_root() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "agent-workflow-pack"


def _positive_int(contract: Mapping[str, object], field: str) -> int:
    value = contract.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID",
            "initializer limit is invalid",
            details={"field": field},
        )
    return value


def _string_environment(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID", "initializer environment is invalid"
        )
    environment: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise ProviderFailure(
                "AWP_PROVIDER_PLAN_INVALID", "initializer environment is invalid"
            )
        environment[key] = item
    return environment


def _validate_contract(plan: ProviderPlan) -> Mapping[str, object]:
    contract = plan.deterministic_output_contract
    if set(contract) != _OUTPUT_FIELDS:
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID", "initializer output contract fields are not closed"
        )
    expected = {
        "schema_id": "agent-workflow.initializer-output-contract",
        "schema_version": 1,
        "provider_id": plan.provider_id,
        "provider_version": plan.provider_version,
        "command_digest": plan.command_digest,
        "input_digests": list(plan.input_digests),
        "locale": "C.UTF-8",
        "timezone": "UTC",
        "umask": "0022",
        "mode_policy_id": "posix-mode-v1",
        "file_order_policy_id": "normalized-path-order-v1",
    }
    mismatch = sorted(field for field, value in expected.items() if contract.get(field) != value)
    if mismatch:
        raise ProviderFailure(
            "AWP_PROVIDER_PLAN_INVALID", "initializer output contract disagrees with plan", details={"fields": mismatch}
        )
    if digest("agent-workflow.provider-command.v1", plan.command) != plan.command_digest:
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "provider command digest is invalid")
    for field in (
        "timeout_seconds",
        "max_output_bytes",
        "max_memory_bytes",
        "max_cpu_seconds",
        "renderer_version",
    ):
        _positive_int(contract, field)
    expected_root = contract.get("expected_content_root_digest")
    if not isinstance(expected_root, str) or len(expected_root) != 64:
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "expected content root is invalid")
    environment = _string_environment(contract.get("environment"))
    if any(any(marker in key.upper() for marker in _SECRET_MARKERS) for key in environment):
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "initializer environment contains a secret-like name")
    return contract


def _approval_digest(
    plan: ProviderPlan, approval: VerifiedProviderApproval | None, now: datetime
) -> str:
    if plan.measured_isolation_gaps:
        if approval is None:
            raise ProviderFailure(
                "AWP_PROVIDER_APPROVAL_REQUIRED", "measured isolation gap requires direct-human approval"
            )
        if (
            approval.provider_plan_digest != plan.provider_plan_digest
            or approval.prospective_transaction_id != plan.prospective_transaction_id
            or approval.expires_at <= now
        ):
            raise ProviderFailure(
                "AWP_PROVIDER_APPROVAL_INVALID", "verified provider approval is stale or mismatched"
            )
        return approval.approval_digest
    if approval is not None and approval.provider_plan_digest != plan.provider_plan_digest:
        raise ProviderFailure("AWP_PROVIDER_APPROVAL_INVALID", "provider approval plan mismatch")
    return approval.approval_digest if approval is not None else CANONICAL_NULL


def _provider_executable(cache_root: Path, plan: ProviderPlan) -> tuple[Path, tuple[str, ...]]:
    command = plan.command
    if set(command) != {"executable_id", "arguments"}:
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "provider command fields are not closed")
    executable_id = command.get("executable_id")
    arguments = command.get("arguments")
    if not isinstance(executable_id, str) or not isinstance(arguments, list) or not all(
        isinstance(item, str) for item in arguments
    ):
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "provider command is invalid")
    try:
        relative = normalize_path(executable_id)
    except CoreFailure as error:
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "provider executable id is invalid") from error
    provider_root = (
        cache_root
        / "extracted/sha256"
        / plan.provider_artifact_digest[:2]
        / plan.provider_artifact_digest
    )
    if provider_root.is_symlink() or not provider_root.is_dir():
        raise ProviderFailure("AWP_PROVIDER_CACHE_CORRUPT", "provider artifact root is unavailable")
    executable = provider_root / relative
    current = provider_root
    for segment in Path(relative).parts:
        current /= segment
        if current.is_symlink():
            raise ProviderFailure(
                "AWP_PROVIDER_CACHE_CORRUPT", "provider executable path contains a symlink"
            )
    try:
        resolved_root = provider_root.resolve(strict=True)
        resolved_executable = executable.resolve(strict=True)
    except OSError as error:
        raise ProviderFailure("AWP_PROVIDER_CACHE_CORRUPT", "provider executable is unavailable") from error
    if (
        not resolved_executable.is_relative_to(resolved_root)
        or not resolved_executable.is_file()
        or not os.access(resolved_executable, os.X_OK)
    ):
        raise ProviderFailure("AWP_PROVIDER_CACHE_CORRUPT", "provider executable is unsafe")
    return resolved_executable, tuple(arguments)


def execute_initializer(
    plan: ProviderPlan, approval: VerifiedProviderApproval | None
) -> ProviderExecutionResult:
    contract = _validate_contract(plan)
    now = datetime.now(UTC)
    approval_digest = _approval_digest(plan, approval, now)
    cache_root = provider_cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)
    executable, arguments = _provider_executable(cache_root, plan)
    attempt_id = str(uuid.uuid4())
    token = secrets.token_bytes(32)
    token_digest = __import__("hashlib").sha256(token).hexdigest()
    store = AttemptStore(
        cache_root,
        workspace_instance_id=plan.workspace_instance_id,
        provider_plan_digest=plan.provider_plan_digest,
        prospective_transaction_id=plan.prospective_transaction_id,
        approval_digest=approval_digest,
    )
    timeout_seconds = _positive_int(contract, "timeout_seconds")
    broker = TrustedBroker.start(
        store,
        attempt_id=attempt_id,
        release_token_digest=token_digest,
        deadline_seconds=min(timeout_seconds, 30),
    )
    prepared_at = now.isoformat().replace("+00:00", "Z")
    store.prepare(
        attempt_id=attempt_id,
        release_token_digest=token_digest,
        broker_liveness_identity=broker.liveness_identity,
        prepared_at=prepared_at,
        release_deadline=(now + timedelta(seconds=min(timeout_seconds, 30))).isoformat().replace("+00:00", "Z"),
        command_digest=plan.command_digest,
        isolation_measurements={
            control: ("gap" if control in plan.measured_isolation_gaps else "requested")
            for control in sorted(plan.requested_controls)
        },
    )
    broker.release_once(token)
    broker.wait(timeout=2)

    work_root = Path(tempfile.mkdtemp(prefix=f"provider-{attempt_id}-", dir=cache_root))
    home = work_root / "home"
    output = work_root / "output"
    for directory in (home, output, home / ".config", home / ".cache", home / ".local/share"):
        directory.mkdir(parents=True, exist_ok=True)
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "TZ": "UTC",
        "AWP_OUTPUT_DIR": str(output),
        **_string_environment(contract["environment"]),
    }
    try:
        execution = run_sandboxed(
            [str(executable), *arguments],
            cwd=executable.parents[1],
            environment=environment,
            timeout_seconds=timeout_seconds,
            max_output_bytes=_positive_int(contract, "max_output_bytes"),
            max_memory_bytes=_positive_int(contract, "max_memory_bytes"),
            max_cpu_seconds=_positive_int(contract, "max_cpu_seconds"),
            umask=0o022,
        )
    except ProviderFailure as error:
        store.record_terminal(
            attempt_id,
            state="interrupted",
            terminal_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            result_category=error.code,
            sanitized_output_digest=digest("agent-workflow.provider-diagnostics.v1", error.to_document()),
            candidate_output_digest=CANONICAL_NULL,
        )
        raise
    diagnostics_digest = digest(
        "agent-workflow.provider-diagnostics.v1",
        {
            "exit_code": execution.exit_code,
            "stdout_digest": __import__("hashlib").sha256(execution.stdout).hexdigest(),
            "stderr_digest": __import__("hashlib").sha256(execution.stderr).hexdigest(),
        },
    )
    if execution.exit_code != 0:
        store.record_terminal(
            attempt_id,
            state="failed",
            terminal_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            result_category="provider-exit-failure",
            sanitized_output_digest=diagnostics_digest,
            candidate_output_digest=CANONICAL_NULL,
        )
        raise ProviderFailure(
            "AWP_INITIALIZER_NONDETERMINISTIC", "initializer exited without a valid candidate"
        )
    candidate_digest = content_root_digest(output)
    if candidate_digest != contract["expected_content_root_digest"]:
        store.record_terminal(
            attempt_id,
            state="failed",
            terminal_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            result_category="content-root-mismatch",
            sanitized_output_digest=diagnostics_digest,
            candidate_output_digest=candidate_digest,
        )
        raise ProviderFailure(
            "AWP_INITIALIZER_NONDETERMINISTIC",
            "initializer output differs from the lock-bound content root",
        )
    store.record_terminal(
        attempt_id,
        state="succeeded",
        terminal_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        result_category="validated",
        sanitized_output_digest=diagnostics_digest,
        candidate_output_digest=candidate_digest,
    )
    return ProviderExecutionResult(
        provider_plan_digest=plan.provider_plan_digest,
        approval_digest=approval_digest,
        attempt_id=attempt_id,
        terminal_state="succeeded",
        containment_evidence_digest=execution.containment_evidence_digest,
        result_category="validated",
        candidate_output_root_digest=candidate_digest,
        candidate_output_path=str(output),
        diagnostics_digest=diagnostics_digest,
        provenance_records=(),
    )
