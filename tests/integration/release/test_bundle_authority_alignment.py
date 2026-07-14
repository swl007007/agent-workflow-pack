from pathlib import Path

from agent_stack.core.api import (
    compute_artifact_bundle_digest,
    compute_workflow_lock_digest,
)
from agent_stack.reconcile.production_bundle import load_production_bundle
from tools.release.publish_release import _bundle_roots


ROOT = Path(__file__).resolve().parents[3]


def test_detached_manifest_bundle_roots_equal_production_resolver_authority() -> None:
    bundle = load_production_bundle(ROOT)
    roots = _bundle_roots(ROOT)

    assert roots["workflow_lock"] == compute_workflow_lock_digest(
        bundle.workflow_lock
    )
    assert roots["artifact"] == compute_artifact_bundle_digest(
        bundle.artifact_definitions
    )
