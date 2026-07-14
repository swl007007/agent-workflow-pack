from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_stack.providers.api import execute_provider
from tests.integration.providers.test_initializer import (
    _cache_root,
    _expected_root,
    _install_provider,
    _plan,
)


@given(st.sampled_from(("first", "second", "third")))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_independent_clean_roots_produce_the_same_validated_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    run_root = tmp_path / suffix
    cache = _cache_root(run_root, monkeypatch)
    _install_provider(
        cache,
        "a" * 64,
        "#!/bin/sh\nmkdir -p \"$AWP_OUTPUT_DIR\"\nprintf 'stable-output\\n' > \"$AWP_OUTPUT_DIR/result.txt\"\n",
    )
    expected = _expected_root(run_root)

    result = execute_provider(_plan(expected), None)

    assert result.candidate_output_root_digest == expected
