"""Intelligent Environment: entities of thesis Ch.5, scenario loader, control logic and
entity stores (in memory, or Orion-LD in `ngsild`)."""

from .backend import (
    AuthenticationError,
    CommandNotSupportedError,
    DeviceFailure,
    EnvironmentBackend,
    Neighbourhood,
    OutOfScopeError,
    Restoration,
    ScopeDescription,
    UnknownEntityError,
)
from .commands import CATEGORY_COMMANDS, InvalidValue
from .control import EnvironmentControl
from .emulator import EmulatedEnvironment
from .model import (
    DEFAULT_SCENARIO,
    Building,
    Device,
    DoorwaySegment,
    DwellSegment,
    ManagementPolicy,
    PathScript,
    PositioningSignal,
    Scenario,
    Zone,
    load_scenario,
)
from .store import EntityStore, InMemoryStore

__all__ = [
    "CATEGORY_COMMANDS",
    "DEFAULT_SCENARIO",
    "AuthenticationError",
    "Building",
    "CommandNotSupportedError",
    "Device",
    "DeviceFailure",
    "DoorwaySegment",
    "DwellSegment",
    "EmulatedEnvironment",
    "EntityStore",
    "EnvironmentControl",
    "EnvironmentBackend",
    "InvalidValue",
    "InMemoryStore",
    "ManagementPolicy",
    "Neighbourhood",
    "OutOfScopeError",
    "PathScript",
    "PositioningSignal",
    "Restoration",
    "Scenario",
    "ScopeDescription",
    "UnknownEntityError",
    "Zone",
    "load_scenario",
]
