"""Load the closed, packaged inputs required by production composition."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from agent_stack._vendor import yaml
from agent_stack.core.api import (
    VerifiedDiscoverySchemas,
    VerifiedTrellisTaskLayout,
    canonical_json_bytes,
    digest,
)
from agent_stack.core.artifact_policy import validate_artifact_definitions, validate_trellis_layout
from agent_stack.core.catalog import normalize_workflow_lock
from agent_stack.core.profile import resolve_profile
from agent_stack.core.surfaces import validate_surface_registry
from agent_stack.reconcile.errors import RendererFailure


@dataclass(frozen=True)
class ProductionBundle:
    profile: Mapping[str, object]
    catalog: Mapping[str, object]
    workflow_lock: Mapping[str, object]
    surface_registry: Mapping[str, object]
    runtime_unit_inventory: Mapping[str, object]
    runtime_unit_evidence: tuple[Mapping[str, object], ...]
    artifact_definitions: tuple[Mapping[str, object], ...]
    template_root: Path
    trellis_layout: VerifiedTrellisTaskLayout
    discovery_schemas: VerifiedDiscoverySchemas
    route_policy: Mapping[str, object]
    router_contract: Mapping[str, object]
    trust_policy: Mapping[str, object]


def _failure(message: str, **details: object) -> RendererFailure:
    return RendererFailure("AWP_OWNERSHIP_CONFLICT", message, details=details)


def _load_yaml(path: Path) -> Mapping[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[no-untyped-call]
    except (OSError, UnicodeError, ValueError) as error:
        raise _failure("packaged production input cannot be loaded", path=path.as_posix()) from error
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise _failure("packaged production input is not an object", path=path.as_posix())
    return MappingProxyType(dict(value))


def _unit_path(root: Path, unit: Mapping[str, object]) -> Path:
    relative = unit.get("normalized_path")
    scope = unit.get("distribution_scope")
    if not isinstance(relative, str):
        raise _failure("runtime unit path is invalid")
    if scope == "rendered-project":
        template_by_target = {
            "AGENTS.md": "templates/platforms/codex/AGENTS.md.tmpl",
            ".agents/skills/agent-workflow/SKILL.md": "templates/platforms/codex/SKILL.md.tmpl",
            ".agent-workflow/bin/codex-wrapper": "templates/platforms/codex/codex-wrapper.tmpl",
        }
        try:
            relative = template_by_target[relative]
        except KeyError as error:
            raise _failure("rendered runtime unit lacks one frozen template") from error
    elif scope == "runtime-package" and relative.startswith("src/agent_stack/"):
        checkout_candidate = root / relative
        if checkout_candidate.is_file():
            return checkout_candidate
        relative = relative.removeprefix("src/agent_stack/")
        return root.parent / relative
    return root / relative


def _evidence(root: Path, inventory: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw_units = inventory.get("units")
    if not isinstance(raw_units, list):
        raise _failure("runtime unit inventory is invalid")
    rows: list[Mapping[str, object]] = []
    for raw in raw_units:
        if not isinstance(raw, Mapping):
            raise _failure("runtime unit inventory row is invalid")
        unit_id = raw.get("unit_id")
        if not isinstance(unit_id, str):
            raise _failure("runtime unit ID is invalid")
        path = _unit_path(root, raw)
        if not path.is_file() or path.is_symlink():
            raise _failure("runtime unit content is unavailable", unit_id=unit_id)
        payload = path.read_bytes()
        byte_hash = hashlib.sha256(payload).hexdigest()
        scope = raw.get("distribution_scope")
        distributions = (
            ["rendered-project"]
            if scope == "rendered-project"
            else ["git-checkout", "sdist", "wheel"]
        )
        rows.append(
            MappingProxyType(
                {
                    "unit_id": unit_id,
                    "byte_hash": byte_hash,
                    "mode": "0755" if unit_id.endswith("codex-wrapper") else "0644",
                    "contract_digest": digest(
                        "agent-workflow.runtime-unit-contract.v1",
                        {"unit_id": unit_id, "byte_hash": byte_hash, "path": str(raw["normalized_path"])},
                    ),
                    "distributions": distributions,
                }
            )
        )
    return tuple(sorted(rows, key=lambda row: str(row["unit_id"])))


def _artifact_targets(
    definitions: tuple[Mapping[str, object], ...],
) -> tuple[str, ...]:
    paths: list[str] = []
    for definition in definitions:
        targets = definition.get("targets")
        if not isinstance(targets, list):
            raise _failure("artifact definition targets are invalid")
        for target in targets:
            if not isinstance(target, Mapping) or not isinstance(target.get("path"), str):
                raise _failure("artifact definition target is invalid")
            paths.append(str(target["path"]))
    return tuple(paths)


def load_production_bundle(root: Path) -> ProductionBundle:
    """Validate production inputs from a repository root or installed data root."""

    root = root.resolve(strict=True)
    profile = _load_yaml(root / "profiles/default.yaml")
    catalog = _load_yaml(root / "catalog/workflow-components.yaml")
    workflow_lock = _load_yaml(root / "catalog/workflow.lock")
    registry = _load_yaml(root / "catalog/runtime-surfaces.yaml")
    inventory = _load_yaml(root / "catalog/runtime-units.yaml")
    route_policy = _load_yaml(root / "catalog/route-policy.yaml")
    router_contract = _load_yaml(root / "catalog/router-contract.yaml")
    trust_policy = _load_yaml(root / "release/trust-policy.yaml")
    try:
        layout_document = json.loads(
            (root / "catalog/trellis-task-layout.json").read_text(encoding="utf-8")
        )
        discovery_document = json.loads(
            (root / "catalog/trellis-discovery-schemas.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise _failure("packaged Trellis discovery input cannot be loaded") from error
    if not isinstance(layout_document, Mapping) or not isinstance(discovery_document, Mapping):
        raise _failure("packaged Trellis discovery input is not an object")
    definitions = tuple(
        _load_yaml(root / f"artifact-definitions/platforms/{name}.yaml")
        for name in ("codex-agents", "codex-skill", "codex-wrapper")
    )

    resolve_profile((profile,), "default")
    normalize_workflow_lock(workflow_lock)
    validate_artifact_definitions(definitions)
    validate_surface_registry(registry, inventory)
    trellis_layout = validate_trellis_layout(
        layout_document,
        artifact_targets=_artifact_targets(definitions),
    )
    discovery_schemas = VerifiedDiscoverySchemas(
        hashlib.sha256(canonical_json_bytes(discovery_document)).hexdigest(),
        discovery_document,
    )
    for definition in definitions:
        source = definition.get("source")
        if not isinstance(source, str) or not (root / source).is_file():
            raise _failure("artifact definition source is unavailable")

    return ProductionBundle(
        profile=profile,
        catalog=catalog,
        workflow_lock=workflow_lock,
        surface_registry=registry,
        runtime_unit_inventory=inventory,
        runtime_unit_evidence=_evidence(root, inventory),
        artifact_definitions=definitions,
        template_root=root / "templates",
        trellis_layout=trellis_layout,
        discovery_schemas=discovery_schemas,
        route_policy=route_policy,
        router_contract=router_contract,
        trust_policy=trust_policy,
    )


__all__ = ["ProductionBundle", "load_production_bundle"]
