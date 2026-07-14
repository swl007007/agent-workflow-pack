from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from agent_stack.route.wrappers import (
    ExecuteLightRuntimeContext,
    invoke_execute_light,
    production_route_verifier_ports,
)
from tests.integration.route.test_wrappers import authority_mapping, launcher, light_decision


FIXTURE = Path(__file__).with_name("fixtures") / "wrapper-outputs.json"


def test_native_light_wrapper_output_has_no_task_or_catalog_authority(tmp_path) -> None:
    documents = []
    context = ExecuteLightRuntimeContext(
        platform="codex",
        repository_launcher=launcher(tmp_path),
        native_light_entry_id="sol-native",
        current_authorities=authority_mapping(),
        decision_verifier=production_route_verifier_ports().decision,
        dispatcher=lambda dispatch: documents.append(dispatch.to_document())
        or dispatch.to_document(),
    )

    document = invoke_execute_light(light_decision(), context)
    summary = {
        "schema_id": document["schema_id"],
        "operation": document["operation"],
        "platform": document["platform"],
        "entry_id": document["entry_id"],
        "launcher_suffix": "/".join(Path(document["repository_launcher"]).parts[-3:]),
        "fields": sorted(document),
    }

    assert summary == json.loads(FIXTURE.read_text(encoding="utf-8"))["native_light"]
    assert len(documents) == 1
    assert not ({"task_id", "task_ref", "catalog_path", "approval_proof"} & set(document))
    assert "decision" not in {field.name for field in dataclasses.fields(context)}

