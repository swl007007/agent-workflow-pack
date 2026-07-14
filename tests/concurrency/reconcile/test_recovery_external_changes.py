from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.reconcile.api import recover_transaction
from agent_stack.reconcile.errors import RendererFailure
from tests.integration.reconcile.apply_helpers import RecordingScanner
from tests.integration.reconcile.test_recovery import interrupt_apply


@pytest.mark.parametrize("killpoint", ["applying", "files_applied"])
def test_rollback_preserves_external_third_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    killpoint: str,
) -> None:
    envelope, task_state, approval = interrupt_apply(tmp_path, monkeypatch, killpoint)
    target = tmp_path / "generated/config.txt"
    target.write_bytes(b"external\n")

    with pytest.raises(RendererFailure, match="AWP_ROLLBACK_CONFLICT"):
        recover_transaction(
            str(envelope.plan_core["transaction_id"]),
            "rollback",
            root=tmp_path,
            scanner=RecordingScanner([task_state]),
            scanner_context=approval,
        )

    assert target.read_bytes() == b"external\n"


def test_resume_rejects_external_change_instead_of_overwriting_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope, task_state, approval = interrupt_apply(tmp_path, monkeypatch, "applying")
    target = tmp_path / "generated/config.txt"
    target.write_bytes(b"external\n")

    with pytest.raises(RendererFailure, match="AWP_FILE_CAS_MISMATCH"):
        recover_transaction(
            str(envelope.plan_core["transaction_id"]),
            "resume",
            root=tmp_path,
            scanner=RecordingScanner([task_state]),
            scanner_context=approval,
        )

    assert target.read_bytes() == b"external\n"
