"""Environment Binding (R9/R10, R14): discovery and binding protocol of thesis Ch.5.

Executed once, when the person enters the environment:
  1. Locate       broker endpoint from configuration -> broker
  2. Authenticate token; its scope (zones, operations) is fixed by the environment
  3. Enumerate    the environment follows the person: it places the person in a zone, arms
                  triggers on the adjacent zones and returns that neighbourhood; each time
                  a trigger fires it re-arms and pushes the new neighbourhood
  4. Subscribe    positioning signals of the followed zones are pushed to the agent (R13),
                  so re-planning stays event driven

The environment also tells the session each time its management policy restores a device
the agent changed (`on_restoration`). The session only passes it on: the restoration is the
environment's action, and the engine's state does not change for it.

No capability catalogue is built here: the engine asks the environment for the devices it
needs in the Plan state (listDevices). Output: a BoundSession. What the engine needs to
reason (neighbourhood, known adjacency) and what the Interface needs to act (endpoint,
token, scope) are kept apart (R10/R11).
"""

import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from cpsagent.contracts import GroundingResult, ZoneEstimate
from cpsagent.environment import (
    AuthenticationError,
    EnvironmentBackend,
    Neighbourhood,
    PositioningSignal,
    Restoration,
)

SignalListener = Callable[[PositioningSignal], None]
NeighbourhoodListener = Callable[[Neighbourhood], None]
RestorationListener = Callable[[Restoration], None]


class BindingError(Exception):
    """A protocol step failed; the message says which one."""


@dataclass
class Subscription:
    """Active position subscription (the Subscribe step of the protocol). Listeners
    (e.g. Localization) attach later."""

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
    subject: str
    token: str
    broker: EnvironmentBackend  # the "connection" the Environment Interface will use
    scope_zones: frozenset[str]  # granted by the environment
    subscription: Subscription
    # Enumerate: the person's zone and armed neighbours as the environment last pushed
    # them, and the union of every neighbourhood received (never shrinks), so a reader
    # whose own zone lags behind the environment's still finds its adjacency.
    neighbourhood: Neighbourhood = field(default_factory=lambda: Neighbourhood(None))
    known_adjacency: dict[str, list[str]] = field(default_factory=dict)
    _neighbourhood_listeners: list[NeighbourhoodListener] = field(default_factory=list)
    _restoration_listeners: list[RestorationListener] = field(default_factory=list)

    @property
    def bound(self) -> bool:
        return self.subscription.active

    def on_neighbourhood(self, listener: NeighbourhoodListener) -> None:
        """Called with each new neighbourhood, before the signal that caused it."""
        self._neighbourhood_listeners.append(listener)

    def _neighbourhood_changed(self, neighbourhood: Neighbourhood) -> None:
        self.neighbourhood = neighbourhood
        for zone, adjacent in neighbourhood.adjacency.items():
            self.known_adjacency.setdefault(zone, list(adjacent))
        for listener in list(self._neighbourhood_listeners):
            listener(neighbourhood)

    def on_restoration(self, listener: RestorationListener) -> None:
        """Called each time the environment restores a device this session's token changed
        (management policy), including the restorations made when the session closes."""
        self._restoration_listeners.append(listener)

    def _restored(self, restoration: Restoration) -> None:
        for listener in list(self._restoration_listeners):
            listener(restoration)

    def interpret(
        self, text: str, language: str, zone: ZoneEstimate, history: list[str]
    ) -> GroundingResult:
        """Ask the environment to interpret a request (its interpretation service): the
        request crosses the agent-environment boundary; the catalogue stays there."""
        return self.broker.interpret(self.token, text, language, zone, history)

    def close(self) -> None:
        self.broker.unsubscribe(self.subscription.subscription_id)
        self.subscription.active = False

    # --- for the frozen evaluation code only ---------------------------------------------
    # The evaluation (cpsagent.eval, and grounding/try.py) runs the grounders itself, outside
    # the engine, and reads these names from the session it binds; it is frozen. They hold
    # nothing: each read asks the emulated environment for the catalogue and adjacency its
    # interpreter is given. The engine, the planner, the Interface and Binding never use
    # them (tested): the agent never holds the catalogue.

    def _interpreter_context(self):
        return self.broker.interpreter_context(self.token)  # type: ignore[attr-defined]

    @property
    def catalogue(self):
        return self._interpreter_context().catalogue

    @property
    def spatial_model(self):
        """Has `.adjacency`, the attribute the evaluation reads."""
        return self._interpreter_context()

    def catalogue_properties(self) -> set[str]:
        return self._interpreter_context().catalogue_properties()


class EnvironmentBinding:
    def __init__(self, brokers: Mapping[str, EnvironmentBackend]) -> None:
        """`brokers`: endpoint -> environment backend (stands for the network in Locate)."""
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
        session = BoundSession(
            session_id=f"sess-{next(self._session_ids):03d}",
            endpoint=endpoint,
            agent_id=agent_id,
            subject=subject,
            token=token,
            broker=broker,
            scope_zones=frozenset(broker.scope(token)),
            subscription=Subscription("", subject),
        )
        # 3. Enumerate: the environment follows the person and arms its triggers
        session._neighbourhood_changed(
            broker.follow(token, subject, session._neighbourhood_changed, session._restored)
        )
        # 4. Subscribe
        subscription = session.subscription
        subscription.subscription_id = broker.subscribe(token, subject, subscription.deliver)
        return session
