"""NGSI-LD form of the entities (offline: no broker needed)."""

from datetime import UTC, datetime

from cpsagent.environment import PositioningSignal, load_scenario
from cpsagent.environment.ngsild.entities import (
    building_from,
    device_from,
    load_context,
    local_id,
    scenario_entities,
    signal_entity,
    signal_from,
    zone_from,
)

SCENARIO = load_scenario()


def compacted(entity):
    """What the broker gives back: one-element arrays become their element and integral
    floats lose their fractional part (JSON-LD compaction, MongoDB numbers)."""

    def squash(v):
        if isinstance(v, list):
            return v[0] if len(v) == 1 else [squash(x) for x in v]
        if isinstance(v, dict):
            return {k: squash(x) for k, x in v.items()}
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v

    return {k: squash(v) for k, v in entity.items()}


def test_ids_are_urns_and_links_are_relationships():
    entities = scenario_entities(SCENARIO)
    assert entities[0]["id"] == "urn:ngsi-ld:Building:lab_building"
    lamp = next(e for e in entities if e["id"] == "urn:ngsi-ld:Device:lamp_hallway")
    assert lamp["refZone"] == {"type": "Relationship", "object": "urn:ngsi-ld:Zone:hallway"}
    for attr in ("state", "defaultState", "supportedCommand", "controlledProperty"):
        assert lamp[attr]["type"] == "Property"
    zone = next(e for e in entities if e["id"] == "urn:ngsi-ld:Zone:lobby")
    assert zone["refBuilding"]["type"] == "Relationship"
    assert zone["adjacency"] == {"type": "Property", "value": ["urn:ngsi-ld:Zone:hallway"]}
    assert local_id("urn:ngsi-ld:PositioningSignal:user-1:hallway") == "user-1:hallway"


def test_every_term_used_is_in_the_context_or_core():
    terms = set(load_context()["@context"])
    core = {"id", "type", "name", "location"}
    for entity in scenario_entities(SCENARIO):
        assert entity["type"] in terms
        assert set(entity) - core <= terms


def test_entities_read_back_as_the_scenario_after_compaction():
    entities = [compacted(e) for e in scenario_entities(SCENARIO)]
    building = building_from(entities[0])
    assert building == SCENARIO.building
    names = {entities[0]["id"]: building.name}
    zones = [zone_from(e, names) for e in entities[1 : 1 + len(SCENARIO.zones)]]
    assert zones == SCENARIO.zones
    devices = [device_from(e) for e in entities[1 + len(SCENARIO.zones) :]]
    assert [d.model_dump() for d in devices] == [d.model_dump() for d in SCENARIO.devices]
    thermostat = next(d for d in devices if d.category == "thermostat")
    assert type(thermostat.state["setpoint"]) is float


def test_signal_round_trip():
    signal = PositioningSignal(
        rssi=-55.0, observed_at=datetime(2026, 11, 10, 9, 30, tzinfo=UTC),
        ref_zone="hallway", ref_subject="user-1",
    )  # fmt: skip
    entity = signal_entity(signal)
    assert entity["id"] == "urn:ngsi-ld:PositioningSignal:user-1:hallway"
    assert entity["rssi"]["observedAt"] == "2026-11-10T09:30:00.000Z"
    assert signal_from(compacted(entity)) == signal
