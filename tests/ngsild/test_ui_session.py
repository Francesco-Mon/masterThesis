"""A UI session on Orion-LD: the same turns as in memory, device states in the broker."""

import pytest

from cpsagent.grounding.keyword import KeywordGrounder
from cpsagent.ui.session import AgentSession

pytestmark = pytest.mark.ngsild


def walk(store, url, tmp_path):
    a = AgentSession(KeywordGrounder(), log_dir=tmp_path / store, store=store, url=url)
    a.say("I want to walk in the light", "en")
    a.walk_to("office")
    a.stay(15)
    view = a.environment_view()
    turns = [(t.kind, t.text, [r.guard for r in t.transitions]) for t in a.turns]
    devices = a.devices()
    a.close()
    assert a.verify().ok
    return view, turns, devices


def test_ui_session_on_orion_ld_is_the_same_as_in_memory(broker_url, tmp_path):
    view, turns, devices = walk("ngsild", broker_url, tmp_path)
    ref_view, ref_turns, ref_devices = walk("memory", None, tmp_path)
    assert view["store"] == f"Orion-LD at {broker_url}"
    assert ref_view["store"] == "in memory"
    assert turns == ref_turns and devices == ref_devices
    assert any(t[0] == "restoration" for t in turns)
