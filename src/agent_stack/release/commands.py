"""Production lifecycle command handlers that do not redefine domain policy."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack._vendor import yaml
from agent_stack.cli.production import ProductionCommand, production_owner_bindings
from agent_stack.cli.production import _authorize_running_release
from agent_stack.reconcile.production import compose_sync
from agent_stack.release.manifest import VerifiedRelease

from .errors import LifecycleFailure
from .distribution import UpgradeResult
from .compatibility import RuntimeJournalReference
from .manifest import discover_release_locator, verify_release_manifest
from .trust import PackagedTrustPolicy


def _data_root() -> Path:
    return Path(str(files("agent_stack").joinpath("data")))


def run_doctor(payload: object) -> Mapping[str, object]:
    command = cast(ProductionCommand, payload)
    release = cast(VerifiedRelease, _authorize_running_release())
    policy_path = _data_root() / "release/trust-policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))  # type: ignore[no-untyped-call]
    if not isinstance(policy, Mapping):
        raise LifecycleFailure(
            "AWP_RELEASE_TRUST_POLICY_INVALID",
            "packaged trust policy is invalid",
            exit_code=30,
        )
    manifest = command.repository_root / ".agent-workflow/manifest.json"
    authority = compose_sync(
        command,
        release,
        apply=False,
        data_root=_data_root(),
    )
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.doctor-result",
            "schema_version": 1,
            "repository_root": str(command.repository_root),
            "initialized": manifest.is_file() and authority.get("no_op") is True,
            "manifest_path": ".agent-workflow/manifest.json",
            "authority_verified": True,
            "existing_trellis": (command.repository_root / ".trellis").exists(),
            "existing_specify": (command.repository_root / ".specify").exists(),
            "trust_policy": {
                "host": policy.get("host"),
                "owner": policy.get("owner"),
                "repository": policy.get("repository"),
                "policy_digest": policy.get("policy_digest"),
            },
            "production_owner_binding_count": len(production_owner_bindings()),
        }
    )


def run_upgrade(payload: object) -> object:
    command = cast(ProductionCommand, payload)
    installed = cast(VerifiedRelease, _authorize_running_release())
    compose_sync(command, installed, apply=False, data_root=_data_root())
    target = command.invocation.options.get("target")
    if target is None or target == installed.identity.version:
        return MappingProxyType(
            UpgradeResult(
                transaction_id=None,
                target_release_id=installed.identity.release_id,
                recovery_runtime=RuntimeJournalReference(
                    "committed",
                    installed.identity.release_id,
                    installed.manifest_digest,
                ),
                committed=False,
                no_op=True,
            ).to_document()
        )
    if not isinstance(target, str) or not target:
        raise LifecycleFailure(
            "AWP_RELEASE_UPGRADE_INPUT_REQUIRED",
            "upgrade target version is invalid",
            exit_code=21,
        )
    policy_document = yaml.safe_load(  # type: ignore[no-untyped-call]
        (_data_root() / "release/trust-policy.yaml").read_text(encoding="utf-8")
    )
    if not isinstance(policy_document, Mapping):
        raise LifecycleFailure(
            "AWP_RELEASE_TRUST_POLICY_INVALID",
            "packaged trust policy is invalid",
            exit_code=30,
        )
    policy = PackagedTrustPolicy.from_document(policy_document)
    candidate = verify_release_manifest(
        discover_release_locator(target, policy), policy
    )
    raise LifecycleFailure(
        "AWP_UPGRADE_APPROVAL_REQUIRED",
        "verified upgrade candidate requires an exact approved saved plan",
        exit_code=22,
        details={"target_release_id": candidate.identity.release_id},
    )
