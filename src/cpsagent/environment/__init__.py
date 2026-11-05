"""Emulated Intelligent Environment: entities of thesis Ch.5, scenario loader, emulator."""

from .commands import CATEGORY_COMMANDS, InvalidValue
from .emulator import AuthenticationError, DeviceFailure, EmulatedEnvironment
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
    "Device",
    "DeviceFailure",
    "DoorwaySegment",
    "DwellSegment",
    "EmulatedEnvironment",
    "InvalidValue",
    "PathScript",
    "PositioningSignal",
    "Scenario",
    "Zone",
    "load_scenario",
]
