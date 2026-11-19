"""Management policy of the building: the environment restores what a guest's agent changed.

Full stack, as in the demo: emulated environment, Environment Binding, Localization fed by
the subscription, Orchestration Engine with a scripted grounder, mobility simulator. The
restoration is the environment's action: it never goes through the Environment Interface
and adds no event record.
"""

from datetime import timedelta

import pytest
import yaml

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import State, StructuredIntent
from cpsagent.engine import OrchestrationEngine
from cpsagent.environment import (
    DEFAULT_SCENARIO,
    EmulatedEnvironment,
    ManagementPolicy,
    PathScript,
    Scenario,
    load_scenario,
)
from cpsagent.environment.mobility import DEFAULT_START, MobilitySimulator
from cpsagent.grounding import FakeGrounder
from cpsagent.interface import EnvironmentInterface
from cpsagent.localization import ZoneEstimator

WALK = "I want to walk in the light"
COLD = "I'm cold"
DARK_OFF = "turn off the light"
DELAY = load_scenario().building.management_policy.restore_after_seconds
OFF = {"power": "off", "brightness": 0}


def _intent(action, prop, scope="current_zone", persistence="one_off"):
    intent = StructuredIntent(
        action=action,
        controlled_property=prop,
        scope=scope,
        persistence=persistence,
        confidence=0.9,
    )
    return {"kind": "intent", "intent": intent}


SCRIPT = {
    WALK: _intent("activate", "light", "path", "following"),
    COLD: _intent("increase", "temperature"),
    DARK_OFF: _intent("deactivate", "light"),
}


def path(*segments, transit=4) -> PathScript:
    """PathScript from (zone, ticks) pairs."""
    return PathScript.model_validate(
        {
            "subject": "user-1",
            "transitTicks": transit,
            "segments": [{"zone": z, "ticks": n} for z, n in segments],
        }
    )


class SpyInterface:
    """Records every call the engine sends through the Environment Interface."""

    def __init__(self, interface):
        self._interface = interface
        self.calls = []

    def execute(self, call):
        self.calls.append(call)
        return self._interface.execute(call)


class Walk:
    """One bound session driven tick by tick, wired like the demo and the UI."""

    def __init__(self, scenario: Scenario | None = None, seed: int = 0):
        self.env = EmulatedEnvironment(scenario)
        self.session = EnvironmentBinding({self.env.endpoint: self.env}).bind(
            self.env.endpoint, "person-agent", "user-1"
        )
        self.loc = ZoneEstimator(dict(self.session.known_adjacency), "user-1")
        self.session.on_neighbourhood(lambda n: self.loc.add_adjacency(n.adjacency))
        self.session.subscription.add_listener(self.loc.on_signal)
        self.restorations = []
        self.session.on_restoration(self._restored)
        self.interface = SpyInterface(EnvironmentInterface(self.session))
        self.now = DEFAULT_START
        self.seed = seed
        self.engine = OrchestrationEngine(
            self.session, self.loc, FakeGrounder(SCRIPT), self.interface, clock=lambda: self.now
        )
        self.env_zone = []  # (time, zone where the environment places the person), per tick
        self.engine_state_at_restoration = []
        self._start = DEFAULT_START

    def _restored(self, restoration):
        self.restorations.append(restoration)
        self.engine_state_at_restoration.append((self.engine.state, len(self.engine.trace)))

    def play(self, script, say=None, when_in=None):
        """Walk `script`; say `say` once Localization places the person in `when_in`."""
        sim = MobilitySimulator(self.env.scenario, script, seed=self.seed, start=self._start)
        for tick in sim.ticks():
            self.now = tick.time
            for signal in tick.signals:
                self.env.publish(signal)
            self.env_zone.append((tick.time, self.session.neighbourhood.zone_id))
            estimate = self.loc.estimate()
            if say and estimate.zone_id == when_in and estimate.confidence >= 0.6:
                self.engine.handle_request(say)
                say = None
        self._start = self.now + timedelta(seconds=1)
        self.seed += 1

    def left_at(self, zone):
        """Time the environment last placed the person outside `zone` after being in it."""
        left = None
        for (_, before), (time, after) in zip(self.env_zone, self.env_zone[1:], strict=False):
            if before == zone and after != zone:
                left = time
        return left

    def state(self, device_id):
        return self.env.device_states()[device_id]

    def lamps_on(self):
        states = self.env.device_states()
        return {d for d, s in states.items() if d.startswith("lamp_") and s["power"] == "on"}

    def records(self):
        return [t.record_fields() for t in self.engine.trace]


