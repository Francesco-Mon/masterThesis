"""Interpretation is a service of the environment, reached through the bound session."""

from engine_rig import WALK, Rig

from cpsagent.environment import emulator


def test_interpretation_goes_through_the_session_and_the_environment_interpreter():
    rig = Rig()
    rig.engine.handle_request(WALK)
    request = rig.grounder.calls[0]
    assert request.text == WALK and request.zone.zone_id == "hallway"
    assert [z.zone_id for z in request.catalogue][:2] == ["lobby", "hallway"]  # env's own


def test_zone_outside_the_scope_is_refused_without_interpreting():
    rig = Rig(zone="server_room", previous="corridor")
    rig.engine.handle_request(WALK)
    assert rig.grounder.calls == []
    assert rig.guards == ["T1", "T3", "T12"]
    assert rig.engine.trace[1].outcome == "interpretation_refused:out_of_scope"
    assert rig.queries == []


def test_absent_property_is_refused_by_the_environment_with_the_same_record():
    rig = Rig()
    rig.engine.handle_request("make it humid")  # the interpreter hallucinates a property
    assert rig.guards == ["T1", "T3", "T12"]
    assert rig.engine.trace[1].outcome == "unsupported:capability_absent"
    assert rig.engine.trace[1].intent is None


def test_without_the_environment_check_an_absent_property_ends_in_t5(monkeypatch):
    """Defence in depth on the agent side, which has no catalogue: Plan asks listDevices,
    the answer is empty, no command."""
    monkeypatch.setattr(emulator, "checked", lambda result, context: result)
    rig = Rig()
    rig.engine.handle_request("make it humid")
    assert rig.guards == ["T1", "T2", "T5", "T12"]
    assert rig.engine.trace[2].outcome == "capability_absent"
    assert rig.queries == [("hallway", "humidity")]
