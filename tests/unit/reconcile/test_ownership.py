from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_stack.core.api import SchemaCatalog
from agent_stack.reconcile.models import StagedFile, StagedRenderTree
from agent_stack.reconcile.ownership import plan_ownership


ROOT = Path(__file__).resolve().parents[3]


def state(
    path: str,
    content: bytes | None,
    *,
    mode: str = "0644",
) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.file-state",
        "schema_version": 1,
        "path": path,
        "exists": content is not None,
        "file_type": "regular" if content is not None else "absent",
        "byte_hash": hashlib.sha256(content).hexdigest() if content is not None else "canonical-null",
        "mode": mode if content is not None else "canonical-null",
        "non_symlink": True,
        "managed_block_hash": "canonical-null",
    }


def staged(
    path: str,
    content: bytes,
    *,
    definition_id: str,
    ownership: str = "managed",
    merge_strategy: str = "whole-file",
    mode_policy: str = "exact",
    candidate_mode: str = "0644",
) -> StagedFile:
    byte_hash = hashlib.sha256(content).hexdigest()
    return StagedFile(
        path=path,
        definition_id=definition_id,
        surface_id=f"runtime-entry:{definition_id}",
        ownership=ownership,
        merge_strategy=merge_strategy,
        source_digest="1" * 64,
        render_digest="2" * 64,
        candidate_byte_hash=byte_hash,
        mode_policy=mode_policy,
        candidate_mode=candidate_mode,
        candidate_bytes=content,
        neutral_source_bytes=content,
    )


def definition(
    definition_id: str,
    path: str,
    *,
    ownership: str = "managed",
    merge_strategy: str = "whole-file",
    mode_policy: str = "exact",
    mode: str | None = "0644",
    markers: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "id": definition_id,
        "source": f"templates/{definition_id}.txt",
        "targets": [
            {
                "path": path,
                "ownership": ownership,
                "merge_strategy": merge_strategy,
                "mode_policy": mode_policy,
                "mode": mode,
                "markers": markers,
            }
        ],
        "forbidden_paths": [],
        "validators": [],
    }


def manifest_record(
    record: StagedFile,
    current: dict[str, object],
    *,
    managed_block_hash: str = "canonical-null",
    created_once: bool = False,
    markers: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "path": record.path,
        "definition_id": record.definition_id,
        "ownership": record.ownership,
        "file_state": current,
        "managed_block_hash": managed_block_hash,
        "created_once": created_once,
        "markers": markers,
    }


def test_ownership_schemas_are_registered_and_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.supported_versions("agent-workflow.ownership-decision") == (1,)
    assert catalog.supported_versions("agent-workflow.ownership-observation") == (1,)


def test_managed_create_replace_enrollment_and_retirement() -> None:
    created = staged("generated/new.txt", b"new\n", definition_id="new")
    replaced = staged("generated/replace.txt", b"after\n", definition_id="replace")
    enrolled = staged("generated/enroll.txt", b"same\n", definition_id="enroll")
    retired = staged("generated/retired.txt", b"old\n", definition_id="retired")
    before = state(replaced.path, b"before\n")
    retired_before = state(retired.path, b"old\n")
    tree = StagedRenderTree((created, replaced, enrolled), "3" * 64)
    plan = plan_ownership(
        tree,
        [
            definition("new", created.path),
            definition("replace", replaced.path),
            definition("enroll", enrolled.path),
        ],
        [
            manifest_record(replaced, before),
            manifest_record(retired, retired_before),
        ],
        {
            created.path: {"state": state(created.path, None), "content": None},
            replaced.path: {"state": before, "content": "before\n"},
            enrolled.path: {"state": state(enrolled.path, b"same\n"), "content": "same\n"},
            retired.path: {"state": retired_before, "content": "old\n"},
        },
        operation="sync",
    )

    actions = {item["path"]: item["action"] for item in plan.decisions}
    assert actions == {
        created.path: "create",
        replaced.path: "replace",
        enrolled.path: "no-op",
        retired.path: "replace",
    }
    assert {item.path for item in plan.candidate_file_states} == {
        created.path,
        replaced.path,
        retired.path,
    }
    assert plan.has_manifest_changes is True


def test_overlay_external_edits_are_ignored_but_marker_corruption_blocks() -> None:
    markers = {"begin": "# BEGIN AWP", "end": "# END AWP"}
    before_block = b"managed=before\n"
    after_block = b"managed=after\n"
    record = staged(
        "AGENTS.md",
        after_block,
        definition_id="instructions",
        ownership="overlay-managed",
        merge_strategy="marked-block",
        mode_policy="preserve",
        candidate_mode="canonical-null",
    )
    host = b"user prefix\n# BEGIN AWP\n" + before_block + b"# END AWP\nuser suffix\n"
    current = state(record.path, host, mode="0600")
    baseline_hash = hashlib.sha256(before_block).hexdigest()
    tree = StagedRenderTree((record,), "4" * 64)
    artifact = definition(
        "instructions",
        record.path,
        ownership="overlay-managed",
        merge_strategy="marked-block",
        mode_policy="preserve",
        mode=None,
        markers=markers,
    )
    plan = plan_ownership(
        tree,
        [artifact],
        [manifest_record(record, current, managed_block_hash=baseline_hash, markers=markers)],
        {record.path: {"state": current, "content": host.decode()}},
        operation="sync",
    )

    assert plan.decisions[0]["action"] == "update-managed-block"
    assert plan.candidate_file_states[0].mode == "0600"

    corrupt = host.replace(b"# END AWP\n", b"# BEGIN AWP\n")
    with pytest.raises(Exception, match="AWP_OWNERSHIP_CONFLICT"):
        plan_ownership(
            tree,
            [artifact],
            [manifest_record(record, current, managed_block_hash=baseline_hash, markers=markers)],
            {record.path: {"state": state(record.path, corrupt), "content": corrupt.decode()}},
            operation="sync",
        )


