"""Rule-based planner: scope -> zones and guards, catalogue decides the commands."""

from datetime import UTC, datetime

import pytest

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import StructuredIntent, ZoneEstimate
from cpsagent.engine import explain_no_step, make_plan
from cpsagent.environment import EmulatedEnvironment


@pytest.fixture(scope="module")
def session():
    env = EmulatedEnvironment()
    return EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")


def zone(zid, previous=None):
    t = datetime(2026, 11, 10, tzinfo=UTC)
    return ZoneEstimate(zone_id=zid, confidence=0.9, observed_at=t, previous_zone_id=previous)


def plan(session, z, action="activate", prop="light", scope="path"):
    intent = StructuredIntent(
        action=action,
        controlled_property=prop,
        scope=scope,
        persistence="following",
        confidence=0.9,
    )
    return make_plan(intent, z, session.catalogue, session.spatial_model.adjacency), intent


def test_walk_in_the_light_from_hallway(session):
    p, _ = plan(session, zone("hallway", previous="lobby"))
    steps = [
        (s.device_id, s.command, s.guard.type, getattr(s.guard, "zone_id", None)) for s in p.steps
    ]
    # hallway lamp now, corridor (and kitchen) lamp on arrival; lobby is behind the user
    assert steps == [
        ("lamp_hallway", "on", "now", None),
        ("lamp_corridor", "on", "on_enter_zone", "corridor"),
        ("lamp_kitchen", "on", "on_enter_zone", "kitchen"),
    ]
    assert p.valid_for.zone_id == "hallway"


def test_path_never_reaches_a_zone_out_of_scope(session):
    p, _ = plan(
        session, zone("corridor", previous="hallway"), prop="temperature", action="increase"
    )
    assert "thermostat_server_room" not in {s.device_id for s in p.steps}


def test_command_missing_from_catalogue_is_dropped(session):
    p, intent = plan(session, zone("corridor"), action="decrease", scope="current_zone")
    assert p.steps == []  # lamp_corridor has no "dim"
    assert explain_no_step(intent, zone("corridor"), session.catalogue) == "command_absent"


def test_zone_without_the_property(session):
    p, intent = plan(session, zone("storage"), scope="current_zone")
    assert p.steps == []
    assert explain_no_step(intent, zone("storage"), session.catalogue) == "capability_absent"


def test_environment_scope_covers_every_catalogued_zone(session):
    p, _ = plan(session, zone("hallway"), action="deactivate", scope="environment")
    assert [s.device_id for s in p.steps] == [
        "lamp_lobby",
        "lamp_hallway",
        "lamp_corridor",
        "lamp_office",
        "lamp_meeting_room",
        "lamp_kitchen",
    ]
    assert all(s.command == "off" and s.guard.type == "now" for s in p.steps)


def test_target_zone_replaces_the_current_zone(session):
    intent = StructuredIntent(
        action="activate",
        controlled_property="light",
        scope="current_zone",
        persistence="one_off",
        confidence=0.9,
        target_zone_id="kitchen",
    )
    here = zone("hallway")
    p = make_plan(intent, here, session.catalogue, session.spatial_model.adjacency)
    assert [(s.device_id, s.command, s.guard.type) for s in p.steps] == [
        ("lamp_kitchen", "on", "now")
    ]
    dim = intent.model_copy(update={"action": "decrease"})  # lamp_kitchen has no "dim"
    assert make_plan(dim, here, session.catalogue, session.spatial_model.adjacency).steps == []
    assert explain_no_step(dim, here, session.catalogue) == "command_absent"


def set_intent(prop, value, target=None):
    return StructuredIntent(
        action="set",
        controlled_property=prop,
        scope="current_zone",
        persistence="one_off",
        confidence=0.9,
        target_zone_id=target,
        value=value,
    )


@pytest.mark.parametrize(
    "prop, value, expected",
    [
        ("temperature", 22, [("thermostat_office", "setSetpoint", 22)]),
        ("light", 40, [("lamp_office", "dim", 40)]),
        ("shading", 30, [("blind_office", "setPosition", 70)]),  # 30% shaded = 70% open
    ],
)
def test_set_uses_the_intent_value(session, prop, value, expected):
    p = make_plan(
        set_intent(prop, value), zone("office"), session.catalogue, session.spatial_model.adjacency
    )
    assert [(s.device_id, s.command, s.value) for s in p.steps] == expected


@pytest.mark.parametrize("prop, here", [("light", "corridor"), ("shading", "meeting_room")])
def test_set_on_a_device_without_the_value_command_is_command_absent(session, prop, here):
    intent = set_intent(prop, 40)  # lamp_corridor has no "dim", blind_meeting_room no "setPosition"
    adjacency = session.spatial_model.adjacency
    assert make_plan(intent, zone(here), session.catalogue, adjacency).steps == []
    assert explain_no_step(intent, zone(here), session.catalogue) == "command_absent"
