"""Frozen public release interface."""

from .errors import LifecycleFailure
from .kernel import (
    PUBLIC_MODELS,
    CompatibilityResult,
    LocalStateContract,
    PackagedTrustPolicy,
    RELEASE_KERNEL_INTERFACE_VERSION,
    ReleaseIdentity,
    ReleaseLocator,
    RuntimeJournalReference,
    StaticReleaseMetadata,
    VerifiedRelease,
    classify_compatibility,
    inspect_source_static_metadata,
    release_id,
    select_candidate_runtime,
    verify_release_manifest,
)

__all__ = [
    "LifecycleFailure",
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
