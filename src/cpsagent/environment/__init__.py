"""Emulated Intelligent Environment: entities of thesis Ch.5, scenario loader, emulator."""

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
    "EnvironmentBackend",
    "InvalidValue",
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
