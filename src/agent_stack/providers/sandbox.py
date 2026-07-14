"""Minimal process-group containment liveness and termination primitives."""

from __future__ import annotations

import os
import resource
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .errors import ProviderFailure


@dataclass(frozen=True)
class Containment:
    process: subprocess.Popen[bytes]
    process_group_id: int


@dataclass(frozen=True)
class SandboxExecutionResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    containment_evidence_digest: str


def start_containment(
    command: Sequence[str], *, cwd: Path, environment: Mapping[str, str]
) -> Containment:
    """Start one command in a new process group with closed stdin."""

    if not command or not all(isinstance(item, str) and item for item in command):
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "containment command is invalid")
    if cwd.is_symlink() or not cwd.is_dir():
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "containment cwd is invalid")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise ProviderFailure(
            "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS", "cannot start provider containment"
        ) from error
    return Containment(process=process, process_group_id=process.pid)


def containment_liveness(containment: Containment) -> str:
    """Return positive live/gone evidence for a locally owned Popen handle."""

    return "live" if containment.process.poll() is None else "gone"


def terminate_containment(containment: Containment, *, timeout: float) -> None:
    """Terminate the complete process group, escalating only after a deadline."""

    if containment_liveness(containment) == "gone":
        return
    try:
        os.killpg(containment.process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        containment.process.poll()
        return
    deadline = time.monotonic() + max(timeout, 0)
    while time.monotonic() < deadline:
        if containment.process.poll() is not None:
            return
        time.sleep(0.01)
    try:
        os.killpg(containment.process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        containment.process.wait(timeout=max(timeout, 0.1))
    except subprocess.TimeoutExpired as error:
        raise ProviderFailure(
            "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS",
            "provider process group did not terminate",
        ) from error


def run_sandboxed(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    max_output_bytes: int,
    max_memory_bytes: int,
    max_cpu_seconds: int,
    umask: int,
) -> SandboxExecutionResult:
    """Run a bounded command with closed stdin and a clean caller-supplied environment."""

    if min(timeout_seconds, max_output_bytes, max_memory_bytes, max_cpu_seconds) <= 0:
        raise ProviderFailure("AWP_PROVIDER_PLAN_INVALID", "sandbox limits must be positive")

    def limits() -> None:
        os.umask(umask)
        resource.setrlimit(resource.RLIMIT_CPU, (max_cpu_seconds, max_cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))

    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=limits,
        )
    except OSError as error:
        raise ProviderFailure(
            "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS", "cannot start initializer containment"
        ) from error
    containment = Containment(process=process, process_group_id=process.pid)
    stdout_stream = process.stdout
    stderr_stream = process.stderr
    if stdout_stream is None or stderr_stream is None:
        terminate_containment(containment, timeout=1)
        raise ProviderFailure(
            "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS", "initializer output pipes are unavailable"
        )
    output = {"stdout": bytearray(), "stderr": bytearray()}
    selector = selectors.DefaultSelector()
    selector.register(stdout_stream, selectors.EVENT_READ, "stdout")
    selector.register(stderr_stream, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminate_containment(containment, timeout=1)
                raise ProviderFailure(
                    "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS",
                    "initializer exceeded its time limit",
                )
            events = selector.select(remaining)
            if not events:
                terminate_containment(containment, timeout=1)
                raise ProviderFailure(
                    "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS",
                    "initializer exceeded its time limit",
                )
            for key, _ in events:
                total = len(output["stdout"]) + len(output["stderr"])
                read_size = max(1, min(65536, max_output_bytes - total + 1))
                chunk = os.read(key.fd, read_size)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                label = str(key.data)
                output[label].extend(chunk)
                if len(output["stdout"]) + len(output["stderr"]) > max_output_bytes:
                    terminate_containment(containment, timeout=1)
                    raise ProviderFailure(
                        "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS",
                        "initializer exceeded its output limit",
                    )
        try:
            process.wait(timeout=max(deadline - time.monotonic(), 0.001))
        except subprocess.TimeoutExpired as error:
            terminate_containment(containment, timeout=1)
            raise ProviderFailure(
                "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS",
                "initializer exceeded its time limit",
            ) from error
    finally:
        selector.close()
        stdout_stream.close()
        stderr_stream.close()
    stdout = bytes(output["stdout"])
    stderr = bytes(output["stderr"])
    from agent_stack.core.api import digest

    evidence_digest = digest(
        "agent-workflow.provider-containment.v1",
        {
            "exit_code": process.returncode,
            "stdout_bytes": len(stdout),
            "stderr_bytes": len(stderr),
            "process_group_ended": containment_liveness(containment) == "gone",
        },
    )
    return SandboxExecutionResult(process.returncode, stdout, stderr, evidence_digest)
