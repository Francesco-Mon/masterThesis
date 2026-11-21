"""Load harness: N persons, each with its own agent, on one shared environment.

Run (closed loop, a sweep over N):
  python -m cpsagent.bench.load --store memory|ngsild --interpreter keyword|embedding \
      --mode closed --persons 1,2,5,10 [--think 1.0] [--pace 1.0] [--min-duration 60] \
      [--min-requests 400] [--max-duration 450] [--warmup 10] [--seed 0] [--out results/load]
Run (open loop, a sweep over the total request rate at one N):
  python -m cpsagent.bench.load --store memory --interpreter keyword --mode open \
      --persons 10 --rates 2,5,10,20 [--duration 60]
Options: --tracemalloc (memory by component; slows everything down, for memory runs only),
  --requests-per-client K (closed loop: each client stops after K requests),
  --stop-on-fail (skip the larger N of a sweep after a failed point), --url (Orion-LD),
  --interpreter llm --model M [--provider P] [--no-cache] [--max-cost USD].

What runs. One environment (one control logic, one entity store, one interpreter) and N
persons. Each person has its own agent stack, as on its own device: its own agent id in the
scenario (built here from the scenario's `person-agent`, same scope; data/scenario.yaml is
not edited), token and subject, Environment Binding, Localization, Orchestration Engine,
Environment Interface and Event Log (a file per person). Each person walks its own seeded
random route along the adjacency of the zones of the scope, with its own mobility
simulator, at `--pace` ticks per wall-clock second (one tick is one simulated second of the
simulator); the persons' ticks are spread evenly over the tick period. Each person sends
requests drawn from data/load/requests.jsonl with its own seeded generator: in the closed
loop the next request goes after the reply and an exponential think time; in the open loop
requests arrive as a Poisson process at the given rate, and a request that arrives while
the previous one is still being handled waits (its latency counts from its arrival).

Concurrency. Every person runs two threads: its walker (positioning signals) and its
client (requests). The environment has no concurrency control for intents and none is
added. Only what is not safe to call from several threads is serialized, and exactly this:
  - one lock for the environment's shared state (`SharedEnvironment.lock`): every call of
    the control logic that reads or writes its tables or the store's device states
    (authenticate, follow, subscribe, unsubscribe, zones, devices, device, execute) and the
    handling of a positioning signal (publish: triggers, policy, delivery to the person's
    agent). On Orion-LD this also serializes `NgsiLdStore.publish`, whose single
    notification queue cannot be shared by two publishers;
  - one lock for the interpreter (`SharedInterpreter.lock`): the interpreter is called one
    request at a time (the embedding model's tokenizer and the LLM client's rate limiter
    and spending counter are not thread-safe). Interpretation itself does not take the
    environment lock: building the catalogue reads the store, and checking the answer is
    pure, so interpretations wait only for one another;
  - one lock per person (`Person.lock`): the agent handles one event at a time, as the
    engine is written to (a request, or a tick of positioning signals with what it
    triggers); a tick that comes while the person's request is being handled waits.
Lock order is always person, then environment, then interpreter, so there is no deadlock.

Recorded. Per request (requests.jsonl.gz): end-to-end latency (text in, reply out; in the
open loop from the arrival), the wait for the person's own agent, the interpretations with
their wait for the interpreter and their service time, every environment operation with
its wait for the environment lock and its service time, the reply, the commands and their
results, and the CPU time of the request's thread by section (accounting.py). Per tick and
person (ticks.jsonl.gz): delay against the schedule, signals, publication time, operations
and CPU by section. Per point (point.json): throughput, errors, latency percentiles, CPU
per request and per signal by side, memory (process resident memory sampled every second,
per-person and environment structures, optionally tracemalloc by component), the
environment's tables (follows, armed triggers, change records, pending restorations), on
Orion-LD the containers' CPU and memory, and the conflicts: two persons commanding the same
device within `--conflict-window` seconds (both commands and the state left), and every
restoration of the policy on a device in a zone where another person still is. Conflicts
are recorded, not resolved.

A point fails when more than 1% of its requests raise an error, when the 95th percentile of
the ticks' delay exceeds 10 s (the walk can no longer keep the pace), or when a closed-loop
point cannot reach --min-requests within --max-duration.
"""

import argparse
import csv
import gzip
import json
import random
import shutil
import sys
import tempfile
import threading
import time
import tracemalloc
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import ToolResult
from cpsagent.engine import OrchestrationEngine
from cpsagent.environment import EmulatedEnvironment, load_scenario
from cpsagent.environment.mobility import DEFAULT_START, MobilitySimulator
from cpsagent.environment.model import AgentPolicy, PathScript, Scenario
from cpsagent.eventlog import EventLog, EventStore
from cpsagent.interface import EnvironmentInterface
from cpsagent.localization import ZoneEstimator

from . import meta as runmeta
from .accounting import (
    CpuAccount,
    RssSampler,
    deep_size,
    delta,
    max_rss_bytes,
    process_cpu_ns,
    tracemalloc_by_component,
)

now_ns = time.perf_counter_ns
MIX = runmeta.ROOT / "data" / "load" / "requests.jsonl"
MIX_META = runmeta.ROOT / "data" / "load" / "metadata.json"
BASE_AGENT = "person-agent"
TRANSIT_TICKS = 4
DWELL = (8, 30)  # ticks spent in each zone of the random route
STORE_METHODS = ("building", "zones", "devices", "device", "write_state", "publish")
LAG_FAIL_S = 10.0
ERROR_FAIL = 0.01


# --- what the threads record ---------------------------------------------------------


class Collector:
    """Environment operations and interpretations made on the current thread since the
    last `reset` (one request, or one tick)."""

    def __init__(self) -> None:
        self._local = threading.local()

    def reset(self) -> None:
        self._local.ops = defaultdict(lambda: [0, 0, 0])  # op -> [calls, wait, service]
        self._local.interp = []  # [wait, service] per interpretation
        self._local.store = defaultdict(int)

    def _get(self, name):
        if not hasattr(self._local, "ops"):
            self.reset()
        return getattr(self._local, name)

    def op(self, name: str, wait: int, service: int) -> None:
        row = self._get("ops")[name]
        row[0] += 1
        row[1] += wait
        row[2] += service

    def interp(self, wait: int, service: int) -> None:
        self._get("interp").append([wait, service])

    def store_call(self, name: str) -> None:
        self._get("store")[name] += 1

    def take(self) -> dict[str, Any]:
        return {
            "ops": {k: v for k, v in self._get("ops").items()},
            "interp": list(self._get("interp")),
            "store": dict(self._get("store")),
        }


