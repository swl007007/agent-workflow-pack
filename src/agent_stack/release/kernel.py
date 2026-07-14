"""Leaf public API for release identity, trust, and compatibility."""

from __future__ import annotations

from typing import Final

from .identity import ReleaseIdentity, release_id


RELEASE_KERNEL_INTERFACE_VERSION: Final = 1
PUBLIC_MODELS: Final = (ReleaseIdentity,)


def verify_release_manifest(locator: object, packaged_policy: object) -> object:
    """Verify one detached immutable release; implemented by release-kernel Task 2."""

    raise NotImplementedError("detached release verification is not implemented yet")


def classify_compatibility(
    current_release: object, target_release: object, local_state_contract: object
) -> object:
    """Classify one exact directed relation; implemented by release-kernel Task 3."""

    raise NotImplementedError("release compatibility is not implemented yet")


def select_candidate_runtime(
    committed_release: object, candidate_release: object, journal_reference: object | None = None
) -> object:
    """Select only an allowed committed/candidate runtime; implemented by Task 3."""

    raise NotImplementedError("candidate runtime selection is not implemented yet")


__all__ = [
    "PUBLIC_MODELS",
    "RELEASE_KERNEL_INTERFACE_VERSION",
    "ReleaseIdentity",
    "classify_compatibility",
    "release_id",
    "select_candidate_runtime",
    "verify_release_manifest",
]
