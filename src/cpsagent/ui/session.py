"""One UI session: emulated building, simulated walk, engine and event log.

Kept apart from the Streamlit page so it can be tested offline. The wiring is the one
of `cpsagent.demo_agent`; what is added here is a walk the user drives by hand (go to a
zone along the adjacency, or play a scripted path tick by tick) and one `Turn` per
request or movement, holding what the page shows.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import ActionPlan, PlanStep, State, ToolResult, ZoneEstimate
from cpsagent.engine import OrchestrationEngine, Reply, Transition
from cpsagent.environment import EmulatedEnvironment
from cpsagent.environment.mobility import DEFAULT_START, MobilitySimulator, Tick
from cpsagent.environment.model import PathScript
from cpsagent.eventlog import EventLog, EventStore, verify
from cpsagent.eventlog.verifier import VerificationReport
from cpsagent.interface import EnvironmentInterface
from cpsagent.localization import ZoneEstimator

AGENT = "person-agent"
SUBJECT = "user-1"
DWELL_TICKS = 5  # ticks spent in the destination zone: enough for the hysteresis to settle


@dataclass
class Turn:
    """What happened between two user actions: one request, or one stretch of walking."""

    kind: str  # "request" | "movement"
    text: str = ""
    transcript: Any = None  # ui.stt.Transcription when the request came from audio
    zone: ZoneEstimate | None = None
    transitions: list[Transition] = field(default_factory=list)
    reply: Reply | None = None
    plan: ActionPlan | None = None

    @property
    def interpretation(self) -> Transition | None:
        """The Interpret -> Plan/Recover row: intent, or the reason there is none."""
        return next((t for t in self.transitions if t.source == State.INTERPRET), None)

    @property
    def commands(self) -> list[Transition]:
        """Rows that sent a command. Not every ToolResult outcome is one: the row that ends
        a request (T8, Observe -> Perceive) carries the last result without an action."""
        return [
            t for t in self.transitions
            if t.action is not None and isinstance(t.outcome, ToolResult)
        ]  # fmt: skip


class AgentSession:
    def __init__(self, grounder, *, start_zone: str = "hallway", seed: int = 0, log_dir="logs"):
        self.env = EmulatedEnvironment()
        self.scenario = self.env.scenario
        self.session = EnvironmentBinding({self.env.endpoint: self.env}).bind(
            self.env.endpoint, AGENT, SUBJECT
        )
        adjacency = self.session.spatial_model.adjacency
        self._adjacency = {z: set(n) for z, n in adjacency.items()}
        self.localization = ZoneEstimator(adjacency, SUBJECT)
        self.session.subscription.add_listener(self.localization.on_signal)  # R13

        self.log_path = Path(log_dir) / f"ui_{self.session.session_id}.jsonl"
        self.log_path.unlink(missing_ok=True)  # one UI session = one fresh chain
        self.store = EventStore(self.log_path)
        self.log = EventLog(self.store, self.session.session_id)

        self.now = DEFAULT_START
        self.seed = seed
        self.position = start_zone  # where the simulated user really is (never told to the agent)
        self._pending: deque[Tick] = deque()
        self._recorded: list[Transition] = []
        self.engine = OrchestrationEngine(
            self.session,
            self.localization,
            grounder,
            EnvironmentInterface(self.session),
            recorder=self._record,
            clock=lambda: self.now,
        )
        self.turns: list[Turn] = []
        self._enqueue([start_zone], dwell=DWELL_TICKS)
        self.advance("end")
        self.turns.clear()  # placing the user at the start is not a turn

    # --- what the user does -----------------------------------------------------------------

    def say(self, text: str, language: str, transcript=None) -> Turn:
        """R2: one request. Empty text (an unreliable transcription) makes the engine ask
        to repeat without grounding."""
        start = len(self._recorded)
        reply = self.engine.handle_request(text, language)
        turn = Turn(
            "request",
            text=text,
            transcript=transcript,
            zone=self.localization.estimate(),
            transitions=self._recorded[start:],
            reply=reply,
        )
        if any(t.source == State.PLAN for t in turn.transitions):
            turn.plan = self.engine.last_plan
        self.turns.append(turn)
        return turn

    def walk_to(self, zone: str) -> Turn:
        """Walk from the current zone to `zone` along the shortest adjacency path."""
        return self._movement(lambda: self._enqueue(self.route(self.position, zone)), "end")

    def load_path(self, name: str) -> None:
        """Queue a scripted path, preceded by a walk to its first zone."""
        script = self.scenario.paths[name]
        first = script.segments[0]
        first_zone = first.zone if hasattr(first, "zone") else first.doorway[0]
        self._enqueue(self.route(self.position, first_zone), dwell=1)
        self._pending.extend(self._ticks(script))

    def advance(self, until: str = "tick") -> Turn:
        """Play queued ticks: one ("tick"), until the estimated zone changes ("zone"),
        or all of them ("end")."""
        return self._movement(lambda: None, until)

    @property
    def pending_ticks(self) -> int:
        return len(self._pending)

    # --- what the page shows ----------------------------------------------------------------

    def devices(self) -> list[dict[str, Any]]:
        token = self.env.authenticate(AGENT)
        rows = []
        for d in self.scenario.devices:
            live = self.env.device(token, d.device_id)
            rows.append({"device": d.device_id, "zone": d.ref_zone, **live.state})
        return rows

    def events(self) -> list[dict[str, Any]]:
        self.log.flush()
        return self.store.lines()

    def verify(self) -> VerificationReport:
        self.log.flush()
        return verify(self.store, self.session.session_id)

    def close(self) -> None:
        self.engine.close()
        self.log.close()

    # --- internals --------------------------------------------------------------------------

    def _record(self, t: Transition) -> None:
        self._recorded.append(t)
        self.log.submit(t.record_fields())  # R16: enqueue only

    def route(self, a: str, b: str) -> list[str]:
        """Shortest path a -> b over the adjacency (breadth-first), both ends included."""
        previous: dict[str, str | None] = {a: None}
        frontier = deque([a])
        while frontier:
            zone = frontier.popleft()
            if zone == b:
                break
            for nxt in sorted(self._adjacency[zone]):
                if nxt not in previous:
                    previous[nxt] = zone
                    frontier.append(nxt)
        if b not in previous:
            raise ValueError(f"no path from {a} to {b}")
        path = [b]
        while (p := previous[path[-1]]) is not None:
            path.append(p)
        return path[::-1]

    def _enqueue(self, zones: list[str], dwell: int = DWELL_TICKS) -> None:
        segments = [{"zone": z, "ticks": 2} for z in zones[:-1]]
        segments.append({"zone": zones[-1], "ticks": dwell})
        script = PathScript.model_validate(
            {"subject": SUBJECT, "transitTicks": 2, "segments": segments}
        )
        self._pending.extend(self._ticks(script))

    def _ticks(self, script: PathScript) -> list[Tick]:
        start = (self._pending[-1].time if self._pending else self.now) + timedelta(seconds=1)
        self.seed += 1  # a new noise draw per stretch, still reproducible from the start seed
        return list(MobilitySimulator(self.scenario, script, seed=self.seed, start=start).ticks())

    def _movement(self, queue, until: str) -> Turn:
        queue()
        start = len(self._recorded)
        before = self.localization.estimate()
        while self._pending:
            tick = self._pending.popleft()
            self.now, self.position = tick.time, tick.true_zone
            for signal in tick.signals:
                self.env.publish(signal)  # -> subscription -> Localization -> R6 -> engine
            zone = self.localization.estimate()
            if until == "tick":
                break
            changed = zone and before and zone.zone_id != before.zone_id
            if until == "zone" and changed:
                break
        turn = Turn(
            "movement", zone=self.localization.estimate(), transitions=self._recorded[start:]
        )
        if any(t.source == State.PLAN for t in turn.transitions):
            turn.plan = self.engine.last_plan
        self.turns.append(turn)
        return turn


def plan_status(turn: Turn) -> list[tuple[PlanStep, str]]:
    """Every step of the turn's plan with "done", "failed" or "pending" (not sent in this
    turn: its guard does not hold yet, e.g. the lamp of the next zone on the path)."""
    if turn.plan is None:
        return []
    sent = {}
    for c in turn.commands:
        a = c.action.args
        sent[(a.device_id, a.command, a.value)] = "done" if c.outcome.ok else "failed"
    return [(s, sent.get((s.device_id, s.command, s.value), "pending")) for s in turn.plan.steps]


def result_summary(turn: Turn) -> str:
    """Intent fields, or the reason the request did not reach a plan."""
    row = turn.interpretation
    if row is None:
        return "-"
    if row.intent is not None and row.target == State.PLAN:
        i = row.intent.model_dump(mode="json", exclude_none=True)
        return "intent: " + ", ".join(f"{k}={v}" for k, v in i.items())
    return f"no intent: {row.outcome}"
