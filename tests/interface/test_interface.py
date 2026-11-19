"""Environment Interface: 4 operations, allow-list, scope, only invokeCommand mutates."""

from datetime import UTC, datetime

import pytest

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import Operation, ToolResult
from cpsagent.contracts.tool import InvokeCommandArgs, InvokeCommandCall
from cpsagent.environment import (
    CommandNotSupportedError,
    EmulatedEnvironment,
    OutOfScopeError,
    PositioningSignal,
    UnknownEntityError,
)
from cpsagent.interface import ALLOWED_OPERATIONS, MUTATING_OPERATIONS, EnvironmentInterface


@pytest.fixture
def env():
    return EmulatedEnvironment()


@pytest.fixture
def session(env):
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")
    signal = PositioningSignal(
        rssi=-50.0,
        observed_at=datetime(2026, 11, 10, 9, 30, tzinfo=UTC),
        ref_zone="hallway",
        ref_subject="user-1",
    )
    env.publish(signal)  # the environment hears the person in the hallway
    return session


@pytest.fixture
def api(session):
    return EnvironmentInterface(session)


def snapshot(env):
    return env.device_states()  # observer view, whatever the scope


def assert_rejected(result: ToolResult, error: str):
    assert not result.ok and result.error == error and result.state is None
    ToolResult.model_validate(result.model_dump(mode="json"))  # still a valid C3 message


def test_allow_list_is_exactly_the_four_operations():
    assert ALLOWED_OPERATIONS == set(Operation) and len(ALLOWED_OPERATIONS) == 4
    assert MUTATING_OPERATIONS == {Operation.INVOKE_COMMAND}


def test_list_zones_returns_only_the_followed_neighbourhood(api):
    r = api.list_zones()
    assert r.ok and r.operation == "listZones"
    zones = {z["zoneId"]: z["adjacency"] for z in r.state}
    assert list(zones) == ["hallway", "lobby", "corridor", "kitchen"]  # person's zone first
    assert zones["corridor"] == ["hallway", "office", "meeting_room", "storage", "server_room"]


def test_list_zones_is_empty_until_the_person_is_heard(env):
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")
    assert EnvironmentInterface(session).list_zones().state == []


def test_list_devices_returns_supported_commands(api):
    r = api.list_devices("corridor")
    assert r.ok and r.state == [
        {
            "deviceId": "lamp_corridor",
            "category": "lamp",
            "controlledProperty": "light",
            "supportedCommand": ["on", "off"],
            "refZone": "corridor",
            "defaultState": {"power": "off", "brightness": 0},
        }
    ]
    assert api.list_devices("storage").state == []


def test_list_devices_filters_by_property_and_covers_the_scope_without_zone(api):
    office = api.list_devices("office", "shading").state
    assert [d["deviceId"] for d in office] == ["blind_office"]
    assert [d["deviceId"] for d in api.list_devices("office").state] == [
        "lamp_office", "blind_office", "thermostat_office"
    ]  # fmt: skip
    every = api.list_devices(controlled_property="temperature").state
    assert [d["deviceId"] for d in every] == ["thermostat_office", "thermostat_meeting_room"]
    assert api.list_devices(controlled_property="humidity").state == []  # capability absent
    assert len(api.list_devices().state) == 10  # all devices of the scope, not server_room


def test_invoke_command_changes_state_and_get_reads_it(api):
    r = api.invoke_command("lamp_hallway", "on")
    assert r.ok and r.state == {"deviceId": "lamp_hallway", "power": "on", "brightness": 100}
    assert api.get_device_state("lamp_hallway").state["power"] == "on"
    assert api.invoke_command("thermostat_office", "setSetpoint", 23).state["setpoint"] == 23.0


def test_get_device_state_includes_the_default_state(api):
    api.invoke_command("lamp_hallway", "on")
    assert api.get_device_state("lamp_hallway").state == {
        "deviceId": "lamp_hallway",
        "power": "on",
        "brightness": 100,
        "defaultState": {"power": "off", "brightness": 0},
    }
    thermostat = api.get_device_state("thermostat_office").state
    assert thermostat["defaultState"] == {"setpoint": 21.0}


def test_typed_tool_call_is_accepted(api):
    call = InvokeCommandCall(
        operation=Operation.INVOKE_COMMAND,
        args=InvokeCommandArgs(device_id="blind_office", command="setPosition", value=40),
    )
    assert api.execute(call).state["position"] == 40


def test_only_invoke_command_changes_the_environment(api, env):
    before = snapshot(env)
    api.list_zones()
    api.list_devices()
    for zone in env.scenario.zones:
        api.list_devices(zone.zone_id)
        api.list_devices(zone.zone_id, "light")
    for device in env.scenario.devices:
        api.get_device_state(device.device_id)
    assert snapshot(env) == before
    api.invoke_command("lamp_office", "on")
    assert snapshot(env) != before


