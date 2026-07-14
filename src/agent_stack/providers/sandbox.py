"""Minimal process-group containment liveness and termination primitives."""

from __future__ import annotations

import os
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
