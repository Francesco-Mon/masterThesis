import pytest

from cpsagent.contracts import State
from cpsagent.grounding import FakeGrounder
from cpsagent.ui.session import AgentSession, catalogue_queries, plan_status, result_summary

WALK = {
    "I want to walk in the light": {
        "kind": "intent",
        "intent": {
            "action": "activate",
            "controlledProperty": "light",
            "scope": "path",
            "persistence": "following",
            "confidence": 0.9,
        },  # fmt: skip
    }
}


@pytest.fixture
def agent(tmp_path):
    a = AgentSession(FakeGrounder(WALK), start_zone="hallway", log_dir=tmp_path)
    yield a
    a.close()


def test_starts_localized_in_the_start_zone(agent):
    assert agent.localization.estimate().zone_id == "hallway"
    assert agent.turns == [] and agent.verify().length == 0
    view = agent.environment_view()
    assert view["zone"] == "hallway" and view["armed"] == ["lobby", "corridor", "kitchen"]
    assert "server_room" not in view["scope"]


def test_route_follows_the_adjacency(agent):
    assert agent.route("lobby", "office") == ["lobby", "hallway", "corridor", "office"]
    assert agent.route("office", "office") == ["office"]


def test_following_request_replans_on_walk_without_grounding_again(agent):
    turn = agent.say("I want to walk in the light", "en")
    assert turn.reply.status == "following"
    assert result_summary(turn).startswith("intent: action=activate")
    assert [c.action.args.device_id for c in turn.commands] == ["lamp_hallway"]
    assert turn.plan.valid_for.zone_id == "hallway"
    assert catalogue_queries(turn)[0] == (
        "listDevices(zone=hallway, property=light) -> ['lamp_hallway']"
    )
    walk = agent.walk_to("office")
    assert [c.action.args.device_id for c in walk.commands] == ["lamp_corridor", "lamp_office"]
    assert "listDevices(zone=office, property=light) -> ['lamp_office']" in catalogue_queries(walk)
    assert all(t.source != State.INTERPRET for t in walk.transitions)  # no re-grounding
    assert len(agent.env.interpreter.calls) == 1
    report = agent.verify()
    assert report.ok and report.length == len(turn.transitions) + len(walk.transitions)


def test_empty_text_asks_to_repeat(agent):
    turn = agent.say("", "it")
    assert turn.reply.status == "recovered" and "Puoi ripetere" in turn.reply.message  # it
    assert result_summary(turn) == "no intent: request_unintelligible"


def test_scripted_path_is_played_tick_by_tick(agent):
    agent.load_path("walk_in_the_light")
    queued = agent.pending_ticks
    agent.advance("tick")
    assert agent.pending_ticks == queued - 1
    agent.advance("zone")
    agent.advance("end")
    assert agent.pending_ticks == 0
    assert agent.localization.estimate().zone_id == agent.position == "office"


def test_plan_status_marks_done_and_pending_steps(agent):
    turn = agent.say("I want to walk in the light", "en")
    status = {s.device_id: st for s, st in plan_status(turn)}
    assert status["lamp_hallway"] == "done"  # the guard holds now
    assert status["lamp_corridor"] == "pending"  # on entering the corridor
    assert len(status) == len(turn.plan.steps) > 1


def test_full_plan_is_kept_after_replanning(tmp_path):
    from cpsagent.grounding.keyword import KeywordGrounder

    a = AgentSession(KeywordGrounder(), log_dir=tmp_path)
    turn = a.say("spegni tutte le luci", "it")
    a.close()
    statuses = plan_status(turn)
    assert len(statuses) == len(turn.commands) > 1  # not only the last step left
    assert {st for _, st in statuses} == {"done"}


# --- management policy of the environment -------------------------------------------------


def test_devices_table_shows_the_default_state(agent):
    rows = {r["device"]: r for r in agent.devices()}
    assert rows["lamp_hallway"]["default"] == "power=off, brightness=0"
    assert rows["thermostat_office"]["default"] == "setpoint=21.0"


def test_environment_view_shows_the_policy_and_the_pending_restorations(agent):
    view = agent.environment_view()
    assert view["restoreOnExit"] and view["restoreAfterSeconds"] == 12
    assert view["pending"] == []
    agent.say("I want to walk in the light", "en")
    assert agent.environment_view()["pending"] == [
        {"device": "lamp_hallway", "zone": "hallway", "inSeconds": None}
    ]
    agent.walk_to("corridor")
    pending = {p["device"]: p for p in agent.environment_view()["pending"]}
    assert 0 < pending["lamp_hallway"]["inSeconds"] <= 12  # countdown running
    assert pending["lamp_corridor"]["inSeconds"] is None  # the person is there


def test_restoration_is_a_turn_of_its_own(agent):
    agent.say("I want to walk in the light", "en")
    agent.walk_to("corridor")
    assert [t.kind for t in agent.turns] == ["request", "movement"]
    agent.stay(12)
    restored = [t for t in agent.turns if t.kind == "restoration"]
    assert [t.text for t in restored] == [
        "Environment restored lamp_hallway to default (person left hallway)"
    ]
    assert restored[0].restoration.state == {"power": "off", "brightness": 0}
    assert restored[0].transitions == []  # no record: the engine did nothing
    rows = {r["device"]: r for r in agent.devices()}
    assert rows["lamp_hallway"]["power"] == "off" and rows["lamp_corridor"]["power"] == "on"


def test_closing_the_session_restores_what_the_agent_changed(tmp_path):
    a = AgentSession(FakeGrounder(WALK), start_zone="hallway", log_dir=tmp_path)
    a.say("I want to walk in the light", "en")
    a.close()
    assert a.turns[-1].text == "Environment restored lamp_hallway to default (session closed)"
    assert all(r["power"] == "off" for r in a.devices() if r["device"].startswith("lamp_"))
    assert a.verify().ok


# --- interpretation by the environment ----------------------------------------------------


def test_the_chosen_grounder_is_the_environment_interpreter(agent):
    assert agent.environment_view()["interpreter"] == "FakeGrounder"
    turn = agent.say("I want to walk in the light", "en")
    assert turn.interpreted == "Interpreted by the environment (interpreter: FakeGrounder)"
    assert agent.say("", "en").interpreted is None  # nothing was sent to the environment
