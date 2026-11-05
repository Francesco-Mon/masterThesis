"""In-process emulation of the Intelligent Environment (the broker side of R14/R15).

It stands where Orion-LD would stand: it holds the entities and their state, issues
tokens, executes commands and pushes positioning signals to subscribers. The agent never
calls it directly: Environment Binding and Environment Interface do.
"""

import itertools
from collections.abc import Callable
from typing import Any

from . import commands
from .model import Building, Device, PositioningSignal, Scenario, Zone, load_scenario


class AuthenticationError(Exception):
    pass


class DeviceFailure(Exception):
    """The command was accepted but the device did not execute it (emulated fault)."""


SignalCallback = Callable[[PositioningSignal], None]


class EmulatedEnvironment:
    def __init__(self, scenario: Scenario | None = None) -> None:
        self.scenario = scenario or load_scenario()
        self.endpoint = self.scenario.broker.endpoint
        self.building: Building = self.scenario.building
        self._zones = {z.zone_id: z for z in self.scenario.zones}
        # deep copy: two emulators built from the same Scenario must not share device state
        self._devices = {d.device_id: d.model_copy(deep=True) for d in self.scenario.devices}
        self._tokens: dict[str, str] = {}  # token -> agent id
        self._token_ids = itertools.count(1)
        self._subscriptions: dict[str, tuple[str, SignalCallback]] = {}  # id -> (subject, cb)
        self._sub_ids = itertools.count(1)
        self._faults: dict[str, int] = {}  # device id -> remaining failures to emulate

    # --- access control -----------------------------------------------------------------

    def authenticate(self, agent_id: str) -> str:
        """Emulated token: issued to any agent registered in the scenario, no real secret."""
        if agent_id not in self.scenario.broker.agents:
            raise AuthenticationError(f"unknown agent {agent_id!r}")
        token = f"token-{next(self._token_ids)}"
        self._tokens[token] = agent_id
        return token

    def _agent(self, token: str) -> str:
        if token not in self._tokens:
            raise AuthenticationError("invalid token")
        return self._tokens[token]

    def scope_zones(self, token: str) -> set[str]:
        """Zones whose devices the token's agent may see and act on."""
        return set(self.scenario.broker.agents[self._agent(token)].scope_zones)

    # --- entities -----------------------------------------------------------------------

    def zones(self, token: str) -> list[Zone]:
        self._agent(token)
        return list(self._zones.values())

    def devices(self, token: str, zone_id: str) -> list[Device]:
        self._agent(token)
        return [d for d in self._devices.values() if d.ref_zone == zone_id]

    def device(self, token: str, device_id: str) -> Device | None:
        self._agent(token)
        return self._devices.get(device_id)

    def execute(self, token: str, device_id: str, command: str, value: Any) -> dict[str, Any]:
        """Apply a command (already checked by the Environment Interface); return the new state.

        Raises commands.InvalidValue or DeviceFailure; the state is unchanged in both cases.
        """
        self._agent(token)
        device = self._devices[device_id]
        if self._faults.get(device_id, 0) > 0:
            self._faults[device_id] -= 1
            raise DeviceFailure(device_id)
        device.state = commands.apply(device.category, command, device.state, value)
        return dict(device.state)

    def inject_failure(self, device_id: str, times: int = 1) -> None:
        """Test hook: the next `times` commands to this device fail (drives T10/T11)."""
        self._faults[device_id] = times

    # --- positioning (R13 source) -------------------------------------------------------

    def subscribe(self, token: str, subject: str, callback: SignalCallback) -> str:
        self._agent(token)
        sub_id = f"sub-{next(self._sub_ids)}"
        self._subscriptions[sub_id] = (subject, callback)
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        self._subscriptions.pop(sub_id, None)

    def publish(self, signal: PositioningSignal) -> None:
        """Called by the mobility simulator; pushes the signal to matching subscriptions."""
        for subject, callback in list(self._subscriptions.values()):
            if subject == signal.ref_subject:
                callback(signal)
