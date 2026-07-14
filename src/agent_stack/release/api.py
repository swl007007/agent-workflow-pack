"""Frozen public release interface."""

from .errors import LifecycleFailure
from .kernel import (
    PUBLIC_MODELS,
    PackagedTrustPolicy,
    RELEASE_KERNEL_INTERFACE_VERSION,
    ReleaseIdentity,
    ReleaseLocator,
    VerifiedRelease,
    classify_compatibility,
    release_id,
    select_candidate_runtime,
    verify_release_manifest,
)

__all__ = [
    "LifecycleFailure",
    "PUBLIC_MODELS",
    "PackagedTrustPolicy",
    "RELEASE_KERNEL_INTERFACE_VERSION",
    "ReleaseIdentity",
    "ReleaseLocator",
    "VerifiedRelease",
    "classify_compatibility",
    "release_id",
    "select_candidate_runtime",
    "verify_release_manifest",
]
