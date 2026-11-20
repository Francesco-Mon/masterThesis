"""The control logic runs on any EntityStore and does not know which one."""

import re
from pathlib import Path

from cpsagent.environment import EnvironmentControl, InMemoryStore, load_scenario
from cpsagent.environment.mobility import MobilitySimulator

CONTROL = Path(__file__).resolve().parents[2] / "src/cpsagent/environment/control.py"


class CountingStore(InMemoryStore):
    """An in-memory store that counts the calls the control logic makes."""

    def __init__(self, scenario):
        super().__init__(scenario)
        self.calls: dict[str, int] = {}

    def __getattribute__(self, name):
        if name in {"zones", "devices", "device", "write_state", "publish"}:
            calls = object.__getattribute__(self, "calls")
            calls[name] = calls.get(name, 0) + 1
        return object.__getattribute__(self, name)


def test_control_imports_no_concrete_store():
    imports = re.findall(r"^\s*(?:from|import) .*$", CONTROL.read_text("utf-8"), re.MULTILINE)
    assert imports and not [i for i in imports if re.search(r"InMemory|NgsiLd|ngsild|http", i)]
    assert "from .store import EntityStore" in imports


def test_two_in_memory_stores_do_not_share_device_state():
    scenario = load_scenario()
    a, b = InMemoryStore(scenario), InMemoryStore(scenario)
    a.write_state("lamp_hallway", {"power": "on", "brightness": 100})
    assert b.device("lamp_hallway").state == {"power": "off", "brightness": 0}
    assert scenario.devices[1].state == {"power": "off", "brightness": 0}


def test_entities_and_signals_go_through_the_store():
    scenario = load_scenario()
    store = CountingStore(scenario)
    env = EnvironmentControl(scenario, store)
    token = env.authenticate("person-agent")
    MobilitySimulator(scenario, "walk_in_the_light").run(env.publish)
    env.execute(token, "lamp_office", "on", None)
    assert store.device("lamp_office").state["power"] == "on"
    assert store.calls["publish"] > 0 and store.calls["write_state"] == 1
    assert env.endpoint == scenario.broker.endpoint
