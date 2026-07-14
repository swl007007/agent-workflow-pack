from __future__ import annotations

import hashlib
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from agent_stack.reconcile.api import render
from tests.unit.reconcile.test_render import (
    artifact,
    make_ir,
    provider_result,
    render_unit,
)


@given(text=st.text(alphabet=st.characters(exclude_categories=("Cs",)), max_size=200))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_independent_provider_roots_render_identically(tmp_path: Path, text: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n") + "\n"
    source = normalized.encode("utf-8")
    case_root = tmp_path / hashlib.sha256(source).hexdigest()
    trees = []
    for name in ("first", "second"):
        root = case_root / name
        root.mkdir(parents=True, exist_ok=True)
        (root / "source.txt").write_bytes(source)
        unit = render_unit(
            "source.txt",
            source,
            "output.txt",
            source,
            definition_id="output",
            surface_id="skill:output",
        )
        trees.append(
            render(
                make_ir([unit], [artifact("output", "source.txt", "output.txt")]),
                [provider_result(root)],
            )
        )

    assert trees[0].content_root_digest == trees[1].content_root_digest
    assert trees[0].distribution_render_digest == trees[1].distribution_render_digest
