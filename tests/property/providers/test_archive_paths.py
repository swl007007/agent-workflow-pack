from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_stack.providers.archive import inspect_archive
from agent_stack.providers.errors import ProviderFailure
from tests.unit.providers.test_archive import _policy


@given(
    st.sampled_from(
        (
            "../escape",
            "/absolute",
            "./dot",
            "a/../b",
            "a//b",
            "C:/device",
            "a/./b",
        )
    )
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_unsafe_member_paths_never_pass_normalization(tmp_path: Path, member: str) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(member, b"x")
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()

    with pytest.raises(ProviderFailure, match="AWP_PROVIDER_ARCHIVE_UNSAFE"):
        inspect_archive(archive, expected, _policy())
