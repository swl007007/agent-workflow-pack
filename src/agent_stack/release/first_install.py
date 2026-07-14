"""Pure deterministic renderer for the external canonical first-install shell."""

from __future__ import annotations

import hashlib
import re
import shlex
from urllib.parse import urlsplit

from agent_stack.release.errors import LifecycleFailure
from agent_stack.release.manifest import VerifiedRelease


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_REPOSITORY_ID = "github.com/swl007007/agent-workflow-pack"


def _failure(message: str, **details: object) -> LifecycleFailure:
    return LifecycleFailure(
        "AWP_CANONICAL_FIRST_INSTALL_INVALID",
        f"canonical first-install {message}",
        exit_code=30,
        details=details,
    )


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise _failure("digest is invalid", field=field)
    return value


def _closed_wheel_url(value: object, version: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise _failure("wheel URL is invalid")
    if any(ord(character) < 32 for character in value):
        raise _failure("wheel URL is shell-unsafe")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise _failure("wheel URL is invalid") from error
    prefix = f"/swl007007/agent-workflow-pack/releases/download/v{version}/"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(prefix)
        or not parsed.path.endswith(".whl")
    ):
        raise _failure("wheel URL violates frozen release authority")
    return value


def render_canonical_first_install_shell(
    verified_manifest: VerifiedRelease,
    manifest_digest: str,
) -> str:
    """Render stable POSIX shell from verified release authority only."""

    identity = verified_manifest.identity
    if not verified_manifest.immutable_release:
        raise _failure("release is not immutable")
    if identity.repository_id != _REPOSITORY_ID:
        raise _failure("repository identity is invalid")
    if identity.distribution_name != "agent-workflow-pack":
        raise _failure("distribution identity is invalid")
    version = identity.version
    if _VERSION.fullmatch(version) is None:
        raise _failure("version is invalid")
    digest_value = _digest(manifest_digest, "manifest_digest")
    if digest_value != verified_manifest.manifest_digest:
        raise _failure("manifest digest disagrees with verified authority")
    try:
        wheel = verified_manifest.assets["wheel"]
        wheel_url = _closed_wheel_url(wheel["url"], version)
        wheel_sha256 = _digest(wheel["sha256"], "wheel.sha256")
    except (KeyError, TypeError) as error:
        raise _failure("wheel authority is incomplete") from error

    tag = f"v{version}"
    manifest_url = (
        f"https://github.com/swl007007/agent-workflow-pack/releases/download/{tag}/"
        "release-manifest.json"
    )
    api_url = (
        "https://api.github.com/repos/swl007007/agent-workflow-pack/releases/tags/"
        f"{tag}"
    )
    verifier = (
        "import hashlib,json,sys,urllib.request;"
        "api,manifest,expected,tag=sys.argv[1:];"
        "meta=json.load(urllib.request.urlopen(api,timeout=60));"
        "assert meta.get('immutable') is True and meta.get('tag_name')==tag;"
        "body=urllib.request.urlopen(manifest,timeout=60).read();"
        "assert hashlib.sha256(body).hexdigest()==expected"
    )
    values = {
        "version": version,
        "tag": tag,
        "manifest_url": manifest_url,
        "manifest_digest": digest_value,
        "api_url": api_url,
        "wheel_url": wheel_url,
        "wheel_sha256": wheel_sha256,
        "verifier": verifier,
    }
    quoted = {name: shlex.quote(value) for name, value in values.items()}
    return f"""#!/bin/sh
set -eu
version={quoted['version']}
tag={quoted['tag']}
manifest_url={quoted['manifest_url']}
manifest_digest={quoted['manifest_digest']}
api_url={quoted['api_url']}
wheel_url={quoted['wheel_url']}
wheel_sha256={quoted['wheel_sha256']}
project_root=$(pwd -P)
caller_home=${{HOME-}}
case "$project_root:$caller_home" in /*:/*) ;; *) exit 30 ;; esac
uvx_path=$(command -v uvx 2>/dev/null || command -v uv 2>/dev/null || true)
case "$uvx_path" in /*) ;; *) exit 30 ;; esac
python_path=
for name in python3.14 python3.13 python3.12 python3.11; do
  candidate=$(command -v "$name" 2>/dev/null || true)
  case "$candidate" in /*) python_path=$candidate; break ;; esac
done
[ -n "$python_path" ] || exit 30
env_path=$(command -v env 2>/dev/null || true)
mkdir_path=$(command -v mkdir 2>/dev/null || true)
case "$env_path:$mkdir_path" in /*:/*) ;; *) exit 30 ;; esac
"$python_path" -c {quoted['verifier']} "$api_url" "$manifest_url" "$manifest_digest" "$tag" || exit 30
cache_root=$caller_home/.cache/agent-workflow-pack
bootstrap_home=$cache_root/bootstrap-home
uv_cache=$cache_root/uv-cache
"$mkdir_path" -p "$bootstrap_home" "$uv_cache" || exit 30
stdin_tty=false; stdout_tty=false; stderr_tty=false
[ -t 0 ] && stdin_tty=true || true
[ -t 1 ] && stdout_tty=true || true
[ -t 2 ] && stderr_tty=true || true
direct_confirmation=false
[ "$stdin_tty" = true ] && [ "$stdout_tty" = true ] && direct_confirmation=true || true
caller_tty="stdin=$stdin_tty,stdout=$stdout_tty,stderr=$stderr_tty,direct_confirmation_capable=$direct_confirmation"
bootstrap_path=${{uvx_path%/*}}:${{python_path%/*}}:${{env_path%/*}}:${{mkdir_path%/*}}
wheel_requirement=$wheel_url#sha256=$wheel_sha256
run_exact_cli() {{
  "$env_path" -i PATH="$bootstrap_path" HOME="$bootstrap_home" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
    "$uvx_path" --isolated --no-config --no-env-file --no-index \
    --keyring-provider disabled --no-sources --no-build --no-python-downloads \
    --python "$python_path" --cache-dir "$uv_cache" --from "$wheel_requirement" agent-stack \
    --bootstrap-project "$project_root" --caller-context-version 1 \
    --caller-platform unknown --caller-user-home "$caller_home" --caller-tty "$caller_tty" \
    "$@"
}}
run_exact_cli bootstrap --json
run_exact_cli init --dry-run --json
run_exact_cli init --json
project_launcher="$project_root/.agent-workflow/bin/agent-stack"
[ -x "$project_launcher" ] || exit 30
"$project_launcher" doctor --json
"""


def canonical_first_install_command_digest(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def render_release_body(
    verified_manifest: VerifiedRelease, manifest_digest: str
) -> str:
    command = render_canonical_first_install_shell(verified_manifest, manifest_digest)
    version = verified_manifest.identity.version
    wheel = verified_manifest.assets["wheel"]
    sdist = verified_manifest.assets["sdist"]
    manifest_url = (
        "https://github.com/swl007007/agent-workflow-pack/releases/download/"
        f"v{version}/release-manifest.json"
    )
    return (
        "<!-- generated by agent-workflow-pack; do not edit -->\n"
        f"# Agent Workflow Pack v{version}\n\n"
        f"Source commit: `{verified_manifest.source_commit}`\n\n"
        "This release is immutable. Use only the generated command below; do not "
        "construct a latest-version or alternate-index install.\n\n"
        "## Canonical first-install command\n\n"
        f"```sh\n{command}```\n\n"
        "## Frozen evidence\n\n"
        f"- Wheel SHA-256: `{wheel['sha256']}`\n"
        f"- sdist SHA-256: `{sdist['sha256']}`\n"
        f"- Manifest SHA-256: `{manifest_digest}`\n"
        f"- Detached manifest: {manifest_url}\n"
    )
