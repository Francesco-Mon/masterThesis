"""In-process emulation of the Intelligent Environment: the environment's control logic
(`control.py`) over the in-memory entity store (`store.py`).

It stands where Orion-LD and the manager's services would stand. The same control logic
runs on Orion-LD with `NgsiLdStore` (`ngsild/`); only where the entities live and how
signals travel change.
"""

from .control import STALE_AFTER_S, EnvironmentControl
from .model import Scenario, load_scenario
from .store import InMemoryStore

__all__ = ["STALE_AFTER_S", "EmulatedEnvironment"]


class EmulatedEnvironment(EnvironmentControl):
    def __init__(self, scenario: Scenario | None = None, interpreter=None) -> None:
        """`interpreter`: the grounder of the environment's interpretation service (any
        `cpsagent.grounding.Grounder`); the keyword grounder when not given."""
        scenario = scenario or load_scenario()
        super().__init__(scenario, InMemoryStore(scenario), interpreter)
