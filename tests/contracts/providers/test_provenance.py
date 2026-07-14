from __future__ import annotations

from pathlib import Path

import pytest

from agent_stack.core.api import CoreFailure, SchemaCatalog
from agent_stack.providers.errors import ProviderFailure
from agent_stack.providers.provenance import (
    build_provenance_record,
    generate_third_party_notices,
    validate_provenance_closure,
)


ROOT = Path(__file__).resolve().parents[3]


def _record() -> dict[str, object]:
    return build_provenance_record(
        component_id="trellis-initializer",
        version="1.0.0",
        source_digest="a" * 64,
        upstream_path="src/initializer.py",
        license_expression="MIT",
        license_text_digest="b" * 64,
        modified=True,
        modification_notice_digest="c" * 64,
        projected_unit_ids=("render-unit:trellis",),
    )


def test_provenance_binds_spdx_license_modification_and_projected_units() -> None:
    record = _record()
    closure = validate_provenance_closure([record], {"render-unit:trellis"})
    notices = generate_third_party_notices(closure)

    assert closure == (record,)
    assert "trellis-initializer 1.0.0" in notices
    assert "MIT" in notices


@pytest.mark.parametrize(
    "mutation",
    [
        {"license_expression": ""},
        {"license_text_digest": "canonical-null"},
        {"modification_notice_digest": "canonical-null"},
        {"projected_unit_ids": []},
    ],
)
def test_incomplete_provenance_fails_release_evidence(mutation: dict[str, object]) -> None:
    record = {**_record(), **mutation}
    with pytest.raises(ProviderFailure, match="AWP_PROVENANCE_INCOMPLETE"):
        validate_provenance_closure([record], {"render-unit:trellis"})


def test_provenance_schema_is_closed() -> None:
    catalog = SchemaCatalog.discover(ROOT / "schemas")
    catalog.load_and_validate(_record())
    with pytest.raises(CoreFailure, match="AWP_SCHEMA_INVALID"):
        catalog.load_and_validate({**_record(), "unknown": True})
