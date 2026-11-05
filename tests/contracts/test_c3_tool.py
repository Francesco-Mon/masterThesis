"""C3 - tool call and result (R12)."""

import pytest
from pydantic import ValidationError

from cpsagent.contracts import Operation, ToolCallAdapter, ToolError, ToolResult

VALID_CALLS = [
    {
        "operation": "invokeCommand",
        "args": {"deviceId": "lamp_hallway", "command": "on", "value": None},
    },
    {
        "operation": "invokeCommand",
        "args": {"deviceId": "blind_office", "command": "set", "value": 50},
    },
    {"operation": "listZones", "args": {}},
    {"operation": "listZones"},
    {"operation": "listDevices", "args": {"zoneId": "hallway"}},
    {"operation": "getDeviceState", "args": {"deviceId": "lamp_hallway"}},
]

INVALID_CALLS = [
    {"operation": "deleteDevice", "args": {"deviceId": "lamp_hallway"}},  # not allowed
    {"operation": "listdevices", "args": {"zoneId": "hallway"}},  # wrong case
    {"operation": "invokeCommand", "args": {"deviceId": "lamp_hallway"}},  # command missing
    {"operation": "listDevices", "args": {"deviceId": "lamp_hallway"}},  # args of another op
    {"operation": "listZones", "args": {"zoneId": "hallway"}},  # listZones takes no args
    {"args": {"zoneId": "hallway"}},  # operation missing
]


@pytest.mark.parametrize("data", VALID_CALLS)
def test_valid_call(data):
    call = ToolCallAdapter.validate_python(data)
    assert call.operation in Operation


@pytest.mark.parametrize("data", INVALID_CALLS)
def test_invalid_call(data):
    with pytest.raises(ValidationError):
        ToolCallAdapter.validate_python(data)


def test_operation_enum_is_exactly_the_four():
    assert {op.value for op in Operation} == {
        "listZones",
        "listDevices",
        "getDeviceState",
        "invokeCommand",
    }


def test_call_round_trip_uses_camel_case():
    call = ToolCallAdapter.validate_python(VALID_CALLS[0])
    wire = ToolCallAdapter.dump_python(call, mode="json")
    assert wire == VALID_CALLS[0]


VALID_RESULTS = [
    {
        "ok": True,
        "operation": "invokeCommand",
        "state": {"deviceId": "lamp_hallway", "power": "on"},
        "error": None,
    },
    {"ok": True, "operation": "listZones", "state": [{"zoneId": "hallway", "adjacency": []}]},
    {"ok": False, "operation": "invokeCommand", "error": "command_not_supported"},
    {"ok": False, "operation": None, "error": "operation_not_allowed"},
]

INVALID_RESULTS = [
    {"ok": True, "operation": "invokeCommand", "error": "command_not_supported"},  # ok + error
    {"ok": False, "operation": "invokeCommand"},  # failed without error
    {"ok": False, "operation": "invokeCommand", "error": "device_on_fire"},  # unknown error
    {"ok": True, "operation": "deleteDevice"},  # operation outside the enum
    {"ok": True, "operation": None},  # null operation only when not allowed
    {"operation": "listZones"},  # ok missing
]


@pytest.mark.parametrize("data", VALID_RESULTS)
def test_valid_result(data):
    ToolResult.model_validate(data)


@pytest.mark.parametrize("data", INVALID_RESULTS)
def test_invalid_result(data):
    with pytest.raises(ValidationError):
        ToolResult.model_validate(data)


def test_rejected_call_maps_to_operation_not_allowed():
    # What the Environment Interface does with a call outside the enum.
    try:
        ToolCallAdapter.validate_python(INVALID_CALLS[0])
    except ValidationError:
        result = ToolResult(ok=False, operation=None, error=ToolError.OPERATION_NOT_ALLOWED)
    assert result.model_dump(mode="json")["error"] == "operation_not_allowed"
