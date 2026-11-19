"""Environment Binding: Locate, Authenticate, Enumerate (follow), Subscribe; no catalogue.

Also the temporary grounding context (the frozen grounders' input) and the rule that only
the frozen evaluation code reads the session's compatibility properties.
"""

import ast
import dataclasses
import re
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path

import pytest

from cpsagent.binding import (
    BindingError,
    BoundSession,
    EnvironmentBinding,
    temporary_grounding_context,
)
from cpsagent.contracts import GroundingRequest, ZoneEstimate
from cpsagent.environment import EmulatedEnvironment, PositioningSignal
from cpsagent.environment.mobility import MobilitySimulator
from cpsagent.localization import ZoneEstimator

ENDPOINT = "emulator://lab-building"
SRC = Path(__file__).resolve().parents[2] / "src" / "cpsagent"
T0 = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)


class Spy:
    """Wraps a backend and records the name of every method called on it."""

    def __init__(self, backend):
        self._backend, self.calls = backend, []

    def __getattr__(self, name):
        attr = getattr(self._backend, name)
        if callable(attr):

            def wrapped(*args, **kwargs):
                self.calls.append(name)
                return attr(*args, **kwargs)

            return wrapped
        return attr


@pytest.fixture
def env():
    return EmulatedEnvironment()


@pytest.fixture
def session(env):
    return EnvironmentBinding({env.endpoint: env}).bind(ENDPOINT, "person-agent", "user-1")


def signal(zone, rssi=-50.0):
    return PositioningSignal(rssi=rssi, observed_at=T0, ref_zone=zone, ref_subject="user-1")


def test_bind_produces_bound_session(session):
    assert session.bound and session.session_id == "sess-001"
    assert session.endpoint == ENDPOINT and session.token
    assert session.scope_zones == {
        "lobby", "hallway", "corridor", "office", "meeting_room", "kitchen", "storage"
    }  # fmt: skip
    assert session.subscription.subject == "user-1"


def test_binding_makes_no_catalogue_query_and_session_holds_no_catalogue(env):
    spy = Spy(env)
    session = EnvironmentBinding({env.endpoint: spy}).bind(ENDPOINT, "person-agent", "user-1")
    assert spy.calls == ["authenticate", "scope", "follow", "subscribe"]
    fields = {f.name for f in dataclasses.fields(BoundSession)}
    assert not fields & {"catalogue", "spatial_model"}
    assert session.neighbourhood.zone_id is None  # the person has not been heard yet


def test_enumerate_returns_the_neighbourhood_when_the_person_was_already_heard(env):
    env.publish(signal("hallway"))
    session = EnvironmentBinding({env.endpoint: env}).bind(ENDPOINT, "person-agent", "user-1")
    assert session.neighbourhood.zone_id == "hallway"
    assert session.neighbourhood.armed == ["lobby", "corridor", "kitchen"]
    assert session.known_adjacency["corridor"] == [
        "hallway", "office", "meeting_room", "storage", "server_room"
    ]  # fmt: skip


def test_session_follows_triggers_and_known_adjacency_only_grows(env, session):
    env.publish(signal("hallway"))
    env.publish(signal("hallway", -90.0))
    env.publish(signal("corridor"))
    assert session.neighbourhood.zone_id == "corridor"
    assert "lobby" not in session.neighbourhood.adjacency
    assert {"lobby", "hallway", "corridor", "office"} <= set(session.known_adjacency)
    assert "server_room" not in session.known_adjacency  # never armed: outside the scope


def test_locate_fails_for_unknown_endpoint(env):
    with pytest.raises(BindingError, match="locate"):
        EnvironmentBinding({env.endpoint: env}).bind("emulator://elsewhere", "person-agent", "u")


def test_authenticate_fails_for_unknown_agent(env):
    with pytest.raises(BindingError, match="authenticate"):
        EnvironmentBinding({env.endpoint: env}).bind(ENDPOINT, "intruder", "user-1")


