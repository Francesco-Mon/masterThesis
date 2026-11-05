"""Orchestration Engine: every row T1-T12 is reachable, loops are bounded, re-planning
reuses the intent (no second grounding call)."""

import pytest
from engine_rig import WALK, Rig

from cpsagent.contracts import EventRecord, State
from cpsagent.engine import EngineConfig


def test_one_off_request_t1_t2_t4_t6_t8(rig):
    reply = rig.engine.handle_request("turn on the light")
    assert rig.guards == ["T1", "T2", "T4", "T6", "T8"]
    assert reply.status == "done" and rig.power("lamp_hallway") == "on"
    assert rig.engine.state == State.PERCEIVE
    act = rig.engine.trace[3]
    assert act.action.args.device_id == "lamp_hallway" and act.outcome.ok


def test_t3_low_zone_confidence_skips_grounding():
    rig = Rig(confidence=0.4)
    reply = rig.engine.handle_request("turn on the light")
    assert rig.guards == ["T1", "T3", "T12"]
    assert rig.engine.trace[1].outcome == "zone_confidence_low"
    assert rig.grounder.calls == []  # no grounding call spent on an unreliable zone
    assert reply.status == "recovered" and "Which room" in reply.message


@pytest.mark.parametrize("text", ["", "   "])
def test_t3_empty_text_is_unintelligible_and_skips_grounding(rig, text):
    reply = rig.engine.handle_request(text)  # what the UI sends for an unreliable transcript
    assert rig.guards == ["T1", "T3", "T12"]
    assert rig.engine.trace[1].outcome == "request_unintelligible"
    assert rig.engine.trace[2].outcome == "clarification_asked"
    assert rig.grounder.calls == [] and rig.engine.history == []
    assert reply.status == "recovered" and "say it again" in reply.message


@pytest.mark.parametrize(
    "text, reason",
    [
        ("maybe some light?", "intent_confidence_low"),
        ("do the thing", "clarification:ambiguous_action"),
        ("play some music", "unsupported:capability_absent"),
        ("make it humid", "unsupported:capability_absent"),  # property not in catalogue
    ],
)
def test_t3_grounding_without_a_confident_intent(rig, text, reason):
    rig.engine.handle_request(text)
    assert rig.guards == ["T1", "T3", "T12"]
    assert rig.engine.trace[1].outcome == reason


def test_clarification_question_is_returned_to_the_user(rig):
    assert rig.engine.handle_request("do the thing").message == "What should I do?"


@pytest.mark.parametrize(
    "zone, text, reason",
    [
        ("storage", "turn on the light", "capability_absent"),
        ("corridor", "dim the light", "command_absent"),
    ],
)
def test_t5_no_applicable_step(zone, text, reason):
    rig = Rig(zone=zone)
    rig.engine.handle_request(text)
    assert rig.guards == ["T1", "T2", "T5", "T12"]
    assert rig.engine.trace[2].outcome == reason


def test_t7_step_limit_stops_a_long_plan():
    rig = Rig(config=EngineConfig(step_limit=2))
    rig.engine.handle_request("turn on all the lights")  # 6 lamps, all "now"
    assert rig.guards == ["T1", "T2", "T4", "T6", "T9", "T4", "T6", "T9", "T4", "T7", "T12"]
    assert rig.engine.trace[4].outcome == "steps_pending"
    assert rig.engine.trace[9].outcome == "step_limit_reached"
    assert [rig.power(d) for d in ("lamp_lobby", "lamp_hallway", "lamp_corridor")] == [
        "on",
        "on",
        "off",
    ]


def test_environment_scope_runs_every_step_within_the_limit(rig):
    rig.engine.handle_request("turn on all the lights")
    assert rig.guards.count("T6") == 6 and rig.guards[-1] == "T8"
    assert len(rig.grounder.calls) == 1


def test_t9_zone_change_replans_without_regrounding(rig):
    reply = rig.engine.handle_request(WALK)
    assert rig.guards == ["T1", "T2", "T4", "T6"]  # waits in Observe: intent is following
    assert reply.status == "following" and rig.engine.state == State.OBSERVE
    assert rig.power("lamp_corridor") == "off"

    rig.loc.move_to("corridor")
    assert rig.guards[4:] == ["T9", "T4", "T6"]
    assert rig.engine.trace[4].outcome == "zone_changed"
    assert rig.power("lamp_corridor") == "on"
    rig.loc.move_to("office")
    assert rig.power("lamp_office") == "on"
    assert len(rig.grounder.calls) == 1  # the intent was reused, only the plan revised

    rig.engine.close()
    assert rig.guards[-1] == "T8" and rig.engine.trace[-1].outcome == "session_closed"
    assert rig.engine.state == State.PERCEIVE


def test_a_new_request_ends_a_following_intent(rig):
    rig.engine.handle_request(WALK)
    rig.engine.handle_request("turn on the light")
    assert rig.guards == ["T1", "T2", "T4", "T6", "T8", "T1", "T2", "T4", "T6", "T8"]
    assert rig.engine.trace[4].outcome == "superseded_by_request"
    assert rig.engine.history == [WALK, "turn on the light"]


