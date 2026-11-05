"""The committed JSON Schemas in docs/schemas/ must match the Pydantic models."""

import pytest

from cpsagent.contracts.export_schemas import SCHEMA_DIR, SCHEMAS, render


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_file_up_to_date(name):
    path = SCHEMA_DIR / f"{name}.schema.json"
    assert path.exists(), "run: python -m cpsagent.contracts.export_schemas"
    assert path.read_text(encoding="utf-8") == render(SCHEMAS[name]), (
        f"{path.name} is stale; run: python -m cpsagent.contracts.export_schemas"
    )
