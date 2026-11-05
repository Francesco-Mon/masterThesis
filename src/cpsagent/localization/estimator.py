"""Localization (F2): zone estimate from raw positioning signals, with hysteresis.

Input  R13: `on_signal(PositioningSignal)`, one raw reading at a time.
Output R5:  `estimate()` -> ZoneEstimate (query).
       R6:  `subscribe(callback)` -> ZoneChangedEvent pushed when the zone changes.

Signals are grouped into scans: all readings with the same `observedAt` (one BLE scan of
the phone). The decision runs once per complete scan, so the order in which the readings
of one scan arrive does not matter. A scan is complete when a newer reading arrives or
when the estimate is queried.

Proximity rule: the zone whose beacon is (on average) strongest. Two mechanisms stop the
estimate from oscillating on a doorway:
  1. smoothing: each beacon's RSSI is an exponential moving average (alpha);
  2. hysteresis based on adjacency: the estimate moves to an *adjacent* zone only if that
     zone's beacon beats the current one by at least `margin_db`; it never jumps to a
     *non-adjacent* zone (physically impossible in one step) unless the current zone's
     beacon has not been heard for `stale_after_s` seconds (the track was lost).
"""

import math
from collections.abc import Callable
from datetime import datetime

from cpsagent.contracts import ZoneChangedEvent, ZoneEstimate
from cpsagent.environment import PositioningSignal

ZoneListener = Callable[[ZoneChangedEvent], None]


class ZoneEstimator:
    def __init__(
        self,
        adjacency: dict[str, list[str]],
        subject: str | None = None,
        *,
        alpha: float = 0.5,
        margin_db: float = 8.0,  # chosen by a sweep over 200 seeds, see DECISIONS.md
        stale_after_s: float = 3.0,
        confidence_scale_db: float = 5.0,
        floor_db: float = -100.0,
    ) -> None:
        self._adjacency = {z: set(adj) for z, adj in adjacency.items()}
        self._subject = subject
        self._alpha = alpha
        self._margin = margin_db
        self._stale_after = stale_after_s
        self._scale = confidence_scale_db
        self._floor = floor_db
        self._level: dict[str, float] = {}  # zone -> smoothed RSSI of its beacon
        self._last_seen: dict[str, datetime] = {}
        self._now: datetime | None = None
        self._zone: str | None = None
        self._previous: str | None = None
        self._listeners: list[ZoneListener] = []
        self._scan: list[PositioningSignal] = []  # readings of the scan in progress

    # --- R13 input ----------------------------------------------------------------------

    def on_signal(self, signal: PositioningSignal) -> None:
        if self._subject is not None and signal.ref_subject != self._subject:
            return
        if signal.ref_zone not in self._adjacency:  # not in the bound spatial model
            return
        if self._scan and signal.observed_at > self._scan[0].observed_at:
            self._close_scan()
        self._scan.append(signal)

    def _close_scan(self) -> None:
        if not self._scan:
            return
        scan, self._scan = self._scan, []
        t = scan[0].observed_at
        self._now = t if self._now is None else max(self._now, t)
        for signal in scan:
            zone = signal.ref_zone
            if zone in self._level and not self._is_stale(zone):
                self._level[zone] = (
                    self._alpha * signal.rssi + (1 - self._alpha) * self._level[zone]
                )
            else:
                self._level[zone] = signal.rssi
            self._last_seen[zone] = t
        self._update()

    def _is_stale(self, zone: str) -> bool:
        return (self._now - self._last_seen[zone]).total_seconds() > self._stale_after

    def _heard(self) -> dict[str, float]:
        return {z: lvl for z, lvl in self._level.items() if not self._is_stale(z)}

    def _update(self) -> None:
        heard = self._heard()
        # strongest beacon; ties broken by zone id so the result is deterministic
        best = max(sorted(heard), key=heard.__getitem__)
        if self._zone is None:
            self._move_to(best)
            return
        if best == self._zone:
            return
        current = heard.get(self._zone)  # None if the current beacon is no longer heard
        if best in self._adjacency[self._zone]:
            if current is None or heard[best] - current >= self._margin:
                self._move_to(best)
        elif current is None:
            self._move_to(best)  # track lost: accept a non-adjacent zone

    def _move_to(self, zone: str) -> None:
        self._previous, self._zone = self._zone, zone
        event = ZoneChangedEvent(estimate=self._current())
        for listener in list(self._listeners):
            listener(event)

    # --- R5 / R6 output -----------------------------------------------------------------

    def estimate(self) -> ZoneEstimate | None:
        """Current zone; None before the first signal.

        confidence = logistic(margin / scale), margin = smoothed RSSI of the current zone
        minus the strongest other beacon heard: 0.5 when they are equal (doorway), close
        to 1 when the user is clearly inside, below 0.5 while hysteresis holds the old zone.
        """
        self._close_scan()
        return self._current()

    def _current(self) -> ZoneEstimate | None:
        if self._zone is None:
            return None
        heard = self._heard()
        own = heard.get(self._zone, self._floor)
        others = [lvl for z, lvl in heard.items() if z != self._zone]
        margin = own - max(others, default=self._floor)
        confidence = 1.0 / (1.0 + math.exp(-margin / self._scale))
        return ZoneEstimate(
            zone_id=self._zone,
            confidence=round(confidence, 3),
            observed_at=self._now,
            previous_zone_id=self._previous,
        )

    def subscribe(self, listener: ZoneListener) -> None:
        self._listeners.append(listener)
