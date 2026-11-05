"""Mobility simulator: a scripted user walk that emits PositioningSignals (R13 source).

Model (deliberately simple, zone level): every zone has one BLE beacon. At each tick
the user's phone hears
  - the beacon of the zone it is in at RSSI_NEAR,
  - the beacons of adjacent zones at RSSI_FAR (through walls/doors),
  - nothing from non-adjacent zones.
While walking from A to B (transitTicks ticks) the two beacons cross over linearly;
standing on a doorway, both are heard at the midpoint level. Gaussian noise with a fixed
seed is added to every reading, so runs are reproducible.
"""

import random
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .model import DwellSegment, PathScript, PositioningSignal, Scenario

RSSI_NEAR = -55.0  # dBm, beacon of the zone the user is in
RSSI_FAR = -80.0  # dBm, beacon of an adjacent zone
DEFAULT_START = datetime(2026, 11, 10, 9, 30, tzinfo=UTC)


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


@dataclass
class Tick:
    index: int
    time: datetime
    true_zone: str  # ground truth, for tests and evaluation only (never given to the agent)
    signals: list[PositioningSignal] = field(default_factory=list)


class MobilitySimulator:
    def __init__(
        self,
        scenario: Scenario,
        path: str | PathScript,
        *,
        seed: int = 0,
        noise_db: float = 3.0,
        start: datetime = DEFAULT_START,
        tick_seconds: float = 1.0,
    ) -> None:
        self.path = scenario.paths[path] if isinstance(path, str) else path
        self.subject = self.path.subject
        self._adjacency = {z.zone_id: set(z.adjacency) for z in scenario.zones}
        self._rng = random.Random(seed)
        self._noise_db = noise_db
        self._start = start
        self._dt = timedelta(seconds=tick_seconds)

    def _levels(self) -> Iterator[tuple[str, dict[str, float]]]:
        """Noise-free (true_zone, {zone: rssi of its beacon}) for every tick of the path."""
        previous: str | None = None
        for seg in self.path.segments:
            if isinstance(seg, DwellSegment):
                if previous is not None and previous != seg.zone:
                    yield from self._transit(previous, seg.zone)
                for _ in range(seg.ticks):
                    yield seg.zone, self._around({seg.zone: RSSI_NEAR})
                previous = seg.zone
            else:  # doorway: on the boundary, both beacons at the midpoint level
                a, b = seg.doorway
                mid = _lerp(RSSI_NEAR, RSSI_FAR, 0.5)
                for _ in range(seg.ticks):
                    yield a, self._around({a: mid, b: mid})

    def _transit(self, a: str, b: str) -> Iterator[tuple[str, dict[str, float]]]:
        n = self.path.transit_ticks
        for k in range(1, n + 1):
            f = k / (n + 1)
            levels = {a: _lerp(RSSI_NEAR, RSSI_FAR, f), b: _lerp(RSSI_FAR, RSSI_NEAR, f)}
            yield (a if f < 0.5 else b), self._around(levels)

    def _around(self, levels: dict[str, float]) -> dict[str, float]:
        """Add the adjacent beacons, heard at RSSI_FAR."""
        out = dict(levels)
        for zone in levels:
            for other in self._adjacency[zone]:
                out.setdefault(other, RSSI_FAR)
        return out

    def ticks(self) -> Iterator[Tick]:
        for i, (true_zone, levels) in enumerate(self._levels()):
            time = self._start + i * self._dt
            signals = [
                PositioningSignal(
                    rssi=round(rssi + self._rng.gauss(0.0, self._noise_db), 1),
                    observed_at=time,
                    ref_zone=zone,
                    ref_subject=self.subject,
                )
                for zone, rssi in sorted(levels.items())  # sorted: deterministic order
            ]
            yield Tick(i, time, true_zone, signals)

    def run(self, deliver: Callable[[PositioningSignal], None]) -> list[Tick]:
        """Deliver every signal through the callback (R13), in time order; return the ticks."""
        done = []
        for tick in self.ticks():
            for signal in tick.signals:
                deliver(signal)
            done.append(tick)
        return done
