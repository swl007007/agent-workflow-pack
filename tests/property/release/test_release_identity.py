from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.release.identity import ReleaseIdentity, release_id


IDENTIFIER = st.from_regex(r"[a-z][a-z0-9-]{0,20}", fullmatch=True)
VERSION = st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True)


@given(owner=IDENTIFIER, repository=IDENTIFIER, version=VERSION)
def test_release_identity_is_distribution_form_independent(
    owner: str, repository: str, version: str
) -> None:
    repository_id = f"github.com/{owner}/{repository}"
    expected = release_id(repository_id, "agent-workflow-pack", version)

    for _distribution_form in ("wheel", "sdist", "git-checkout"):
        identity = ReleaseIdentity(repository_id, "agent-workflow-pack", version)
        assert identity.release_id == expected


def test_release_identity_changes_for_each_authority_field() -> None:
    baseline = release_id(
        "github.com/example/agent-workflow-pack", "agent-workflow-pack", "0.1.0"
    )
    assert release_id(
        "github.com/other/agent-workflow-pack", "agent-workflow-pack", "0.1.0"
    ) != baseline
    assert release_id(
        "github.com/example/agent-workflow-pack", "different", "0.1.0"
    ) != baseline
    assert release_id(
        "github.com/example/agent-workflow-pack", "agent-workflow-pack", "0.1.1"
    ) != baseline


def test_release_identity_has_no_source_or_container_inputs() -> None:
    identity = ReleaseIdentity(
        "github.com/example/agent-workflow-pack", "agent-workflow-pack", "0.1.0"
    )
    assert set(identity.to_document()) == {
        "schema_id",
        "schema_version",
        "repository_id",
        "distribution_name",
        "version",
        "release_id",
    }
