from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_stack.core.api import digest
from agent_stack.providers.api import execute_provider
from agent_stack.providers.archive import content_root_digest
from agent_stack.providers.errors import ProviderFailure
from agent_stack.providers.models import ProviderPlan
from agent_stack.providers.sandbox import run_sandboxed


def _cache_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    xdg = tmp_path / "xdg-cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg))
    return xdg / "agent-workflow-pack"


def _expected_root(tmp_path: Path) -> str:
    root = tmp_path / "expected"
    root.mkdir(parents=True)
    result = root / "result.txt"
    result.write_bytes(b"stable-output\n")
    os.chmod(result, 0o644)
    return content_root_digest(root)


def _install_provider(cache: Path, artifact_digest: str, script: str) -> None:
    root = cache / "extracted/sha256" / artifact_digest[:2] / artifact_digest
    executable = root / "bin/init.sh"
    executable.parent.mkdir(parents=True)
    executable.write_text(script, encoding="utf-8")
    os.chmod(executable, 0o755)


def _plan(expected_root: str, *, artifact_digest: str = "a" * 64) -> ProviderPlan:
    command = {"executable_id": "bin/init.sh", "arguments": []}
    return ProviderPlan(
        provider_id="test-initializer",
        provider_version="1.0.0",
        provider_artifact_digest=artifact_digest,
        command_digest=digest("agent-workflow.provider-command.v1", command),
        command=command,
        project_id="11111111-1111-4111-8111-111111111111",
        workspace_instance_id="22222222-2222-4222-8222-222222222222",
        workflow_lock_digest="c" * 64,
        input_digests=(),
        requested_controls={
            "temporary-home": "required",
            "environment-allowlist": "required",
            "network-isolation": "best-effort",
        },
        measured_isolation_gaps=(),
        approval_challenge="d" * 64,
        prospective_transaction_id="33333333-3333-4333-8333-333333333333",
        deterministic_output_contract={
            "schema_id": "agent-workflow.initializer-output-contract",
            "schema_version": 1,
            "provider_id": "test-initializer",
            "provider_version": "1.0.0",
            "command_digest": digest("agent-workflow.provider-command.v1", command),
            "input_digests": [],
            "locale": "C.UTF-8",
            "timezone": "UTC",
            "environment": {},
            "umask": "0022",
            "mode_policy_id": "posix-mode-v1",
            "file_order_policy_id": "normalized-path-order-v1",
            "renderer_id": "test-renderer",
            "renderer_version": 1,
            "expected_content_root_digest": expected_root,
            "timeout_seconds": 3,
            "max_output_bytes": 4096,
            "max_memory_bytes": 134217728,
            "max_cpu_seconds": 2,
        },
    )


def test_initializer_runs_with_clean_environment_and_validated_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache_root(tmp_path, monkeypatch)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-leak")
    script = """#!/bin/sh
set -eu
[ -z "${AWS_SECRET_ACCESS_KEY+x}" ]
[ "$LC_ALL" = "C.UTF-8" ]
[ "$TZ" = "UTC" ]
if read leaked; then exit 92; fi
mkdir -p "$AWP_OUTPUT_DIR"
printf 'stable-output\n' > "$AWP_OUTPUT_DIR/result.txt"
"""
    _install_provider(cache, "a" * 64, script)
    target = tmp_path / "target-project"
    target.mkdir()
    sentinel = target / "sentinel"
    sentinel.write_text("unchanged", encoding="utf-8")

    result = execute_provider(_plan(_expected_root(tmp_path)), None)

    assert result.terminal_state == "succeeded"
    assert result.candidate_output_root_digest == _expected_root(tmp_path / "again")
    assert Path(result.candidate_output_path).is_dir()
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


def test_timeout_output_limit_and_expected_root_mismatch_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache_root(tmp_path, monkeypatch)
    _install_provider(cache, "a" * 64, "#!/bin/sh\nsleep 30\n")
    plan = _plan(_expected_root(tmp_path))
    contract = dict(plan.deterministic_output_contract)
    contract["timeout_seconds"] = 1
    timeout_plan = ProviderPlan(**{**plan.__dict__, "deterministic_output_contract": contract})
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_CONTAINMENT_AMBIGUOUS"):
        execute_provider(timeout_plan, None)

    _install_provider(
        cache,
        "b" * 64,
        "#!/bin/sh\nmkdir -p \"$AWP_OUTPUT_DIR\"\nprintf wrong > \"$AWP_OUTPUT_DIR/result.txt\"\n",
    )
    with pytest.raises(ProviderFailure, match="AWP_INITIALIZER_NONDETERMINISTIC"):
        execute_provider(_plan(_expected_root(tmp_path / "other"), artifact_digest="b" * 64), None)


def test_unapproved_measured_gap_never_reaches_broker_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache_root(tmp_path, monkeypatch)
    _install_provider(cache, "a" * 64, "#!/bin/sh\nexit 0\n")
    plan = _plan(_expected_root(tmp_path))
    plan = ProviderPlan(**{**plan.__dict__, "measured_isolation_gaps": ("network-isolation",)})
    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_APPROVAL_REQUIRED"):
        execute_provider(plan, None)


def test_output_limit_terminates_before_later_side_effect(tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist"
    executable = tmp_path / "noisy.sh"
    executable.write_text(
        "#!/bin/sh\n"
        "i=0\n"
        "while [ \"$i\" -lt 256 ]; do\n"
        "  printf 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'\n"
        "  i=$((i + 1))\n"
        "done\n"
        "sleep 1\n"
        ": > \"$1\"\n",
        encoding="utf-8",
    )
    os.chmod(executable, 0o755)

    with pytest.raises(ProviderFailure, match="output limit"):
        run_sandboxed(
            [str(executable), str(sentinel)],
            cwd=tmp_path,
            environment={"PATH": "/usr/bin:/bin"},
            timeout_seconds=3,
            max_output_bytes=64,
            max_memory_bytes=134217728,
            max_cpu_seconds=2,
            umask=0o022,
        )

    assert not sentinel.exists()


def test_symlinked_provider_executable_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache_root(tmp_path, monkeypatch)
    provider_root = cache / "extracted/sha256" / "aa" / ("a" * 64)
    real = provider_root / "bin/real.sh"
    real.parent.mkdir(parents=True)
    real.write_text(
        "#!/bin/sh\nmkdir -p \"$AWP_OUTPUT_DIR\"\n"
        "printf 'stable-output\\n' > \"$AWP_OUTPUT_DIR/result.txt\"\n",
        encoding="utf-8",
    )
    os.chmod(real, 0o755)
    (real.parent / "init.sh").symlink_to("real.sh")

    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_CACHE_CORRUPT"):
        execute_provider(_plan(_expected_root(tmp_path)), None)