def test_zone_change_while_idle_triggers_nothing(rig):
    rig.loc.move_to("corridor")
    assert rig.engine.trace == []


def test_t10_retry_after_a_transient_failure(rig):
    rig.env.inject_failure("lamp_hallway", times=1)
    rig.engine.handle_request("turn on the light")
    assert rig.guards == ["T1", "T2", "T4", "T6", "T10", "T6", "T8"]
    assert rig.engine.trace[4].outcome.error == "device_failure"
    assert rig.power("lamp_hallway") == "on"


def test_t11_repeated_failures_end_in_recover(rig):
    rig.env.inject_failure("lamp_hallway", times=100)
    reply = rig.engine.handle_request("turn on the light")
    assert rig.guards == ["T1", "T2", "T4", "T6", "T10", "T6", "T10", "T6", "T11", "T12"]
    assert rig.engine.trace[8].outcome == "retry_limit_reached:device_failure"
    assert reply.status == "recovered" and rig.engine.state == State.PERCEIVE


@pytest.mark.parametrize("step_limit", [1, 2, 3, 8])
@pytest.mark.parametrize("retry_limit", [0, 1, 2, 5, 50])
def test_permanent_failure_always_terminates(step_limit, retry_limit):
    """Bounded loops: whatever the limits, a device that never works ends in Recover ->
    Perceive, after at most min(step_limit, retry_limit + 1) commands."""
    rig = Rig(config=EngineConfig(step_limit=step_limit, retry_limit=retry_limit))
    rig.env.inject_failure("lamp_hallway", times=10_000)
    rig.engine.handle_request("turn on the light")
    assert rig.engine.state == State.PERCEIVE
    assert rig.guards[-2:] in (["T7", "T12"], ["T11", "T12"])
    assert rig.guards.count("T6") == min(step_limit, retry_limit + 1)
    assert "T8" not in rig.guards


def test_following_intent_is_bounded_by_the_step_limit():
    rig = Rig(config=EngineConfig(step_limit=2))
    rig.engine.handle_request(WALK)
    rig.loc.move_to("corridor")
    rig.loc.move_to("office")  # third command would exceed the limit
    assert rig.guards[-2:] == ["T7", "T12"] and rig.engine.state == State.PERCEIVE
    assert rig.power("lamp_office") == "off"


def test_unbound_session_rejects_the_request(rig):
    rig.session.close()
    reply = rig.engine.handle_request("turn on the light")
    assert reply.status == "rejected" and rig.engine.trace == []


def test_every_row_t1_t12_is_reachable():
    fired = set()
    for zone, conf, text, fail, cfg in [
        ("hallway", 0.9, "turn on the light", 1, None),  # T1 T2 T4 T6 T10 T8
        ("hallway", 0.4, "turn on the light", 0, None),  # T3 T12
        ("storage", 0.9, "turn on the light", 0, None),  # T5
        ("hallway", 0.9, "turn on the light", 100, None),  # T11
        ("hallway", 0.9, "turn on all the lights", 0, EngineConfig(step_limit=1)),  # T9 T7
    ]:
        rig = Rig(zone=zone, confidence=conf, config=cfg)
        rig.env.inject_failure("lamp_hallway", times=fail)
        rig.engine.handle_request(text)
        fired |= set(rig.guards)
    rig = Rig()
    rig.engine.handle_request(WALK)
    rig.loc.move_to("corridor")  # T9 on zone change
    fired |= set(rig.guards)
    assert fired == {f"T{i}" for i in range(1, 13)}


def test_recorder_gets_one_valid_record_per_transition():
    got = []
    rig = Rig(recorder=got.append)
    rig.engine.handle_request(WALK)
    rig.loc.move_to("corridor")
    assert got == rig.engine.trace
    for i, t in enumerate(got, start=1):
        EventRecord.model_validate({"seq": i, "session": "s", **t.record_fields()})


def test_target_zone_acts_on_the_named_zone(rig):
    rig.engine.handle_request("turn on the kitchen light")  # said in the hallway
    assert rig.guards == ["T1", "T2", "T4", "T6", "T8"]
    assert rig.power("lamp_kitchen") == "on" and rig.power("lamp_hallway") == "off"


def test_target_zone_out_of_scope_is_rejected_by_the_engine(rig):
    rig.engine.handle_request("warm up the server room")  # grounder not trusted
    assert rig.guards == ["T1", "T3", "T12"]
    assert rig.engine.trace[1].outcome == "unsupported:out_of_scope"


def test_set_value_reaches_the_device(rig):
    rig.engine.handle_request("set the office thermostat to 22")  # said in the hallway
    assert rig.guards == ["T1", "T2", "T4", "T6", "T8"]
    token = rig.env.authenticate("person-agent")
    assert rig.env.device(token, "thermostat_office").state["setpoint"] == 22.0
