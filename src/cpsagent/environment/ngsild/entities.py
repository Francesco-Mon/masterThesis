"""The environment's entities in NGSI-LD form, and back (docs/NGSI_LD.md).

Ids are URNs, `urn:ngsi-ld:<Type>:<id>` (e.g. `urn:ngsi-ld:Device:lamp_hallway`); a
positioning signal is one entity per subject and beacon zone,
`urn:ngsi-ld:PositioningSignal:user-1:hallway`, updated at every reading. Links between
entities (`refBuilding`, `refZone`, `refSubject`) are Relationships; everything else is a
Property (`location` a GeoProperty). The time of a reading is the `observedAt` of its
`rssi` Property. The project's terms are defined by `data/ngsi-ld/context.jsonld`.

Reading back, the broker's JSON is mapped to the model's types: JSON-LD compaction turns a
one-element array into its element (`supportedCommand`, `adjacency`), and a number with no
fractional part loses its `.0` (a thermostat's setpoint, an RSSI); both are restored here.
"""

import json
import re
from datetime import UTC
from pathlib import Path
from typing import Any

from ..commands import initial_state
from ..model import (
    DEFAULT_SCENARIO,
    Building,
    Device,
    ManagementPolicy,
    PositioningSignal,
    Scenario,
    Zone,
)

CONTEXT_FILE = DEFAULT_SCENARIO.parent / "ngsi-ld" / "context.jsonld"


def load_context(path: str | Path = CONTEXT_FILE) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def urn(kind: str, local: str) -> str:
    return f"urn:ngsi-ld:{kind}:{local}"


def local_id(entity_id: str) -> str:
    """`urn:ngsi-ld:Device:lamp_hallway` -> `lamp_hallway`."""
    return entity_id.split(":", 3)[3]


def building_id(building: Building) -> str:
    """The scenario names the building but gives it no id: one is made from the name."""
    return urn("Building", re.sub(r"\W+", "_", building.name.strip().lower()))


def signal_id(subject: str, zone_id: str) -> str:
    return urn("PositioningSignal", f"{subject}:{zone_id}")


def _prop(value: Any) -> dict[str, Any]:
    return {"type": "Property", "value": value}


def _rel(target: str) -> dict[str, Any]:
    return {"type": "Relationship", "object": target}


def _iso(time) -> str:
    return time.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# --- to NGSI-LD -------------------------------------------------------------------------


def building_entity(building: Building) -> dict[str, Any]:
    return {
        "id": building_id(building),
        "type": "Building",
        "name": _prop(building.name),
        "category": _prop(building.category),
        "location": {"type": "GeoProperty", "value": building.location},
        "managementPolicy": _prop(building.management_policy.model_dump(by_alias=True)),
    }


def zone_entity(zone: Zone, building: Building) -> dict[str, Any]:
    return {
        "id": urn("Zone", zone.zone_id),
        "type": "Zone",
        "name": _prop(zone.name),
        "adjacency": _prop([urn("Zone", z) for z in zone.adjacency]),
        "refBuilding": _rel(building_id(building)),
    }


def device_entity(device: Device) -> dict[str, Any]:
    return {
        "id": urn("Device", device.device_id),
        "type": "Device",
        "category": _prop(device.category),
        "controlledProperty": _prop(device.controlled_property),
        "supportedCommand": _prop(list(device.supported_command)),
        "refZone": _rel(urn("Zone", device.ref_zone)),
        "state": _prop(dict(device.state)),
        "defaultState": _prop(dict(device.default_state)),
    }


def scenario_entities(scenario: Scenario) -> list[dict[str, Any]]:
    """Building, zones and devices, in the scenario's order (the order the broker lists
    them in, since it lists entities in creation order)."""
    return [
        building_entity(scenario.building),
        *(zone_entity(z, scenario.building) for z in scenario.zones),
        *(device_entity(d) for d in scenario.devices),
    ]


def rssi_attribute(signal: PositioningSignal) -> dict[str, Any]:
    return {"type": "Property", "value": signal.rssi, "observedAt": _iso(signal.observed_at)}


def signal_entity(signal: PositioningSignal) -> dict[str, Any]:
    return {
        "id": signal_id(signal.ref_subject, signal.ref_zone),
        "type": "PositioningSignal",
        "signalType": _prop(signal.signal_type),
        "rssi": rssi_attribute(signal),
        "refZone": _rel(urn("Zone", signal.ref_zone)),
        "refSubject": _rel(urn("Person", signal.ref_subject)),
    }


# --- from NGSI-LD -----------------------------------------------------------------------


def _value(entity: dict[str, Any], attr: str) -> Any:
    return entity[attr]["value"]


def _object(entity: dict[str, Any], attr: str) -> str:
    return entity[attr]["object"]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _typed_state(category: str, state: dict[str, Any]) -> dict[str, Any]:
    """Give back their float type to the state values the category defines as floats."""
    template = initial_state(category)
    return {
        k: float(v) if isinstance(template.get(k), float) and type(v) is int else v
        for k, v in state.items()
    }


def building_from(entity: dict[str, Any]) -> Building:
    return Building(
        name=_value(entity, "name"),
        category=_value(entity, "category"),
        location=_value(entity, "location"),
        management_policy=ManagementPolicy.model_validate(_value(entity, "managementPolicy")),
    )


def zone_from(entity: dict[str, Any], building_names: dict[str, str]) -> Zone:
    return Zone(
        zone_id=local_id(entity["id"]),
        name=_value(entity, "name"),
        adjacency=[local_id(z) for z in _list(_value(entity, "adjacency"))],
        ref_building=building_names.get(_object(entity, "refBuilding")),
    )


def device_from(entity: dict[str, Any]) -> Device:
    category = _value(entity, "category")
    return Device(
        device_id=local_id(entity["id"]),
        category=category,
        controlled_property=_value(entity, "controlledProperty"),
        supported_command=_list(_value(entity, "supportedCommand")),
        ref_zone=local_id(_object(entity, "refZone")),
        state=_typed_state(category, _value(entity, "state")),
        default_state=_typed_state(category, _value(entity, "defaultState")),
    )


def signal_from(entity: dict[str, Any]) -> PositioningSignal:
    rssi = entity["rssi"]
    return PositioningSignal(
        signal_type=_value(entity, "signalType"),
        rssi=float(rssi["value"]),
        observed_at=rssi["observedAt"],
        ref_zone=local_id(_object(entity, "refZone")),
        ref_subject=local_id(_object(entity, "refSubject")),
    )
