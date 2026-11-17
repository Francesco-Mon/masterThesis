"""The environment follows the person (Enumerate): triggers, re-arming, forwarded signals."""

from datetime import UTC, datetime, timedelta

import pytest

from cpsagent.environment import EmulatedEnvironment, PositioningSignal

T0 = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)


def reading(zone, rssi, t=0.0, subject="user-1"):
    return PositioningSignal(
        rssi=rssi, observed_at=T0 + timedelta(seconds=t), ref_zone=zone, ref_subject=subject
    )


@pytest.fixture
def env():
    return EmulatedEnvironment()


@pytest.fixture
def followed(env):
    """A token following user-1; `events` interleaves neighbourhoods and delivered signals."""
    token = env.authenticate("person-agent")
    events = []
    first = env.follow(token, "user-1", lambda n: events.append(("neighbourhood", n)))
    env.subscribe(token, "user-1", lambda s: events.append(("signal", s)))
    return token, events, first


def neighbourhoods(events):
    return [e for kind, e in events if kind == "neighbourhood"]


def test_follow_returns_no_zone_until_the_person_is_heard(env, followed):
    _, _, first = followed
    assert first.zone_id is None and first.adjacency == {}


def test_follow_places_a_person_already_heard_on_the_strongest_beacon(env):
    env.publish(reading("lobby", -80.0))
    env.publish(reading("hallway", -60.0))
    token = env.authenticate("person-agent")
    n = env.follow(token, "user-1", lambda n: None)
    assert n.zone_id == "hallway" and n.armed == ["lobby", "corridor", "kitchen"]


def test_armed_zones_are_exactly_the_in_scope_neighbours(env, followed):
    token, events, _ = followed
    env.publish(reading("corridor", -55.0))
    n = neighbourhoods(events)[-1]
    adjacency = {z.zone_id: z.adjacency for z in env.scenario.zones}
    assert n.zone_id == "corridor"
    assert n.armed == [z for z in adjacency["corridor"] if z != "server_room"]
    assert n.adjacency["office"] == adjacency["office"]  # each neighbour with its adjacency
    assert [z.zone_id for z in env.zones(token)] == ["corridor", *n.armed]


def test_trigger_re_arms_around_the_new_zone_and_notifies_before_the_signal(env, followed):
    _, events, _ = followed
    env.publish(reading("hallway", -55.0))
    env.publish(reading("corridor", -75.0, t=1))  # armed but weaker: no trigger
    assert neighbourhoods(events)[-1].zone_id == "hallway"
    events.clear()
    env.publish(reading("hallway", -70.0, t=2))
    env.publish(reading("corridor", -60.0, t=2))  # armed and now the strongest: fires
    kinds = [(k, e.zone_id if k == "neighbourhood" else e.ref_zone) for k, e in events]
    assert kinds == [
        ("signal", "hallway"),
        ("neighbourhood", "corridor"),  # told before the signal that fired the trigger
        ("signal", "corridor"),
    ]
    assert neighbourhoods(events)[-1].armed == ["hallway", "office", "meeting_room", "storage"]


def test_only_signals_of_the_followed_zones_are_forwarded(env, followed):
    _, events, _ = followed
    env.publish(reading("hallway", -55.0))
    events.clear()
    for zone in ("lobby", "corridor", "kitchen", "office", "server_room"):
        env.publish(reading(zone, -85.0))
    delivered = [e.ref_zone for k, e in events if k == "signal"]
    assert delivered == ["lobby", "corridor", "kitchen"]  # office: not armed; server_room: scope


def test_an_out_of_scope_beacon_never_moves_the_person(env, followed):
    _, events, _ = followed
    env.publish(reading("corridor", -60.0))
    env.publish(reading("server_room", -40.0))
    assert neighbourhoods(events)[-1].zone_id == "corridor"


def test_track_lost_the_next_reading_in_scope_places_the_person(env, followed):
    _, events, _ = followed
    env.publish(reading("hallway", -55.0))
    env.publish(reading("office", -55.0, t=5))  # neither hallway nor its neighbours heard
    assert neighbourhoods(events)[-1].zone_id == "office"


def test_unsubscribe_disarms_the_triggers(env, followed):
    token, events, _ = followed
    sub = env.subscribe(token, "user-1", lambda s: None)
    env.unsubscribe(sub)
    env.publish(reading("hallway", -55.0))
    assert neighbourhoods(events) == [] and env.zones(token) == []