def test_subscription_drives_localization_end_to_end(session, env):
    """Simulator -> broker.publish -> triggers + subscription (R13) -> Localization -> R6."""
    est = ZoneEstimator(dict(session.known_adjacency), "user-1")
    session.on_neighbourhood(lambda n: est.add_adjacency(n.adjacency))
    session.subscription.add_listener(est.on_signal)
    zones = []
    est.subscribe(lambda e: zones.append(e.estimate.zone_id))
    MobilitySimulator(env.scenario, "walk_in_the_light").run(env.publish)
    est.estimate()
    assert [k for k, _ in groupby(zones)] == ["lobby", "hallway", "corridor", "office"]


def test_close_stops_signal_delivery(session, env):
    received = []
    session.subscription.add_listener(received.append)
    session.close()
    MobilitySimulator(env.scenario, "walk_in_the_light").run(env.publish)
    assert not session.bound and received == []


# --- temporary grounding context ----------------------------------------------------------


def test_grounding_context_matches_the_input_the_grounders_were_tuned_with(env):
    token = env.authenticate("person-agent")
    context = temporary_grounding_context(env, token)
    building = {z.zone_id: z.adjacency for z in env.scenario.zones}
    assert context.adjacency == building and list(context.adjacency) == list(building)
    assert context.adjacency["server_room"] == ["corridor"]  # rebuilt by symmetry
    assert [z.zone_id for z in context.catalogue] == [
        "lobby", "hallway", "corridor", "office", "meeting_room", "kitchen", "storage"
    ]  # fmt: skip
    assert context.catalogue_properties() == {"light", "shading", "temperature"}
    devices = {d.device_id for z in context.catalogue for d in z.devices}
    assert "thermostat_server_room" not in devices
    GroundingRequest(
        text="I want to walk in the light",
        language="en",
        zone=ZoneEstimate(zone_id="hallway", confidence=0.9, observed_at=T0),
        catalogue=context.catalogue,
        adjacency=context.adjacency,
    )


def test_session_compatibility_properties_ask_the_environment_each_time(env):
    spy = Spy(env)
    session = EnvironmentBinding({env.endpoint: spy}).bind(ENDPOINT, "person-agent", "user-1")
    spy.calls.clear()
    token = env.authenticate("person-agent")
    assert session.catalogue == temporary_grounding_context(env, token).catalogue
    assert session.spatial_model.adjacency["hallway"] == ["lobby", "corridor", "kitchen"]
    assert session.catalogue_properties() == {"light", "shading", "temperature"}
    assert spy.calls == ["describe_scope"] * 3


def _uses(path: Path, names: set[str]) -> list[str]:
    """Attribute names in `names` read anywhere in the module at `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in names]


# Frozen code that binds a session and reads its catalogue: the evaluation package and the
# one-request tool next to the grounders.
FROZEN = ("eval/", "grounding/try.py")


def test_only_frozen_eval_reads_the_session_compatibility_properties():
    pattern = re.compile(r"session\.(catalogue|spatial_model|catalogue_properties)\b")
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if not path.relative_to(SRC).as_posix().startswith(FROZEN)
        and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_only_the_grounding_context_function_calls_describe_scope():
    callers = []
    for path in SRC.rglob("*.py"):
        if "describe_scope" in _uses(path, {"describe_scope"}):
            callers.append(path.relative_to(SRC).as_posix())
    assert callers == ["binding/grounding_context.py"]


def test_session_compatibility_properties_are_not_used_at_runtime(env, monkeypatch):
    """Binding, engine, planner and Interface run a full request without touching them."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
    from engine_rig import WALK, Rig

    def forbidden(self):
        raise AssertionError("compatibility property used outside the frozen evaluation")

    for name in ("catalogue", "spatial_model"):
        monkeypatch.setattr(BoundSession, name, property(forbidden))
    monkeypatch.setattr(BoundSession, "catalogue_properties", forbidden)
    rig = Rig()
    rig.engine.handle_request(WALK)
    rig.loc.move_to("corridor")
    rig.engine.handle_request("turn on all the lights")
    rig.engine.handle_request("make it humid")
    assert rig.power("lamp_corridor") == "on"


def test_grounding_context_does_not_carry_the_default_state():
    env = EmulatedEnvironment()
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")
    context = temporary_grounding_context(env, session.token)
    for zone in context.catalogue:
        for device in zone.model_dump(by_alias=True)["devices"]:
            assert set(device) == {"deviceId", "category", "controlledProperty", "supportedCommand"}
