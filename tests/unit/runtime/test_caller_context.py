from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_stack.core.api import CoreFailure, SchemaCatalog


ROOT = Path(__file__).resolve().parents[3]


def _document(home: Path, harness: Path) -> dict[str, object]:
    return {
        "schema_id": "agent-workflow.caller-context",
        "schema_version": 1,
        "platform": "codex",
        "user_home": str(home),
        "config_roots": {"codex_home": str(home / "codex")},
        "harness": {
            "executable": str(harness),
            "version_probe_id": "codex-version-v1",
        },
        "tty": {
            "stdin": False,
            "stdout": False,
            "stderr": False,
            "direct_confirmation_capable": False,
        },
    }


def _authority() -> object:
    from agent_stack.runtime.authority import VerifiedRuntimeAuthority

    return VerifiedRuntimeAuthority(
        release=None,
        runtime_role="committed",
        command="test",
        recovery_transaction_id=None,
        release_id="a" * 64,
    )


def test_caller_context_schema_is_closed_and_separates_schema_version() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    home = Path("/home/example")
    document = _document(home, home / "bin/codex")

    assert catalog.load_and_validate(document) == document
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**document, "token": "secret"})


def test_verified_context_requires_authority_before_any_external_probe(tmp_path: Path) -> None:
    from agent_stack.runtime.caller_context import verify_caller_context
    from agent_stack.runtime.errors import RuntimeFailure

    home = tmp_path / "home"
    harness = home / "bin" / "codex"
    (home / "codex").mkdir(parents=True)
    harness.parent.mkdir(parents=True)
    harness.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    harness.chmod(0o755)
    calls: list[str] = []

    def probe(_: object) -> dict[str, object]:
        calls.append("probed")
        return {
            "user_home": str(home),
            "harness_executable": str(harness),
            "harness_version_probe_id": "codex-version-v1",
            "tty": {
                "stdin": False,
                "stdout": False,
                "stderr": False,
                "direct_confirmation_capable": False,
            },
        }

    with pytest.raises(RuntimeFailure, match="AWP_RUNTIME_BINDING_MISMATCH"):
        verify_caller_context(_document(home, harness), object(), probe=probe)
    assert calls == []

    verified = verify_caller_context(_document(home, harness), _authority(), probe=probe)
    assert calls == ["probed"]
    assert verified.platform == "codex"
    assert verified.user_home == home
    assert verified.config_roots == {"codex_home": home / "codex"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_home", "relative/home"),
        ("user_home", "/home/example\n--secret"),
        ("platform", "codex\nclaude"),
        ("config_roots", {"codex_home": "relative/config"}),
        ("config_roots", {"AWS_SECRET_ACCESS_KEY": "/tmp/value"}),
    ],
)
def test_context_rejects_relative_control_and_secret_shaped_fields(
    tmp_path: Path, field: str, value: object
) -> None:
    from agent_stack.runtime.caller_context import verify_caller_context
    from agent_stack.runtime.errors import RuntimeFailure

    home = tmp_path / "home"
    harness = home / "bin/codex"
    (home / "codex").mkdir(parents=True)
    harness.parent.mkdir(parents=True)
    harness.write_text("#!/bin/sh\n", encoding="utf-8")
    harness.chmod(0o755)
    document = _document(home, harness)
    document[field] = value

    with pytest.raises(RuntimeFailure, match="AWP_CALLER_CONTEXT_INVALID"):
        verify_caller_context(document, _authority(), probe=lambda _: {})


def test_context_rejects_symlinked_harness_and_probe_mismatch(tmp_path: Path) -> None:
    from agent_stack.runtime.caller_context import verify_caller_context
    from agent_stack.runtime.errors import RuntimeFailure

    home = tmp_path / "home"
    real = home / "bin/real-codex"
    harness = home / "bin/codex"
    (home / "codex").mkdir(parents=True)
    real.parent.mkdir(parents=True)
    real.write_text("#!/bin/sh\n", encoding="utf-8")
    real.chmod(0o755)
    harness.symlink_to(real)

    with pytest.raises(RuntimeFailure, match="AWP_CALLER_CONTEXT_INVALID"):
        verify_caller_context(_document(home, harness), _authority(), probe=lambda _: {})

    harness.unlink()
    os.replace(real, harness)
    with pytest.raises(RuntimeFailure, match="AWP_CALLER_CONTEXT_INVALID"):
        verify_caller_context(
            _document(home, harness),
            _authority(),
            probe=lambda _: {
                "user_home": str(home),
                "harness_executable": str(harness),
                "harness_version_probe_id": "codex-version-v2",
                "tty": {
                    "stdin": False,
                    "stdout": False,
                    "stderr": False,
                    "direct_confirmation_capable": False,
                },
            },
        )