def test_overlay_host_only_edit_is_a_true_ownership_noop() -> None:
    markers = {"begin": "# BEGIN AWP", "end": "# END AWP"}
    block = b"managed=true\n"
    record = staged(
        "AGENTS.md",
        block,
        definition_id="instructions",
        ownership="overlay-managed",
        merge_strategy="marked-block",
        mode_policy="preserve",
        candidate_mode="canonical-null",
    )
    baseline_host = b"old user prefix\n# BEGIN AWP\n" + block + b"# END AWP\n"
    observed_host = b"new user prefix\n# BEGIN AWP\n" + block + b"# END AWP\n"
    baseline = state(record.path, baseline_host, mode="0600")
    observed = state(record.path, observed_host, mode="0600")
    block_hash = hashlib.sha256(block).hexdigest()
    plan = plan_ownership(
        StagedRenderTree((record,), "7" * 64),
        [
            definition(
                "instructions",
                record.path,
                ownership="overlay-managed",
                merge_strategy="marked-block",
                mode_policy="preserve",
                mode=None,
                markers=markers,
            )
        ],
        [
            manifest_record(
                record,
                baseline,
                managed_block_hash=block_hash,
                markers=markers,
            )
        ],
        {record.path: {"state": observed, "content": observed_host.decode()}},
        operation="sync",
    )

    assert plan.decisions[0]["action"] == "no-op"
    assert plan.candidate_file_states == ()
    assert plan.has_manifest_changes is False


def test_overlay_retirement_removes_only_the_managed_block() -> None:
    markers = {"begin": "# BEGIN AWP", "end": "# END AWP"}
    block = b"managed=true\n"
    record = staged(
        "AGENTS.md",
        block,
        definition_id="instructions",
        ownership="overlay-managed",
        merge_strategy="marked-block",
        mode_policy="preserve",
        candidate_mode="canonical-null",
    )
    host = b"user prefix\n# BEGIN AWP\n" + block + b"# END AWP\nuser suffix\n"
    current = state(record.path, host, mode="0600")
    plan = plan_ownership(
        StagedRenderTree((), "6" * 64),
        [],
        [
            manifest_record(
                record,
                current,
                managed_block_hash=hashlib.sha256(block).hexdigest(),
                markers=markers,
            )
        ],
        {record.path: {"state": current, "content": host.decode()}},
        operation="sync",
    )

    assert plan.decisions[0]["reason_code"] == "retire-managed-block"
    assert plan.candidate_file_states[0].mode == "0600"
    assert plan.candidate_contents[record.path] == b"user prefix\nuser suffix\n"


def test_adopted_create_once_and_user_owned_never_gain_overwrite_authority() -> None:
    adopted = staged(
        "config/adopted.txt",
        b"ignored\n",
        definition_id="adopted",
        ownership="adopted",
        merge_strategy="observe-baseline",
        mode_policy="preserve",
        candidate_mode="canonical-null",
    )
    create_once = staged(
        "config/seed.txt",
        b"seed\n",
        definition_id="seed",
        ownership="create-once-then-user-owned",
    )
    user = staged(
        "config/user.txt",
        b"ignored\n",
        definition_id="user",
        ownership="user-owned",
        merge_strategy="none",
        mode_policy="preserve",
        candidate_mode="canonical-null",
    )
    tree = StagedRenderTree((adopted, create_once, user), "5" * 64)
    observed = {
        adopted.path: {"state": state(adopted.path, b"custom\n"), "content": "custom\n"},
        create_once.path: {"state": state(create_once.path, None), "content": None},
        user.path: {"state": state(user.path, b"custom\n"), "content": "custom\n"},
    }
    plan = plan_ownership(
        tree,
        [
            definition("adopted", adopted.path, ownership="adopted", merge_strategy="observe-baseline", mode_policy="preserve", mode=None),
            definition("seed", create_once.path, ownership="create-once-then-user-owned"),
            definition("user", user.path, ownership="user-owned", merge_strategy="none", mode_policy="preserve", mode=None),
        ],
        [],
        observed,
        operation="init",
    )

    actions = {item["path"]: item["action"] for item in plan.decisions}
    assert actions == {
        adopted.path: "adopt-baseline",
        create_once.path: "create",
        user.path: "no-op",
    }
    assert {item.path for item in plan.candidate_file_states} == {create_once.path}
