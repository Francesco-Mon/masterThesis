"""C4 - event record (R16) and stored form."""

import pytest
from pydantic import ValidationError

from cpsagent.contracts import TRANSITIONS, EventRecord, Guard, State, StoredRecord

RECORD = {
    "seq": 3,
    "time": "2026-11-10T09:30:13Z",
    "session": "sess-001",
    "from": "Plan",
    "to": "Act",
    "guard": "T4",
    "zone": {
        "zoneId": "hallway",
        "confidence": 0.87,
        "observedAt": "2026-11-10T09:30:12Z",
        "previousZoneId": None,
    },
    "intent": {
        "action": "activate",
        "controlledProperty": "light",
        "scope": "path",
        "persistence": "following",
        "confidence": 0.9,
    },
    "action": {"operation": "invokeCommand", "args": {"deviceId": "lamp_hallway", "command": "on"}},
    "outcome": None,
}

VALID_RECORDS = [
    RECORD,
    {
        "seq": 1,
        "time": "2026-11-10T09:30:00Z",
        "session": "s",
        "from": "Perceive",
        "to": "Interpret",
        "guard": "T1",
    },
    {
        **RECORD,
        "seq": 5,
        "from": "Act",
        "to": "Observe",
        "guard": "T6",
        "outcome": {"ok": True, "operation": "invokeCommand", "state": {"power": "on"}},
    },
    {
        **RECORD,
        "seq": 9,
        "from": "Plan",
        "to": "Recover",
        "guard": "T5",
        "action": None,
        "outcome": "capability_absent",
    },
]

INVALID_RECORDS = [
    {**RECORD, "seq": 0},  # seq starts at 1
    {**RECORD, "guard": "T2"},  # T2 is Interpret -> Plan, not Plan -> Act
    {**RECORD, "guard": "T13"},  # no such row
    {**RECORD, "to": "Sleep"},  # unknown state
    {**RECORD, "time": "2026-11-10T09:30:13"},  # naive time
    {k: v for k, v in RECORD.items() if k != "session"},  # missing field
    {**RECORD, "action": {"operation": "rebootBuilding", "args": {}}},  # not an allowed op
]


@pytest.mark.parametrize("data", VALID_RECORDS)
def test_valid_record(data):
    EventRecord.model_validate(data)


@pytest.mark.parametrize("data", INVALID_RECORDS)
def test_invalid_record(data):
    with pytest.raises(ValidationError):
        EventRecord.model_validate(data)


def test_record_round_trip_keeps_from_key():
    record = EventRecord.model_validate(RECORD)
    wire = record.model_dump(mode="json")
    assert wire["from"] == "Plan" and "from_" not in wire
    assert EventRecord.model_validate(wire) == record


def test_transition_table_has_twelve_rows():
    assert list(TRANSITIONS) == list(Guard)
    assert {s for pair in TRANSITIONS.values() for s in pair} == set(State)


H = "ab" * 32  # a well-formed 64-char hex digest

VALID_STORED = [
    {"record": RECORD, "salt": H, "commitment": H, "link": H},
    {"record": None, "salt": None, "commitment": H, "link": H},  # erased
    {"record": VALID_RECORDS[1], "salt": "0" * 64, "commitment": "f" * 64, "link": "1" * 64},
]

INVALID_STORED = [
    {"record": RECORD, "salt": None, "commitment": H, "link": H},  # salt erased alone
    {"record": None, "salt": H, "commitment": H, "link": H},  # record erased alone
    {"record": RECORD, "salt": H, "commitment": "xyz", "link": H},  # not hex
    {"record": RECORD, "salt": H, "commitment": H.upper(), "link": H},  # uppercase hex
    {"record": RECORD, "salt": H, "commitment": H},  # link missing
]


@pytest.mark.parametrize("data", VALID_STORED)
def test_valid_stored(data):
    StoredRecord.model_validate(data)


@pytest.mark.parametrize("data", INVALID_STORED)
def test_invalid_stored(data):
    with pytest.raises(ValidationError):
        StoredRecord.model_validate(data)


def test_erased_flag():
    assert StoredRecord.model_validate(VALID_STORED[1]).erased
    assert not StoredRecord.model_validate(VALID_STORED[0]).erased
