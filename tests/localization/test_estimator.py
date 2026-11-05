"""Localization: ZoneEstimate (R5), zone_changed (R6), hysteresis."""

from datetime import UTC, datetime, timedelta

import pytest

from cpsagent.contracts import ZoneChangedEvent, ZoneEstimate
from cpsagent.environment import PositioningSignal, load_scenario
from cpsagent.environment.mobility import MobilitySimulator
from cpsagent.localization import ZoneEstimator

SCENARIO = load_scenario()
ADJACENCY = {z.zone_id: z.adjacency for z in SCENARIO.zones}
T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def run_path(path, seed=0, **params):
    """Feed a scripted path to an estimator; return (zone sequence from R6 events, estimator)."""
    est = ZoneEstimator(ADJACENCY, "user-1", **params)
    events: list[ZoneChangedEvent] = []
    est.subscribe(events.append)
    MobilitySimulator(SCENARIO, path, seed=seed).run(est.on_signal)
    return [e.estimate.zone_id for e in events], est, events


def sig(zone, rssi, second, subject="user-1"):
    return PositioningSignal(
        rssi=rssi, observed_at=T0 + timedelta(seconds=second), ref_zone=zone, ref_subject=subject
    )


@pytest.mark.parametrize("seed", range(20))
def test_scripted_walk_gives_expected_zone_sequence(seed):
    zones, _, _ = run_path("walk_in_the_light", seed=seed)
    assert zones == ["lobby", "hallway", "corridor", "office"]


def test_zone_changes_follow_the_true_change_with_small_lag():
    _, _, events = run_path("walk_in_the_light")
    ticks = list(MobilitySimulator(SCENARIO, "walk_in_the_light").ticks())
    true_change = {t.true_zone: t.time for t in reversed(ticks)}  # first tick in each zone
    for e in events[1:]:
        lag = (e.estimate.observed_at - true_change[e.estimate.zone_id]).total_seconds()
        assert 0 <= lag <= 3


@pytest.mark.parametrize("seed", range(20))
def test_hysteresis_prevents_ping_pong_on_doorway(seed):
    zones, _, _ = run_path("doorway_linger", seed=seed)
    assert zones == ["hallway"]


def test_without_hysteresis_the_doorway_oscillates():
    """Same signals, no smoothing and no margin: shows the test above is meaningful."""
    zones, _, _ = run_path("doorway_linger", alpha=1.0, margin_db=0.0)
    assert len(zones) > 4


def test_low_confidence_on_doorway_high_inside_zone():
    est = ZoneEstimator(ADJACENCY, "user-1")
    confidences = {}

    def record(signal):
        est.on_signal(signal)
        confidences[signal.observed_at] = est.estimate().confidence

    ticks = MobilitySimulator(SCENARIO, "doorway_linger").run(record)
    inside = [confidences[t.time] for t in ticks[:4]]
    doorway = [confidences[t.time] for t in ticks[8:20]]
    assert min(inside) > 0.9
    assert max(doorway) < 0.8  # below what an engine would trust without asking


def test_estimate_is_a_valid_c1_contract_with_previous_zone():
    _, est, events = run_path("walk_in_the_light")
    final = est.estimate()
    assert isinstance(final, ZoneEstimate)
    assert final.zone_id == "office" and final.previous_zone_id == "corridor"
    assert events[0].type == "zone_changed" and events[0].estimate.previous_zone_id is None
    ZoneChangedEvent.model_validate(events[-1].model_dump(mode="json"))


def test_no_estimate_before_any_signal():
    assert ZoneEstimator(ADJACENCY).estimate() is None


def test_never_jumps_to_non_adjacent_zone_while_current_is_heard():
    est = ZoneEstimator(ADJACENCY, "user-1")
    est.on_signal(sig("lobby", -60, 0))
    est.on_signal(sig("office", -40, 1))  # much stronger, but office is not adjacent to lobby
    assert est.estimate().zone_id == "lobby"


def test_jumps_to_non_adjacent_zone_when_current_track_is_lost():
    est = ZoneEstimator(ADJACENCY, "user-1", stale_after_s=3.0)
    est.on_signal(sig("lobby", -60, 0))
    est.on_signal(sig("office", -55, 5))  # lobby not heard for 5 s
    assert est.estimate().zone_id == "office"
    assert est.estimate().previous_zone_id == "lobby"


def test_ignores_other_subjects_and_unknown_zones():
    est = ZoneEstimator(ADJACENCY, "user-1")
    est.on_signal(sig("lobby", -50, 0, subject="user-2"))
    est.on_signal(sig("attic", -50, 0))
    assert est.estimate() is None
