"""Export the JSON Schema of every contract to docs/schemas/.

Run: python -m cpsagent.contracts.export_schemas
A test checks that the committed files match the models, so rerun after any change.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from . import (
    ActionPlan,
    EventRecord,
    GroundingRequest,
    GroundingResultAdapter,
    StoredRecord,
    StructuredIntent,
    ToolCallAdapter,
    ToolResult,
    ZoneChangedEvent,
    ZoneEstimate,
)

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "docs" / "schemas"

# file name -> model or TypeAdapter (for the discriminated unions)
SCHEMAS: dict[str, Any] = {
    "c1_zone_estimate": ZoneEstimate,
    "c1_zone_changed_event": ZoneChangedEvent,
    "c2_grounding_request": GroundingRequest,
    "c2_structured_intent": StructuredIntent,
    "c2_grounding_result": GroundingResultAdapter,
    "c2_action_plan": ActionPlan,
    "c3_tool_call": ToolCallAdapter,
    "c3_tool_result": ToolResult,
    "c4_event_record": EventRecord,
    "c4_stored_record": StoredRecord,
}


def schema_of(target: Any) -> dict[str, Any]:
    if isinstance(target, TypeAdapter):
        return target.json_schema(by_alias=True)
    return target.model_json_schema(by_alias=True)


def render(target: Any) -> str:
    return json.dumps(schema_of(target), indent=2, sort_keys=True) + "\n"


def main() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for name, target in SCHEMAS.items():
        path = SCHEMA_DIR / f"{name}.schema.json"
        path.write_text(render(target), encoding="utf-8")
        print(f"wrote {path.relative_to(SCHEMA_DIR.parents[1])}")


if __name__ == "__main__":
    main()
