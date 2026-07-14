"""Durable standalone filesystem-probe transactions for ``doctor --write-probe``."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType

from agent_stack.core.api import canonical_json_bytes

from .errors import RendererFailure
from .locks import acquire_project_locks
from .probes import ProbeEvidence, run_write_probe


_JOURNAL_ROOT = ".agent-workflow/local/probe-transactions"


def _hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _expected_files() -> list[dict[str, object]]:
    first = _hash(b"first")
    second = _hash(b"second")
    values = {
        "lock": [_hash(b"")],
        "original": [_hash(b"original"), _hash(b"candidate")],
        "candidate": [_hash(b"candidate")],
        "CaseProbe": [first],
        "caseprobe": [second],
        "café-probe": [first],
        unicodedata.normalize("NFD", "café-probe"): [second],
    }
    return [
        {"name_utf8_hex": name.encode("utf-8").hex(), "sha256": hashes}
        for name, hashes in sorted(values.items(), key=lambda item: item[0].encode("utf-8"))
    ]


def _failure(message: str, **details: object) -> RendererFailure:
    return RendererFailure(
        "AWP_RECONCILE_RECOVERY_REQUIRED", message, details=details
    )


def _journal_path(root: Path, probe_id: str) -> Path:
    try:
        canonical = str(uuid.UUID(probe_id))
    except ValueError as error:
        raise _failure("standalone probe identity is invalid") from error
    if canonical != probe_id:
        raise _failure("standalone probe identity is not canonical")
    return root / _JOURNAL_ROOT / f"{probe_id}.json"


def _atomic_write(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(canonical_json_bytes(document))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _load(root: Path, probe_id: str) -> dict[str, object]:
    path = _journal_path(root, probe_id)
    if path.is_symlink() or not path.is_file():
        raise _failure("standalone probe journal is unavailable")
    try:
        body = path.read_bytes()
        document = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise _failure("standalone probe journal is invalid") from error
    expected = {
        "schema_id",
        "schema_version",
        "probe_id",
        "status",
        "expected_file_hashes",
        "evidence",
    }
    if (
        not isinstance(document, dict)
        or canonical_json_bytes(document) != body
        or set(document) != expected
        or document.get("schema_id") != "agent-workflow.probe-transaction"
        or document.get("schema_version") != 1
        or document.get("probe_id") != probe_id
        or document.get("status") not in {"prepared", "complete", "rolled-back"}
        or document.get("expected_file_hashes") != _expected_files()
    ):
        raise _failure("standalone probe journal contract is invalid")
    return document


def _evidence_document(evidence: ProbeEvidence) -> dict[str, object]:
    return {
        "probe_id": evidence.probe_id,
        "supported": evidence.supported,
        "advisory_lock": evidence.advisory_lock,
        "atomic_replace": evidence.atomic_replace,
        "posix_mode": evidence.posix_mode,
        "case_behavior": evidence.case_behavior,
        "unicode_behavior": evidence.unicode_behavior,
        "filesystem_type": evidence.filesystem_type,
        "evidence_digest": evidence.evidence_digest,
    }


def _cleanup_recorded_residue(root: Path, journal: Mapping[str, object]) -> None:
    probe_id = str(journal["probe_id"])
    residue = root / f".agent-workflow-probe-{probe_id}"
    if not residue.exists() and not residue.is_symlink():
        return
    if residue.is_symlink() or not residue.is_dir():
        raise _failure("standalone probe residue is not a real directory")
    raw_expected = journal.get("expected_file_hashes")
    if not isinstance(raw_expected, Sequence) or isinstance(raw_expected, (str, bytes)):
        raise _failure("standalone probe residue contract is invalid")
    expected: dict[str, tuple[str, ...]] = {}
    for raw in raw_expected:
        if not isinstance(raw, Mapping) or set(raw) != {"name_utf8_hex", "sha256"}:
            raise _failure("standalone probe residue hashes are invalid")
        name_hex = raw.get("name_utf8_hex")
        hashes = raw.get("sha256")
        if not isinstance(name_hex, str) or not isinstance(hashes, list):
            raise _failure("standalone probe residue hashes are invalid")
        try:
            name = bytes.fromhex(name_hex).decode("utf-8")
        except (ValueError, UnicodeError) as error:
            raise _failure("standalone probe residue filename is invalid") from error
        expected[name] = tuple(str(value) for value in hashes)
    actual = {path.name for path in residue.iterdir()}
    unknown = sorted(actual - set(expected))
    if unknown:
        raise _failure("standalone probe residue has unknown paths", paths=unknown)
    for name in sorted(actual):
        path = residue / name
        if path.is_symlink() or not path.is_file():
            raise _failure("standalone probe residue path changed type", path=name)
        if hashlib.sha256(path.read_bytes()).hexdigest() not in expected[name]:
            raise _failure("standalone probe residue bytes changed", path=name)
        path.unlink()
    residue.rmdir()


def run_standalone_probe(root: Path) -> Mapping[str, object]:
    probe_id = str(uuid.uuid4())
    journal = {
        "schema_id": "agent-workflow.probe-transaction",
        "schema_version": 1,
        "probe_id": probe_id,
        "status": "prepared",
        "expected_file_hashes": _expected_files(),
        "evidence": None,
    }
    with acquire_project_locks(root):
        _atomic_write(_journal_path(root, probe_id), journal)
        evidence = run_write_probe(root, probe_id=probe_id)
        journal["status"] = "complete"
        journal["evidence"] = _evidence_document(evidence)
        _atomic_write(_journal_path(root, probe_id), journal)
    return MappingProxyType(dict(journal))


def recover_standalone_probe(
    root: Path, probe_id: str, *, action: str
) -> Mapping[str, object]:
    if action not in {"resume", "rollback"}:
        raise _failure("standalone probe recovery action is invalid")
    with acquire_project_locks(root):
        journal = _load(root, probe_id)
        if journal["status"] == "complete":
            if action == "rollback":
                raise _failure("completed standalone probe cannot be rolled back")
            return MappingProxyType(dict(journal))
        _cleanup_recorded_residue(root, journal)
        if action == "rollback":
            journal["status"] = "rolled-back"
            _atomic_write(_journal_path(root, probe_id), journal)
            return MappingProxyType(dict(journal))
        evidence = run_write_probe(root, probe_id=probe_id)
        journal["status"] = "complete"
        journal["evidence"] = _evidence_document(evidence)
        _atomic_write(_journal_path(root, probe_id), journal)
        return MappingProxyType(dict(journal))


__all__ = ["recover_standalone_probe", "run_standalone_probe"]
