"""In-process emulation of the Intelligent Environment (the broker side of R14/R15).

It stands where Orion-LD would stand and implements `EnvironmentBackend`: it holds the
entities and their state, issues tokens whose scope it fixes, refuses calls outside that
scope, follows the person and pushes positioning signals to subscribers. The agent never
calls it directly: Environment Binding and Environment Interface do.

Following a person (Enumerate). The environment keeps the latest RSSI of every beacon it
heard for each subject. It places the person in a zone and arms triggers on the adjacent
zones inside the scope. When a reading from an armed zone is stronger than the latest
reading of the person's zone and of every other armed zone, the trigger fires: the
environment moves the person, re-arms around the new zone and tells the client the new
neighbourhood before forwarding that reading. Readings older than `STALE_AFTER_S` are
ignored in that comparison; when neither the person's zone nor any armed zone has been
heard within it, the track is lost and the next reading inside the scope places the person
again. No smoothing here: smoothing and hysteresis stay in the agent's Localization. Only
readings of the person's zone and of the armed zones are forwarded to a subscriber that
follows the person.
"""

import itertools
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import commands
from .backend import (
    AuthenticationError,
    CommandNotSupportedError,
    DeviceFailure,
    Neighbourhood,
    NeighbourhoodCallback,
    OutOfScopeError,
    ScopeDescription,
    SignalCallback,
    UnknownEntityError,
)
from .model import Building, Device, PositioningSignal, Scenario, Zone, load_scenario

# A reading older than this (one scan of the simulated phone) no longer competes in a
# trigger. Without it, a strong reading of a zone the person has left would keep the
# environment from following them.
STALE_AFTER_S = 1.0


