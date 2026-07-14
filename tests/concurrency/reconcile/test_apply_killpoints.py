from __future__ import annotations

from pathlib import Path

import pytest

import agent_stack.reconcile.apply as apply_module
from agent_stack.reconcile.api import apply_plan
from tests.integration.reconcile.apply_helpers import (
    RecordingScanner,
    make_apply_case,
    read_json,
)


class InjectedTermination(BaseException):
    pass


@pytest.mark.parametrize(
    ("killpoint", "committed"),
    [
        ("planned", False),
        ("probing", False),
        ("prepared", False),
        ("applying", False),
        ("files_applied", False),
        ("before_manifest", False),
        ("after_manifest", True),
        ("manifest_committed", True),
        ("cleanup_pending", True),
    ],
)
def test_every_apply_killpoint_has_one_recognizable_commit_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    killpoint: str,
    committed: bool,
) -> None:
    envelope, task_state, approval = make_apply_case(tmp_path)

    def terminate(point: str) -> None:
        if point == killpoint:
            raise InjectedTermination(point)

    monkeypatch.setattr(apply_module, "_crash_at", terminate)
    with pytest.raises(InjectedTermination):
        apply_plan(envelope, approval, scanner=RecordingScanner([task_state, task_state]))

    manifest = read_json(tmp_path / ".agent-workflow/manifest.json")
    assert (
        manifest.get("last_transaction_binding_digest")
        == envelope.journal_binding_digest
    ) is committed
    journal = read_json(
        tmp_path / f".agent-workflow/transactions/{envelope.plan_core['transaction_id']}.json"
    )
    assert journal["journal_binding_digest"] == envelope.journal_binding_digest
