"""Plan asks the environment for the catalogue (listDevices with the intent's property).

The answer is used for that plan only; an empty answer is "capability absent" (T5) and no
command is sent; after a zone change Plan asks again for the new zone.
"""

import inspect

import pytest
from engine_rig import WALK, Rig, intent

from cpsagent.contracts import Operation, State
from cpsagent.grounding import FakeGrounder


class CallLog:
    """Counts the Interface calls per operation."""

    def __init__(self, rig):
        self.calls = []
        execute = rig.engine._interface.execute

        def logged(call):
            self.calls.append((call.operation, getattr(call.args, "zone_id", None)))
            return execute(call)

        rig.engine._interface.execute = logged

    def ops(self):
        return [op for op, _ in self.calls]


def plan_queries(rig):
    """Queries carried by the rows that leave the Plan state, per Plan visit."""
    return [
        [(q.call.args.zone_id, q.call.args.controlled_property) for q in t.queries]
        for t in rig.engine.trace
        if t.source == State.PLAN
    ]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("turn on the light", [("hallway", "light")]),  # current_zone
        ("turn on the kitchen light", [("kitchen", "light")]),  # current_zone, targetZoneId
        # path: here, then the adjacent zones ahead (the user came from the lobby)
        (WALK, [("hallway", "light"), ("corridor", "light"), ("kitchen", "light")]),
        ("turn on all the lights", [(None, "light")]),  # environment: one query, no zoneId
    ],
)
def test_plan_asks_the_environment_with_the_intents_property(text, expected):
    rig = Rig()
    log = CallLog(rig)
    rig.engine.handle_request(text)
    assert plan_queries(rig)[0] == expected
    assert rig.queries[: len(expected)] == expected
    first_command = log.ops().index(Operation.INVOKE_COMMAND)
    assert set(log.ops()[:first_command]) == {Operation.LIST_DEVICES}  # asked before acting
    assert all(t.queries == () for t in rig.engine.trace if t.source != State.PLAN)


def test_environment_scope_plan_comes_from_the_single_answer():
    rig = Rig()
    rig.engine.handle_request("turn on all the lights")
    lamps = ["lamp_lobby", "lamp_hallway", "lamp_corridor"] + [
        "lamp_office", "lamp_meeting_room", "lamp_kitchen"
    ]  # fmt: skip
    assert [s.device_id for s in rig.engine.last_plan.steps] == lamps


def test_empty_answer_recovers_with_t5_and_sends_no_command():
    rig = Rig(zone="storage", previous="corridor")  # storage has no device at all
    log = CallLog(rig)
    rig.engine.handle_request("turn on the light")
    assert rig.guards == ["T1", "T2", "T5", "T12"]
    t5 = rig.engine.trace[2]
    assert t5.outcome == "capability_absent"
    assert [(q.call.args.zone_id, q.result.state) for q in t5.queries] == [("storage", [])]
    assert Operation.INVOKE_COMMAND not in log.ops()


def test_device_without_the_command_is_command_absent():
    rig = Rig(zone="corridor", previous="hallway")
    rig.engine.handle_request("dim the light")  # lamp_corridor cannot dim
    assert rig.guards[2] == "T5" and rig.engine.trace[2].outcome == "command_absent"


def test_answer_is_used_for_that_plan_only_and_asked_again_after_a_zone_change():
    rig = Rig()
    rig.engine.handle_request(WALK)
    rig.loc.move_to("corridor")  # T9 -> Plan asks again around the new zone
    rig.loc.move_to("office")
    visits = plan_queries(rig)
    assert [v[0] for v in visits] == [
        ("hallway", "light"), ("corridor", "light"), ("office", "light")
    ]  # fmt: skip
    assert ("office", "light") in visits[1]  # ahead of the corridor
    assert ("server_room", "light") not in visits[1]  # outside the scope: never asked
    assert len(rig.grounder.calls) == 1


def test_capability_the_environment_lacks_in_the_zone_ends_in_t5():
    script = {"cool the hallway": intent(action="decrease", prop="temperature")}
    rig = Rig()
    rig.env._interpreter = FakeGrounder(script)
    rig.engine.handle_request("cool the hallway")  # no thermostat in the hallway
    assert rig.guards == ["T1", "T2", "T5", "T12"]
    assert rig.engine.trace[2].outcome == "capability_absent"
    assert rig.queries == [("hallway", "temperature")]


def test_only_the_interpretation_service_reads_the_whole_scope(monkeypatch):
    """The whole scope is read inside the environment, once per interpreted request; the
    re-planning asks listDevices only."""
    rig = Rig()
    callers = []
    original = rig.env._describe_scope

    def spy(token):
        callers.append(inspect.stack()[1].function)
        return original(token)

    monkeypatch.setattr(rig.env, "_describe_scope", spy)
    rig.engine.handle_request(WALK)
    rig.loc.move_to("corridor")  # re-plan: no new interpretation, no scope read
    rig.engine.handle_request("turn on all the lights")
    assert callers == ["interpreter_context"] * 2
    assert len(rig.grounder.calls) == 2


def test_reference_scenario_keeps_its_records_and_single_grounder_call():
    """Hallway lamp now, corridor on arrival, office on arrival, then close: the queries
    are in the trace but not in the event log, so the record count is unchanged."""
    records = []
    rig = Rig(recorder=lambda t: records.append(t.record_fields()))
    rig.engine.handle_request(WALK)
    rig.loc.move_to("corridor")
    rig.loc.move_to("office")
    rig.engine.close()
    assert [r["guard"].value for r in records] == [
        "T1", "T2", "T4", "T6", "T9", "T4", "T6", "T9", "T4", "T6", "T8"
    ]  # fmt: skip
    assert len(records) == 11 and len(rig.grounder.calls) == 1
    assert all("queries" not in r for r in records)
