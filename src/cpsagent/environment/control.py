"""Control logic of the Intelligent Environment (the manager's side of R14/R15).

It stands where the manager's services around an NGSI-LD broker would stand and implements
`EnvironmentBackend`: it issues tokens whose scope it fixes, refuses calls outside that
scope, follows the person, interprets requests, applies the management policy and gives
commands their meaning. The entities themselves (building, zones, devices with their
state, positioning signals) live in an `EntityStore` (`store.py`): in this process
(`InMemoryStore`) or in Orion-LD (`NgsiLdStore`). This module does not know which one it
uses. The agent never calls it directly: Environment Binding and Environment Interface do.

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

Interpretation service. The environment also interprets requests for its clients
(`interpret`): it builds the GroundingRequest from its own catalogue and adjacency for the
token's scope (see `interpreter.py`), calls the grounder it was configured with and checks
the answer against that catalogue. It refuses, without grounding, a zone estimate outside
the scope. This is a service of the environment, not one of the four device operations.

Management policy (restoration). The building's `managementPolicy` belongs to the manager
of the environment, so the environment applies it, never the agent. For each token the
environment remembers the devices changed by `invokeCommand`, grouped by the device's zone.
Once the person it follows has been outside that zone, continuously, for
`restoreAfterSeconds` (its own placement, measured on the time of the positioning
signals), it puts those devices back to their `defaultState` and tells the client
(`on_restore`). Coming back to the zone before then cancels the countdown. When the
subscription is closed, everything the token changed is restored at once. A device that
another token has also changed and not yet seen restored is left as it is.

Commands. What a command does to a device's state is decided here (`commands.py`, the
device simulator side); the store only keeps the resulting state.
"""

import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cpsagent.contracts import GroundingRequest, GroundingResult, ZoneEstimate

from . import commands
from .backend import (
    AuthenticationError,
    CommandNotSupportedError,
    DeviceFailure,
    Neighbourhood,
    NeighbourhoodCallback,
    OutOfScopeError,
    Restoration,
    RestorationCallback,
    RestorationReason,
    ScopeDescription,
    SignalCallback,
    UnknownEntityError,
)
from .interpreter import GroundingContext, checked, grounding_context
from .model import Building, Device, PositioningSignal, Scenario, Zone
from .store import EntityStore

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
    restore: RestorationCallback | None = None
    zone: str | None = None
    armed: tuple[str, ...] = ()


