from __future__ import annotations

from pathlib import Path

from agent_stack.cli.redaction import sanitize_document


def test_redaction_removes_url_credentials_secrets_and_external_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    document = sanitize_document(
        {
            "url": "https://alice:pw@example.test/a?token=secret&ok=yes",
            "authorization": "Bearer top-secret",
            "proxy_password": "proxy-secret",
            "external_stderr": "failed with password=hunter2 and token abcdefghijklmnop",
            "managed_path": root / ".agent-workflow" / "Manifest.json",
            "config_path": tmp_path / "outside" / "config.json",
        },
        repository_root=root,
    )

    flattened = repr(document)
    for secret in ("alice", "pw", "secret", "top-secret", "proxy-secret", "hunter2", "abcdefghijklmnop"):
        assert secret not in flattened
    assert document["url"] == "https://example.test/a?token=%5BREDACTED%5D&ok=yes"
    assert document["authorization"] == "[REDACTED]"
    assert document["managed_path"] == ".agent-workflow/Manifest.json"
    assert document["config_path"] == "<external>"


def test_debug_does_not_disable_redaction_or_expose_traceback() -> None:
    document = sanitize_document(
        {
            "debug": True,
            "traceback": "Traceback: Authorization: Bearer abcdefghijklmnop",
            "details": {"cookie": "session=secret"},
        }
    )

    assert document["traceback"] == "[REDACTED]"
    assert document["details"]["cookie"] == "[REDACTED]"
