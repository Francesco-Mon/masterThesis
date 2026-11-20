"""Where the environment's entities live and how positioning signals travel.

The control logic of the environment (`control.py`: scope, following and triggers,
interpretation service, management policy, command semantics) reads and writes entities
only through `EntityStore`, so it does not know which store it runs on:
  - `InMemoryStore` (here): the entities are Python objects of this process and a published
    signal is handed to the subscriber by a direct call;
  - `NgsiLdStore` (`ngsild/store.py`): the entities live in an NGSI-LD Context Broker
    (Orion-LD) and are reached over its REST API; a published signal is an update of a
    PositioningSignal entity, and it comes back through an NGSI-LD notification.

A store only stores: what a command does to a device's state is decided by the control
logic (`commands.py`), which then writes the new state.
"""

from collections.abc import Callable
from typing import Any, Protocol

from .model import Building, Device, PositioningSignal, Scenario, Zone

SignalSink = Callable[[PositioningSignal], None]


class EntityStore(Protocol):
    endpoint: str  # where the agent locates the environment (Binding, Locate step)

    def building(self) -> Building:
        """The Building entity, with the manager's management policy."""
        ...

    def zones(self) -> list[Zone]:
        """Every zone of the building, in the scenario's order."""
        ...

    def devices(self) -> list[Device]:
        """Every device of the building, in the scenario's order, with its current state."""
        ...

    def device(self, device_id: str) -> Device | None:
        """One device with its current state; None if there is no such device."""
        ...

    def write_state(self, device_id: str, state: dict[str, Any]) -> None:
        """Store a device's new state (already computed by the control logic)."""
        ...

    def publish(self, signal: PositioningSignal) -> None:
        """Called by the mobility simulator: one positioning signal enters the environment.
        Returns once the subscriber has been given the signal."""
        ...

    def subscribe(self, sink: SignalSink) -> None:
        """Every published positioning signal is given to `sink`, in publication order."""
        ...

    def close(self) -> None:
        """Release what the store holds (connections, subscriptions)."""
        ...


class InMemoryStore:
    """The entities of a scenario as objects of this process. Each store has its own copy
    of the devices: two stores built from the same Scenario do not share device state."""

    def __init__(self, scenario: Scenario) -> None:
        self.endpoint = scenario.broker.endpoint
        self._building = scenario.building
        self._zones = list(scenario.zones)
        self._devices = {d.device_id: d.model_copy(deep=True) for d in scenario.devices}
        self._sinks: list[SignalSink] = []

    def building(self) -> Building:
        return self._building

    def zones(self) -> list[Zone]:
        return list(self._zones)

    def devices(self) -> list[Device]:
        return list(self._devices.values())

    def device(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def write_state(self, device_id: str, state: dict[str, Any]) -> None:
        self._devices[device_id].state = dict(state)

    def publish(self, signal: PositioningSignal) -> None:
        for sink in list(self._sinks):
            sink(signal)

    def subscribe(self, sink: SignalSink) -> None:
        self._sinks.append(sink)

    def close(self) -> None:
        self._sinks.clear()
