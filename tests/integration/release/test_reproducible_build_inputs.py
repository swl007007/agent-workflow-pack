from __future__ import annotations

from agent_stack.release.gates import _source_date_epoch


def test_source_date_epoch_is_frozen_outside_commit_and_checkout_metadata() -> None:
    assert _source_date_epoch() == "315532800"