class SharedInterpreter:
    """The environment's interpreter, unchanged, called one request at a time."""

    def __init__(self, inner, account: CpuAccount, collector: Collector) -> None:
        self.inner, self.account, self.collector = inner, account, collector
        self.lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def ground(self, request):
        t0 = now_ns()
        with self.lock:
            t1 = now_ns()
            with self.account.section("env.interpreter"):
                result = self.inner.ground(request)
            t2 = now_ns()
        self.collector.interp(t1 - t0, t2 - t1)
        return result


class SharedEnvironment:
    """The one environment, as every agent reaches it: its EnvironmentBackend methods
    behind the environment lock (except `interpret`, see the module docstring), timed and
    charged to `env.control`; the callbacks it makes into an agent charged to the agent."""

    def __init__(self, env, account: CpuAccount, collector: Collector) -> None:
        self.env, self.account, self.collector = env, account, collector
        self.lock = threading.RLock()
        self.endpoint = env.endpoint
        self.scenario = env.scenario

    def _locked(self, op: str, fn, *args):
        t0 = now_ns()
        with self.lock:
            t1 = now_ns()
            try:
                with self.account.section("env.control"):
                    return fn(*args)
            finally:
                self.collector.op(op, t1 - t0, now_ns() - t1)

    def authenticate(self, agent_id):
        return self._locked("authenticate", self.env.authenticate, agent_id)

    def scope(self, token):
        return self._locked("scope", self.env.scope, token)

    def follow(self, token, subject, on_change, on_restore=None):
        on_change = self.account.wrap("agent.binding", on_change)
        if on_restore is not None:
            on_restore = self.account.wrap("agent.binding", on_restore)
        return self._locked("follow", self.env.follow, token, subject, on_change, on_restore)

    def zones(self, token):
        return self._locked("zones", self.env.zones, token)

    def devices(self, token, zone_id=None, controlled_property=None):
        return self._locked("devices", self.env.devices, token, zone_id, controlled_property)

    def device(self, token, device_id):
        return self._locked("device", self.env.device, token, device_id)

    def execute(self, token, device_id, command, value):
        return self._locked("execute", self.env.execute, token, device_id, command, value)

    def subscribe(self, token, subject, callback):
        callback = self.account.wrap("agent.binding", callback)
        return self._locked("subscribe", self.env.subscribe, token, subject, callback)

    def unsubscribe(self, sub_id):
        return self._locked("unsubscribe", self.env.unsubscribe, sub_id)

    def publish(self, signal):
        return self._locked("publish", self.env.publish, signal)

    def interpret(self, token, text, language, zone_estimate, history):
        t0 = now_ns()
        try:
            with self.account.section("env.control"):
                return self.env.interpret(token, text, language, zone_estimate, history)
        finally:
            self.collector.op("interpret", 0, now_ns() - t0)

    def device_states(self):
        with self.lock:
            return self.env.device_states()


def _store_call(name: str, fn, collector: Collector):
    def timed(*args, **kwargs):
        collector.store_call(name)
        return fn(*args, **kwargs)

    return timed


def probe_store(store, account: CpuAccount, collector: Collector) -> None:
    """Charge the store's own work to `env.store`, and the control logic it calls back
    (the signal sink) to `env.control`; count the store calls."""
    for name in STORE_METHODS:
        fn = getattr(store, name)

        setattr(store, name, _store_call(name, account.wrap("env.store", fn), collector))
    store._sinks[:] = [account.wrap("env.control", s) for s in store._sinks]


class LocalizationView:
    """The person's Localization as its engine sees it, with the engine's listener charged
    to the engine and the estimate to Localization."""

    def __init__(self, inner: ZoneEstimator, account: CpuAccount) -> None:
        self.inner, self.account = inner, account

    def estimate(self):
        with self.account.section("agent.localization"):
            return self.inner.estimate()

    def subscribe(self, listener) -> None:
        self.inner.subscribe(self.account.wrap("agent.engine", listener))


class InterfaceView:
    def __init__(self, inner: EnvironmentInterface, account: CpuAccount) -> None:
        self.inner, self.account = inner, account

    def execute(self, call):
        with self.account.section("agent.interface"):
            return self.inner.execute(call)


# --- scenario and persons ------------------------------------------------------------


def scenario_for(n: int) -> Scenario:
    """The reference scenario with agents person-agent-1..n, each with the scope of
    `person-agent` (built in memory; the scenario file is not changed)."""
    scenario = load_scenario()
    scope = list(scenario.broker.agents[BASE_AGENT].scope_zones)
    for i in range(1, n + 1):
        scenario.broker.agents[f"{BASE_AGENT}-{i}"] = AgentPolicy(scope_zones=scope)
    return scenario


def random_route(scenario: Scenario, rng: random.Random, ticks: int, subject: str) -> PathScript:
    """A walk along the adjacency, inside the scope, at least `ticks` ticks long."""
    scope = set(scenario.broker.agents[BASE_AGENT].scope_zones)
    adjacency = {z.zone_id: [a for a in z.adjacency if a in scope] for z in scenario.zones}
    zone = rng.choice(sorted(scope))
    segments, total = [], 0
    while total < ticks:
        dwell = rng.randint(*DWELL)
        segments.append({"zone": zone, "ticks": dwell})
        total += dwell + TRANSIT_TICKS
        zone = rng.choice(sorted(adjacency[zone]))
    return PathScript.model_validate(
        {"subject": subject, "transitTicks": TRANSIT_TICKS, "segments": segments}
    )


def _command_value(v):
    return None if v is None else float(v)


