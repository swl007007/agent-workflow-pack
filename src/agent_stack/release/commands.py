"""Production lifecycle command handlers that do not redefine domain policy."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import cast

from agent_stack._vendor import yaml
from agent_stack.cli.production import ProductionCommand, production_owner_bindings

from .errors import LifecycleFailure


def _data_root() -> Path:
    return Path(str(files("agent_stack").joinpath("data")))


def run_doctor(payload: object) -> Mapping[str, object]:
    command = cast(ProductionCommand, payload)
    policy_path = _data_root() / "release/trust-policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))  # type: ignore[no-untyped-call]
    if not isinstance(policy, Mapping):
        raise LifecycleFailure(
            "AWP_RELEASE_TRUST_POLICY_INVALID",
            "packaged trust policy is invalid",
            exit_code=30,
        )
    manifest = command.repository_root / ".agent-workflow/Manifest.json"
    return MappingProxyType(
        {
            "schema_id": "agent-workflow.doctor-result",
            "schema_version": 1,
            "repository_root": str(command.repository_root),
            "initialized": manifest.is_file(),
            "manifest_path": ".agent-workflow/Manifest.json",
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
    raise LifecycleFailure(
        "AWP_RELEASE_UPGRADE_INPUT_REQUIRED",
        "upgrade requires an initialized project and verified candidate release",
        exit_code=21,
    )

