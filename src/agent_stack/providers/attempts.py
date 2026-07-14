"""Whole-file provider attempt journal and immutable release receipts."""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from agent_stack.core.api import CANONICAL_NULL, canonical_json_bytes

from .errors import ProviderFailure


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL = frozenset({"succeeded", "failed", "interrupted"})


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    state: str
    release_token_digest: str
    broker_liveness_identity: str
    document: Mapping[str, object]


def _corrupt(message: str, **details: object) -> ProviderFailure:
    return ProviderFailure("AWP_PROVIDER_ATTEMPT_CORRUPT", message, details=details)


def _uuid(value: str, label: str) -> str:
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError) as error:
        raise _corrupt(f"{label} is not a canonical UUID") from error
    if parsed != value:
        raise _corrupt(f"{label} is not a canonical UUID")
    return value


def _digest(value: str, label: str, *, allow_null: bool = False) -> str:
    if allow_null and value == CANONICAL_NULL:
        return value
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise _corrupt(f"{label} is not lowercase SHA-256")
    return value


class AttemptStore:
    """Serialize one immutable provider plan's retry/audit state under an OS lock."""

    def __init__(
        self,
        root: Path,
        *,
        workspace_instance_id: str,
        provider_plan_digest: str,
        prospective_transaction_id: str,
        approval_digest: str,
    ) -> None:
        self.root = root
        self.workspace_instance_id = _uuid(workspace_instance_id, "workspace_instance_id")
        self.provider_plan_digest = _digest(provider_plan_digest, "provider_plan_digest")
        self.prospective_transaction_id = _uuid(
            prospective_transaction_id, "prospective_transaction_id"
        )
        self.approval_digest = _digest(approval_digest, "approval_digest", allow_null=True)
        self.journal_path = (
            root
            / "provider-attempts"
            / self.workspace_instance_id
            / f"{self.provider_plan_digest}.json"
        )
        self.receipt_root = self.journal_path.with_suffix(".releases")
        self.lock_path = root / "locks" / f"provider-{self.provider_plan_digest}.lock"
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self.receipt_root.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

    def release_receipt_path(self, attempt_id: str) -> Path:
        return self.receipt_root / f"{_uuid(attempt_id, 'attempt_id')}.json"

    @contextmanager
    def _lock(self) -> Iterator[None]:
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.lock_path, flags, 0o600)
        except OSError as error:
            raise _corrupt("cannot open provider-plan lock") from error
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _empty(self) -> dict[str, object]:
        return {
            "schema_id": "agent-workflow.provider-attempts",
            "schema_version": 1,
            "workspace_instance_id": self.workspace_instance_id,
            "provider_plan_digest": self.provider_plan_digest,
            "prospective_transaction_id": self.prospective_transaction_id,
            "approval_digest": self.approval_digest,
            "attempts": [],
        }

    def _load(self) -> dict[str, object]:
        if not self.journal_path.exists():
            return self._empty()
        if self.journal_path.is_symlink() or not self.journal_path.is_file():
            raise _corrupt("attempt journal is not a regular file")
        try:
            document = json.loads(self.journal_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise _corrupt("attempt journal is corrupt JSON") from error
        if not isinstance(document, dict):
            raise _corrupt("attempt journal must be an object")
        expected = self._empty()
        for field in (
            "schema_id",
            "schema_version",
            "workspace_instance_id",
            "provider_plan_digest",
            "prospective_transaction_id",
            "approval_digest",
        ):
            if document.get(field) != expected[field]:
                raise _corrupt("attempt journal identity mismatch", field=field)
        if set(document) != set(expected) or not isinstance(document.get("attempts"), list):
            raise _corrupt("attempt journal fields are not closed")
        self._validate_attempts(document["attempts"])
        return document

    def _validate_attempts(self, raw_attempts: object) -> None:
        if not isinstance(raw_attempts, list):
            raise _corrupt("attempts must be an array")
        ids: set[str] = set()
        tokens: set[str] = set()
        live_count = 0
        for raw in raw_attempts:
            if not isinstance(raw, dict):
                raise _corrupt("attempt record must be an object")
            attempt_id = _uuid(str(raw.get("attempt_id")), "attempt_id")
            token = _digest(str(raw.get("release_token_digest")), "release_token_digest")
            state = raw.get("state")
            if state not in {"prepared", "released"} | _TERMINAL:
                raise _corrupt("attempt state is invalid", state=state)
            if attempt_id in ids or token in tokens:
                raise _corrupt("attempt id or release token repeats")
            ids.add(attempt_id)
            tokens.add(token)
            if state in {"prepared", "released"}:
                live_count += 1
        if live_count > 1:
            raise _corrupt("multiple provider attempts overlap")

    def _write(self, document: Mapping[str, object]) -> None:
        self._validate_attempts(document.get("attempts"))
        descriptor, raw_path = tempfile.mkstemp(
            prefix=f".{self.provider_plan_digest}.",
            suffix=".tmp",
            dir=self.journal_path.parent,
        )
        temporary = Path(raw_path)
        try:
            payload = canonical_json_bytes(document)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.journal_path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _record(raw: Mapping[str, object]) -> AttemptRecord:
        return AttemptRecord(
            attempt_id=str(raw["attempt_id"]),
            state=str(raw["state"]),
            release_token_digest=str(raw["release_token_digest"]),
            broker_liveness_identity=str(raw["broker_liveness_identity"]),
            document=dict(raw),
        )

    @staticmethod
    def _find(document: Mapping[str, object], attempt_id: str) -> tuple[list[object], int, dict[str, object]]:
        attempts = document.get("attempts")
        if not isinstance(attempts, list):
            raise _corrupt("attempt journal has no attempts array")
        for index, raw in enumerate(attempts):
            if isinstance(raw, dict) and raw.get("attempt_id") == attempt_id:
                return attempts, index, raw
        raise _corrupt("attempt id does not exist", attempt_id=attempt_id)

    def prepare(
        self,
        *,
        attempt_id: str,
        release_token_digest: str,
        broker_liveness_identity: str,
        prepared_at: str,
        release_deadline: str,
        command_digest: str,
        isolation_measurements: Mapping[str, object],
    ) -> AttemptRecord:
        with self._lock():
            document = self._load()
            attempts = document["attempts"]
            assert isinstance(attempts, list)
            if any(
                isinstance(raw, dict) and raw.get("state") in {"prepared", "released"}
                for raw in attempts
            ):
                raise _corrupt("a provider attempt is already live or ambiguous")
            normalized_id = _uuid(attempt_id, "attempt_id")
            token = _digest(release_token_digest, "release_token_digest")
            if any(
                isinstance(raw, dict)
                and (raw.get("attempt_id") == normalized_id or raw.get("release_token_digest") == token)
                for raw in attempts
            ):
                raise _corrupt("attempt id or release token repeats")
            if not broker_liveness_identity:
                raise _corrupt("broker liveness identity is empty")
            record: dict[str, object] = {
                "attempt_id": normalized_id,
                "state": "prepared",
                "release_token_digest": token,
                "broker_liveness_identity": broker_liveness_identity,
                "prepared_at": prepared_at,
                "release_deadline": release_deadline,
                "command_digest": _digest(command_digest, "command_digest"),
                "isolation_measurements": dict(isolation_measurements),
            }
            attempts.append(record)
            self._write(document)
            return self._record(record)

    def _validate_receipt(
        self, attempt: Mapping[str, object], receipt: Mapping[str, object]
    ) -> None:
        expected_fields = {
            "schema_id",
            "schema_version",
            "workspace_instance_id",
            "provider_plan_digest",
            "prospective_transaction_id",
            "attempt_id",
            "release_token_digest",
            "broker_liveness_identity",
            "released_at",
        }
        if set(receipt) != expected_fields:
            raise _corrupt("release receipt fields are not closed")
        expected = {
            "schema_id": "agent-workflow.provider-release-receipt",
            "schema_version": 1,
            "workspace_instance_id": self.workspace_instance_id,
            "provider_plan_digest": self.provider_plan_digest,
            "prospective_transaction_id": self.prospective_transaction_id,
            "attempt_id": attempt.get("attempt_id"),
            "release_token_digest": attempt.get("release_token_digest"),
            "broker_liveness_identity": attempt.get("broker_liveness_identity"),
        }
        mismatches = sorted(field for field, value in expected.items() if receipt.get(field) != value)
        if mismatches or not isinstance(receipt.get("released_at"), str):
            raise _corrupt("release receipt identity mismatch", fields=mismatches)

    def _write_receipt(self, attempt_id: str, receipt: Mapping[str, object]) -> None:
        path = self.release_receipt_path(attempt_id)
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o444,
            )
        except FileExistsError as error:
            raise _corrupt("release receipt already exists") from error
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(canonical_json_bytes(receipt))
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def record_released(
        self, attempt_id: str, receipt: Mapping[str, object]
    ) -> AttemptRecord:
        with self._lock():
            document = self._load()
            attempts, index, attempt = self._find(document, attempt_id)
            if attempt.get("state") != "prepared":
                raise _corrupt("only a prepared attempt may become released")
            self._validate_receipt(attempt, receipt)
            stored_receipt = self._load_receipt(attempt_id)
            if stored_receipt is None:
                self._write_receipt(attempt_id, receipt)
            elif stored_receipt != receipt:
                raise _corrupt("stored release receipt disagrees with broker acknowledgement")
            released = {
                **attempt,
                "state": "released",
                "released_at": receipt["released_at"],
            }
            attempts[index] = released
            self._write(document)
            return self._record(released)

    def get_attempt(self, attempt_id: str) -> AttemptRecord:
        """Read one validated attempt under the provider-plan lock."""

        with self._lock():
            document = self._load()
            _, _, attempt = self._find(document, attempt_id)
            return self._record(attempt)

    def record_terminal(
        self,
        attempt_id: str,
        *,
        state: str,
        terminal_at: str,
        result_category: str,
        sanitized_output_digest: str,
        candidate_output_digest: str,
    ) -> AttemptRecord:
        if state not in _TERMINAL:
            raise _corrupt("terminal attempt state is invalid")
        with self._lock():
            document = self._load()
            attempts, index, attempt = self._find(document, attempt_id)
            if attempt.get("state") != "released":
                raise _corrupt("only a released attempt may record a provider result")
            terminal = {
                **attempt,
                "state": state,
                "terminal_at": terminal_at,
                "result_category": result_category,
                "sanitized_output_digest": _digest(
                    sanitized_output_digest, "sanitized_output_digest"
                ),
                "candidate_output_digest": _digest(
                    candidate_output_digest, "candidate_output_digest", allow_null=True
                ),
            }
            attempts[index] = terminal
            self._write(document)
            return self._record(terminal)

    def _load_receipt(self, attempt_id: str) -> Mapping[str, object] | None:
        path = self.release_receipt_path(attempt_id)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file():
            raise _corrupt("release receipt is not a regular file")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise _corrupt("release receipt is corrupt") from error
        if not isinstance(value, dict):
            raise _corrupt("release receipt must be an object")
        return value

    def recover_interrupted(
        self,
        attempt_id: str,
        *,
        containment_state: str,
        receipt: Mapping[str, object] | None,
        recorded_at: str,
    ) -> AttemptRecord:
        if containment_state in {"live", "ambiguous"}:
            raise ProviderFailure(
                "AWP_PROVIDER_CONTAINMENT_AMBIGUOUS",
                "prior provider containment is still live or ambiguous",
            )
        if containment_state != "gone":
            raise _corrupt("containment liveness state is invalid")
        with self._lock():
            document = self._load()
            attempts, index, attempt = self._find(document, attempt_id)
            if attempt.get("state") in _TERMINAL:
                return self._record(attempt)
            stored_receipt = self._load_receipt(attempt_id)
            effective_receipt = receipt or stored_receipt
            if receipt is not None and stored_receipt is not None and receipt != stored_receipt:
                raise _corrupt("supplied and stored release receipts disagree")
            if effective_receipt is not None:
                self._validate_receipt(attempt, effective_receipt)
                if stored_receipt is None:
                    raise _corrupt("recovery receipt was not durably present")
            interrupted = {
                **attempt,
                "state": "interrupted",
                "terminal_at": recorded_at,
                "result_category": "interrupted",
                "sanitized_output_digest": CANONICAL_NULL,
                "candidate_output_digest": CANONICAL_NULL,
            }
            attempts[index] = interrupted
            self._write(document)
            return self._record(interrupted)
