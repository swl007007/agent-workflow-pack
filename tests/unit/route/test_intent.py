from __future__ import annotations

import copy
from pathlib import Path

import pytest

from agent_stack.core.api import digest
from agent_stack.route.errors import RouteFailure
from agent_stack.route.intent import validate_task_intent
from agent_stack.route.signals import load_compiled_policy


ROOT = Path(__file__).resolve().parents[3]


def intent_document() -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.task-intent",
        "schema_version": 1,
        "intent_id": "feature-intent-id",
        "title": "Add a public API",
        "objective": "Change the public contract safely",
        "requested_mode": None,
        "acceptance_summary": "Public API and migration tests pass",
        "signals": ["public_contract_change", "schema_or_data_migration"],
    }


def test_intent_is_the_only_executable_signal_source_and_binds_digest() -> None:
    policy = load_compiled_policy(ROOT / "catalog/route-policy.yaml")
    document = intent_document()

    verified = validate_task_intent(document, policy=policy)

    assert verified.signals == (
        "public_contract_change",
        "schema_or_data_migration",
    )
    assert verified.intent_digest == digest(
        "agent-workflow.task-intent.v1", verified.document
    )
    with pytest.raises(RouteFailure, match="separate --signals"):
        validate_task_intent(
            document,
            policy=policy,
            separate_signals=("architecture_or_subsystem_change",),
        )


def test_intent_fields_modes_signals_and_normalization_are_closed() -> None:
    policy = load_compiled_policy(ROOT / "catalog/route-policy.yaml")
    unknown = intent_document()
    unknown["model_hint"] = "heavy"
    bad_mode = intent_document()
    bad_mode["requested_mode"] = "model-heavy"
    duplicate = intent_document()
    duplicate["signals"] = ["public_contract_change", "public_contract_change"]
    unsorted = intent_document()
    unsorted["signals"] = ["schema_or_data_migration", "public_contract_change"]

    for document in (unknown, bad_mode, duplicate):
        with pytest.raises(RouteFailure):
            validate_task_intent(document, policy=policy)

    verified = validate_task_intent(unsorted, policy=policy)
    assert verified.document["signals"] == [
        "public_contract_change",
        "schema_or_data_migration",
    ]


def test_title_objective_acceptance_and_signal_changes_change_intent_digest() -> None:
    policy = load_compiled_policy(ROOT / "catalog/route-policy.yaml")
    baseline = validate_task_intent(intent_document(), policy=policy).intent_digest
    for field, value in (
        ("title", "Different title"),
        ("objective", "Different objective"),
        ("acceptance_summary", "Different acceptance"),
        ("requested_mode", "speckit-superpowers"),
    ):
        changed = copy.deepcopy(intent_document())
        changed[field] = value
        assert validate_task_intent(changed, policy=policy).intent_digest != baseline
