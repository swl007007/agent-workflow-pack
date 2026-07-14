from __future__ import annotations

import dataclasses
from pathlib import Path
from types import MappingProxyType

import pytest

from agent_stack.route.calculator import RouteCalculationInputs, calculate_route
from agent_stack.route.errors import RouteFailure
from agent_stack.route.wrappers import (
    ExecuteLightRuntimeContext,
    IntegratedWrapperInvocation,
    NativeLightDispatch,
    invoke_execute_light,
    invoke_integrated_wrapper,
    production_route_verifier_ports,
)
from agent_stack.runtime.errors import RuntimeFailure
from agent_stack.runtime.runtime_load import ImmutableDispatchBundle
from tests.integration.runtime.test_runtime_load import load_case
from tests.unit.route.test_calculator import authorities, intent


def authority_mapping() -> dict[str, object]:
    auth = authorities()
    return {field.name: getattr(auth, field.name) for field in dataclasses.fields(auth)}


def launcher(tmp_path: Path) -> Path:
    path = tmp_path / ".agent-workflow/bin/agent-stack"
    path.parent.mkdir(parents=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def light_decision() -> dict[str, object]:
    return dict(
        calculate_route(
            "execute-light",
            RouteCalculationInputs(intent=intent()),
            authorities(),
        )
    )


def test_execute_light_reverifies_then_dispatches_only_native_binding(tmp_path: Path) -> None:
    observed: list[NativeLightDispatch] = []
    context = ExecuteLightRuntimeContext(
        platform="codex",
        repository_launcher=launcher(tmp_path),
        native_light_entry_id="sol-native",
        current_authorities=authority_mapping(),
        decision_verifier=production_route_verifier_ports().decision,
        dispatcher=lambda dispatch: observed.append(dispatch) or "native-ok",
    )

    result = invoke_execute_light(light_decision(), context)

    assert result == "native-ok"
    assert len(observed) == 1
    assert observed[0].entry_id == "sol-native"
    assert observed[0].operation == "execute-light"
    assert not hasattr(observed[0], "task_id")


def test_classify_integrated_and_non_repository_launcher_are_rejected(tmp_path: Path) -> None:
    auth = authorities()
    classified = calculate_route(
        "classify-only", RouteCalculationInputs(candidate_signals=()), auth
    )
    integrated = calculate_route(
        "create-integrated-task",
        RouteCalculationInputs(
            intent=intent(requested_mode="trellis-native"),
            requested_task_ref=".trellis/tasks/example",
        ),
        auth,
    )
    valid = ExecuteLightRuntimeContext(
        platform="codex",
        repository_launcher=launcher(tmp_path),
        native_light_entry_id="sol-native",
        current_authorities=authority_mapping(),
        decision_verifier=production_route_verifier_ports().decision,
        dispatcher=lambda dispatch: dispatch,
    )
    invalid_launcher = dataclasses.replace(
        valid, repository_launcher=tmp_path / "global/bin/agent-stack"
    )

    for decision, context in (
        (classified, valid),
        (integrated, valid),
        (light_decision(), invalid_launcher),
    ):
        with pytest.raises(RouteFailure):
            invoke_execute_light(decision, context)


def test_integrated_wrapper_calls_runtime_load_and_dispatches_only_bundle(
    tmp_path: Path,
) -> None:
    request, units, _ = load_case(tmp_path)
    observed: list[ImmutableDispatchBundle] = []

    def dispatch(bundle: ImmutableDispatchBundle) -> bytes:
        observed.append(bundle)
        for path, _, _, _ in units.values():
            path.unlink()
        return bundle.units["runtime-entry:trellis-implement"].content

    invocation = IntegratedWrapperInvocation(
        repository_launcher=launcher(request.project_root),
        load_request=request,
        dispatcher=dispatch,
    )

    result = invoke_integrated_wrapper(invocation)

    assert result == b"run trellis\n"
    assert len(observed) == 1
    assert observed[0].runtime_entry_id == request.runtime_entry_id
    assert "decision" not in {field.name for field in dataclasses.fields(invocation)}
    assert "approval_proof" not in {field.name for field in dataclasses.fields(invocation)}
    assert all(unit.content for unit in observed[0].units.values())


def test_runtime_maintenance_phase_and_claim_failures_propagate_before_dispatch(
    tmp_path: Path,
) -> None:
    request, _, _ = load_case(tmp_path)
    called = False

    def dispatch(bundle: ImmutableDispatchBundle) -> None:
        nonlocal called
        called = True

    invocation = IntegratedWrapperInvocation(
        repository_launcher=launcher(request.project_root),
        load_request=request,
        dispatcher=dispatch,
    )
    (request.project_root / ".agent-workflow/maintenance.json").write_text("{}")
    with pytest.raises(RuntimeFailure, match="AWP_TASK_RUNTIME_LOAD_DENIED"):
        invoke_integrated_wrapper(invocation)
    assert called is False


def test_heavy_mode_can_dispatch_only_the_heavy_development_router(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _, _ = load_case(tmp_path)
    wrong = ImmutableDispatchBundle(
        task_id=request.task_id,
        task_ref=request.task_ref,
        state_revision=2,
        mode="speckit-superpowers",
        lifecycle_status="active",
        phase="implementing",
        surface_id="runtime-entry:trellis-implement",
        runtime_entry_id="trellis-implement",
        authorized_surface_ids=("runtime-control-plane", "surface-registry"),
        units=MappingProxyType({}),
    )
    monkeypatch.setattr("agent_stack.route.wrappers.load_task_runtime", lambda _: wrong)
    invocation = IntegratedWrapperInvocation(
        repository_launcher=launcher(request.project_root),
        load_request=request,
        dispatcher=lambda bundle: bundle,
    )

    with pytest.raises(RouteFailure, match="AWP_ADAPTER_BYPASS_DETECTED"):
        invoke_integrated_wrapper(invocation)

