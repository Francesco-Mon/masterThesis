"""Mobility simulator: scripted path -> PositioningSignals via callback (R13)."""

from itertools import groupby

from cpsagent.environment import EmulatedEnvironment, PositioningSignal, load_scenario
from cpsagent.environment.mobility import RSSI_NEAR, MobilitySimulator


def dedup(seq):
    return [k for k, _ in groupby(seq)]


def test_walk_produces_expected_true_zone_sequence():
    sim = MobilitySimulator(load_scenario(), "walk_in_the_light")
    zones = [t.true_zone for t in sim.ticks()]
    assert dedup(zones) == ["lobby", "hallway", "corridor", "office"]
    # 4 + 6 + 6 + 4 dwell ticks + 3 transits of 4 ticks
    assert len(zones) == 20 + 3 * 4


def test_signals_are_delivered_by_callback_in_time_order():
    received: list[PositioningSignal] = []
    ticks = MobilitySimulator(load_scenario(), "walk_in_the_light").run(received.append)
    assert len(received) == sum(len(t.signals) for t in ticks)
    times = [s.observed_at for s in received]
    assert times == sorted(times)
    assert {s.ref_subject for s in received} == {"user-1"}


def test_only_own_and_adjacent_beacons_are_heard():
    s = load_scenario()
    adjacency = {z.zone_id: set(z.adjacency) for z in s.zones}
    for tick in MobilitySimulator(s, "walk_in_the_light").ticks():
        heard = {sig.ref_zone for sig in tick.signals}
        assert tick.true_zone in heard
        assert heard <= {tick.true_zone} | adjacency[tick.true_zone] | {
            z for h in heard for z in adjacency[h]
        }


def test_during_dwell_strongest_beacon_is_the_true_zone():
    sim = MobilitySimulator(load_scenario(), "walk_in_the_light", noise_db=0.0)
    for tick in sim.ticks():
        strongest = max(tick.signals, key=lambda sig: sig.rssi)
        if strongest.rssi == RSSI_NEAR:  # dwell tick
            assert strongest.ref_zone == tick.true_zone


def test_same_seed_same_signals_different_seed_different_noise():
    s = load_scenario()

    def rssi(seed):
        return [
            sig.rssi
            for t in MobilitySimulator(s, "walk_in_the_light", seed=seed).ticks()
            for sig in t.signals
        ]

    assert rssi(7) == rssi(7)
    assert rssi(7) != rssi(8)


def test_doorway_hears_both_zones_at_similar_level():
    sim = MobilitySimulator(load_scenario(), "doorway_linger", noise_db=0.0)
    doorway = [t for t in sim.ticks() if 4 <= t.index < 20]
    for tick in doorway:
        levels = {sig.ref_zone: sig.rssi for sig in tick.signals}
        assert levels["hallway"] == levels["corridor"]


def test_emulator_pushes_published_signals_to_matching_subscribers():
    env = EmulatedEnvironment()
    token = env.authenticate("person-agent")
    mine, other = [], []
    env.subscribe(token, "user-1", mine.append)
    sub = env.subscribe(token, "user-2", other.append)
    MobilitySimulator(env.scenario, "walk_in_the_light").run(env.publish)
    assert mine and not other
    env.unsubscribe(sub)
