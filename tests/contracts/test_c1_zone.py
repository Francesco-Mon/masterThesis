"""C1 - ZoneEstimate and zone-change event."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cpsagent.contracts import ZoneChangedEvent, ZoneEstimate

VALID = [
    {
        "zoneId": "hallway",
        "confidence": 0.87,
        "observedAt": "2026-11-10T09:30:12Z",
        "previousZoneId": "livingroom",
    },
    {"zoneId": "corridor", "confidence": 1.0, "observedAt": "2026-11-10T09:30:12+00:00"},
    {"zoneId": "kitchen", "confidence": 0.0, "observedAt": "2026-11-10T10:30:12+01:00"},
]

INVALID = [
    {"zoneId": "hallway", "confidence": 1.2, "observedAt": "2026-11-10T09:30:12Z"},
    {"zoneId": "hallway", "confidence": -0.1, "observedAt": "2026-11-10T09:30:12Z"},
    {"zoneId": "hallway", "confidence": 0.5, "observedAt": "2026-11-10T09:30:12"},  # naive
    {"confidence": 0.5, "observedAt": "2026-11-10T09:30:12Z"},  # zoneId missing
    {"zoneId": "", "confidence": 0.5, "observedAt": "2026-11-10T09:30:12Z"},
    {"zoneId": "a", "confidence": 0.5, "observedAt": "2026-11-10T09:30:12Z", "floor": 2},
]


@pytest.mark.parametrize("data", VALID)
def test_valid_zone_estimate(data):
    estimate = ZoneEstimate.model_validate(data)
    assert estimate.observed_at.tzinfo == UTC


@pytest.mark.parametrize("data", INVALID)
def test_invalid_zone_estimate(data):
    with pytest.raises(ValidationError):
        ZoneEstimate.model_validate(data)


def test_time_normalised_to_utc_and_round_trip():
    estimate = ZoneEstimate.model_validate(VALID[2])
    assert estimate.observed_at == datetime(2026, 11, 10, 9, 30, 12, tzinfo=UTC)
    wire = estimate.model_dump(mode="json")
    assert wire["observedAt"] == "2026-11-10T09:30:12Z"
    assert "zoneId" in wire and "zone_id" not in wire
    assert ZoneEstimate.model_validate(wire) == estimate


def test_zone_changed_event():
    event = ZoneChangedEvent.model_validate({"type": "zone_changed", "estimate": VALID[0]})
    assert event.estimate.zone_id == "hallway"
    with pytest.raises(ValidationError):
        ZoneChangedEvent.model_validate({"type": "zone_left", "estimate": VALID[0]})
