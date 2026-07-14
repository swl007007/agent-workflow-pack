"""First-party one-token broker that durably receipts provider release."""

from __future__ import annotations

import ctypes
import hashlib
import json
import multiprocessing
import os
import select
import signal
import struct
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from agent_stack.core.api import canonical_json_bytes

from .attempts import AttemptRecord, AttemptStore
from .errors import ProviderFailure


_PR_SET_PDEATHSIG = 1
_MAX_TOKEN_BYTES = 4096


def _arm_parent_death(expected_parent: int) -> bool:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
            return False
    except (AttributeError, OSError):
        return False
    return os.getppid() == expected_parent


def _read_exact(descriptor: int, size: int, deadline: float) -> bytes | None:
    chunks = bytearray()
    while len(chunks) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        readable, _, _ = select.select([descriptor], [], [], remaining)
        if not readable:
            return None
        chunk = os.read(descriptor, size - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


def _broker_main(
    control_read: int,
    unused_control_write: int,
    unused_ack_read: int,
    ack_write: int,
    parent_pid: int,
    receipt_path: str,
    workspace_instance_id: str,
    provider_plan_digest: str,
    prospective_transaction_id: str,
    attempt_id: str,
    expected_token_digest: str,
    deadline_seconds: float,
) -> None:
    try:
        os.close(unused_control_write)
        os.close(unused_ack_read)
        os.setsid()
        if not _arm_parent_death(parent_pid):
            return
        liveness_identity = f"pid:{os.getpid()}:{parent_pid}"
        deadline = time.monotonic() + max(deadline_seconds, 0)
        header = _read_exact(control_read, 4, deadline)
        if header is None:
            return
        (length,) = struct.unpack("!I", header)
        if length <= 0 or length > _MAX_TOKEN_BYTES:
            return
        token = _read_exact(control_read, length, deadline)
        if token is None or hashlib.sha256(token).hexdigest() != expected_token_digest:
            return
        receipt = {
            "schema_id": "agent-workflow.provider-release-receipt",
            "schema_version": 1,
            "workspace_instance_id": workspace_instance_id,
            "provider_plan_digest": provider_plan_digest,
            "prospective_transaction_id": prospective_transaction_id,
            "attempt_id": attempt_id,
            "release_token_digest": expected_token_digest,
            "broker_liveness_identity": liveness_identity,
            "released_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(receipt_path, flags, 0o444)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(receipt))
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                os.unlink(receipt_path)
            except OSError:
                pass
            raise
        os.write(ack_write, b"RELEASED")
    finally:
        for descriptor in (control_read, ack_write):
            try:
                os.close(descriptor)
            except OSError:
                pass


@dataclass
class TrustedBroker:
    store: AttemptStore
    attempt_id: str
    release_token_digest: str
    process: multiprocessing.Process
    control_write: int
    ack_read: int
    liveness_identity: str
    _closed: bool = False
    _released: bool = False

    @classmethod
    def start(
        cls,
        store: AttemptStore,
        *,
        attempt_id: str,
        release_token_digest: str,
        deadline_seconds: float,
    ) -> TrustedBroker:
        control_read, control_write = os.pipe()
        ack_read, ack_write = os.pipe()
        parent_pid = os.getpid()
        process = multiprocessing.Process(
            target=_broker_main,
            args=(
                control_read,
                control_write,
                ack_read,
                ack_write,
                parent_pid,
                str(store.release_receipt_path(attempt_id)),
                store.workspace_instance_id,
                store.provider_plan_digest,
                store.prospective_transaction_id,
                attempt_id,
                release_token_digest,
                deadline_seconds,
            ),
        )
        process.start()
        os.close(control_read)
        os.close(ack_write)
        identity = f"pid:{process.pid}:{parent_pid}"
        return cls(
            store=store,
            attempt_id=attempt_id,
            release_token_digest=release_token_digest,
            process=process,
            control_write=control_write,
            ack_read=ack_read,
            liveness_identity=identity,
        )

    def liveness(self) -> str:
        if self.process.is_alive():
            return "live"
        if self.process.exitcode is not None:
            return "gone"
        return "ambiguous"

    def _close_descriptors(self) -> None:
        if self._closed:
            return
        for descriptor in (self.control_write, self.ack_read):
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._closed = True

    def release_once(self, token: bytes) -> AttemptRecord:
        if self._released or self._closed:
            raise ProviderFailure(
                "AWP_PROVIDER_ATTEMPT_CORRUPT", "broker release token is not reusable"
            )
        attempt = self.store.get_attempt(self.attempt_id)
        if (
            attempt.state != "prepared"
            or attempt.release_token_digest != self.release_token_digest
            or attempt.broker_liveness_identity != self.liveness_identity
        ):
            raise ProviderFailure(
                "AWP_PROVIDER_ATTEMPT_CORRUPT",
                "broker release is not bound to durable prepared state",
            )
        if hashlib.sha256(token).hexdigest() != self.release_token_digest:
            self.close_without_release()
            raise ProviderFailure(
                "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS", "broker release token is invalid"
            )
        frame = struct.pack("!I", len(token)) + token
        try:
            os.write(self.control_write, frame)
            os.close(self.control_write)
            self.control_write = -1
            readable, _, _ = select.select([self.ack_read], [], [], 5)
            acknowledgement = os.read(self.ack_read, 8) if readable else b""
        except OSError as error:
            self._close_descriptors()
            raise ProviderFailure(
                "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS", "broker handshake failed"
            ) from error
        if acknowledgement != b"RELEASED":
            self._close_descriptors()
            raise ProviderFailure(
                "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS", "broker did not acknowledge release"
            )
        receipt_path = self.store.release_receipt_path(self.attempt_id)
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            self._close_descriptors()
            raise ProviderFailure(
                "AWP_PROVIDER_ATTEMPT_CORRUPT", "broker receipt is missing or corrupt"
            ) from error
        if not isinstance(receipt, dict):
            raise ProviderFailure(
                "AWP_PROVIDER_ATTEMPT_CORRUPT", "broker receipt is not an object"
            )
        self._released = True
        self._close_descriptors()
        return self.store.record_released(self.attempt_id, receipt)

    def close_without_release(self) -> None:
        self._close_descriptors()

    def terminate(self) -> None:
        self._close_descriptors()
        if self.process.is_alive():
            self.process.kill()

    def wait(self, *, timeout: float) -> None:
        self.process.join(timeout)
        if self.process.is_alive():
            raise ProviderFailure(
                "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS", "broker did not exit before deadline"
            )
