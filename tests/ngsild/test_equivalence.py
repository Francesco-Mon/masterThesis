"""Functional equivalence of the environment on Orion-LD and in memory.

The same control logic, the same scenario, the same grounder (keyword) and seed: only
where the entities live and how signals travel differ. Everything but time must agree.
"""

import json
from pathlib import Path

import httpx
import pytest

from cpsagent.bench.scenario import command_outcomes, run_scenario
from cpsagent.binding import EnvironmentBinding
from cpsagent.environment import EmulatedEnvironment, OutOfScopeError
from cpsagent.environment.mobility import MobilitySimulator
from cpsagent.eval.dataset import load_cases
from cpsagent.grounding.keyword import KeywordGrounder
from cpsagent.interface import EnvironmentInterface

pytestmark = pytest.mark.ngsild

REGRESSION = Path(__file__).resolve().parents[1] / "regression"
STORE_BASELINE = json.loads((REGRESSION / "store_baseline.json").read_text("utf-8"))
REQUEST_BASELINE = json.loads((REGRESSION / "baseline.json").read_text("utf-8"))


def plain(data):
    return json.loads(json.dumps(data))


def memory():
    return EmulatedEnvironment(interpreter=KeywordGrounder())


def test_the_broker_holds_the_scenario(orion):
    env, ref = orion(), memory()
    assert env.building == ref.building
    assert [z.model_dump() for z in env.store.zones()] == [
        z.model_dump() for z in ref.store.zones()
    ]
    assert [d.model_dump() for d in env.store.devices()] == [
        d.model_dump() for d in ref.store.devices()
    ]


@pytest.mark.parametrize("key", sorted(STORE_BASELINE["runs"]))
def test_scenario_run_is_the_same_as_in_memory(orion, key):
    """Records (guards, states, outcomes), replies, commands, zone changes, triggers,
    restorations and device states: equal to the in-memory run and to the baseline."""
    path, seed = key.split("/")
    run = run_scenario(orion(), path, seed=int(seed))
    ref = run_scenario(memory(), path, seed=int(seed))
    assert plain(run.behaviour()) == plain(ref.behaviour()) == STORE_BASELINE["runs"][key]
    assert command_outcomes(run) == command_outcomes(ref)


def test_doorway_linger_zone_changes_match_the_baseline(orion):
    run = run_scenario(orion(), "doorway_linger", request=None)
    events = [[e["zone"], e["previous"], e["tick"]] for e in run.zone_events]
    assert events == REQUEST_BASELINE["zoneEvents"]["doorway_linger"]


def test_device_state_lives_in_the_broker(orion, broker_url):
    env = orion()
    token = env.authenticate("person-agent")
    env.execute(token, "lamp_office", "dim", 40)
    store = env.store
    raw = httpx.get(
        f"{broker_url}/ngsi-ld/v1/entities/urn:ngsi-ld:Device:lamp_office",
        headers={"Link": store._headers["Link"], "Accept": "application/json"},
    ).json()
    assert raw["state"] == {"type": "Property", "value": {"power": "on", "brightness": 40}}


# Calls of the command-line demo: allowed, out of scope, unsupported, unknown, not allowed.
CALLS = [
    {"operation": "listZones", "args": {}},
    {"operation": "listDevices", "args": {"zoneId": "corridor", "controlledProperty": "light"}},
    {"operation": "listDevices", "args": {"controlledProperty": "temperature"}},
    {"operation": "listDevices", "args": {"zoneId": "server_room"}},
    {"operation": "listDevices", "args": {"zoneId": "attic"}},
    {"operation": "invokeCommand", "args": {"deviceId": "lamp_hallway", "command": "on"}},
    {"operation": "getDeviceState", "args": {"deviceId": "lamp_hallway"}},
    {"operation": "invokeCommand",
     "args": {"deviceId": "lamp_corridor", "command": "dim", "value": 40}},
    {"operation": "invokeCommand",
     "args": {"deviceId": "thermostat_server_room", "command": "setSetpoint", "value": 18}},
    {"operation": "invokeCommand",
     "args": {"deviceId": "thermostat_office", "command": "setSetpoint", "value": 40}},
    {"operation": "getDeviceState", "args": {"deviceId": "thermostat_server_room"}},
    {"operation": "getDeviceState", "args": {"deviceId": "no_such_device"}},
    {"operation": "deleteDevice", "args": {"deviceId": "lamp_hallway"}},
]  # fmt: skip


def interface_results(env):
    scenario = env.scenario
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")
    MobilitySimulator(scenario, "doorway_linger").run(env.publish)  # followed: listZones
    api = EnvironmentInterface(session)
    out = [api.execute(call).model_dump(mode="json") for call in CALLS]
    session.close()
    return out, env.device_states()


def test_interface_calls_and_scope_refusals_are_the_same(orion):
    assert interface_results(orion()) == interface_results(memory())


def test_environment_refuses_to_interpret_outside_the_scope(orion):
    env = orion()
    token = env.authenticate("person-agent")
    case = next(c for c in load_cases()[0] if c.zone.zoneId == "server_room")
    with pytest.raises(OutOfScopeError):
        env.interpret(token, case.text, case.language, case.zone_estimate(), [])


def test_grounding_request_of_every_case_matches_the_baseline(orion):
    """The interpreter gets, from the broker's entities, the same GroundingRequest."""
    import sys

    sys.path.insert(0, str(REGRESSION))
    from test_alignment_regression import _sha

    env = orion()
    token = env.authenticate("person-agent")
    cases, _ = load_cases()
    got = {
        c.id: _sha(env.grounding_request(token, c.text, c.language, c.zone_estimate(), []))
        for c in cases
    }
    assert got == REQUEST_BASELINE["groundingRequestSha256"]


def test_policy_restores_in_the_broker_when_the_subscription_closes(orion):
    env = orion()
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")
    restored = []
    session.on_restoration(restored.append)
    MobilitySimulator(env.scenario, "doorway_linger").run(env.publish)
    EnvironmentInterface(session).invoke_command("lamp_hallway", "on")
    assert env.store.device("lamp_hallway").state["power"] == "on"
    session.close()
    assert [(r.device_id, r.reason) for r in restored] == [("lamp_hallway", "subscription_closed")]
    assert env.store.device("lamp_hallway").state == {"power": "off", "brightness": 0}