@pytest.mark.parametrize(
    "call",
    [
        {"operation": "deleteDevice", "args": {"deviceId": "lamp_hallway"}},
        {"operation": "setZoneEstimate", "args": {"zoneId": "office"}},  # not an env action
        {"operation": "INVOKECOMMAND", "args": {"deviceId": "lamp_hallway", "command": "on"}},
        {"args": {"deviceId": "lamp_hallway", "command": "on"}},
        {"operation": None},
    ],
)
def test_operation_outside_allow_list_rejected(api, env, call):
    before = snapshot(env)
    r = api.execute(call)
    assert_rejected(r, "operation_not_allowed")
    assert r.operation is None
    assert snapshot(env) == before


@pytest.mark.parametrize(
    "call",
    [
        {"operation": "invokeCommand", "args": {"deviceId": "lamp_hallway"}},  # no command
        {"operation": "listDevices"},  # args may be empty but not missing
        {"operation": "listDevices", "args": {"zoneId": ""}},
        {"operation": "listZones", "args": {"zoneId": "hallway"}},  # listZones takes none
        {
            "operation": "invokeCommand",
            "args": {"deviceId": "lamp_hallway", "command": "on", "force": True},
        },
    ],
)
def test_bad_arguments_rejected(api, call):
    r = api.execute(call)
    assert_rejected(r, "invalid_args")
    assert r.operation == call["operation"]


def test_command_not_in_supported_command_rejected(api, env):
    before = snapshot(env)
    assert_rejected(api.invoke_command("lamp_corridor", "dim", 50), "command_not_supported")
    assert_rejected(
        api.invoke_command("blind_meeting_room", "setPosition", 50), "command_not_supported"
    )
    assert_rejected(api.invoke_command("lamp_hallway", "setColor", "red"), "command_not_supported")
    assert_rejected(api.invoke_command("lamp_hallway", "ON"), "command_not_supported")
    assert snapshot(env) == before


def test_device_and_zone_outside_scope_rejected(api, env):
    before = snapshot(env)
    assert_rejected(api.invoke_command("thermostat_server_room", "setSetpoint", 18), "out_of_scope")
    assert_rejected(api.get_device_state("thermostat_server_room"), "out_of_scope")
    assert_rejected(api.list_devices("server_room"), "out_of_scope")
    assert snapshot(env) == before


def test_unknown_device_and_zone_rejected(api):
    assert_rejected(api.invoke_command("lamp_attic", "on"), "unknown_device")
    assert_rejected(api.get_device_state("lamp_attic"), "unknown_device")
    # the agent only knows its scope: any other zone is out of scope from its side
    assert_rejected(api.list_devices("attic"), "out_of_scope")


def test_environment_refuses_out_of_scope_calls_itself(env):
    token = env.authenticate("person-agent")
    before = snapshot(env)
    with pytest.raises(OutOfScopeError):
        env.execute(token, "thermostat_server_room", "setSetpoint", 18)
    with pytest.raises(OutOfScopeError):
        env.device(token, "thermostat_server_room")
    with pytest.raises(OutOfScopeError):
        env.devices(token, "server_room")
    with pytest.raises(UnknownEntityError):
        env.devices(token, "attic")
    with pytest.raises(CommandNotSupportedError):
        env.execute(token, "lamp_corridor", "dim", 40)
    assert "thermostat_server_room" not in {d.device_id for d in env.devices(token)}
    assert snapshot(env) == before


def test_environment_refuses_even_when_the_interface_check_is_bypassed(session, env):
    """Defence in depth: widen the agent's own view of the scope; the environment, which
    granted the token, still refuses and the Interface maps its refusal to C3."""
    session.scope_zones = frozenset(z.zone_id for z in env.scenario.zones)
    api = EnvironmentInterface(session)
    before = snapshot(env)
    assert_rejected(api.invoke_command("thermostat_server_room", "setSetpoint", 18), "out_of_scope")
    assert_rejected(api.get_device_state("thermostat_server_room"), "out_of_scope")
    assert_rejected(api.list_devices("server_room"), "out_of_scope")
    assert snapshot(env) == before


def test_invalid_value_rejected_without_changing_state(api, env):
    before = snapshot(env)
    assert_rejected(api.invoke_command("lamp_hallway", "dim", 150), "invalid_args")
    assert_rejected(api.invoke_command("thermostat_office", "setSetpoint", 40), "invalid_args")
    assert_rejected(api.invoke_command("thermostat_office", "setSetpoint", None), "invalid_args")
    assert snapshot(env) == before


def test_device_failure_reported(api, env):
    env.inject_failure("lamp_corridor", times=1)
    assert_rejected(api.invoke_command("lamp_corridor", "on"), "device_failure")
    assert api.invoke_command("lamp_corridor", "on").ok  # retry succeeds


def test_closed_session_cannot_be_used(env):
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")
    api = EnvironmentInterface(session)
    session.close()
    with pytest.raises(RuntimeError):
        api.list_zones()