class EnvironmentControl:
    def __init__(self, scenario: Scenario, store: EntityStore, interpreter=None) -> None:
        """`scenario`: the manager's configuration (registered agents and their scope; the
        scripted paths of the mobility simulator). `store`: where the entities live.
        `interpreter`: the grounder of the interpretation service (any
        `cpsagent.grounding.Grounder`); the keyword grounder when not given."""
        self.scenario = scenario
        self.store = store
        self._interpreter = interpreter
        self.endpoint = store.endpoint
        self.building: Building = store.building()
        self._tokens: dict[str, str] = {}  # token -> agent id
        self._token_ids = itertools.count(1)
        # id -> (token, subject, callback)
        self._subscriptions: dict[str, tuple[str, str, SignalCallback]] = {}
        self._sub_ids = itertools.count(1)
        self._follows: dict[str, _Follow] = {}  # token -> follow
        # subject -> zone -> (latest RSSI, observedAt)
        self._latest: dict[str, dict[str, tuple[float, datetime]]] = {}
        self._faults: dict[str, int] = {}  # device id -> remaining failures to emulate
        # Management policy: token -> device id -> device's zone, for every device the
        # token changed and the environment has not restored yet; token -> zone -> time
        # the followed person was first seen outside that zone (countdown running).
        self.policy = self.building.management_policy
        self._changed: dict[str, dict[str, str]] = {}
        self._out_since: dict[str, dict[str, datetime]] = {}
        self._now: datetime | None = None  # environment time: latest positioning signal
        store.subscribe(self._on_signal)

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

    def _zone_map(self) -> dict[str, Zone]:
        return {z.zone_id: z for z in self.store.zones()}

    def _zone_in_scope(self, token: str, zone_id: str) -> None:
        if zone_id not in self._zone_map():
            raise UnknownEntityError(zone_id)
        if zone_id not in self.scope(token):
            raise OutOfScopeError(zone_id)

    # --- entities -----------------------------------------------------------------------

    def zones(self, token: str) -> list[Zone]:
        follow = self._follows.get(token)
        if follow is None or follow.zone is None:
            self._agent(token)
            return []
        zones = self._zone_map()
        return [zones[z] for z in (follow.zone, *follow.armed)]

    def devices(
        self, token: str, zone_id: str | None = None, controlled_property: str | None = None
    ) -> list[Device]:
        scope = self.scope(token)
        if zone_id is not None:
            self._zone_in_scope(token, zone_id)
        return [
            d
            for d in self.store.devices()
            if d.ref_zone in scope
            and (zone_id is None or d.ref_zone == zone_id)
            and (controlled_property is None or d.controlled_property == controlled_property)
        ]

    def device(self, token: str, device_id: str) -> Device:
        scope = self.scope(token)
        device = self.store.device(device_id)
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
        state = commands.apply(device.category, command, device.state, value)
        self.store.write_state(device_id, state)
        if self.policy.restore_on_exit:
            self._changed.setdefault(token, {})[device_id] = device.ref_zone
        return dict(state)

    def device_states(self) -> dict[str, dict[str, Any]]:
        """Observer view for tests and the UI page, not part of EnvironmentBackend: the
        state of every device, whatever any token's scope."""
        return {d.device_id: dict(d.state) for d in self.store.devices()}

    def pending_restorations(self) -> list[dict[str, Any]]:
        """Observer view for tests and the UI page, not part of EnvironmentBackend: every
        device changed by a token and not restored yet, with the time its restoration is
        due (None while the person is in the device's zone)."""
        delay = timedelta(seconds=self.policy.restore_after_seconds)
        pending = []
        for token, changed in self._changed.items():
            out = self._out_since.get(token, {})
            for device_id, zone in changed.items():
                due = out[zone] + delay if zone in out else None
                pending.append({"deviceId": device_id, "zoneId": zone, "restoreAt": due})
        return pending

    def inject_failure(self, device_id: str, times: int = 1) -> None:
        """Test hook: the next `times` commands to this device fail (drives T10/T11)."""
        self._faults[device_id] = times

    def _describe_scope(self, token: str) -> ScopeDescription:
        """Every zone and device of the token's scope (internal: input of the interpreter)."""
        scope = self.scope(token)
        return ScopeDescription(
            zones=[z for z in self.store.zones() if z.zone_id in scope],
            devices=[d for d in self.store.devices() if d.ref_zone in scope],
        )

    # --- following the person (Enumerate) -----------------------------------------------

    def follow(
        self,
        token: str,
        subject: str,
        on_change: NeighbourhoodCallback,
        on_restore: RestorationCallback | None = None,
    ) -> Neighbourhood:
        follow = _Follow(subject, self.scope(token), on_change, on_restore)
        heard = {z: r for z, (r, _) in self._latest.get(subject, {}).items() if z in follow.scope}
        zones = self._zone_map()
        if heard:  # the person was already heard: strongest beacon, ties by zone id
            self._place(follow, max(sorted(heard), key=heard.__getitem__), zones)
        self._follows[token] = follow
        return self._neighbourhood(follow, zones)

    @staticmethod
    def _place(follow: _Follow, zone: str, zones: dict[str, Zone]) -> None:
        follow.zone = zone
        follow.armed = tuple(z for z in zones[zone].adjacency if z in follow.scope)

    @staticmethod
    def _neighbourhood(follow: _Follow, zones: dict[str, Zone]) -> Neighbourhood:
        if follow.zone is None:
            return Neighbourhood(None)
        followed = (follow.zone, *follow.armed)
        return Neighbourhood(follow.zone, {z: list(zones[z].adjacency) for z in followed})

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
            zones = self._zone_map()  # the building's map, as the store holds it
            self._place(follow, zone, zones)
            follow.notify(self._neighbourhood(follow, zones))

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
            token = entry[0]
            for zone in dict.fromkeys(self._changed.get(token, {}).values()):
                self._restore(token, zone, "subscription_closed")
            self._changed.pop(token, None)
            self._out_since.pop(token, None)
            self._follows.pop(token, None)  # the client leaves: its triggers are disarmed

    def publish(self, signal: PositioningSignal) -> None:
        """Called by the mobility simulator: the signal enters the store, which hands it
        back to `_on_signal` (directly in memory, through a notification in NGSI-LD)."""
        self.store.publish(signal)

    def _on_signal(self, signal: PositioningSignal) -> None:
        """Update the follows (triggers), apply the policy, then push the signal to the
        matching subscriptions."""
        latest = self._latest.setdefault(signal.ref_subject, {})
        latest[signal.ref_zone] = (signal.rssi, signal.observed_at)
        self._now = max(self._now or signal.observed_at, signal.observed_at)
        for follow in list(self._follows.values()):
            if follow.subject == signal.ref_subject:
                self._track(follow, signal)
        self._apply_policy()
        for token, subject, callback in list(self._subscriptions.values()):
            if subject == signal.ref_subject and self._forwarded(token, signal):
                callback(signal)

    # --- management policy (restoration) ------------------------------------------------

    def _apply_policy(self) -> None:
        """Start, cancel or complete the countdown of every zone where a token changed
        devices, from the zone the environment places the followed person in."""
        assert self._now is not None
        delay = self.policy.restore_after_seconds
        for token, changed in list(self._changed.items()):
            follow = self._follows.get(token)
            if follow is None or follow.zone is None:
                continue  # nobody followed for this token: restored when it unsubscribes
            out = self._out_since.setdefault(token, {})
            for zone in dict.fromkeys(changed.values()):
                if zone == follow.zone:
                    out.pop(zone, None)  # back in the zone (or never left): no restoration
                    continue
                since = out.setdefault(zone, self._now)
                if (self._now - since).total_seconds() >= delay:
                    self._restore(token, zone, "person_left_zone")

    def _restore(self, token: str, zone: str, reason: RestorationReason) -> None:
        """Put back to defaultState the devices of `zone` changed by `token`."""
        changed = self._changed.get(token, {})
        self._out_since.get(token, {}).pop(zone, None)
        follow = self._follows.get(token)
        for device_id in [d for d, z in changed.items() if z == zone]:
            del changed[device_id]
            if any(device_id in other for other in self._changed.values()):
                continue  # another token changed it too: restored when that token lets go
            device = self.store.device(device_id)
            if device.state == device.default_state:
                continue  # already in its default state (e.g. switched off by the agent)
            state = dict(device.default_state)
            self.store.write_state(device_id, state)
            if follow is not None and follow.restore is not None:
                follow.restore(Restoration(device_id, zone, dict(state), reason, self._now))

    # --- interpretation service ---------------------------------------------------------

    @property
    def interpreter(self):
        if self._interpreter is None:  # imported here: grounding depends on the engine
            from cpsagent.grounding.keyword import KeywordGrounder

            self._interpreter = KeywordGrounder()
        return self._interpreter

    def interpreter_context(self, token: str) -> GroundingContext:
        """Catalogue and adjacency the interpreter is given for the token's scope. Not part
        of EnvironmentBackend: read by the interpretation service below and, through the
        evaluation-only properties of BoundSession, by the frozen evaluation code."""
        return grounding_context(self._describe_scope(token))

    def grounding_request(
        self,
        token: str,
        text: str,
        language: str,
        zone_estimate: ZoneEstimate,
        history: list[str],
    ) -> GroundingRequest:
        """The GroundingRequest the interpreter receives (also used by the regression
        tests to compare it with the one the agent used to build)."""
        return self._request(
            self.interpreter_context(token), text, language, zone_estimate, history
        )

    @staticmethod
    def _request(context, text, language, zone_estimate, history) -> GroundingRequest:
        return GroundingRequest(
            text=text,
            language=language,
            zone=zone_estimate,
            catalogue=context.catalogue,
            adjacency=context.adjacency,
            history=list(history),
        )

    def interpret(
        self,
        token: str,
        text: str,
        language: str,
        zone_estimate: ZoneEstimate,
        history: list[str],
    ) -> GroundingResult:
        if zone_estimate.zone_id not in self.scope(token):  # also checks the token
            raise OutOfScopeError(zone_estimate.zone_id)  # refused before any grounding
        context = self.interpreter_context(token)
        request = self._request(context, text, language, zone_estimate, history)
        return checked(self.interpreter.ground(request), context)

    def close(self) -> None:
        """Release the store (connections and subscriptions of a remote broker)."""
        self.store.close()
