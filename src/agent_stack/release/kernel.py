"""Leaf public API for release identity, trust, and compatibility."""

from __future__ import annotations

from typing import Final

from .compatibility import (
    CompatibilityResult,
    LocalStateContract,
    RuntimeJournalReference,
    StaticReleaseMetadata,
    classify_compatibility,
    inspect_source_static_metadata,
    select_candidate_runtime,
)
from .identity import ReleaseIdentity, release_id
from .manifest import ReleaseLocator, VerifiedRelease, verify_release_manifest
from .trust import PackagedTrustPolicy


RELEASE_KERNEL_INTERFACE_VERSION: Final = 1
PUBLIC_MODELS: Final = (
    PackagedTrustPolicy,
    CompatibilityResult,
    LocalStateContract,
    ReleaseIdentity,
    ReleaseLocator,
    RuntimeJournalReference,
    StaticReleaseMetadata,
    VerifiedRelease,
)


__all__ = [
    "PUBLIC_MODELS",
    "CompatibilityResult",
    "LocalStateContract",
    "PackagedTrustPolicy",
    "RELEASE_KERNEL_INTERFACE_VERSION",
    "ReleaseIdentity",
    "ReleaseLocator",
    "RuntimeJournalReference",
    "StaticReleaseMetadata",
    "VerifiedRelease",
    "classify_compatibility",
    "inspect_source_static_metadata",
    "release_id",
    "select_candidate_runtime",
    "verify_release_manifest",
]
