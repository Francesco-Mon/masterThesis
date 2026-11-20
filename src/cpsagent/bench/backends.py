"""Measurement harness: the same scenarios on the in-memory store or on Orion-LD.

Run: python -m cpsagent.bench.backends --store memory|ngsild [--repeats 30] [--warmup 2]
                                       [--seed 0] [--calls 10] [--url http://localhost:1026]
                                       [--out results/bench]

Each repeat runs four phases, each on a fresh environment (on Orion-LD the broker is
seeded again first, so every phase starts from the scenario's state):
  operations  the four operations of the Environment Interface and the interpretation
              request, `--calls` times each, as the agent sees them
  requests    a few requests to the engine, from text in to reply out, per state
  walk_in_the_light, doorway_linger
              a full run of the path with "I want to walk in the light" (scenario.py)

The interpreter is always the keyword grounder: deterministic, no network, no cost. The
ticks of a path are played one after the other, without waiting the tick's simulated
second: wall-clock delays measure processing, simulated delays are reported apart.

Output, in `<out>/<RUN_ID>/`: `events.jsonl`, one row per measured event (durations in
nanoseconds, `perf_counter_ns`), and `metadata.json` (store, broker and database versions,
Python, machine, seed, repeats, date, commit). Rows of warm-up repeats are kept, with
`"warmup": true`. The harness only measures: it plots nothing; at the end it prints the
median and 95th percentile of the main measures, warm-ups excluded.
"""

import argparse
import json
import platform
import statistics
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cpsagent.binding import EnvironmentBinding
from cpsagent.engine import OrchestrationEngine
from cpsagent.environment import EmulatedEnvironment, load_scenario
from cpsagent.environment.mobility import DEFAULT_START, MobilitySimulator
from cpsagent.grounding.keyword import KeywordGrounder
from cpsagent.interface import EnvironmentInterface
from cpsagent.localization import ZoneEstimator

from .scenario import AGENT, ScenarioRun, _signal_key, now_ns, run_scenario

ROOT = Path(__file__).resolve().parents[3]
PATHS = ("walk_in_the_light", "doorway_linger")
# Interface calls of the operations phase: the person is in the hallway.
OPERATIONS: list[tuple[str, dict[str, Any]]] = [
    ("listZones", {}),
    ("listDevices", {}),
    ("listDevices", {"zoneId": "hallway", "controlledProperty": "light"}),
    ("getDeviceState", {"deviceId": "lamp_hallway"}),
    ("invokeCommand", {"deviceId": "lamp_hallway", "command": "on"}),
    ("invokeCommand", {"deviceId": "lamp_hallway", "command": "off"}),
    ("listDevices", {"zoneId": "server_room"}),  # refused by the scope
]
# Requests of the interpretation and requests phases (keyword grounder).
REQUESTS = [
    "turn on the light",
    "it's too dark here",
    "turn off the light",
    "close the blinds",
    "play some music",
    "I want to walk in the light",
]
STORE_METHODS = ("building", "zones", "devices", "device", "write_state")


