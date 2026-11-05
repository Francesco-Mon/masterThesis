"""What each command does to a device's `state`, per device category.

A device may support only a subset of its category's commands (`supportedCommand`);
that subset, not this table, is what the catalogue exposes.
"""

from collections.abc import Callable
from typing import Any

State = dict[str, Any]
CommandFn = Callable[[State, Any], State]


class InvalidValue(ValueError):
    """The command exists but its `value` is missing or out of range."""


def _percent(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 100:
        raise InvalidValue("value must be a number in [0, 100]")
    return int(value)


def _setpoint(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 16 <= value <= 28:
        raise InvalidValue("setpoint must be a number in [16, 28] degrees Celsius")
    return float(value)


def _dim(state: State, value: Any) -> State:
    level = _percent(value)
    return {**state, "power": "on" if level > 0 else "off", "brightness": level}


CATEGORY_COMMANDS: dict[str, dict[str, CommandFn]] = {
    "lamp": {
        "on": lambda s, v: {**s, "power": "on", "brightness": 100},
        "off": lambda s, v: {**s, "power": "off", "brightness": 0},
        "dim": _dim,
    },
    "blind": {  # position: 0 = closed, 100 = fully open
        "open": lambda s, v: {**s, "position": 100},
        "close": lambda s, v: {**s, "position": 0},
        "setPosition": lambda s, v: {**s, "position": _percent(v)},
    },
    "thermostat": {
        "setSetpoint": lambda s, v: {**s, "setpoint": _setpoint(v)},
    },
}

_INITIAL: dict[str, State] = {
    "lamp": {"power": "off", "brightness": 0},
    "blind": {"position": 0},
    "thermostat": {"setpoint": 21.0},
}


def initial_state(category: str) -> State:
    return dict(_INITIAL[category])


def apply(category: str, command: str, state: State, value: Any) -> State:
    """New state after `command`; raises InvalidValue for a bad value."""
    return CATEGORY_COMMANDS[category][command](state, value)
