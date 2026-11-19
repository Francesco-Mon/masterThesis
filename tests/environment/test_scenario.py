"""Scenario file and emulated environment."""

import pytest
import yaml
from pydantic import ValidationError

from cpsagent.environment import (
    DEFAULT_SCENARIO,
    AuthenticationError,
    DeviceFailure,
    EmulatedEnvironment,
    InvalidValue,
    Scenario,
    load_scenario,
)


@pytest.fixture
def raw():
    with open(DEFAULT_SCENARIO, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_scenario_loads_with_required_shape():
    s = load_scenario()
    assert len(s.zones) >= 5
    assert {d.category for d in s.devices} == {"lamp", "blind", "thermostat"}
    assert all(z.ref_building == s.building.name for z in s.zones)


def test_scenario_makes_grounding_non_trivial():
    s = load_scenario()
    zone_ids = {z.zone_id for z in s.zones}
    assert {"hallway", "corridor"} <= zone_ids
    lamp_zones = {d.ref_zone for d in s.devices if d.category == "lamp"}
    assert zone_ids - lamp_zones, "at least one zone without lamps"
    lamps = [d for d in s.devices if d.category == "lamp"]
    assert any("dim" not in d.supported_command for d in lamps), "a lamp that cannot dim"
    offered = {d.controlled_property for d in s.devices}
    assert s.absent_capabilities and not offered & set(s.absent_capabilities)


def test_commands_on_off_are_strings_not_yaml_booleans():
    s = load_scenario()
    lamp = next(d for d in s.devices if d.category == "lamp")
    assert lamp.supported_command[:2] == ["on", "off"]


def test_asymmetric_adjacency_rejected(raw):
    raw["zones"][0]["adjacency"] = ["hallway", "office"]  # office does not list lobby
    with pytest.raises(ValidationError, match="not symmetric"):
        Scenario.model_validate(raw)


def test_device_in_unknown_zone_rejected(raw):
    raw["devices"][0]["refZone"] = "attic"
    with pytest.raises(ValidationError, match="unknown refZone"):
        Scenario.model_validate(raw)


def test_command_outside_category_rejected(raw):
    raw["devices"][0]["supportedCommand"] = ["on", "open"]  # a lamp cannot "open"
    with pytest.raises(ValidationError, match="not defined for category"):
        Scenario.model_validate(raw)


def test_path_with_non_adjacent_step_rejected(raw):
    raw["paths"]["walk_in_the_light"]["segments"] = [
        {"zone": "lobby", "ticks": 2},
        {"zone": "office", "ticks": 2},
    ]
    with pytest.raises(ValidationError, match="not adjacent"):
        Scenario.model_validate(raw)


def test_emulator_requires_registered_agent_and_valid_token():
    env = EmulatedEnvironment()
    with pytest.raises(AuthenticationError):
        env.authenticate("intruder")
    with pytest.raises(AuthenticationError):
        env.zones("forged-token")
    token = env.authenticate("person-agent")
    assert "server_room" not in env.scope(token)


def test_emulator_executes_commands_and_rejects_bad_values():
    env = EmulatedEnvironment()
    token = env.authenticate("person-agent")
    assert env.execute(token, "lamp_hallway", "on", None) == {"power": "on", "brightness": 100}
    assert env.execute(token, "lamp_hallway", "dim", 30)["brightness"] == 30
    with pytest.raises(InvalidValue):
        env.execute(token, "lamp_hallway", "dim", 150)
    assert env.device(token, "lamp_hallway").state["brightness"] == 30  # unchanged


def test_injected_failure_leaves_state_unchanged_then_clears():
    env = EmulatedEnvironment()
    token = env.authenticate("person-agent")
    env.inject_failure("lamp_corridor", times=1)
    with pytest.raises(DeviceFailure):
        env.execute(token, "lamp_corridor", "on", None)
    assert env.device(token, "lamp_corridor").state["power"] == "off"
    assert env.execute(token, "lamp_corridor", "on", None)["power"] == "on"


def test_emulators_sharing_a_scenario_do_not_share_state():
    s = load_scenario()
    a, b = EmulatedEnvironment(s), EmulatedEnvironment(s)
    a.execute(a.authenticate("person-agent"), "lamp_lobby", "on", None)
    assert b.device(b.authenticate("person-agent"), "lamp_lobby").state["power"] == "off"


# --- environmental policy: defaultState and managementPolicy ----------------------------


def test_building_starts_in_its_policy_state():
    s = load_scenario()
    policy = s.building.management_policy
    assert policy.restore_on_exit and policy.restore_after_seconds > 0
    for d in s.devices:
        assert d.state == d.default_state
    defaults = {d.device_id: d.default_state for d in s.devices}
    assert defaults["lamp_hallway"] == {"power": "off", "brightness": 0}
    assert defaults["blind_office"] == {"position": 0}
    assert defaults["thermostat_office"] == {"setpoint": 21.0}


@pytest.mark.parametrize(
    "default",
    [{"power": "on", "brightness": 100}, {"power": "on", "brightness": 50}],
)
def test_default_state_reachable_by_a_command_is_accepted(raw, default):
    raw["devices"][0]["defaultState"] = default
    device = Scenario.model_validate(raw).devices[0]
    assert device.default_state == default and device.state == default


@pytest.mark.parametrize(
    "default",
    [
        {"power": "on", "brightness": 0},  # no command gives it
        {"power": "off"},  # not the shape of a lamp's state
        {"setpoint": 21.0},  # a thermostat's state on a lamp
        {"power": "on", "brightness": 120},  # out of range
    ],
)
def test_default_state_not_reachable_is_rejected(raw, default):
    raw["devices"][0]["defaultState"] = default
    with pytest.raises(ValidationError, match="defaultState"):
        Scenario.model_validate(raw)


def test_thermostat_default_outside_the_setpoint_range_is_rejected(raw):
    device = next(d for d in raw["devices"] if d["category"] == "thermostat")
    device["defaultState"] = {"setpoint": 35}
    with pytest.raises(ValidationError, match="defaultState"):
        Scenario.model_validate(raw)


def test_missing_policy_fields_mean_no_restoration_and_initial_defaults(raw):
    del raw["building"]["managementPolicy"]
    for d in raw["devices"]:
        del d["defaultState"]
    s = Scenario.model_validate(raw)
    assert not s.building.management_policy.restore_on_exit
    assert all(d.default_state == d.state for d in s.devices)


def test_negative_restoration_delay_is_rejected(raw):
    raw["building"]["managementPolicy"]["restoreAfterSeconds"] = -1
    with pytest.raises(ValidationError):
        Scenario.model_validate(raw)
