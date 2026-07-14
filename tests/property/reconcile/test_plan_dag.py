from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

from hypothesis import given
from hypothesis import strategies as st

from agent_stack.core.api import validate_saved_plan_envelope
from agent_stack.reconcile.api import plan_reconcile
from agent_stack.reconcile.models import StagedRenderTree
from agent_stack.reconcile.plan import render_candidate_manifest
from tests.unit.reconcile.test_ownership import definition, manifest_record, staged, state
from tests.unit.reconcile.test_plan import (
    empty_task_state,
    ir_for,
    manifest_for,
    observed_for,
)


@given(
    reverse_staged=st.booleans(),
    reverse_definitions=st.booleans(),
    reverse_manifest=st.booleans(),
    reverse_observed=st.booleans(),
)
def test_plan_digest_dag_is_acyclic_and_input_order_independent(
    reverse_staged: bool,
    reverse_definitions: bool,
    reverse_manifest: bool,
    reverse_observed: bool,
) -> None:
    first = staged("generated/a.txt", b"after-a\n", definition_id="a")
    second = staged("generated/b.txt", b"after-b\n", definition_id="b")
    records = [first, second]
    definitions = [definition("a", first.path), definition("b", second.path)]
    manifest = manifest_for(first)
    first_before = state(first.path, b"before\n")
    second_before = state(second.path, b"before\n")
    manifest["files"] = [
        manifest_record(first, first_before),
        manifest_record(second, second_before),
    ]
    observed = observed_for(first, "sync")
    observed_files = {
        first.path: {"state": first_before, "content": "before\n"},
        second.path: {"state": second_before, "content": "before\n"},
    }
    ir = replace(
        ir_for("sync", first),
        artifact_definitions=tuple(MappingProxyType(item) for item in definitions),
    )

    baseline = plan_reconcile(
        ir,
        StagedRenderTree(tuple(records), "a" * 64),
        manifest,
        {**observed, "files": observed_files},
        empty_task_state(),
    )

    if reverse_staged:
        records.reverse()
    if reverse_definitions:
        definitions.reverse()
    if reverse_manifest:
        manifest["files"] = list(reversed(manifest["files"]))  # type: ignore[arg-type]
    if reverse_observed:
        observed_files = dict(reversed(tuple(observed_files.items())))
    permuted_ir = replace(
        ir,
        artifact_definitions=tuple(MappingProxyType(item) for item in definitions),
    )
    permuted = plan_reconcile(
        permuted_ir,
        StagedRenderTree(tuple(records), "a" * 64),
        manifest,
        {**observed, "files": observed_files},
        empty_task_state(),
    )

    assert permuted.plan_digest == baseline.plan_digest
    assert permuted.journal_binding_digest == baseline.journal_binding_digest
    assert not {
        "plan_core_digest",
        "journal_binding_digest",
        "candidate_manifest",
        "candidate_manifest_digest",
        "plan_digest",
    } & set(permuted.plan_core)
    candidate_manifest = render_candidate_manifest(permuted)
    validate_saved_plan_envelope(permuted.to_document(), candidate_manifest)
