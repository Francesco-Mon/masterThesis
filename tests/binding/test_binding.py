"""Environment Binding: bound session with spatial model and capability catalogue."""

from datetime import UTC, datetime
from itertools import groupby

import pytest

from cpsagent.binding import BindingError, EnvironmentBinding
from cpsagent.contracts import GroundingRequest, ZoneEstimate
from cpsagent.environment import EmulatedEnvironment
from cpsagent.environment.mobility import MobilitySimulator
from cpsagent.localization import ZoneEstimator

ENDPOINT = "emulator://lab-building"


@pytest.fixture
def env():
    return EmulatedEnvironment()


@pytest.fixture
def session(env):
    return EnvironmentBinding({env.endpoint: env}).bind(ENDPOINT, "person-agent", "user-1")


def devices(session):
    return {d.device_id: d for z in session.catalogue for d in z.devices}


def test_bind_produces_bound_session(session):
    assert session.bound and session.session_id == "sess-001"
    assert session.spatial_model.building.name == "Lab Building"
    assert session.spatial_model.adjacency["hallway"] == ["lobby", "corridor", "kitchen"]


def test_catalogue_reflects_supported_command(session, env):
    cat = devices(session)
    assert cat["lamp_hallway"].supported_command == ["on", "off", "dim"]
    assert cat["lamp_corridor"].supported_command == ["on", "off"]  # cannot dim
    assert cat["blind_meeting_room"].supported_command == ["open", "close"]
    for d in env.scenario.devices:
        if d.device_id in cat:
            assert cat[d.device_id].supported_command == d.supported_command


def test_catalogue_is_indexed_by_zone_and_respects_scope(session):
    by_zone = {z.zone_id: z for z in session.catalogue}
    assert by_zone["storage"].devices == []  # in scope, nothing to control
    assert "server_room" not in by_zone  # out of scope: its thermostat is not catalogued
    assert "server_room" in session.spatial_model.zones  # but the user can still walk there
    assert "thermostat_server_room" not in devices(session)


def test_absent_capabilities_are_not_in_catalogue(session, env):
    assert session.catalogue_properties() == {"light", "shading", "temperature"}
    assert not session.catalogue_properties() & set(env.scenario.absent_capabilities)


def test_catalogue_feeds_a_valid_grounding_request(session):
    zone = ZoneEstimate(zone_id="hallway", confidence=0.9, observed_at=datetime.now(UTC))
    GroundingRequest(
        text="I want to walk in the light",
        language="en",
        zone=zone,
        catalogue=session.catalogue,
        adjacency=session.spatial_model.adjacency,
    )


def test_locate_fails_for_unknown_endpoint(env):
    with pytest.raises(BindingError, match="locate"):
        EnvironmentBinding({env.endpoint: env}).bind("emulator://elsewhere", "person-agent", "u")


def test_authenticate_fails_for_unknown_agent(env):
    with pytest.raises(BindingError, match="authenticate"):
        EnvironmentBinding({env.endpoint: env}).bind(ENDPOINT, "intruder", "user-1")


def test_subscription_drives_localization_end_to_end(session, env):
    """Simulator -> broker.publish -> subscription (R13) -> Localization -> R6 events."""
    est = ZoneEstimator(session.spatial_model.adjacency, "user-1")
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
