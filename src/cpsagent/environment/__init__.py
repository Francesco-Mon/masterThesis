"""Emulated Intelligent Environment: entities of thesis Ch.5, scenario loader, emulator."""

from .backend import (
    AuthenticationError,
    CommandNotSupportedError,
    DeviceFailure,
    EnvironmentBackend,
    Neighbourhood,
    OutOfScopeError,
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
    "Neighbourhood",
    "OutOfScopeError",
    "PathScript",
    "PositioningSignal",
    "Scenario",
    "ScopeDescription",
    "UnknownEntityError",
    "Zone",
    "load_scenario",
]