def scenario_with(**defaults) -> Scenario:
    """The reference scenario with some defaultStates changed (test only)."""
    with open(DEFAULT_SCENARIO, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    for device in raw["devices"]:
        if device["deviceId"] in defaults:
            device["defaultState"] = defaults[device["deviceId"]]
    return Scenario.model_validate(raw)


def without_policy() -> Scenario:
    scenario = load_scenario()
    scenario.building.management_policy = ManagementPolicy()
    return scenario


def test_the_reference_policy_restores_after_twelve_seconds():
    policy = load_scenario().building.management_policy
    assert policy.restore_on_exit and policy.restore_after_seconds == 12


# 1. Walk in the light, lobby -> office ---------------------------------------------------


def test_walk_in_the_light_restores_every_lamp_left_behind_after_the_delay():
    w = Walk()
    w.play(w.env.scenario.paths["walk_in_the_light"], say=WALK, when_in="hallway")
    w.play(path(("office", int(DELAY))))  # the person stays in the office
    restored = {r.device_id: r for r in w.restorations}
    assert set(restored) == {"lamp_hallway", "lamp_corridor"}
    for device, zone in (("lamp_hallway", "hallway"), ("lamp_corridor", "corridor")):
        r = restored[device]
        assert (r.zone_id, r.reason, r.state) == (zone, "person_left_zone", OFF)
        assert r.time - w.left_at(zone) == timedelta(seconds=DELAY)
        assert w.state(device) == OFF
    assert w.lamps_on() == {"lamp_office"}
    assert w.env.pending_restorations() == [
        {"deviceId": "lamp_office", "zoneId": "office", "restoreAt": None}
    ]


def test_walk_in_the_light_keeps_the_agent_records_unchanged():
    with_policy, plain = Walk(), Walk(without_policy())
    for w in (with_policy, plain):
        w.play(w.env.scenario.paths["walk_in_the_light"], say=WALK, when_in="hallway")
        w.play(path(("office", int(DELAY))))
    assert with_policy.restorations and not plain.restorations
    assert with_policy.records() == plain.records()
    assert len(with_policy.records()) == 10  # the demo's 11 include the close (T8)
    assert plain.lamps_on() == {"lamp_hallway", "lamp_corridor", "lamp_office"}


def test_restoration_bypasses_the_interface_and_leaves_the_engine_alone():
    w = Walk()
    w.play(w.env.scenario.paths["walk_in_the_light"], say=WALK, when_in="hallway")
    w.play(path(("office", int(DELAY))))
    sent = [c for c in w.interface.calls if c.operation == "invokeCommand"]
    acted = [t.action for t in w.engine.trace if t.action is not None and t.source == State.ACT]
    assert sent == acted  # every command came from the engine; none is a restoration
    assert all(c.args.command == "on" for c in sent)
    # the engine was waiting in Observe and did not fire any row for the restoration
    traces_after = [n for _, n in w.engine_state_at_restoration]
    assert {s for s, _ in w.engine_state_at_restoration} == {State.OBSERVE}
    assert traces_after == sorted(traces_after) and len(w.engine.trace) == traces_after[-1]


# 2. Doorway linger: the environment's own zone flickers, the person never leaves --------


@pytest.mark.parametrize("seed", range(10))
def test_doorway_linger_never_restores_the_hallway_lamp(seed):
    w = Walk(seed=seed)
    w.play(w.env.scenario.paths["doorway_linger"], say=WALK, when_in="hallway")
    zones = {z for _, z in w.env_zone}
    if seed == 0:
        assert zones == {"hallway", "corridor"}  # the flicker happens
    assert "lamp_hallway" not in {r.device_id for r in w.restorations}
    assert w.state("lamp_hallway")["power"] == "on"


# 3. "I'm cold" in the office, then the corridor ------------------------------------------


def test_office_thermostat_goes_back_to_21_after_leaving_the_office():
    w = Walk()
    w.play(path(("office", 4), ("corridor", int(DELAY) + 4)), say=COLD, when_in="office")
    assert [(r.device_id, r.zone_id, r.state) for r in w.restorations] == [
        ("thermostat_office", "office", {"setpoint": 21.0})
    ]
    assert w.restorations[0].time - w.left_at("office") == timedelta(seconds=DELAY)
    assert w.state("thermostat_office") == {"setpoint": 21.0}


def test_office_thermostat_stays_raised_before_the_delay():
    w = Walk()
    w.play(path(("office", 4), ("corridor", 4)), say=COLD, when_in="office")
    assert w.state("thermostat_office") == {"setpoint": 23.0}
    assert w.restorations == []


# 4. A device the agent did not change is never touched -----------------------------------


def test_devices_not_changed_by_the_agent_are_never_restored():
    w = Walk()
    manager = w.env.authenticate("person-agent")  # another client, not following anyone
    w.env.execute(manager, "lamp_lobby", "on", None)
    w.env.execute(manager, "blind_office", "setPosition", 40)
    before = w.env.device_states()
    w.play(w.env.scenario.paths["walk_in_the_light"], say=WALK, when_in="hallway")
    w.play(path(("office", int(DELAY))))
    w.session.close()
    touched = {"lamp_hallway", "lamp_corridor", "lamp_office"}
    assert {r.device_id for r in w.restorations} == touched
    after = w.env.device_states()
    assert {d: s for d, s in after.items() if d not in touched} == {
        d: s for d, s in before.items() if d not in touched
    }
    assert after["lamp_lobby"]["power"] == "on" and after["blind_office"] == {"position": 40}


def test_a_device_another_client_also_changed_is_left_to_that_client():
    w = Walk()
    w.play(path(("hallway", 4)), say=WALK, when_in="hallway")
    other = w.env.authenticate("person-agent")
    w.env.execute(other, "lamp_hallway", "on", None)
    w.play(path(("hallway", 1), ("corridor", int(DELAY) + 4)))
    assert "lamp_hallway" not in {r.device_id for r in w.restorations}
    assert w.state("lamp_hallway")["power"] == "on"


def test_no_policy_no_restoration():
    w = Walk(without_policy())
    w.play(w.env.scenario.paths["walk_in_the_light"], say=WALK, when_in="hallway")
    w.play(path(("office", int(DELAY))))
    w.session.close()
    assert w.restorations == []
    assert w.lamps_on() == {"lamp_hallway", "lamp_corridor", "lamp_office"}


# 5. Defaults other than "off" -------------------------------------------------------------


def test_lamp_whose_default_is_dimmed_returns_to_exactly_that_state():
    dimmed = {"power": "on", "brightness": 50}
    w = Walk(scenario_with(lamp_hallway=dimmed))
    assert w.state("lamp_hallway") == dimmed  # the building starts in its policy state
    w.play(path(("hallway", 4), ("corridor", int(DELAY) + 4)), say=WALK, when_in="hallway")
    sent = [t.outcome.state for t in w.engine.trace if t.action and t.source == State.ACT]
    assert sent[0] == {"deviceId": "lamp_hallway", "power": "on", "brightness": 100}
    r = next(r for r in w.restorations if r.device_id == "lamp_hallway")
    assert r.state == dimmed and w.state("lamp_hallway") == dimmed


def test_lamp_whose_default_is_on_is_switched_back_on():
    on = {"power": "on", "brightness": 100}
    w = Walk(scenario_with(lamp_kitchen=on))
    w.play(path(("kitchen", 4)), say=DARK_OFF, when_in="kitchen")
    assert w.state("lamp_kitchen") == OFF  # the guest switched it off
    w.play(path(("kitchen", 1), ("hallway", int(DELAY) + 4)))
    assert [(r.device_id, r.state) for r in w.restorations] == [("lamp_kitchen", on)]
    assert w.state("lamp_kitchen") == on


def test_a_device_already_back_in_its_default_state_is_not_reported():
    w = Walk()
    w.play(path(("kitchen", 4)), say="I want to walk in the light", when_in="kitchen")
    w.engine.handle_request(DARK_OFF)  # the guest switches the kitchen lamp off again
    w.play(path(("kitchen", 1), ("hallway", int(DELAY) + 4)))
    assert "lamp_kitchen" not in {r.device_id for r in w.restorations}
    assert w.state("lamp_kitchen") == OFF


# 6. Coming back before the delay cancels the restoration ---------------------------------


def test_coming_back_before_the_delay_cancels_the_restoration():
    w = Walk()
    w.play(path(("office", 4), ("corridor", 3), ("office", 3 * int(DELAY))), say=COLD,
           when_in="office")  # fmt: skip
    out = [t for (t, z), (_, prev) in zip(w.env_zone[1:], w.env_zone, strict=False)
           if prev == "office" and z != "office"]  # fmt: skip
    assert out, "the person did leave the office"
    assert w.restorations == []
    assert w.state("thermostat_office") == {"setpoint": 23.0}
    assert w.env.pending_restorations() == [
        {"deviceId": "thermostat_office", "zoneId": "office", "restoreAt": None}
    ]


def test_leaving_again_starts_a_new_countdown():
    w = Walk()
    w.play(path(("office", 4), ("corridor", 3), ("office", 4), ("corridor", int(DELAY) + 4)),
           say=COLD, when_in="office")  # fmt: skip
    assert len(w.restorations) == 1
    assert w.restorations[0].time - w.left_at("office") == timedelta(seconds=DELAY)


def test_coming_back_after_the_restoration_replans_and_switches_the_lamp_on_again():
    w = Walk()
    w.play(path(("hallway", 4), ("corridor", int(DELAY) + 4), ("hallway", 6)), say=WALK,
           when_in="hallway")  # fmt: skip
    assert [r.device_id for r in w.restorations][:1] == ["lamp_hallway"]
    assert w.state("lamp_hallway")["power"] == "on"  # T9 re-plan in the hallway, lamp on
    hallway_on = [
        t for t in w.engine.trace
        if t.action is not None and t.source == State.ACT
        and t.action.args.device_id == "lamp_hallway"
    ]  # fmt: skip
    assert len(hallway_on) == 2 and hallway_on[1].time > w.restorations[0].time


# 7. Closing the session restores everything the token changed ----------------------------


def test_closing_the_session_restores_everything_the_token_changed():
    w = Walk()
    w.play(w.env.scenario.paths["walk_in_the_light"], say=WALK, when_in="hallway")
    w.play(path(("office", 2)))
    pending = {p["deviceId"] for p in w.env.pending_restorations()}
    assert pending == {"lamp_corridor", "lamp_office"}  # hallway already restored
    by_delay = len(w.restorations)
    w.engine.close()
    w.session.close()
    closed = w.restorations[by_delay:]
    assert {r.device_id for r in closed} == pending
    assert {r.reason for r in closed} == {"subscription_closed"}
    assert all(r.time == w.now for r in closed)
    assert w.lamps_on() == set()
    assert w.env.pending_restorations() == []
