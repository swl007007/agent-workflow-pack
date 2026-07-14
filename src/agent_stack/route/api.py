"""Frozen public Route/Adapters API."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import cast


def _implementation(module: str, name: str) -> Callable[..., object]:
    loaded = importlib.import_module(module, package=__package__)
    return cast(Callable[..., object], getattr(loaded, name))


def calculate_route(operation: object, normalized_inputs: object, authorities: object) -> object:
    return _implementation(".calculator", "calculate_route")(
        operation, normalized_inputs, authorities
    )


def verify_route_decision(
    decision: object, current_authorities: object, consumer: object
) -> object:
    return _implementation(".verifier", "verify_route_decision")(
        decision, current_authorities, consumer
    )


def verify_task_creation_approval(
    proof: object, decision: object, capability: object, runtime_context: object
) -> object:
    return _implementation(".approval", "verify_task_creation_approval")(
        proof, decision, capability, runtime_context
    )


def derive_task_surface_closure(
    route: object, platform: object, entry_owner: object, registry: object
) -> object:
    return _implementation(".surfaces", "derive_task_surface_closure")(
        route, platform, entry_owner, registry
    )


def measure_capability_manifest(inputs: object) -> object:
    return _implementation(".capabilities", "measure_capability_manifest")(inputs)


def project_platform_adapter(ir: object, adapter: object) -> object:
    return _implementation(".projection", "project_platform_adapter")(ir, adapter)


def invoke_execute_light(decision: object, runtime_context: object) -> object:
    return _implementation(".wrappers", "invoke_execute_light")(decision, runtime_context)


def invoke_integrated_wrapper(invocation: object) -> object:
    return _implementation(".wrappers", "invoke_integrated_wrapper")(invocation)


def production_route_verifier_ports() -> object:
    return _implementation(".wrappers", "production_route_verifier_ports")()
