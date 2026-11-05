import pytest

from cpsagent.contracts import State
from cpsagent.grounding import FakeGrounder
from cpsagent.ui.session import AgentSession, plan_status, result_summary

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


def test_route_follows_the_adjacency(agent):
    assert agent.route("lobby", "office") == ["lobby", "hallway", "corridor", "office"]
    assert agent.route("office", "office") == ["office"]


def test_following_request_replans_on_walk_without_grounding_again(agent):
    turn = agent.say("I want to walk in the light", "en")
    assert turn.reply.status == "following"
    assert result_summary(turn).startswith("intent: action=activate")
    assert [c.action.args.device_id for c in turn.commands] == ["lamp_hallway"]
    assert turn.plan.valid_for.zone_id == "hallway"
    walk = agent.walk_to("office")
    assert [c.action.args.device_id for c in walk.commands] == ["lamp_corridor", "lamp_office"]
    assert all(t.source != State.INTERPRET for t in walk.transitions)  # no re-grounding
    assert len(agent.engine._grounder.calls) == 1
    report = agent.verify()
    assert report.ok and report.length == len(turn.transitions) + len(walk.transitions)


def test_empty_text_asks_to_repeat(agent):
    turn = agent.say("", "it")
    assert turn.reply.status == "recovered" and "say it again" in turn.reply.message
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
