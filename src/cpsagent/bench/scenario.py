"""One run of a scripted path with the agent, wired as `cpsagent.demo_agent` wires it.

The person walks a path of the scenario; once Localization places them in the hallway
(confidence at least 0.6) they say REQUEST once. The environment's interpreter is whatever
the environment was built with (the keyword grounder in the regression tests and in the
harness: deterministic and free). At the end the engine is closed and then the
subscription, so the restorations made at closing are part of the run.

The run keeps two kinds of data:
  - the behaviour (`behaviour()`): every transition record, reply, zone change, trigger,
    restoration and the device states, with simulated times only. Two runs of the same
    path and seed on two environments must give the same behaviour;
  - wall-clock instants (`time.perf_counter_ns`) of the same events, for the harness.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import EventRecord
from cpsagent.engine import OrchestrationEngine, Reply, Transition
from cpsagent.environment import Neighbourhood, PositioningSignal, Restoration
from cpsagent.environment.mobility import MobilitySimulator
from cpsagent.interface import EnvironmentInterface
from cpsagent.localization import ZoneEstimator

AGENT = "person-agent"
REQUEST = "I want to walk in the light"
ASK_IN = "hallway"
ASK_CONFIDENCE = 0.6

now_ns = time.perf_counter_ns


def _signal_key(s: PositioningSignal) -> tuple:
    return (s.ref_subject, s.ref_zone, s.observed_at, s.rssi)


@dataclass
class ScenarioRun:
    path: str
    seed: int
    ticks: list[dict[str, Any]] = field(default_factory=list)
    transitions: list[dict[str, Any]] = field(default_factory=list)
    replies: list[dict[str, Any]] = field(default_factory=list)
    zone_events: list[dict[str, Any]] = field(default_factory=list)
    neighbourhoods: list[dict[str, Any]] = field(default_factory=list)
    restorations: list[dict[str, Any]] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)
    request: dict[str, Any] | None = None
    final_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    closed_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    started_ns: int = 0
    ended_ns: int = 0

    @property
    def commands(self) -> list[dict[str, Any]]:
        """Every invokeCommand the agent sent: the Act row that carries its result (the
        Plan -> Act row carries the same call before it is sent)."""
        return [t for t in self.transitions if t["record"]["action"] is not None
                and t["record"]["action"]["operation"] == "invokeCommand"
                and isinstance(t["record"]["outcome"], dict)]  # fmt: skip

    def behaviour(self) -> dict[str, Any]:
        """Everything but the wall-clock instants: what two stores must agree on."""

        def strip(rows):
            return [{k: v for k, v in r.items() if not k.endswith("_ns")} for r in rows]

        return {
            "path": self.path,
            "seed": self.seed,
            "request": strip([self.request])[0] if self.request else None,
            "records": [t["record"] for t in self.transitions],
            "replies": strip(self.replies),
            "zoneEvents": strip(self.zone_events),
            "neighbourhoods": strip(self.neighbourhoods),
            "restorations": strip(self.restorations),
            "forwardedSignals": sum(1 for s in self.signals if s["arrived_ns"] is not None),
            "finalStates": self.final_states,
            "closedStates": self.closed_states,
        }


def _record(t: Transition, session: str) -> dict[str, Any]:
    """The C4 record of a transition, as the Event Log serialises it (seq set later)."""
    return EventRecord.model_validate({"seq": 1, "session": session, **t.record_fields()}
                                      ).model_dump(mode="json", exclude={"seq"})  # fmt: skip


def run_scenario(
    env,
    path: str,
    *,
    seed: int = 0,
    request: str | None = REQUEST,
    states: Callable[[], dict[str, dict[str, Any]]] | None = None,
) -> ScenarioRun:
    """Walk `path` on `env` (an EnvironmentBackend that also takes `publish` from the
    mobility simulator). `states`: observer view of every device state; by default
    `env.device_states()`."""
    states = states or env.device_states
    script = env.scenario.paths[path]
    run = ScenarioRun(path, seed)
    run.started_ns = now_ns()
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, AGENT, script.subject)
    localization = ZoneEstimator(dict(session.known_adjacency), script.subject)
    session.on_neighbourhood(lambda n: localization.add_adjacency(n.adjacency))

    tick_index = [-1]
    published: dict[tuple, dict[str, Any]] = {}

    def arrived(signal: PositioningSignal) -> None:
        row = published.get(_signal_key(signal))
        if row is not None and row["arrived_ns"] is None:
            row["arrived_ns"] = now_ns()

    session.subscription.add_listener(arrived)
    session.subscription.add_listener(localization.on_signal)  # R13

    def on_neighbourhood(n: Neighbourhood) -> None:
        run.neighbourhoods.append(
            {"tick": tick_index[0], "zone": n.zone_id, "armed": n.armed, "wall_ns": now_ns()}
        )

    def on_restoration(r: Restoration) -> None:
        run.restorations.append({
            "tick": tick_index[0], "deviceId": r.device_id, "zoneId": r.zone_id,
            "state": r.state, "reason": r.reason,
            "time": r.time.isoformat() if r.time else None, "wall_ns": now_ns(),
        })  # fmt: skip

    session.on_neighbourhood(on_neighbourhood)
    session.on_restoration(on_restoration)
    localization.subscribe(
        lambda e: run.zone_events.append(
            {
                "tick": tick_index[0],
                "zone": e.estimate.zone_id,
                "previous": e.estimate.previous_zone_id,
                "wall_ns": now_ns(),
            }
        )  # fmt: skip
    )

    clock = [None]

    def record(t: Transition) -> None:
        run.transitions.append(
            {"tick": tick_index[0], "record": _record(t, session.session_id), "wall_ns": now_ns()}
        )

    def notify(r: Reply) -> None:
        run.replies.append(
            {"tick": tick_index[0], "status": r.status, "message": r.message, "wall_ns": now_ns()}
        )

    engine = OrchestrationEngine(
        session,
        localization,
        EnvironmentInterface(session),
        recorder=record,
        notify=notify,
        clock=lambda: clock[0],
    )

    asked = request is None
    for tick in MobilitySimulator(env.scenario, script, seed=seed).ticks():
        tick_index[0], clock[0] = tick.index, tick.time
        row = {"tick": tick.index, "time": tick.time.isoformat(), "trueZone": tick.true_zone,
               "start_ns": now_ns()}  # fmt: skip
        for signal in tick.signals:
            entry = {"tick": tick.index, "zone": signal.ref_zone, "published_ns": now_ns(),
                     "returned_ns": None, "arrived_ns": None}  # fmt: skip
            published[_signal_key(signal)] = entry
            run.signals.append(entry)
            env.publish(signal)  # -> environment -> subscription -> Localization -> engine
            entry["returned_ns"] = now_ns()
        row["end_ns"] = now_ns()
        run.ticks.append(row)
        estimate = localization.estimate()
        if not asked and estimate.zone_id == ASK_IN and estimate.confidence >= ASK_CONFIDENCE:
            run.request = {"tick": tick.index, "text": request, "start_ns": now_ns()}
            engine.handle_request(request)
            run.request["end_ns"] = now_ns()
            asked = True

    run.final_states = states()
    engine.close()
    session.close()
    run.closed_states = states()
    run.ended_ns = now_ns()
    return run


def command_outcomes(run: ScenarioRun) -> list[tuple[str, str, bool]]:
    """(deviceId, command, ok) of every command, in order."""
    out = []
    for t in run.commands:
        args = t["record"]["action"]["args"]
        out.append((args["deviceId"], args["command"], t["record"]["outcome"]["ok"]))
    return out


__all__ = ["REQUEST", "ScenarioRun", "command_outcomes", "run_scenario"]
