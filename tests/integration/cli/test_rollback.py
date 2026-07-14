from __future__ import annotations

from agent_stack.release.distribution import UpgradeRequest, orchestrate_upgrade
from agent_stack.release.manifest import ReleaseLocator
from tests.integration.cli.test_upgrade import edge, local_contract, ports, release, with_edges


def test_supported_rollback_is_a_forward_transaction_owned_by_current_runtime() -> None:
    older = release("0.1.0", "b")
    current_base = release("0.2.0", "c")
    current = with_edges(current_base, [edge(current_base, older)])
    events: list[str] = []

    result = orchestrate_upgrade(
        UpgradeRequest(
            installed_release=current,
            running_release=current,
            local_state_contract=local_contract(),
            target_version="0.1.0",
        ),
        ports(
            events=events,
            candidate=older,
            locate=lambda version: ReleaseLocator(version, older.manifest_digest),
        ),
    )

    assert result.target_release_id == older.identity.release_id
    assert result.recovery_runtime.runtime_role == "committed"
    assert "resolve:0.1.0:current" in events
    assert events.index("inspect-static:0.1.0") < events.index("resolve:0.1.0:current")
