"""Environment Binding (R9/R10, R14): discovery and binding protocol of thesis Ch.5.

  1. Locate       broker endpoint from configuration -> broker
  2. Authenticate emulated token for the agent id
  3. Enumerate    Building + Zones (spatial model, with adjacency)
  4. Catalogue    Devices per zone, reading `supportedCommand` (catalogue indexed by zone)
  5. Subscribe    positioning signals pushed for the user (R13), so re-planning is event-driven

Output: a BoundSession. The engine enters Perceive only once a session is bound, and the
Environment Interface is configured by injecting the session (R11).
"""

import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from cpsagent.contracts import DeviceDescriptor, ZoneCatalogue
from cpsagent.environment import (
    AuthenticationError,
    Building,
    EmulatedEnvironment,
    PositioningSignal,
    Zone,
)

SignalListener = Callable[[PositioningSignal], None]


class BindingError(Exception):
    """A protocol step failed; the message says which one."""


@dataclass(frozen=True)
class SpatialModel:
    """Every zone of the building (also those outside the scope) with its adjacency."""

    building: Building
    zones: dict[str, Zone]

    @property
    def adjacency(self) -> dict[str, list[str]]:
        return {zid: list(z.adjacency) for zid, z in self.zones.items()}


@dataclass
class Subscription:
    """Active position subscription (the Subscribe step of the protocol). Listeners
    (e.g. Localization) attach later, once they have been built from the spatial model."""

    subscription_id: str
    subject: str
    listeners: list[SignalListener] = field(default_factory=list)
    active: bool = True

    def add_listener(self, listener: SignalListener) -> None:
        self.listeners.append(listener)

    def deliver(self, signal: PositioningSignal) -> None:
        for listener in list(self.listeners):
            listener(signal)


@dataclass
class BoundSession:
    session_id: str
    endpoint: str
    agent_id: str
    token: str
    broker: EmulatedEnvironment  # the "connection" the Environment Interface will use
    scope_zones: frozenset[str]
    spatial_model: SpatialModel
    catalogue: list[ZoneCatalogue]  # only zones in scope; a zone may have no device
    subscription: Subscription

    @property
    def bound(self) -> bool:
        return self.subscription.active

    def catalogue_properties(self) -> set[str]:
        return {d.controlled_property for z in self.catalogue for d in z.devices}

    def close(self) -> None:
        self.broker.unsubscribe(self.subscription.subscription_id)
        self.subscription.active = False


class EnvironmentBinding:
    def __init__(self, brokers: Mapping[str, EmulatedEnvironment]) -> None:
        """`brokers`: endpoint -> emulated broker (stands for the network in Locate)."""
        self._brokers = dict(brokers)
        self._session_ids = itertools.count(1)

    def bind(self, endpoint: str, agent_id: str, subject: str) -> BoundSession:
        # 1. Locate
        broker = self._brokers.get(endpoint)
        if broker is None:
            raise BindingError(f"locate: no broker at {endpoint!r}")
        # 2. Authenticate
        try:
            token = broker.authenticate(agent_id)
        except AuthenticationError as exc:
            raise BindingError(f"authenticate: {exc}") from exc
        scope = frozenset(broker.scope_zones(token))
        # 3. Enumerate
        zones = broker.zones(token)
        spatial = SpatialModel(broker.building, {z.zone_id: z for z in zones})
        # 4. Catalogue: queried from the devices' supportedCommand, never assumed
        catalogue = [
            ZoneCatalogue(
                zone_id=z.zone_id,
                devices=[
                    DeviceDescriptor(
                        device_id=d.device_id,
                        category=d.category,
                        controlled_property=d.controlled_property,
                        supported_command=list(d.supported_command),
                    )
                    for d in broker.devices(token, z.zone_id)
                ],
            )
            for z in zones
            if z.zone_id in scope
        ]
        # 5. Subscribe
        subscription = Subscription("", subject)
        subscription.subscription_id = broker.subscribe(token, subject, subscription.deliver)
        return BoundSession(
            session_id=f"sess-{next(self._session_ids):03d}",
            endpoint=endpoint,
            agent_id=agent_id,
            token=token,
            broker=broker,
            scope_zones=scope,
            spatial_model=spatial,
            catalogue=catalogue,
            subscription=subscription,
        )