class Person:
    def __init__(self, i: int, harness: "Point") -> None:
        self.i = i
        self.h = harness
        account = harness.account
        self.agent_id = f"{BASE_AGENT}-{i}"
        self.subject = f"user-{i}"
        self.lock = threading.Lock()
        self.now = DEFAULT_START
        self.tick = -1
        self.true_zone: str | None = None
        self.rng = random.Random(f"{harness.seed}-requests-{i}")
        self.route = random_route(
            harness.scenario, random.Random(f"{harness.seed}-route-{i}"), harness.route_ticks,
            self.subject,
        )  # fmt: skip
        with account.section("agent.binding"):
            self.session = EnvironmentBinding({harness.shared.endpoint: harness.shared}).bind(
                harness.shared.endpoint, self.agent_id, self.subject
            )
        self.localization = ZoneEstimator(dict(self.session.known_adjacency), self.subject)
        self.session.on_neighbourhood(lambda n: self.localization.add_adjacency(n.adjacency))
        self.session.subscription.add_listener(
            account.wrap("agent.localization", self.localization.on_signal)
        )
        self.session.on_restoration(self._restored)
        self.store = EventStore(harness.log_dir / f"person-{i:03d}.jsonl")
        self.log = EventLog(self.store, f"{self.session.session_id}-p{i:03d}")
        self.log._write = account.wrap("agent.eventlog.writer", self.log._write)  # its thread
        self.records = 0
        self.transitions: list = []
        self.interface = EnvironmentInterface(self.session)
        self.engine = OrchestrationEngine(
            self.session,
            LocalizationView(self.localization, account),
            InterfaceView(self.interface, account),
            recorder=account.wrap("agent.eventlog", self._record),
            clock=lambda: self.now,
        )
        self.sent = 0

    def _record(self, t) -> None:
        self.transitions.append(t)
        self.records += 1
        self.log.submit(t.record_fields())
        if (
            t.action is not None
            and t.action.operation == "invokeCommand"
            and isinstance(t.outcome, ToolResult)
        ):
            a = t.action.args
            self.h.commands.append({
                "wall_ns": now_ns() - self.h.t0, "sim": self.now.isoformat(), "person": self.i,
                "tick": self.tick, "deviceId": a.device_id, "command": a.command,
                "value": _command_value(a.value), "ok": t.outcome.ok, "error": t.outcome.error,
                "state": t.outcome.state, "trueZone": self.true_zone,
            })  # fmt: skip

    def _restored(self, r) -> None:
        self.h.on_restoration(self, r)

    # --- threads ---------------------------------------------------------------------

    def walk(self) -> None:
        h = self.h
        h.account.enter("harness")
        phase = (self.i - 1) / (h.n * h.pace)  # spread the persons over the tick period
        try:
            sim = MobilitySimulator(h.scenario, self.route, seed=h.seed * 1000 + self.i)
            for tick in sim.ticks():
                due = h.t0 + int((phase + tick.index / h.pace) * 1e9)
                wait = (due - now_ns()) / 1e9
                if wait > 0 and h.stop.wait(wait):
                    break
                if h.stop.is_set():
                    break
                w0 = now_ns()
                with self.lock:
                    w1 = now_ns()
                    self.now, self.true_zone, self.tick = tick.time, tick.true_zone, tick.index
                    h.collector.reset()
                    cpu0 = h.account.snapshot()
                    error = None
                    for signal in tick.signals:
                        try:
                            h.shared.publish(signal)
                        except Exception as exc:  # recorded, the walk goes on
                            error = f"{type(exc).__name__}: {exc}"[:200]
                    w2 = now_ns()
                    cpu = delta(h.account.snapshot(), cpu0)
                    taken = h.collector.take()
                h.ticks.append({
                    "p": self.i, "tick": tick.index, "t_ns": w0 - h.t0, "lag_ns": w0 - due,
                    "agentWait_ns": w1 - w0, "signals": len(tick.signals),
                    "publish_ns": w2 - w1, "trueZone": tick.true_zone, "cpu": cpu,
                    "ops": taken["ops"], "store": taken["store"], "error": error,
                })  # fmt: skip
        finally:
            h.account.exit()

    def client(self) -> None:
        h = self.h
        h.account.enter("harness")
        try:
            start = h.t0 + int(h.client_start_s * 1e9)
            if h.stop.wait(max(0.0, (start - now_ns()) / 1e9)):
                return
            if h.mode == "closed":
                while not h.stop.is_set():
                    if h.per_client and self.sent >= h.per_client:
                        return
                    if h.stop.wait(self.rng.expovariate(1.0 / h.think)):
                        return
                    self._request(None)
            else:
                rate = h.rate / h.n
                arrival = start
                while True:
                    arrival += int(self.rng.expovariate(rate) * 1e9)
                    wait = (arrival - now_ns()) / 1e9
                    if wait > 0 and h.stop.wait(wait):
                        return
                    if h.stop.is_set():
                        return
                    self._request(arrival)
        finally:
            h.account.exit()

    def _request(self, arrival: int | None) -> None:
        h = self.h
        req = h.mix[self.rng.randrange(len(h.mix))]
        self.sent += 1
        t_in = now_ns()
        with self.lock:
            t_lock = now_ns()
            h.collector.reset()
            self.transitions = []
            cpu0 = h.account.snapshot()
            error, reply = None, None
            try:
                with h.account.section("agent.engine"):
                    reply = self.engine.handle_request(req["text"], req["language"])
            except Exception as exc:  # recorded, the client goes on
                error = f"{type(exc).__name__}: {exc}"[:200]
            t_out = now_ns()
            cpu = delta(h.account.snapshot(), cpu0)
            taken = h.collector.take()
            transitions = self.transitions
            parts = self.engine.last_parts
            estimate = self.localization.estimate()
            tick, true_zone = self.tick, self.true_zone
        commands = [
            [t.action.args.device_id, t.action.args.command, _command_value(t.action.args.value),
             t.outcome.ok]
            for t in transitions
            if t.action is not None and t.action.operation == "invokeCommand"
            and isinstance(t.outcome, ToolResult)
        ]  # fmt: skip
        interpret = next((t for t in transitions if t.source.value == "Interpret"), None)
        start = arrival if arrival is not None else t_in
        h.requests.append({
            "p": self.i, "n": self.sent, "req": req["id"], "kind": req["kind"],
            "send_ns": t_in - h.t0, "arrival_ns": None if arrival is None else arrival - h.t0,
            "warmup": (start - h.t0) < h.warmup_ns,
            "latency_ns": t_out - start, "queue_ns": t_in - start, "agentWait_ns": t_lock - t_in,
            "service_ns": t_out - t_lock,
            "status": reply.status if reply else None, "error": error,
            "interpretOutcome": None if interpret is None else (
                interpret.outcome if isinstance(interpret.outcome, str) else "intent"),
            "split": parts is not None, "parts": None if parts is None else len(parts),
            "transitions": len(transitions), "commands": commands,
            "estZone": estimate.zone_id if estimate else None,
            "estConfidence": round(estimate.confidence, 3) if estimate else None,
            "trueZone": true_zone, "tick": tick, "cpu": cpu,
            "ops": taken["ops"], "interp": taken["interp"], "store": taken["store"],
        })  # fmt: skip


