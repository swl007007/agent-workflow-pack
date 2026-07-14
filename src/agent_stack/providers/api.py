"""Frozen public provider acquisition and execution API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .errors import ProviderFailure
from .models import AcquisitionRequest, AcquisitionResult, ProviderExecutionResult, ProviderPlan


PROVIDER_INTERFACE_VERSION: Final = 1
PUBLIC_MODELS: Final = (
    AcquisitionRequest,
    AcquisitionResult,
    ProviderExecutionResult,
    ProviderPlan,
)


def acquire(request: AcquisitionRequest) -> AcquisitionResult:
    """Acquire one authorized object; implemented by the later cache tasks."""

    raise NotImplementedError("provider acquisition is not implemented yet")


def execute_provider(
    plan: ProviderPlan, approval: Mapping[str, object] | None
) -> ProviderExecutionResult:
    """Execute one immutable provider plan; implemented by later provider tasks."""

    raise NotImplementedError("provider execution is not implemented yet")


__all__ = [
    "AcquisitionRequest",
    "AcquisitionResult",
    "PROVIDER_INTERFACE_VERSION",
    "PUBLIC_MODELS",
    "ProviderExecutionResult",
    "ProviderFailure",
    "ProviderPlan",
    "acquire",
    "execute_provider",
]
