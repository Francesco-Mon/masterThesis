"""The environment side of the boundary: what Environment Binding, Environment Interface
and the engine's Interpret state use from an Intelligent Environment.

`EmulatedEnvironment` implements it in process; an NGSI-LD adapter (Orion-LD) can implement
the same Protocol later. The environment is the authority: it fixes the scope of a token,
refuses any call outside it, and decides what it lists. The agent's own checks (allow-list,
Scope Guard) are defence in depth only.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from cpsagent.contracts import GroundingResult, ZoneEstimate

from .model import Device, PositioningSignal, Zone


class AuthenticationError(Exception):
    """Unknown agent or invalid token."""


class OutOfScopeError(Exception):
    """The zone or device exists but is outside the scope granted to the token."""


class UnknownEntityError(Exception):
    """No zone or device with that id."""


class CommandNotSupportedError(Exception):
    """The command is not in the device's `supportedCommand`."""


class DeviceFailure(Exception):
    """The command was accepted but the device did not execute it."""


@dataclass(frozen=True)
class Neighbourhood:
    """What the environment follows for a person: the zone it places the person in and the
    adjacent zones (inside the scope) where it has armed a trigger, each with its adjacency.
    `zone_id` is None until the environment has heard the person."""

    zone_id: str | None
    adjacency: dict[str, list[str]] = field(default_factory=dict)  # person's zone first

    @property
    def armed(self) -> list[str]:
        return [z for z in self.adjacency if z != self.zone_id]


@dataclass(frozen=True)
class ScopeDescription:
    """Every zone and device inside a granted scope: what the environment's interpreter
    builds its catalogue and adjacency from (internal to the environment)."""

    zones: list[Zone]
    devices: list[Device]


RestorationReason = Literal["person_left_zone", "subscription_closed"]


@dataclass(frozen=True)
class Restoration:
    """The environment put a device back to its `defaultState` (management policy): the
    person left the device's zone (`person_left_zone`) or the client's subscription was
    closed (`subscription_closed`). Sent to the client for information only."""

    device_id: str
    zone_id: str
    state: dict[str, Any]  # the restored state, equal to the device's defaultState
    reason: RestorationReason
    time: datetime | None  # environment time (latest positioning signal); None if none yet


SignalCallback = Callable[[PositioningSignal], None]
NeighbourhoodCallback = Callable[[Neighbourhood], None]
RestorationCallback = Callable[[Restoration], None]


class EnvironmentBackend(Protocol):
    endpoint: str

    def authenticate(self, agent_id: str) -> str:
        """A token whose scope (zones, operations) is fixed by the environment."""
        ...

    def scope(self, token: str) -> frozenset[str]:
        """Zones granted to the token. The agent cannot widen it."""
        ...

    def follow(
        self,
        token: str,
        subject: str,
        on_change: NeighbourhoodCallback,
        on_restore: RestorationCallback | None = None,
    ) -> Neighbourhood:
        """Enumerate: follow `subject`, arm triggers on the zones adjacent to its zone and
        return the neighbourhood. `on_change` receives each new neighbourhood when a trigger
        fires, before the signal that fired it is delivered. `on_restore` receives each
        restoration the environment applies to a device this token changed."""
        ...

    def zones(self, token: str) -> list[Zone]:
        """The zones followed for the token: the person's zone first, then the armed ones."""
        ...

    def devices(
        self, token: str, zone_id: str | None = None, controlled_property: str | None = None
    ) -> list[Device]:
        """Devices inside the scope, filtered by zone and property when given."""
        ...

    def device(self, token: str, device_id: str) -> Device:
        """One device inside the scope (OutOfScopeError / UnknownEntityError otherwise)."""
        ...

    def execute(self, token: str, device_id: str, command: str, value: Any) -> dict[str, Any]:
        """The only operation that changes the environment; returns the new state."""
        ...

    def subscribe(self, token: str, subject: str, callback: SignalCallback) -> str:
        """Subscribe: positioning signals of the followed zones are pushed to `callback`."""
        ...

    def unsubscribe(self, sub_id: str) -> None:
        """The client leaves: its triggers are disarmed and, under the management policy,
        every device its token changed is restored."""
        ...

    def interpret(
        self,
        token: str,
        text: str,
        language: str,
        zone_estimate: ZoneEstimate,
        history: list[str],
    ) -> GroundingResult:
        """Interpretation service, not one of the four device operations: the environment
        grounds `text` with its own interpreter, catalogue and adjacency for the token's
        scope, and returns the result checked against that catalogue. Raises
        OutOfScopeError, without interpreting, when the zone estimate is outside the scope;
        AuthenticationError for an invalid token."""
        ...
