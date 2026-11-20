"""The environment's entity store on an NGSI-LD Context Broker (Orion-LD).

Needs the `ngsild` extra (`pip install -e ".[ngsild]"`) and a running broker
(`docker compose up -d`, then `python -m cpsagent.environment.ngsild.seed`).
See docs/NGSI_LD.md.
"""

from ..control import EnvironmentControl
from ..model import Scenario, load_scenario
from .store import DEFAULT_URL, BrokerError, BrokerUnreachable, NgsiLdStore


def ngsild_environment(
    url: str = DEFAULT_URL,
    interpreter=None,
    scenario: Scenario | None = None,
    **store_options,
) -> EnvironmentControl:
    """The environment's control logic over Orion-LD at `url` (already seeded). The
    scenario gives the manager's configuration (agents and scope, scripted paths); the
    entities are read from the broker."""
    scenario = scenario or load_scenario()
    store = NgsiLdStore(url, scenario=scenario, **store_options)
    return EnvironmentControl(scenario, store, interpreter)


__all__ = ["DEFAULT_URL", "BrokerError", "BrokerUnreachable", "NgsiLdStore", "ngsild_environment"]
