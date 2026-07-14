from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent_stack.core.api import CoreFailure, SchemaCatalog
from agent_stack.release.identity import ReleaseIdentity
from agent_stack.release.manifest import VerifiedRelease


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "runtime-launcher" / "agent-stack.sh.tmpl"


def _verified_release(*, wheel_url: str | None = None) -> VerifiedRelease:
    identity = ReleaseIdentity(
        "github.com/example/agent-workflow-pack",
        "agent-workflow-pack",
        "0.1.0",
    )
    return VerifiedRelease(
        identity=identity,
        manifest_digest="a" * 64,
        source_commit="b" * 40,
        bundles={
            name: character * 64
            for name, character in zip(
                (
                    "trust_policy",
                    "workflow_lock",
                    "artifact",
                    "schema",
                    "migration",
                    "compatibility",
                    "launcher",
                ),
                "cdef123",
                strict=True,
            )
        },
        assets={
            "wheel": {
                "name": "agent_workflow_pack-0.1.0-py3-none-any.whl",
                "url": wheel_url
                or "https://github.com/example/agent-workflow-pack/releases/download/"
                "v0.1.0/agent_workflow_pack-0.1.0-py3-none-any.whl",
                "size": 100,
                "sha256": "4" * 64,
            },
            "sdist": {
                "name": "agent_workflow_pack-0.1.0.tar.gz",
                "url": "https://github.com/example/agent-workflow-pack/releases/download/"
                "v0.1.0/agent_workflow_pack-0.1.0.tar.gz",
                "size": 200,
                "sha256": "5" * 64,
            },
        },
        immutable_release=True,
    )


def test_template_contains_only_closed_release_substitutions_and_fixed_uv_contract() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")

    assert source.startswith("#!/bin/sh\n")
    assert set(
        part.split("}}", 1)[0]
        for part in source.split("{{")[1:]
        if "}}" in part
    ) == {
        "launcher_contract_version",
        "launcher_renderer_version",
        "release_id",
        "release_manifest_digest",
        "wheel_url",
        "wheel_sha256",
    }
    for required in (
        "--isolated",
        "--no-config",
        "--no-env-file",
        "--no-index",
        "--keyring-provider",
        "disabled",
        "--no-sources",
        "--no-build",
        "--no-python-downloads",
        "--python",
        "--cache-dir",
        "--from",
        "--bootstrap-project",
        "--caller-context-version",
    ):
        assert required in source
    assert "runtime-control.json" not in source
    assert "grep" not in source
    assert "sed" not in source


def test_verified_release_renders_launcher_and_closed_runtime_control() -> None:
    from agent_stack.runtime.bootstrap import launcher_contract_from_release

    contract = launcher_contract_from_release(_verified_release())
    rendered = contract.render(TEMPLATE.read_bytes())
    control = contract.runtime_control(rendered)

    assert b"{{" not in rendered
    assert contract.wheel_sha256.encode() in rendered
    assert contract.wheel_url.encode() in rendered
    assert control == {
        "schema_id": "agent-workflow.runtime-control",
        "schema_version": 1,
        "launcher_contract_version": 1,
        "launcher_renderer_version": "runtime-launcher-v1",
        "release_id": contract.release_id,
        "release_manifest_digest": contract.release_manifest_digest,
        "wheel_url": contract.wheel_url,
        "wheel_sha256": contract.wheel_sha256,
        "uv_version_range": ">=0.7.0,<1.0.0",
        "python_version_range": ">=3.11,<3.15",
        "render_digest": hashlib.sha256(rendered).hexdigest(),
    }
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    assert catalog.load_and_validate(control) == control


@pytest.mark.parametrize(
    "wheel_url",
    [
        "http://github.com/example/wheel.whl",
        "https://user:password@github.com/example/wheel.whl",
        "https://github.com/example/wheel.whl\n--index-url=https://evil.invalid",
    ],
)
def test_launcher_contract_rejects_untrusted_or_shell_unsafe_wheel_url(
    wheel_url: str,
) -> None:
    from agent_stack.runtime.bootstrap import launcher_contract_from_release

    with pytest.raises(ValueError, match="AWP_RUNTIME_BINDING_MISMATCH"):
        launcher_contract_from_release(_verified_release(wheel_url=wheel_url))


def test_runtime_control_schema_rejects_unknown_authority_fields() -> None:
    from agent_stack.runtime.bootstrap import launcher_contract_from_release

    contract = launcher_contract_from_release(_verified_release())
    control = contract.runtime_control(contract.render(TEMPLATE.read_bytes()))
    catalog = SchemaCatalog.discover(ROOT / "schemas")

    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**control, "descriptor_is_pre_wheel_authority": True})
