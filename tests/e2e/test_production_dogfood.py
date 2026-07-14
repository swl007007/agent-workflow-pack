from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import venv
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from agent_stack.core.api import canonical_json_bytes
from agent_stack.release.identity import release_id
from tools.release.publish_release import _bundle_roots


ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1.2"
TAG = f"v{VERSION}"
REPOSITORY = "swl007007/agent-workflow-pack"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_installed_console(tmp_path: Path) -> tuple[Path, Path, Path]:
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--sdist", "--out-dir", dist],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(dist.glob("agent_workflow_pack-*.whl"))
    sdist = next(dist.glob("agent_workflow_pack-*.tar.gz"))
    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = environment / "bin/python"
    subprocess.run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-index",
            wheel,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return environment / "bin/agent-stack", wheel, sdist


def _transport_boundary(
    tmp_path: Path, wheel: Path, sdist: Path
) -> tuple[Path, dict[str, object]]:
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    asset_base = f"https://github.com/{REPOSITORY}/releases/download/{TAG}"
    assets = {
        "wheel": {
            "name": wheel.name,
            "url": f"{asset_base}/{wheel.name}",
            "size": wheel.stat().st_size,
            "sha256": _sha256(wheel),
        },
        "sdist": {
            "name": sdist.name,
            "url": f"{asset_base}/{sdist.name}",
            "size": sdist.stat().st_size,
            "sha256": _sha256(sdist),
        },
    }
    manifest = {
        "schema_id": "agent-workflow.release-manifest",
        "schema_version": 1,
        "release_id": release_id(
            f"github.com/{REPOSITORY}", "agent-workflow-pack", VERSION
        ),
        "version": VERSION,
        "repository": {
            "host": "github.com",
            "owner": "swl007007",
            "name": "agent-workflow-pack",
            "tag": TAG,
            "immutable_release_required": True,
        },
        "source_commit": source_commit,
        "bundles": _bundle_roots(ROOT),
        "assets": assets,
    }
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_url = f"{asset_base}/release-manifest.json"
    metadata = {
        "tag_name": TAG,
        "target_commitish": source_commit,
        "immutable": True,
        "assets": [
            {
                "name": value["name"],
                "browser_download_url": value["url"],
                "size": value["size"],
                "digest": f"sha256:{value['sha256']}",
            }
            for value in assets.values()
        ]
        + [
            {
                "name": "release-manifest.json",
                "browser_download_url": manifest_url,
                "size": len(manifest_bytes),
                "digest": f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}",
            }
        ],
    }
    api_url = (
        "https://api.github.com/repos/swl007007/agent-workflow-pack/"
        f"releases/tags/{TAG}"
    )
    commit_url = (
        "https://api.github.com/repos/swl007007/agent-workflow-pack/"
        f"commits/{TAG}"
    )
    fixture = {
        api_url: base64.b64encode(canonical_json_bytes(metadata)).decode("ascii"),
        commit_url: base64.b64encode(
            canonical_json_bytes({"sha": source_commit})
        ).decode("ascii"),
        manifest_url: base64.b64encode(manifest_bytes).decode("ascii"),
    }
    boundary = tmp_path / "transport-boundary"
    boundary.mkdir()
    fixture_path = boundary / "release-responses.json"
    fixture_path.write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")
    (boundary / "sitecustomize.py").write_text(
        "import base64, json, os\n"
        "from pathlib import Path\n"
        "import agent_stack.release.trust as trust\n"
        "responses = json.loads(Path(os.environ['AWP_TEST_RELEASE_RESPONSES']).read_text())\n"
        "def fetch_https(url, max_bytes):\n"
        "    body = base64.b64decode(responses[url])\n"
        "    if len(body) > max_bytes: raise RuntimeError('fixture exceeds bound')\n"
        "    return trust.FetchedContent(final_url=url, body=body)\n"
        "trust.fetch_https = fetch_https\n",
        encoding="utf-8",
    )
    return boundary, manifest


def _run(
    console: Path, project: Path, environment: dict[str, str], *arguments: str
) -> dict[str, object]:
    completed = subprocess.run(
        [console, *arguments, "--json"],
        cwd=project,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    document = json.loads(completed.stdout)
    assert isinstance(document, dict)
    assert completed.returncode == 0, (arguments, document, completed.stderr)
    assert document["status"] == "success"
    return cast(dict[str, object], document)


def _result(document: Mapping[str, object]) -> Mapping[str, object]:
    value = document.get("result")
    assert isinstance(value, Mapping)
    return cast(Mapping[str, object], value)


def test_installed_wheel_runs_complete_production_dogfood_chain(tmp_path: Path) -> None:
    console, wheel, sdist = _build_installed_console(tmp_path)
    boundary, manifest = _transport_boundary(tmp_path, wheel, sdist)
    project = tmp_path / "real-project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / ".trellis").mkdir()
    (project / ".specify").mkdir()
    sentinel = project / "user.txt"
    sentinel.write_text("preserve me\n", encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONHOME", "VIRTUAL_ENV"}
    }
    environment.update(
        PYTHONPATH=str(boundary),
        AWP_TEST_RELEASE_RESPONSES=str(boundary / "release-responses.json"),
    )

    _run(console, project, environment, "bootstrap")
    preview = _run(console, project, environment, "init", "--dry-run")
    assert _result(preview)["writes_performed"] == 0
    initialized = _run(console, project, environment, "init")
    assert _result(initialized)["committed"] is True
    doctor = _run(console, project, environment, "doctor")
    assert _result(doctor)["production_owner_binding_count"] == 17
    routing = _run(console, project, environment, "test-routing")
    routing_result = _result(routing)
    assert routing_result["default_route"] == "native-light"
    assert routing_result["heavy_route"] == "speckit-superpowers"
    assert routing_result["heavy_orchestrator"] == "heavy-development-router"
    assert routing_result["superpowers_planner_exposed"] is False
    assert routing_result["superpowers_executor_exposed"] is False
    sync_preview = _run(console, project, environment, "sync", "--dry-run")
    first_sync = _run(console, project, environment, "sync")
    second_sync = _run(console, project, environment, "sync")

    assert _result(sync_preview)["no_op"] is True
    assert _result(first_sync)["no_op"] is True
    assert _result(second_sync)["no_op"] is True
    assert sentinel.read_text(encoding="utf-8") == "preserve me\n"
    assert (project / ".trellis").is_dir()
    assert (project / ".specify").is_dir()
    committed_manifest = json.loads(
        (project / ".agent-workflow/manifest.json").read_text(encoding="utf-8")
    )
    assert committed_manifest["release_id"] == manifest["release_id"]