# --- one point of a sweep --------------------------------------------------------------


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * q // 100))
    return ordered[int(rank) - 1]


def dist_ms(values_ns: list[int]) -> dict[str, float | int | None]:
    ms = [v / 1e6 for v in values_ns]
    out: dict[str, float | int | None] = {"n": len(ms)}
    for q in (50, 90, 95, 99):
        p = percentile(ms, q)
        out[f"p{q}"] = None if p is None else round(p, 3)
    out["max"] = round(max(ms), 3) if ms else None
    out["mean"] = round(sum(ms) / len(ms), 3) if ms else None
    return out


def side(cpu: dict[str, int], prefix: str) -> int:
    return sum(v for k, v in cpu.items() if k.startswith(prefix))


class Point:
    def __init__(self, args, n: int, rate: float | None, interpreter, label: str) -> None:
        self.args = args
        self.n, self.rate, self.label = n, rate, label
        self.mode = args.mode
        self.pace, self.think, self.seed = args.pace, args.think, args.seed
        self.per_client = args.requests_per_client
        self.client_start_s = args.client_start
        self.warmup_ns = int(args.warmup * 1e9)
        self.route_ticks = int((args.max_duration + 60) * args.pace) + 60
        self.mix = [json.loads(x) for x in MIX.read_text(encoding="utf-8").splitlines()]
        self.account = CpuAccount()
        self.collector = Collector()
        self.scenario = scenario_for(n)
        self.stop = threading.Event()
        self.requests: list[dict[str, Any]] = []
        self.ticks: list[dict[str, Any]] = []
        self.commands: list[dict[str, Any]] = []
        self.restorations: list[dict[str, Any]] = []
        self.interpreter = SharedInterpreter(interpreter, self.account, self.collector)
        self.log_dir = Path(tempfile.mkdtemp(prefix="cpsagent-load-"))
        self.t0 = now_ns()
        self.closing = False

    def make_environment(self):
        if self.args.store == "memory":
            return EmulatedEnvironment(self.scenario, self.interpreter)
        from cpsagent.environment.ngsild import ngsild_environment
        from cpsagent.environment.ngsild.seed import seed

        seed(self.args.url, self.scenario)
        return ngsild_environment(self.args.url, self.interpreter, self.scenario)

    def on_restoration(self, owner: Person, r) -> None:
        """Called by the environment (under its lock) for each restoration it makes."""
        follows = self.env._follows  # observer view, read under the environment lock
        others_env = sorted(
            self.by_token[t].i for t, f in follows.items()
            if f.zone == r.zone_id and t != owner.session.token and t in self.by_token
        )  # fmt: skip
        others_true = sorted(
            p.i for p in self.persons if p is not owner and p.true_zone == r.zone_id
        )
        self.restorations.append({
            "wall_ns": now_ns() - self.t0, "sim": r.time.isoformat() if r.time else None,
            "owner": owner.i, "deviceId": r.device_id, "zoneId": r.zone_id,
            "reason": r.reason, "state": r.state, "closing": self.closing,
            "othersPlacedInZone": others_env, "othersTrulyInZone": others_true,
        })  # fmt: skip

    def run(self, out: Path) -> dict[str, Any]:
        args = self.args
        out.mkdir(parents=True, exist_ok=True)
        rss = RssSampler().start()
        docker = None
        if args.store == "ngsild":
            from .dockerstats import ContainerStats, containers

            docker = ContainerStats(containers()).start()
        if args.tracemalloc:
            tracemalloc.start(25)
        rss_before = max_rss_bytes()
        setup_start = now_ns()
        self.env = self.make_environment()
        probe_store(self.env.store, self.account, self.collector)
        self.shared = SharedEnvironment(self.env, self.account, self.collector)
        self.persons = [Person(i, self) for i in range(1, self.n + 1)]
        self.by_token = {p.session.token: p for p in self.persons}
        setup_s = (now_ns() - setup_start) / 1e9

        threads = []
        cpu_start, proc_start = self.account.totals(), process_cpu_ns()
        self.t0 = now_ns() + int(0.5e9)  # every thread starts against the same schedule
        t_run = time.perf_counter() + 0.5
        for p in self.persons:
            threads.append(threading.Thread(target=p.walk, name=f"walk-{p.i}", daemon=True))
            threads.append(threading.Thread(target=p.client, name=f"client-{p.i}", daemon=True))
        for t in threads:
            t.start()
        reason = self._wait()
        self.stop.set()
        stopped = now_ns()
        for t in threads:
            t.join(timeout=120)
        alive = sum(t.is_alive() for t in threads)
        end_wall = time.perf_counter()
        cpu_run = delta(self.account.totals(), cpu_start)  # the run itself, not what follows
        proc_run = process_cpu_ns() - proc_start
        measured_s = (stopped - self.t0 - self.warmup_ns) / 1e9

        # state at the end of the run, all persons still bound
        with self.shared.lock:
            env_tables = self._env_tables()
            final_states = self.env.device_states()
        persons_memory = self._persons_memory()
        tm = None
        if args.tracemalloc:
            snapshot = tracemalloc.take_snapshot()
            tm = tracemalloc_by_component(snapshot)
            tracemalloc.stop()

        # closing: following intents end, subscriptions close (restorations), logs flush
        self.closing = True
        close_start = now_ns()
        for p in self.persons:
            with p.lock:
                p.engine.close()
                p.session.close()
        for p in self.persons:
            p.log.close()
        close_s = (now_ns() - close_start) / 1e9
        log_bytes = sum(p.store.path.stat().st_size for p in self.persons)
        log_records = sum(len(p.store.lines()) for p in self.persons)
        log_errors = sum(len(p.log.errors) for p in self.persons)
        recovered = getattr(self.env.store, "recovered", None)
        self.env.close()
        shutil.rmtree(self.log_dir, ignore_errors=True)
        rss_samples = rss.stop()
        container = None
        if docker is not None:
            from .dockerstats import window

            samples = docker.stop()
            container = window(samples, t_run, end_wall)
            with gzip.open(out / "docker.jsonl.gz", "wt", encoding="utf-8") as f:
                for s in samples:
                    f.write(json.dumps(s) + "\n")

        summary = self._summary(
            reason=reason, measured_s=measured_s, setup_s=setup_s, close_s=close_s,
            alive=alive, cpu_run=cpu_run, proc_run=proc_run, env_tables=env_tables,
            persons_memory=persons_memory, tracemalloc=tm, rss_samples=rss_samples,
            rss_before=rss_before, log_bytes=log_bytes, log_records=log_records,
            log_errors=log_errors, container=container, recovered=recovered,
            final_states=final_states,
        )  # fmt: skip
        self._write(out, summary)
        return summary

    def _wait(self) -> str:
        args = self.args
        while True:
            time.sleep(0.25)
            elapsed = (now_ns() - self.t0) / 1e9
            if self.mode == "open":
                if elapsed >= args.duration:
                    return "duration"
                continue
            measured = sum(1 for r in self.requests if not r["warmup"])
            if self.per_client:
                if all(p.sent >= self.per_client for p in self.persons) and all(
                    not p.lock.locked() for p in self.persons
                ):
                    time.sleep(0.5)
                    return "requests_per_client"
                if elapsed >= args.max_duration:
                    return "max_duration"
                continue
            if elapsed >= args.min_duration and measured >= args.min_requests:
                return "min_requests"
            if elapsed >= args.max_duration:
                return "max_duration"

    def _env_tables(self) -> dict[str, Any]:
        env = self.env
        callbacks = (self.shared, self.interpreter, env.store, env.scenario)
        tables = {
            "tokens": len(env._tokens),
            "subscriptions": len(env._subscriptions),
            "follows": len(env._follows),
            "armedTriggers": sum(len(f.armed) for f in env._follows.values()),
            "latestReadings": sum(len(v) for v in env._latest.values()),
            "changeRecords": sum(len(v) for v in env._changed.values()),
            "pendingRestorations": sum(len(v) for v in env._out_since.values()),
        }
        tables["bytes"] = {
            name: deep_size(getattr(env, name), stop=callbacks)
            for name in (
                "_tokens",
                "_subscriptions",
                "_follows",
                "_latest",
                "_changed",
                "_out_since",
            )  # fmt: skip
        }
        if self.args.store == "memory":
            tables["bytes"]["store"] = deep_size(env.store, stop=(env.scenario,))
        return tables

    def _persons_memory(self) -> dict[str, Any]:
        rows = []
        for p in self.persons:
            stop = (p.session, p.localization, p.interface, self.shared, p.engine._localization,
                    p.engine._interface)  # fmt: skip
            rows.append({
                "p": p.i,
                "engineBytes": deep_size(p.engine, stop=stop),
                "traceBytes": deep_size(p.engine.trace, stop=stop),
                "trace": len(p.engine.trace),
                "history": len(p.engine.history),
                "localizationBytes": deep_size(p.localization, stop=(p.engine,)),
                "sessionBytes": deep_size(p.session, stop=(self.shared, p.engine)),
                "eventLogMemoryBytes": deep_size(p.log, stop=(p.store,)),
                "records": p.records,
            })  # fmt: skip
        out: dict[str, Any] = {"persons": rows}
        for key in ("engineBytes", "traceBytes", "trace", "history", "localizationBytes",
                    "sessionBytes", "eventLogMemoryBytes", "records"):  # fmt: skip
            values = [r[key] for r in rows]
            out[key] = {"mean": round(sum(values) / len(values), 1), "max": max(values),
                        "total": sum(values)}  # fmt: skip
        return out

    def _conflicts(self) -> list[dict[str, Any]]:
        """Pairs of commands of two persons on the same device within the window."""
        window_ns = int(self.args.conflict_window * 1e9)
        by_device = defaultdict(list)
        for c in sorted(self.commands, key=lambda c: c["wall_ns"]):
            if c["ok"]:
                by_device[c["deviceId"]].append(c)
        pairs = []
        for device, cmds in by_device.items():
            for a, b in zip(cmds, cmds[1:], strict=False):
                if a["person"] != b["person"] and b["wall_ns"] - a["wall_ns"] <= window_ns:
                    pairs.append({
                        "deviceId": device, "gap_ms": round((b["wall_ns"] - a["wall_ns"]) / 1e6, 3),
                        "first": {k: a[k] for k in ("person", "command", "value", "state",
                                                    "trueZone", "sim")},
                        "second": {k: b[k] for k in ("person", "command", "value", "state",
                                                     "trueZone", "sim")},
                        "contradictory": a["state"] != b["state"],
                        "stateLeft": b["state"],
                    })  # fmt: skip
        return pairs

    def _summary(self, **m) -> dict[str, Any]:
        measured = [r for r in self.requests if not r["warmup"]]
        ok = [r for r in measured if r["error"] is None]
        errors = [r for r in measured if r["error"] is not None]
        ticks = [t for t in self.ticks if t["t_ns"] >= self.warmup_ns]
        signals = sum(t["signals"] for t in ticks)
        lag = [max(0, t["lag_ns"]) for t in ticks]
        lag_p95 = percentile([x / 1e9 for x in lag], 95) or 0.0
        interp = [w for r in ok for w in r["interp"]]

        def per(items, key_side):
            total = sum(side(x["cpu"], key_side) for x in items)
            return total

        req_agent = per(ok, "agent.")
        req_env = per(ok, "env.")
        tick_agent = per(ticks, "agent.")
        tick_env = per(ticks, "env.")
        by_section_req: dict[str, int] = defaultdict(int)
        by_section_tick: dict[str, int] = defaultdict(int)
        for r in ok:
            for k, v in r["cpu"].items():
                by_section_req[k] += v
        for t in ticks:
            for k, v in t["cpu"].items():
                by_section_tick[k] += v
        ops: dict[str, dict[str, list[int]]] = defaultdict(lambda: {"wait": [], "service": []})
        for r in ok:
            for op, (calls, wait, service) in r["ops"].items():
                ops[op]["wait"].append(wait // calls)
                ops[op]["service"].append(service // calls)
        for t in ticks:
            for op, (calls, wait, service) in t["ops"].items():
                ops[op]["wait"].append(wait // calls)
                ops[op]["service"].append(service // calls)
        status = defaultdict(int)
        for r in ok:
            status[r["status"]] += 1
        conflicts = self._conflicts()
        restoration_conflicts = [
            r for r in self.restorations
            if not r["closing"] and (r["othersPlacedInZone"] or r["othersTrulyInZone"])
        ]  # fmt: skip
        failed = []
        if measured and len(errors) / len(measured) > ERROR_FAIL:
            failed.append("errors")
        if lag_p95 > LAG_FAIL_S:
            failed.append("tick_lag")
        if m["reason"] == "max_duration" and self.mode == "closed" and not self.per_client:
            failed.append("min_requests_not_reached")
        rss_values = [v for _, v in m["rss_samples"]]
        cpu_run, proc_run = m["cpu_run"], m["proc_run"]
        attributed = sum(cpu_run.values())
        records_cpu = cpu_run.get("agent.eventlog.writer", 0)
        return {
            "label": self.label,
            "store": self.args.store,
            "interpreter": self.args.interpreter,
            "mode": self.mode,
            "persons": self.n,
            "rate": self.rate,
            "pace": self.pace,
            "think": self.think if self.mode == "closed" else None,
            "seed": self.seed,
            "stopReason": m["reason"],
            "failed": failed,
            "threadsStillAlive": m["alive"],
            "setupS": round(m["setup_s"], 3),
            "measuredS": round(m["measured_s"], 3),
            "closeS": round(m["close_s"], 3),
            "requests": {
                "all": len(self.requests),
                "measured": len(measured),
                "ok": len(ok),
                "errors": len(errors),
                "errorExamples": [r["error"] for r in errors[:5]],
                "status": dict(status),
            },
            "throughputRps": round(len(ok) / m["measured_s"], 3) if m["measured_s"] > 0 else None,
            "latencyMs": dist_ms([r["latency_ns"] for r in ok]),
            "serviceMs": dist_ms([r["service_ns"] for r in ok]),
            "agentWaitMs": dist_ms([r["agentWait_ns"] for r in ok]),
            "queueMs": dist_ms([r["queue_ns"] for r in ok]) if self.mode == "open" else None,
            "interpretWaitMs": dist_ms([w for w, _ in interp]),
            "interpretServiceMs": dist_ms([s for _, s in interp]),
            "interpretations": len(interp),
            "operationsMs": {
                op: {"wait": dist_ms(v["wait"]), "service": dist_ms(v["service"])}
                for op, v in sorted(ops.items())
            },
            "ticks": {
                "measured": len(ticks),
                "signals": signals,
                "signalsPerS": round(signals / m["measured_s"], 2) if m["measured_s"] else None,
                "lagMs": dist_ms(lag),
                "agentWaitMs": dist_ms([t["agentWait_ns"] for t in ticks]),
                "publishPerSignalMs": dist_ms(
                    [t["publish_ns"] // t["signals"] for t in ticks if t["signals"]]
                ),
                "errors": sum(1 for t in ticks if t["error"]),
            },
            "cpu": {
                "perRequestUs": {
                    "agent": round(req_agent / len(ok) / 1e3, 2) if ok else None,
                    "environment": round(req_env / len(ok) / 1e3, 2) if ok else None,
                    "bySection": {
                        k: round(v / len(ok) / 1e3, 2) for k, v in sorted(by_section_req.items())
                    }
                    if ok
                    else {},
                },
                "perSignalUs": {
                    "agent": round(tick_agent / signals / 1e3, 2) if signals else None,
                    "environment": round(tick_env / signals / 1e3, 2) if signals else None,
                    "bySection": {
                        k: round(v / signals / 1e3, 2) for k, v in sorted(by_section_tick.items())
                    }
                    if signals
                    else {},
                },
                "eventLogWriterPerRecordUs": round(records_cpu / m["log_records"] / 1e3, 2)
                if m["log_records"]
                else None,
                "runSecondsBySection": {k: round(v / 1e9, 4) for k, v in sorted(cpu_run.items())},
                "runAttributedS": round(attributed / 1e9, 4),
                "runProcessS": round(proc_run / 1e9, 4),
                "runUnattributedS": round((proc_run - attributed) / 1e9, 4),
                "processCores": round(proc_run / 1e9 / m["measured_s"], 4)
                if m["measured_s"]
                else None,
            },
            "memory": {
                "rssBeforeBytes": m["rss_before"],
                "rssStartBytes": rss_values[0] if rss_values else None,
                "rssEndBytes": rss_values[-1] if rss_values else None,
                "rssMaxBytes": max(rss_values) if rss_values else None,
                "processPeakRssBytes": max_rss_bytes(),
                "persons": {k: v for k, v in m["persons_memory"].items() if k != "persons"},
                "environment": m["env_tables"],
                "tracemalloc": m["tracemalloc"],
                "eventLogDiskBytes": m["log_bytes"],
                "eventLogRecords": m["log_records"],
                "eventLogBytesPerRecord": round(m["log_bytes"] / m["log_records"], 1)
                if m["log_records"]
                else None,
                "eventLogErrors": m["log_errors"],
            },
            "containers": m["container"],
            "recoveredSignals": m["recovered"],
            "conflicts": {
                "commandPairs": len(conflicts),
                "contradictoryPairs": sum(c["contradictory"] for c in conflicts),
                "restorationsDuringRun": sum(1 for r in self.restorations if not r["closing"]),
                "restorationsWithOthersInZone": len(restoration_conflicts),
                "examples": conflicts[:5],
                "restorationExamples": restoration_conflicts[:5],
            },
            "finalStates": m["final_states"],
            "_personsMemory": m["persons_memory"]["persons"],
            "_conflicts": conflicts,
            "_restorations": self.restorations,
        }

    def _write(self, out: Path, summary: dict[str, Any]) -> None:
        out.mkdir(parents=True, exist_ok=True)
        with gzip.open(out / "requests.jsonl.gz", "wt", encoding="utf-8") as f:
            for r in self.requests:
                f.write(json.dumps(r) + "\n")
        with gzip.open(out / "ticks.jsonl.gz", "wt", encoding="utf-8") as f:
            for t in self.ticks:
                f.write(json.dumps(t) + "\n")
        with gzip.open(out / "commands.jsonl.gz", "wt", encoding="utf-8") as f:
            for c in self.commands:
                f.write(json.dumps(c) + "\n")
        extra = {
            "persons": summary.pop("_personsMemory"),
            "conflicts": summary.pop("_conflicts"),
            "restorations": summary.pop("_restorations"),
        }
        with gzip.open(out / "events.json.gz", "wt", encoding="utf-8") as f:
            f.write(json.dumps(extra, indent=1, default=str) + "\n")
        (out / "point.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")


# --- sweep ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "label", "store", "interpreter", "mode", "persons", "rate", "failed", "stopReason",
    "measuredS", "requests", "errors", "throughputRps", "lat_p50", "lat_p95", "lat_p99",
    "lat_max", "interpWait_p50", "interpWait_p95", "interpService_p50", "interpService_p95",
    "agentWait_p95", "queue_p95", "signalsPerS", "tickLag_p50", "tickLag_p95",
    "publishPerSignal_p50", "publishPerSignal_p95", "cpuReqAgentUs", "cpuReqEnvUs",
    "cpuSigAgentUs", "cpuSigEnvUs", "eventLogWriterRecordUs", "processCores", "unattributedS",
    "rssStartMB", "rssMaxMB", "engineKBPerPerson", "traceLenPerPerson", "localizationKB",
    "sessionKB", "envFollows", "envArmed", "envChangeRecords", "envPending", "envLatest",
    "logBytesPerRecord", "orionCpuCores", "orionMemMB", "mongoCpuCores", "mongoMemMB",
    "conflictPairs", "contradictoryPairs", "restorationsOthersInZone", "recoveredSignals",
]  # fmt: skip


def csv_row(s: dict[str, Any]) -> list[Any]:
    mem, cpu, ticks, c = s["memory"], s["cpu"], s["ticks"], s.get("containers") or {}
    env = mem["environment"]
    mb = 1024 * 1024
    return [
        s["label"], s["store"], s["interpreter"], s["mode"], s["persons"], s["rate"],
        "+".join(s["failed"]), s["stopReason"], s["measuredS"], s["requests"]["measured"],
        s["requests"]["errors"], s["throughputRps"], s["latencyMs"]["p50"],
        s["latencyMs"]["p95"], s["latencyMs"]["p99"], s["latencyMs"]["max"],
        s["interpretWaitMs"]["p50"], s["interpretWaitMs"]["p95"],
        s["interpretServiceMs"]["p50"], s["interpretServiceMs"]["p95"],
        s["agentWaitMs"]["p95"], (s["queueMs"] or {}).get("p95"), ticks["signalsPerS"],
        ticks["lagMs"]["p50"], ticks["lagMs"]["p95"], ticks["publishPerSignalMs"]["p50"],
        ticks["publishPerSignalMs"]["p95"], cpu["perRequestUs"]["agent"],
        cpu["perRequestUs"]["environment"], cpu["perSignalUs"]["agent"],
        cpu["perSignalUs"]["environment"], cpu["eventLogWriterPerRecordUs"], cpu["processCores"],
        cpu["runUnattributedS"],
        round((mem["rssStartBytes"] or 0) / mb, 1), round((mem["rssMaxBytes"] or 0) / mb, 1),
        round(mem["persons"]["engineBytes"]["mean"] / 1024, 1), mem["persons"]["trace"]["mean"],
        round(mem["persons"]["localizationBytes"]["mean"] / 1024, 2),
        round(mem["persons"]["sessionBytes"]["mean"] / 1024, 2),
        env["follows"], env["armedTriggers"], env["changeRecords"], env["pendingRestorations"],
        env["latestReadings"], mem["eventLogBytesPerRecord"],
        (c.get("orion") or {}).get("cpuCores"),
        round((c.get("orion") or {}).get("memMaxBytes", 0) / mb, 1) if c else None,
        (c.get("mongo") or {}).get("cpuCores"),
        round((c.get("mongo") or {}).get("memMaxBytes", 0) / mb, 1) if c else None,
        s["conflicts"]["commandPairs"], s["conflicts"]["contradictoryPairs"],
        s["conflicts"]["restorationsWithOthersInZone"], s["recoveredSignals"],
    ]  # fmt: skip


def print_point(s: dict[str, Any]) -> None:
    lat, cpu = s["latencyMs"], s["cpu"]
    print(
        f"  N={s['persons']:<4} rate={s['rate']!s:<6} req={s['requests']['measured']:<6} "
        f"err={s['requests']['errors']:<3} X={s['throughputRps']!s:<8} "
        f"lat p50={lat['p50']} p95={lat['p95']} p99={lat['p99']} ms | "
        f"interp wait p95={s['interpretWaitMs']['p95']} svc p50={s['interpretServiceMs']['p50']} | "
        f"tick lag p95={s['ticks']['lagMs']['p95']} | cpu/req agent={cpu['perRequestUs']['agent']} "
        f"env={cpu['perRequestUs']['environment']} us | rss max="
        f"{(s['memory']['rssMaxBytes'] or 0) / 2**20:.0f} MB"
        f"{' FAILED ' + '+'.join(s['failed']) if s['failed'] else ''}"
    )


def calibrate(pairs: int = 200_000) -> float:
    """CPU cost of opening and closing one empty section (two thread-clock reads and the
    bookkeeping), charged to whatever section encloses it: the measurement's own overhead."""
    account = CpuAccount()
    account.enter("harness")
    start = time.thread_time_ns()
    for _ in range(pairs):
        account.enter("calibration")
        account.exit()
    elapsed = time.thread_time_ns() - start
    account.exit()
    return round(elapsed / pairs, 1)


def make_interpreter(args):
    from cpsagent.eval.run import make_grounder

    if args.interpreter == "llm":
        from cpsagent.grounding.prompts import PROMPT_VERSION

        args.prompt = args.prompt or PROMPT_VERSION
    ns = argparse.Namespace(
        grounder=args.interpreter, model=args.model, provider=args.provider,
        temperature=0.0, prompt=args.prompt, no_cache=args.no_cache, max_cost=args.max_cost,
    )  # fmt: skip
    start = time.perf_counter()
    grounder, client = make_grounder(ns)
    return grounder, client, time.perf_counter() - start


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(prog="python -m cpsagent.bench.load")
    p.add_argument("--store", choices=["memory", "ngsild"], required=True)
    p.add_argument("--interpreter", choices=["keyword", "embedding", "llm"], required=True)
    p.add_argument("--model")
    p.add_argument("--provider")
    p.add_argument("--prompt")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--max-cost", type=float)
    p.add_argument("--mode", choices=["closed", "open"], default="closed")
    p.add_argument("--persons", default="1", help="comma-separated N values")
    p.add_argument("--rates", help="open loop: comma-separated total request rates (req/s)")
    p.add_argument("--pace", type=float, default=1.0, help="ticks per wall-clock second")
    p.add_argument("--think", type=float, default=1.0, help="closed loop: mean think time, s")
    p.add_argument("--requests-per-client", type=int)
    p.add_argument("--min-duration", type=float, default=60.0)
    p.add_argument("--min-requests", type=int, default=400)
    p.add_argument("--max-duration", type=float, default=450.0)
    p.add_argument("--duration", type=float, default=60.0, help="open loop: seconds per point")
    p.add_argument("--warmup", type=float, default=10.0, help="seconds left out of the stats")
    p.add_argument("--client-start", type=float, default=5.0, help="first request after, s")
    p.add_argument("--conflict-window", type=float, default=5.0, help="seconds")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--tracemalloc", action="store_true")
    p.add_argument("--stop-on-fail", action="store_true")
    p.add_argument("--url", default="http://localhost:1026")
    p.add_argument("--label", help="name of the run directory (default: generated)")
    p.add_argument("--out", type=Path, default=runmeta.ROOT / "results" / "load")
    args = p.parse_args(argv)
    if args.mode == "open" and not args.rates:
        p.error("--rates is required with --mode open")
    if args.interpreter == "llm" and not args.model:
        p.error("--model is required with --interpreter llm")
    mix_bytes = MIX.read_bytes()
    import hashlib

    mix_sha = hashlib.sha256(mix_bytes).hexdigest()
    if json.loads(MIX_META.read_text())["sha256"] != mix_sha:
        raise SystemExit(f"{MIX} does not match the SHA-256 of {MIX_META}")

    persons = [int(x) for x in args.persons.split(",")]
    rates = [float(x) for x in args.rates.split(",")] if args.rates else [None]
    grounder, client, load_s = make_interpreter(args)
    now = datetime.now(UTC)
    run_id = args.label or (
        f"{now:%Y%m%d-%H%M%S}_{args.store}_{args.interpreter}_{args.mode}"
        + ("_tracemalloc" if args.tracemalloc else "")
    )
    out = args.out / run_id
    out.mkdir(parents=True, exist_ok=False)
    info: dict[str, Any] = {
        "runId": run_id,
        "store": args.store,
        "interpreter": args.interpreter,
        "interpreterLoadS": round(load_s, 3),
        "mode": args.mode,
        "persons": persons,
        "rates": rates if args.rates else None,
        "parameters": {k: v for k, v in vars(args).items() if k not in ("out",)},
        "tickPace": f"{args.pace} simulated ticks (1 simulated second each) per wall-clock second",
        "mix": {"file": "data/load/requests.jsonl", "sha256": mix_sha},
        "routes": {
            "transitTicks": TRANSIT_TICKS,
            "dwellTicks": list(DWELL),
            "zones": "the scope of person-agent",
        },  # fmt: skip
        "failure": {"errorShare": ERROR_FAIL, "tickLagP95S": LAG_FAIL_S},
        "clock": "time.perf_counter_ns; CPU time.thread_time_ns per thread",
        "serialized": {
            "environment": "one RLock: authenticate, scope, follow, subscribe, unsubscribe, "
            "zones, devices, device, execute, publish (signal handling with what it triggers)",
            "interpreter": "one Lock: every call of the interpreter's ground()",
            "person": "one Lock per person: a request, or a tick of signals",
        },
    }
    if args.interpreter == "embedding":
        from cpsagent.grounding import embedding

        info |= {"embeddingModel": embedding.MODEL_ID,
                 "embeddingRevision": embedding.MODEL_REVISION,
                 "threshold": grounder.threshold, "margin": grounder.margin}  # fmt: skip
        try:
            import torch

            info["torchThreads"] = torch.get_num_threads()
        except ImportError:
            pass
    if args.interpreter == "llm":
        from cpsagent.grounding.prompts import PROMPT_VERSION

        info |= {"model": args.model, "provider": args.provider,
                 "promptVersion": args.prompt or PROMPT_VERSION, "cache": not args.no_cache,
                 "rpm": getattr(getattr(client, "_limiter", None), "rpm", None),
                 "callsLogRunId": getattr(client, "run_id", None)}  # fmt: skip
    info["accountingOverheadNsPerSection"] = calibrate()
    record = runmeta.run_metadata("cpsagent.bench.load", argv, **info)
    if args.store == "ngsild":
        record["broker"] = runmeta.broker(args.url)
    runmeta.write(out / "metadata.json", record)

    print(f"{run_id}: {args.store}, {args.interpreter}, {args.mode} loop")
    summaries = []
    started = time.perf_counter()
    for n in persons:
        for rate in rates:
            label = f"N{n:03d}" + (f"_r{rate:g}" if rate is not None else "")
            point = Point(args, n, rate, grounder, label)
            summary = point.run(out / "points" / label)
            summaries.append(summary)
            print_point(summary)
            with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(CSV_COLUMNS)
                w.writerows(csv_row(s) for s in summaries)
            if summary["failed"] and args.stop_on_fail:
                break
        if summaries and summaries[-1]["failed"] and args.stop_on_fail:
            print(f"  point {summaries[-1]['label']} failed: the sweep stops here")
            record["stoppedAfter"] = summaries[-1]["label"]
            break
    record["durationS"] = round(time.perf_counter() - started, 1)
    record["points"] = [s["label"] for s in summaries]
    if client is not None:
        record["spentUsd"] = getattr(client, "spent_usd", None)
    runmeta.write(out / "metadata.json", record)
    print(f"saved in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
