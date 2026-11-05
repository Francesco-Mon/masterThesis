"""Entities of the emulated environment (thesis Ch.5): Building, Zone, Device, PositioningSignal.

Same entity and field names as the thesis, camelCase in YAML/JSON. The scenario file
(data/scenario.yaml) is loaded into `Scenario`, which checks the references between entities.
"""

from pathlib import Path
from typing import Annotated, Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from cpsagent.contracts import UtcDatetime

from .commands import CATEGORY_COMMANDS, initial_state

DEFAULT_SCENARIO = Path(__file__).resolve().parents[3] / "data" / "scenario.yaml"


class Entity(BaseModel):
    """Like the contracts (camelCase, unknown fields rejected) but not frozen:
    the emulator owns these objects and updates the device state."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class Building(Entity):
    name: str
    category: str
    location: dict[str, Any]  # GeoJSON, as in NGSI-LD


class Zone(Entity):
    zone_id: str = Field(min_length=1)
    name: str
    adjacency: list[str]
    ref_building: str | None = None  # filled by Scenario with the building name


class Device(Entity):
    device_id: str = Field(min_length=1)
    category: str
    controlled_property: str
    supported_command: list[str] = Field(min_length=1)
    ref_zone: str
    state: dict[str, Any] = {}


class PositioningSignal(Entity):
    """One raw observation (R13): the beacon of zone `refZone` heard by `refSubject`'s phone."""

    signal_type: str = "BLE"
    rssi: float  # dBm, higher = closer
    observed_at: UtcDatetime
    ref_zone: str
    ref_subject: str


class AgentPolicy(Entity):
    scope_zones: list[str]


class Broker(Entity):
    endpoint: str
    agents: dict[str, AgentPolicy]


class DwellSegment(Entity):
    zone: str
    ticks: int = Field(ge=1)


class DoorwaySegment(Entity):
    doorway: Annotated[list[str], Field(min_length=2, max_length=2)]
    ticks: int = Field(ge=1)


class PathScript(Entity):
    subject: str
    transit_ticks: int = Field(ge=1)
    segments: list[DwellSegment | DoorwaySegment] = Field(min_length=1)


class Scenario(Entity):
    building: Building
    zones: list[Zone]
    devices: list[Device]
    absent_capabilities: list[str] = []
    broker: Broker
    paths: dict[str, PathScript] = {}

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        ids = [z.zone_id for z in self.zones]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate zoneId")
        zone_ids = set(ids)
        adjacency = {z.zone_id: set(z.adjacency) for z in self.zones}
        for zone in self.zones:
            zone.ref_building = self.building.name
            for other in zone.adjacency:
                if other not in zone_ids:
                    raise ValueError(f"{zone.zone_id}: unknown adjacent zone {other}")
                # adjacency is physical: if a -> b then b -> a
                if zone.zone_id not in adjacency[other]:
                    raise ValueError(f"adjacency not symmetric: {zone.zone_id} / {other}")

        device_ids = [d.device_id for d in self.devices]
        if len(device_ids) != len(set(device_ids)):
            raise ValueError("duplicate deviceId")
        for device in self.devices:
            if device.ref_zone not in zone_ids:
                raise ValueError(f"{device.device_id}: unknown refZone {device.ref_zone}")
            known = CATEGORY_COMMANDS.get(device.category)
            if known is None:
                raise ValueError(f"{device.device_id}: unknown category {device.category}")
            extra = set(device.supported_command) - set(known)
            if extra:
                raise ValueError(f"{device.device_id}: commands {extra} not defined for category")
            if not device.state:
                device.state = initial_state(device.category)

        offered = {d.controlled_property for d in self.devices}
        if offered & set(self.absent_capabilities):
            raise ValueError("absentCapabilities must not be offered by any device")

        for name, agent in self.broker.agents.items():
            if not set(agent.scope_zones) <= zone_ids:
                raise ValueError(f"agent {name}: scope has unknown zones")

        for name, path in self.paths.items():
            for seg in path.segments:
                zones = [seg.zone] if isinstance(seg, DwellSegment) else seg.doorway
                if not set(zones) <= zone_ids:
                    raise ValueError(f"path {name}: unknown zone in {zones}")
                if isinstance(seg, DoorwaySegment) and zones[1] not in adjacency[zones[0]]:
                    raise ValueError(f"path {name}: doorway between non-adjacent zones")
            dwell = [s.zone for s in path.segments if isinstance(s, DwellSegment)]
            for a, b in zip(dwell, dwell[1:], strict=False):
                if a != b and b not in adjacency[a]:
                    raise ValueError(f"path {name}: {a} -> {b} are not adjacent")
        return self


def load_scenario(path: str | Path = DEFAULT_SCENARIO) -> Scenario:
    with open(path, encoding="utf-8") as f:
        return Scenario.model_validate(yaml.safe_load(f))