class TimedInterpreter:
    """The environment's interpreter, timed: `last_ns` is the duration of the last call."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.last_ns = 0

    def ground(self, request):
        start = now_ns()
        try:
            return self.inner.ground(request)
        finally:
            self.last_ns = now_ns() - start


class StoreProbe:
    """Counts and times the store calls the control logic makes (the broker's round trips
    on Orion-LD). Wraps the methods of one store object."""

    def __init__(self, store) -> None:
        self.calls: list[tuple[str, int]] = []
        for name in STORE_METHODS:
            setattr(store, name, self._timed(name, getattr(store, name)))

    def _timed(self, name: str, fn: Callable) -> Callable:
        def wrapped(*args, **kwargs):
            start = now_ns()
            try:
                return fn(*args, **kwargs)
            finally:
                self.calls.append((name, now_ns() - start))

        return wrapped

    def take(self) -> dict[str, Any]:
        calls, self.calls = self.calls, []
        return {"storeCalls": len(calls), "store_ns": sum(ns for _, ns in calls)}


# --- environments ----------------------------------------------------------------------


class Environments:
    """Fresh environments on the chosen store, each with a timed keyword interpreter."""

    def __init__(self, store: str, url: str) -> None:
        self.store, self.url = store, url
        self.scenario = load_scenario()

    def make(self):
        interpreter = TimedInterpreter(KeywordGrounder())
        if self.store == "memory":
            return EmulatedEnvironment(self.scenario, interpreter)
        from cpsagent.environment.ngsild import ngsild_environment
        from cpsagent.environment.ngsild.seed import seed

        seed(self.url, self.scenario)
        return ngsild_environment(self.url, interpreter, self.scenario)


def bind(env, subject: str = "user-1"):
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, AGENT, subject)
    localization = ZoneEstimator(dict(session.known_adjacency), subject)
    session.on_neighbourhood(lambda n: localization.add_adjacency(n.adjacency))
    session.subscription.add_listener(localization.on_signal)
    return session, localization


def place_in_hallway(env) -> None:
    """Play the first dwell of doorway_linger: the person stands in the hallway."""
    script = env.scenario.paths["doorway_linger"]
    for tick in MobilitySimulator(env.scenario, script).ticks():
        if tick.index >= script.segments[0].ticks:
            break
        for signal in tick.signals:
            env.publish(signal)


# --- phases ----------------------------------------------------------------------------


def operations_phase(env, calls: int) -> list[dict[str, Any]]:
    session, localization = bind(env)
    place_in_hallway(env)
    api = EnvironmentInterface(session)
    probe = StoreProbe(env.store)
    rows = []
    for k in range(calls):
        for operation, args in OPERATIONS:
            probe.take()
            start = now_ns()
            result = api.execute({"operation": operation, "args": args})
            latency = now_ns() - start
            rows.append(
                {
                    "measure": "operation",
                    "operation": operation,
                    "args": args,
                    "call": k,
                    "ok": result.ok,
                    "latency_ns": latency,
                    **probe.take(),
                }
            )
        zone = localization.estimate()
        for text in REQUESTS:
            probe.take()
            start = now_ns()
            result = session.interpret(text, "en", zone, [])
            latency = now_ns() - start
            interpreter_ns = env.interpreter.last_ns
            rows.append(
                {
                    "measure": "operation",
                    "operation": "interpret",
                    "args": {"text": text},
                    "call": k,
                    "ok": True,
                    "result": result.kind,
                    "latency_ns": latency,
                    "interpreter_ns": interpreter_ns,
                    "overhead_ns": latency - interpreter_ns,
                    **probe.take(),
                }
            )
    session.close()
    return rows


def _cycle_rows(kind: str, label: str, transitions, start: int, end: int, **extra):
    """One row for the whole cycle and one per state: the time spent in a state runs from
    the previous transition (or the start) to the transition that leaves it; `reply` is
    what follows the last transition until the reply to a request is out."""
    rows = [
        {
            "measure": "cycle",
            "kind": kind,
            "label": label,
            "total_ns": end - start,
            "transitions": len(transitions),
            **extra,
        }
    ]
    previous = start
    for t in transitions:
        rows.append(
            {
                "measure": "cycle_state",
                "kind": kind,
                "label": label,
                "state": t["record"]["from"],
                "guard": t["record"]["guard"],
                "ns": t["wall_ns"] - previous,
                **extra,
            }
        )
        previous = t["wall_ns"]
    if kind != "request":  # a zone change has no reply: the cycle ends at its last row
        return rows
    rows.append(
        {
            "measure": "cycle_state",
            "kind": kind,
            "label": label,
            "state": "reply",
            "guard": None,
            "ns": end - previous,
            **extra,
        }
    )
    return rows


def requests_phase(env) -> list[dict[str, Any]]:
    session, localization = bind(env)
    place_in_hallway(env)
    recorded: list[dict[str, Any]] = []
    engine = OrchestrationEngine(
        session,
        localization,
        EnvironmentInterface(session),
        recorder=lambda t: recorded.append(
            {"record": {"from": t.source.value, "guard": t.guard.value}, "wall_ns": now_ns()}
        ),
        clock=lambda: DEFAULT_START,
    )
    rows = []
    for text in REQUESTS:
        recorded.clear()
        start = now_ns()
        reply = engine.handle_request(text)
        end = now_ns()
        rows += _cycle_rows("request", text, list(recorded), start, end, status=reply.status)
    engine.close()
    session.close()
    return rows


def _lamps_by_zone(env) -> dict[str, str]:
    return {d.ref_zone: d.device_id for d in env.scenario.devices if d.category == "lamp"}


def scenario_rows(env, run: ScenarioRun, publishes: dict[tuple, tuple]) -> list[dict]:
    path = run.path
    ticks = {t["tick"]: t for t in run.ticks}
    rows = [
        {
            "measure": "scenario_run",
            "path": path,
            "total_ns": run.ended_ns - run.started_ns,
            "walk_ns": run.closing_ns - run.started_ns,
            "close_ns": run.ended_ns - run.closing_ns,
            "ticks": len(run.ticks),
            "signals": len(run.signals),
            "forwarded": sum(s["arrived_ns"] is not None for s in run.signals),
            "commands": len(run.commands),
            "restorations": len(run.restorations),
        }
    ]

    # positioning-signal delivery: publication -> the agent's Localization
    seen: set[str] = set()
    for s in run.signals:
        row = {
            "measure": "signal",
            "path": path,
            "tick": s["tick"],
            "zone": s["zone"],
            "firstReading": s["zone"] not in seen,
            "forwarded": s["arrived_ns"] is not None,
            "publish_ns": s["returned_ns"] - s["published_ns"],
            "delivery_ns": (
                s["arrived_ns"] - s["published_ns"] if s["arrived_ns"] is not None else None
            ),
        }
        seen.add(s["zone"])
        broker = publishes.get(s["key"])
        if broker is not None:  # Orion-LD: update answered, notification arrived
            sent, answered, notified = broker
            row["update_ns"] = answered - sent
            row["notification_ns"] = notified - answered
        rows.append(row)

    # triggers of the environment, from the publication of the signal that fired them
    for n in run.neighbourhoods:
        fired_by = next(
            (s for s in run.signals if s["published_ns"] <= n["wall_ns"] <= s["returned_ns"]), None
        )
        rows.append(
            {
                "measure": "trigger",
                "path": path,
                "tick": n["tick"],
                "zone": n["zone"],
                "ns": n["wall_ns"] - fired_by["published_ns"] if fired_by else None,
            }
        )

    # true zone change -> environment's trigger -> agent's estimate -> lamp on
    lamps = _lamps_by_zone(env)
    ok_commands = [t for t in run.commands if t["record"]["outcome"]["ok"]]
    for prev, cur in zip(run.ticks, run.ticks[1:], strict=False):
        if cur["trueZone"] == prev["trueZone"]:
            continue
        zone, t0 = cur["trueZone"], cur["start_ns"]
        trig = next(
            (n for n in run.neighbourhoods if n["zone"] == zone and n["wall_ns"] >= t0), None
        )
        est = next((e for e in run.zone_events if e["zone"] == zone and e["wall_ns"] >= t0), None)
        lamp = next(
            (
                t
                for t in ok_commands
                if t["wall_ns"] >= t0
                and t["record"]["action"]["args"]["deviceId"] == lamps.get(zone)
            ),
            None,
        )

        def delay(event, key="wall_ns", _t0=t0, _tick=cur["tick"]):
            if event is None:
                return {"ticks": None, "ns": None}
            return {"ticks": event["tick"] - _tick, "ns": event[key] - _t0}

        rows.append(
            {
                "measure": "zone_change",
                "path": path,
                "tick": cur["tick"],
                "from": prev["trueZone"],
                "to": zone,
                "trigger": delay(trig),
                "estimate": delay(est),
                "lampOn": delay(lamp),
            }
        )

    # cycles of the engine: the request, then each re-planning on a zone change
    if run.request is not None:
        r = run.request
        window = [t for t in run.transitions if r["start_ns"] <= t["wall_ns"] <= r["end_ns"]]
        rows += _cycle_rows("request", r["text"], window, r["start_ns"], r["end_ns"], path=path)
    events = run.zone_events
    for i, e in enumerate(events):
        stop = events[i + 1]["wall_ns"] if i + 1 < len(events) else run.closing_ns
        window = [
            t
            for t in run.transitions
            if e["wall_ns"] <= t["wall_ns"] < stop and t["tick"] == e["tick"]
        ]
        if window and not (
            run.request
            and window[0]["wall_ns"] >= run.request["start_ns"]
            and window[-1]["wall_ns"] <= run.request["end_ns"]
        ):
            rows += _cycle_rows(
                "zone_change", e["zone"], window, e["wall_ns"], window[-1]["wall_ns"], path=path
            )

    # restorations: simulated delay after the person left the zone, processing time
    for r in run.restorations:
        tick = ticks.get(r["tick"])
        row = {
            "measure": "restoration",
            "path": path,
            "deviceId": r["deviceId"],
            "zoneId": r["zoneId"],
            "reason": r["reason"],
            "tick": r["tick"],
        }
        if r["reason"] == "person_left_zone":
            left = [n for n in run.neighbourhoods if n["tick"] <= r["tick"]]
            out = next((n for n in reversed(left) if n["zone"] != r["zoneId"]), None)
            true_out = next(
                (t for t in reversed(run.ticks[: r["tick"] + 1]) if t["trueZone"] == r["zoneId"]),
                None,
            )
            row["afterEnvExitTicks"] = r["tick"] - out["tick"] if out else None
            row["afterTrueExitTicks"] = r["tick"] - true_out["tick"] - 1 if true_out else None
            row["ns"] = r["wall_ns"] - tick["start_ns"]  # within the tick that completed it
        else:
            row["ns"] = r["wall_ns"] - run.closing_ns  # from the start of the closing
        rows.append(row)
    return rows


def scenario_phase(env, path: str, seed: int) -> list[dict[str, Any]]:
    publishes: dict[tuple, tuple] = {}
    store = env.store
    if hasattr(store, "on_publish"):
        store.on_publish = lambda s, *t: publishes.__setitem__(_signal_key(s), t)
    return scenario_rows(env, run_scenario(env, path, seed=seed), publishes)


# --- run -------------------------------------------------------------------------------


def _command(*args: str) -> str | None:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=True, cwd=ROOT
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def metadata(args, run_id: str) -> dict[str, Any]:
    import httpx

    machine = {
        "system": platform.system(),
        "release": platform.release(),
        "macOS": platform.mac_ver()[0] or None,
        "machine": platform.machine(),
        "cpu": _command("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor(),
        "model": _command("sysctl", "-n", "hw.model"),
        "logicalCpus": _command("sysctl", "-n", "hw.logicalcpu"),
        "memoryBytes": _command("sysctl", "-n", "hw.memsize"),
    }
    meta = {
        "runId": run_id,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "store": args.store,
        "repeats": args.repeats,
        "warmup": args.warmup,
        "seed": args.seed,
        "calls": args.calls,
        "paths": list(PATHS),
        "interpreter": "keyword",
        "python": sys.version.split()[0],
        "httpx": httpx.__version__,
        "machine": machine,
        "commit": _command("git", "rev-parse", "HEAD"),
        "dirty": bool(_command("git", "status", "--porcelain", "--untracked-files=no")),
        "clock": "time.perf_counter_ns",
        "ticksPaced": False,
    }
    if args.store == "ngsild":
        version = httpx.get(f"{args.url}/ngsi-ld/ex/v1/version", timeout=5).json()
        meta["broker"] = {
            "url": args.url,
            "orionLd": version.get("Orion-LD version"),
            "mongodbServer": version.get("mongodb server version"),
            "mongoc": version.get("mongoc version"),
            "coreContext": version.get("Core Context"),
        }
    return meta


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * q // 100))
    return ordered[int(rank) - 1]


def summary(rows: list[dict[str, Any]]) -> list[tuple[str, int, float, float]]:
    """(measure, n, median ms, p95 ms) of the main measures, warm-ups excluded."""
    groups: dict[str, list[float]] = {}

    def add(name, ns):
        if ns is not None:
            groups.setdefault(name, []).append(ns / 1e6)

    for r in (r for r in rows if not r["warmup"]):
        m = r["measure"]
        if m == "operation":
            add(f"operation {r['operation']}", r["latency_ns"])
            if r["operation"] == "interpret":
                add("operation interpret: interpreter", r["interpreter_ns"])
                add("operation interpret: environment overhead", r["overhead_ns"])
        elif m == "signal" and r["forwarded"]:
            add("signal delivery (forwarded)", r["delivery_ns"])
        elif m == "signal":
            add("signal publish (not forwarded)", r["publish_ns"])
        elif m == "cycle":
            add(f"cycle {r['kind']} total", r["total_ns"])
        elif m == "cycle_state":
            add(f"cycle {r['kind']} state {r['state']}", r["ns"])
        elif m == "scenario_run":
            add(f"run {r['path']} total", r["total_ns"])
        elif m == "zone_change":
            for k in ("trigger", "estimate", "lampOn"):
                add(f"zone change -> {k}", r[k]["ns"])
        elif m == "restoration":
            add(f"restoration ({r['reason']})", r["ns"])
        elif m == "trigger":
            add("trigger from publication", r["ns"])
    return [
        (name, len(v), statistics.median(v), percentile(v, 95))
        for name, v in sorted(groups.items())
    ]


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", choices=["memory", "ngsild"], required=True)
    parser.add_argument("--repeats", type=int, default=30, help="measured repeats")
    parser.add_argument("--warmup", type=int, default=2, help="repeats run first, flagged")
    parser.add_argument("--seed", type=int, default=0, help="noise seed of the paths")
    parser.add_argument("--calls", type=int, default=10, help="calls per operation and repeat")
    parser.add_argument("--url", default="http://localhost:1026", help="Orion-LD (ngsild)")
    parser.add_argument("--out", default=str(ROOT / "results" / "bench"))
    args = parser.parse_args(argv)

    run_id = f"{args.store}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    out = Path(args.out) / run_id
    out.mkdir(parents=True, exist_ok=False)
    environments = Environments(args.store, args.url)
    meta = metadata(args, run_id)
    rows: list[dict[str, Any]] = []
    with open(out / "events.jsonl", "w", encoding="utf-8") as f:
        for i in range(args.warmup + args.repeats):
            warmup = i < args.warmup
            phases = [
                ("operations", lambda env: operations_phase(env, args.calls)),
                ("requests", requests_phase),
            ]
            phases += [(p, lambda env, p=p: scenario_phase(env, p, args.seed)) for p in PATHS]
            for phase, measure in phases:
                env = environments.make()
                try:
                    for row in measure(env):
                        row = {
                            "runId": run_id,
                            "store": args.store,
                            "repeat": i,
                            "warmup": warmup,
                            "phase": phase,
                            **row,
                        }
                        rows.append(row)
                        f.write(json.dumps(row) + "\n")
                finally:
                    env.close()
            print(f"repeat {i + 1}/{args.warmup + args.repeats}{' (warm-up)' if warmup else ''}")
    meta["rows"] = len(rows)
    (out / "metadata.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")

    print(f"\n{out}: {len(rows)} rows. Median and 95th percentile, ms, warm-ups excluded:")
    for name, n, median, p95 in summary(rows):
        print(f"  {name:<45} n={n:<6} median {median:9.3f}  p95 {p95:9.3f}")
    return out


if __name__ == "__main__":
    main()
