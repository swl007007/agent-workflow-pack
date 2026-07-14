"""Materialize an already verified staged tree outside the target project."""

from __future__ import annotations

import os
from pathlib import Path

from .errors import RendererFailure
from .models import StagedRenderTree


def materialize_staged_tree(tree: StagedRenderTree, root: Path) -> None:
    if root.exists() and (root.is_symlink() or any(root.iterdir())):
        raise RendererFailure(
            "AWP_RENDER_NONDETERMINISTIC", "staging root is not an empty real directory"
        )
    root.mkdir(parents=True, exist_ok=True)
    for record in tree.files:
        target = root / record.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(record.candidate_bytes)
        if record.candidate_mode != "canonical-null":
            os.chmod(target, int(record.candidate_mode, 8))