@dataclass
class _Follow:
    """Environment-side state of one follow: where the person is, which triggers are armed."""

    subject: str
    scope: frozenset[str]
    notify: NeighbourhoodCallback
    zone: str | None = None
    armed: tuple[str, ...] = ()


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
        # id -> (token, subject, callback)
        self._subscriptions: dict[str, tuple[str, str, SignalCallback]] = {}
        self._sub_ids = itertools.count(1)
        self._follows: dict[str, _Follow] = {}  # token -> follow
        # subject -> zone -> (latest RSSI, observedAt)
        self._latest: dict[str, dict[str, tuple[float, datetime]]] = {}
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

    def scope(self, token: str) -> frozenset[str]:
        """Zones whose devices the token's agent may see and act on (from the scenario)."""
        return frozenset(self.scenario.broker.agents[self._agent(token)].scope_zones)

    def _zone_in_scope(self, token: str, zone_id: str) -> None:
        if zone_id not in self._zones:
            raise UnknownEntityError(zone_id)
        if zone_id not in self.scope(token):
            raise OutOfScopeError(zone_id)

    # --- entities -----------------------------------------------------------------------

    def zones(self, token: str) -> list[Zone]:
        follow = self._follows.get(token)
        if follow is None or follow.zone is None:
            self._agent(token)
            return []
        return [self._zones[z] for z in (follow.zone, *follow.armed)]

    def devices(
        self, token: str, zone_id: str | None = None, controlled_property: str | None = None
    ) -> list[Device]:
        scope = self.scope(token)
        if zone_id is not None:
            self._zone_in_scope(token, zone_id)
        return [
            d
            for d in self._devices.values()
            if d.ref_zone in scope
            and (zone_id is None or d.ref_zone == zone_id)
            and (controlled_property is None or d.controlled_property == controlled_property)
        ]

    def device(self, token: str, device_id: str) -> Device:
        scope = self.scope(token)
        device = self._devices.get(device_id)
        if device is None:
            raise UnknownEntityError(device_id)
        if device.ref_zone not in scope:
            raise OutOfScopeError(device_id)
        return device

    def execute(self, token: str, device_id: str, command: str, value: Any) -> dict[str, Any]:
        """Apply a command and return the new state. The environment checks scope and
        `supportedCommand` itself, whatever the client checked. Raises OutOfScopeError,
        UnknownEntityError, CommandNotSupportedError, commands.InvalidValue or DeviceFailure;
        the state is unchanged in every case."""
        device = self.device(token, device_id)
        if command not in device.supported_command:
            raise CommandNotSupportedError(command)
        if self._faults.get(device_id, 0) > 0:
            self._faults[device_id] -= 1
            raise DeviceFailure(device_id)
        device.state = commands.apply(device.category, command, device.state, value)
        return dict(device.state)

    def device_states(self) -> dict[str, dict[str, Any]]:
        """Observer view for tests and the UI page, not part of EnvironmentBackend: the
        state of every device, whatever any token's scope."""
        return {d.device_id: dict(d.state) for d in self._devices.values()}

    def inject_failure(self, device_id: str, times: int = 1) -> None:
        """Test hook: the next `times` commands to this device fail (drives T10/T11)."""
        self._faults[device_id] = times

    def describe_scope(self, token: str) -> ScopeDescription:
        """TEMPORARY, not one of the four operations (see EnvironmentBackend)."""
        scope = self.scope(token)
        return ScopeDescription(
            zones=[z for z in self._zones.values() if z.zone_id in scope],
            devices=[d for d in self._devices.values() if d.ref_zone in scope],
        )

    # --- following the person (Enumerate) -----------------------------------------------

    def follow(self, token: str, subject: str, on_change: NeighbourhoodCallback) -> Neighbourhood:
        follow = _Follow(subject, self.scope(token), on_change)
        heard = {z: r for z, (r, _) in self._latest.get(subject, {}).items() if z in follow.scope}
        if heard:  # the person was already heard: strongest beacon, ties by zone id
            self._place(follow, max(sorted(heard), key=heard.__getitem__))
        self._follows[token] = follow
        return self._neighbourhood(follow)

    def _place(self, follow: _Follow, zone: str) -> None:
        follow.zone = zone
        follow.armed = tuple(z for z in self._zones[zone].adjacency if z in follow.scope)

    def _neighbourhood(self, follow: _Follow) -> Neighbourhood:
        if follow.zone is None:
            return Neighbourhood(None)
        zones = (follow.zone, *follow.armed)
        return Neighbourhood(follow.zone, {z: list(self._zones[z].adjacency) for z in zones})

    def _track(self, follow: _Follow, signal: PositioningSignal) -> None:
        """Fire a trigger if this reading moves the person; notify before delivery."""
        zone = signal.ref_zone
        if zone not in follow.scope or zone == follow.zone:
            return
        latest = self._latest[follow.subject]
        rivals = [
            rssi
            for z in (follow.zone, *follow.armed)
            if z != zone and z in latest
            for rssi, seen in [latest[z]]
            if (signal.observed_at - seen).total_seconds() <= STALE_AFTER_S
        ]
        if follow.zone is None or (zone not in follow.armed and not rivals):
            fired = True  # first reading in the scope, or track lost: place the person here
        else:
            fired = zone in follow.armed and all(signal.rssi > r for r in rivals)
        if fired:
            self._place(follow, zone)
            follow.notify(self._neighbourhood(follow))

    def _forwarded(self, token: str, signal: PositioningSignal) -> bool:
        if signal.ref_zone not in self.scope(token):
            return False
        follow = self._follows.get(token)
        if follow is None or follow.subject != signal.ref_subject:
            return True
        return signal.ref_zone in (follow.zone, *follow.armed)

    # --- positioning (R13 source) -------------------------------------------------------

    def subscribe(self, token: str, subject: str, callback: SignalCallback) -> str:
        self._agent(token)
        sub_id = f"sub-{next(self._sub_ids)}"
        self._subscriptions[sub_id] = (token, subject, callback)
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        entry = self._subscriptions.pop(sub_id, None)
        if entry is not None:
            self._follows.pop(entry[0], None)  # the client leaves: its triggers are disarmed

    def publish(self, signal: PositioningSignal) -> None:
        """Called by the mobility simulator: update the follows (triggers), then push the
        signal to the matching subscriptions."""
        latest = self._latest.setdefault(signal.ref_subject, {})
        latest[signal.ref_zone] = (signal.rssi, signal.observed_at)
        for follow in list(self._follows.values()):
            if follow.subject == signal.ref_subject:
                self._track(follow, signal)
        for token, subject, callback in list(self._subscriptions.values()):
            if subject == signal.ref_subject and self._forwarded(token, signal):
                callback(signal)
