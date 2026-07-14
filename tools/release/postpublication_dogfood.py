#!/usr/bin/env python3
"""Execute the immutable release's canonical command and durable launcher handoff."""

from __future__ import annotations

import argparse
import json
import os
import pty
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import cast


def _run_json(command: list[str], root: Path) -> dict[str, object]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise SystemExit(completed.stderr or completed.stdout)
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise SystemExit("command did not return a JSON object")
    if value.get("status") != "success":
        raise SystemExit(completed.stdout)
    return cast(dict[str, object], value)


def _run_canonical_in_pty(script: Path, root: Path) -> None:
    master, slave = pty.openpty()
    try:
        process = subprocess.Popen(
            ["sh", str(script)], cwd=root, stdin=slave, stdout=slave, stderr=slave
        )
    finally:
        os.close(slave)
    output = bytearray()
    while process.poll() is None:
        try:
            output.extend(os.read(master, 65536))
        except OSError:
            break
    process.wait()
    os.close(master)
    if process.returncode:
        raise SystemExit(output.decode("utf-8", errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    arguments = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    request = urllib.request.Request(
        "https://api.github.com/repos/swl007007/agent-workflow-pack/releases/tags/"
        f"v{arguments.version}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        metadata = json.load(response)
    body = metadata.get("body")
    if not isinstance(body, str) or "```sh\n" not in body:
        raise SystemExit("canonical release command is unavailable")
    command = body.split("```sh\n", 1)[1].split("```", 1)[0]
    with tempfile.TemporaryDirectory(prefix="awp-postpublication-") as temporary:
        root = Path(temporary) / "project"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        script = Path(temporary) / "canonical-first-install.sh"
        script.write_text(command, encoding="utf-8")
        _run_canonical_in_pty(script, root)
        launcher = root / ".agent-workflow/bin/agent-stack"
        if not launcher.is_file() or not os.access(launcher, os.X_OK):
            raise SystemExit("canonical first-install did not create an executable launcher")
        _run_json([str(launcher), "doctor", "--json"], root)
        _run_json([str(launcher), "test-routing", "--json"], root)
        _run_json([str(launcher), "sync", "--dry-run", "--json"], root)
        _run_json([str(launcher), "sync", "--json"], root)
        final = _run_json([str(launcher), "sync", "--dry-run", "--json"], root)
        result = final.get("result")
        if not isinstance(result, dict) or result.get("no_op") is not True:
            raise SystemExit("second sync is not a strict no-op")
    print(json.dumps({"status": "passed", "version": arguments.version}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
