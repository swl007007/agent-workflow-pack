from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "runtime-launcher" / "agent-stack.sh.tmpl"
WHEEL_URL = (
    "https://github.com/example/agent-workflow-pack/releases/download/"
    "v0.1.0/agent_workflow_pack-0.1.0-py3-none-any.whl"
)
WHEEL_SHA256 = "4" * 64


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _render_launcher(project: Path) -> Path:
    from agent_stack.runtime.bootstrap import LauncherContract

    contract = LauncherContract(
        launcher_contract_version=1,
        launcher_renderer_version="runtime-launcher-v1",
        release_id="1" * 64,
        release_manifest_digest="2" * 64,
        wheel_url=WHEEL_URL,
        wheel_sha256=WHEEL_SHA256,
    )
    launcher = project / ".agent-workflow" / "bin" / "agent-stack"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(contract.render(TEMPLATE.read_bytes()))
    launcher.chmod(0o755)
    return launcher


def _bootstrap_tools(
    root: Path,
    capture: Path,
    *,
    uv_exit: int = 0,
    include_python: bool = True,
    uv_symlink: bool = False,
) -> Path:
    tools = root / "tools"
    tools.mkdir()
    env_executable = shutil.which("env") or "/usr/bin/env"
    sort_executable = shutil.which("sort") or "/usr/bin/sort"
    real_uv = tools / "real-uvx"
    _write_executable(
        real_uv,
        "#!/bin/sh\n"
        "if [ \"${1-}\" = --version ]; then echo 'uvx 0.7.17'; exit 0; fi\n"
        f"{env_executable} | {sort_executable} > {str(capture)!r}\n"
        f"printf 'ARG=<%s>\\n' \"$@\" >> {str(capture)!r}\n"
        f"exit {uv_exit}\n",
    )
    uvx = tools / "uvx"
    if uv_symlink:
        uvx.symlink_to(real_uv)
    else:
        shutil.copy2(real_uv, uvx)
    if include_python:
        _write_executable(
            tools / "python3.13",
            "#!/bin/sh\nprintf '3.13\\n'\n",
        )
    for utility in ("env", "mkdir"):
        shutil.copy2(shutil.which(utility) or f"/usr/bin/{utility}", tools / utility)
    return tools


def _run(
    launcher: Path,
    tools: Path,
    home: Path,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    codex_home = home / "codex"
    harness = home / "bin" / "codex"
    codex_home.mkdir(parents=True)
    harness.parent.mkdir(parents=True)
    _write_executable(harness, "#!/bin/sh\nexit 0\n")
    return subprocess.run(
        [str(launcher), *args],
        cwd=launcher.parents[3],
        env={
            "PATH": str(tools),
            "HOME": str(home),
            "CODEX_HOME": str(codex_home),
            "AWP_CALLER_PLATFORM": "codex",
            "AWP_CALLER_HARNESS": str(harness),
            "UV_INDEX": "https://evil.invalid/simple",
            "UV_TOOL_DIR": str(home / "evil-tools"),
            "VIRTUAL_ENV": str(home / "evil-venv"),
            "GITHUB_TOKEN": "do-not-forward",
            "HTTPS_PROXY": "https://user:secret@proxy.invalid",
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_launcher_cleans_environment_and_executes_exact_direct_wheel(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    launcher = _render_launcher(project)
    (project / ".agent-workflow" / "runtime-control.json").write_text(
        "not valid JSON", encoding="utf-8"
    )
    capture = tmp_path / "capture.txt"
    tools = _bootstrap_tools(tmp_path, capture)
    home = tmp_path / "home"
    home.mkdir()

    result = _run(launcher, tools, home, "workspace", "register")

    assert result.returncode == 0, result.stderr
    output = capture.read_text(encoding="utf-8")
    for forbidden in (
        "UV_INDEX=",
        "UV_TOOL_DIR=",
        "VIRTUAL_ENV=",
        "GITHUB_TOKEN=",
        "HTTPS_PROXY=",
        "do-not-forward",
        "evil.invalid",
    ):
        assert forbidden not in output
    assert f"HOME={home / '.cache/agent-workflow-pack/bootstrap-home'}" in output
    assert "LANG=C.UTF-8" in output
    assert "LC_ALL=C.UTF-8" in output
    assert "TZ=UTC" in output
    expected_args = [
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
        str(tools / "python3.13"),
        "--cache-dir",
        str(home / ".cache/agent-workflow-pack/uv-cache"),
        "--from",
        f"{WHEEL_URL}#sha256={WHEEL_SHA256}",
        "agent-stack",
        "--bootstrap-project",
        str(project),
        "--caller-context-version",
        "1",
        "--caller-platform",
        "codex",
        "--caller-user-home",
        str(home),
        "--caller-config-root",
        f"codex_home={home / 'codex'}",
        "--caller-harness-executable",
        str(home / "bin/codex"),
        "--caller-harness-version-probe-id",
        "codex-version-v1",
        "--caller-tty",
        "stdin=false,stdout=false,stderr=false,direct_confirmation_capable=false",
        "workspace",
        "register",
    ]
    assert [line[5:-1] for line in output.splitlines() if line.startswith("ARG=<")] == expected_args


def test_reserved_arguments_fail_before_uv_and_leave_project_unchanged(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    launcher = _render_launcher(project)
    capture = tmp_path / "capture.txt"
    tools = _bootstrap_tools(tmp_path, capture)
    home = tmp_path / "home"
    home.mkdir()
    before = sorted(path.relative_to(project) for path in project.rglob("*"))

    result = _run(launcher, tools, home, "--bootstrap-project", "/tmp/evil")

    assert result.returncode == 2
    assert "reserved launcher argument" in result.stderr
    assert not capture.exists()
    assert sorted(path.relative_to(project) for path in project.rglob("*")) == before


def test_missing_python_and_symlinked_uv_fail_closed_before_package_execution(
    tmp_path: Path,
) -> None:
    for name, tool_options in (
        ("missing-python", {"include_python": False}),
        ("symlinked-uv", {"uv_symlink": True}),
    ):
        case = tmp_path / name
        project = case / "project"
        project.mkdir(parents=True)
        launcher = _render_launcher(project)
        capture = case / "capture.txt"
        tools = _bootstrap_tools(case, capture, **tool_options)
        home = case / "home"
        home.mkdir()

        result = _run(launcher, tools, home, "doctor")

        assert result.returncode == 30
        assert "AWP_RUNTIME_BOOTSTRAP_PREREQUISITE_MISSING" in result.stderr
        assert not capture.exists()


def test_uv_cache_miss_or_hash_failure_is_propagated_without_project_write(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    launcher = _render_launcher(project)
    capture = tmp_path / "capture.txt"
    tools = _bootstrap_tools(tmp_path, capture, uv_exit=55)
    home = tmp_path / "home"
    home.mkdir()
    before = {
        path.relative_to(project): (path.read_bytes() if path.is_file() else None)
        for path in project.rglob("*")
    }

    result = _run(launcher, tools, home, "route", "decide")

    assert result.returncode == 55
    assert f"ARG=<{WHEEL_URL}#sha256={WHEEL_SHA256}>" in capture.read_text(
        encoding="utf-8"
    )
    after = {
        path.relative_to(project): (path.read_bytes() if path.is_file() else None)
        for path in project.rglob("*")
    }
    assert after == before
