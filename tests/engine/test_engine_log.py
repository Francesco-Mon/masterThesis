"""Engine-log integration: one record per transition (R16), without waiting for the log."""

import threading

from engine_rig import WALK, Rig

from cpsagent.engine import OrchestrationEngine
from cpsagent.environment.mobility import MobilitySimulator
from cpsagent.eventlog import EventLog, EventStore, verify
from cpsagent.interface import EnvironmentInterface
from cpsagent.localization import ZoneEstimator


class GatedStore(EventStore):
    """Writes block until the gate opens (a very slow disk)."""

    def __init__(self, path):
        super().__init__(path)
        self.gate = threading.Event()

    def append(self, line):
        assert self.gate.wait(timeout=5), "gate never opened"
        super().append(line)


def logged_rig(store):
    rig = Rig(recorder=lambda t: log.submit(t.record_fields()))
    log = EventLog(store, rig.session.session_id)
    return rig, log


def run_session(rig):
    """A session touching most rows: walk, environment request with failures, clarification."""
    rig.engine.handle_request(WALK)
    rig.loc.move_to("corridor")
    rig.loc.move_to("office")
    rig.env.inject_failure("lamp_lobby", times=5)
    rig.engine.handle_request("turn on all the lights")  # T8 superseded, retries, T11
    rig.engine.handle_request("do the thing")  # T3 clarification
    rig.engine.close()


def test_complete_session_chain_verifies(tmp_path):
    store = EventStore(tmp_path / "log.jsonl")
    rig, log = logged_rig(store)
    with log:
        run_session(rig)
    assert not log.errors
    report = verify(store, rig.session.session_id)
    assert report.ok and report.length == len(rig.engine.trace)
    records = [line["record"] for line in store.lines()]
    assert [r["guard"] for r in records] == rig.guards  # exactly one record per transition
    assert {"T1", "T2", "T3", "T4", "T6", "T8", "T9", "T10", "T11", "T12"} <= set(rig.guards)
    # the intent of the walk is the same object in every record until it ends (T8)
    walk = records[1 : rig.guards.index("T8") + 1]
    assert all(r["intent"] == walk[0]["intent"] for r in walk) and walk[0]["intent"]


def test_erasure_inside_a_real_session_keeps_the_chain_valid(tmp_path):
    store = EventStore(tmp_path / "log.jsonl")
    rig, log = logged_rig(store)
    with log:
        run_session(rig)
    store.erase(2)  # e.g. the user asks to delete the record holding their intent
    report = verify(store, rig.session.session_id)
    assert report.ok and report.erased == [2]


def test_engine_does_not_wait_for_the_log(tmp_path):
    store = GatedStore(tmp_path / "log.jsonl")
    rig, log = logged_rig(store)
    run_session(rig)  # would dead-lock (assert after 5 s) if a transition waited
    assert len(rig.engine.trace) > 20 and store.lines() == []
    store.gate.set()
    log.close()
    assert verify(store, rig.session.session_id).length == len(rig.engine.trace)


def test_walk_with_real_localization_is_logged_and_verifies(tmp_path):
    rig = Rig()
    estimator = ZoneEstimator(rig.session.spatial_model.adjacency, "user-1")
    rig.session.subscription.add_listener(estimator.on_signal)
    path = rig.env.scenario.paths["walk_in_the_light"]
    store = EventStore(tmp_path / "log.jsonl")
    log = EventLog(store, rig.session.session_id)
    engine = OrchestrationEngine(
        rig.session,
        estimator,
        rig.grounder,
        EnvironmentInterface(rig.session),
        recorder=lambda t: log.submit(t.record_fields()),
    )
    asked = False
    for tick in MobilitySimulator(rig.env.scenario, path, seed=0).ticks():
        for s in tick.signals:
            rig.env.publish(s)
        if not asked and tick.true_zone == "hallway" and estimator.estimate().zone_id == "hallway":
            engine.handle_request(WALK)
            asked = True
    engine.close()
    log.close()
    assert [rig.power(d) for d in ("lamp_hallway", "lamp_corridor", "lamp_office")] == ["on"] * 3
    assert len(rig.grounder.calls) == 1
    assert verify(store, rig.session.session_id).length == len(engine.trace)
    assert verify(store, rig.session.session_id).ok
