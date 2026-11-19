"""One UI session: emulated building, simulated walk, engine and event log.

Kept apart from the Streamlit page so it can be tested offline. The wiring is the one
of `cpsagent.demo_agent`; what is added here is a walk the user drives by hand (go to a
zone along the adjacency, play a scripted path tick by tick, or stay while time passes)
and one `Turn` per request or movement, holding what the page shows. Each restoration
the environment applies under the building's management policy is a turn of its own.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import ActionPlan, PlanStep, State, ToolResult, ZoneEstimate
from cpsagent.engine import OrchestrationEngine, Reply, Transition
from cpsagent.environment import EmulatedEnvironment, Restoration
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

    kind: str  # "request" | "movement" | "restoration"
    text: str = ""
    transcript: Any = None  # ui.stt.Transcription when the request came from audio
    zone: ZoneEstimate | None = None
    transitions: list[Transition] = field(default_factory=list)
    reply: Reply | None = None
    plan: ActionPlan | None = None
    restoration: Restoration | None = None  # kind "restoration": what the environment did
    interpreted: str | None = None  # who interpreted the request (see interpretation_note)
    parts: list[tuple[str, str]] | None = None  # a message carried out in parts

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
        # the chosen grounder is the environment's interpreter, not the agent's
        self.env = EmulatedEnvironment(interpreter=grounder)
        self.scenario = self.env.scenario
        self.session = EnvironmentBinding({self.env.endpoint: self.env}).bind(
            self.env.endpoint, AGENT, SUBJECT
        )
        # the simulated walk follows the building's real map (ground truth, not the agent's)
        self._adjacency = {z.zone_id: set(z.adjacency) for z in self.scenario.zones}
        # Localization learns the adjacency from the neighbourhoods the environment pushes
        self.localization = ZoneEstimator(dict(self.session.known_adjacency), SUBJECT)
        self.session.on_neighbourhood(lambda n: self.localization.add_adjacency(n.adjacency))
        self.session.subscription.add_listener(self.localization.on_signal)  # R13
        # restorations of the management policy, shown as turns after the movement
        self._restorations: list[Restoration] = []
        self.session.on_restoration(self._restorations.append)

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
            EnvironmentInterface(self.session),
            recorder=self._record,
            clock=lambda: self.now,
        )
        self.turns: list[Turn] = []
        self._enqueue([start_zone], dwell=DWELL_TICKS)
        self.advance("end")
        self.turns.clear()  # placing the user at the start is not a turn
        self._restorations.clear()

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
        turn.interpreted = interpretation_note(turn, type(self.env.interpreter).__name__)
        turn.parts = self.engine.last_parts
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

    def stay(self, seconds: int) -> Turn:
        """The user stays in the current zone for `seconds` ticks (time passes, so the
        environment's restoration countdowns advance)."""
        return self._movement(lambda: self._enqueue([self.position], dwell=seconds), "end")

    def advance(self, until: str = "tick") -> Turn:
        """Play queued ticks: one ("tick"), until the estimated zone changes ("zone"),
        or all of them ("end")."""
        return self._movement(lambda: None, until)

    @property
    def pending_ticks(self) -> int:
        return len(self._pending)

    # --- what the page shows ----------------------------------------------------------------

    def devices(self) -> list[dict[str, Any]]:
        """Every device of the building (observer view, not the agent's)."""
        states = self.env.device_states()
        return [
            {
                "device": d.device_id,
                "zone": d.ref_zone,
                **states[d.device_id],
                "default": format_state(d.default_state),
            }
            for d in self.scenario.devices
        ]

    def environment_view(self) -> dict[str, Any]:
        """What the page shows of the binding: the granted scope, and the person's zone and
        armed neighbours as the environment knows them (updated by its triggers)."""
        n = self.session.neighbourhood
        policy = self.env.building.management_policy
        pending = []
        for p in self.env.pending_restorations():  # observer view of the countdowns
            due = p["restoreAt"]
            left = None if due is None else max(0, int((due - self.now).total_seconds()))
            pending.append({"device": p["deviceId"], "zone": p["zoneId"], "inSeconds": left})
        return {
            "interpreter": type(self.env.interpreter).__name__,
            "scope": sorted(self.session.scope_zones),
            "zone": n.zone_id,
            "armed": n.armed,
            "restoreOnExit": policy.restore_on_exit,
            "restoreAfterSeconds": policy.restore_after_seconds,
            "pending": pending,
        }

    def events(self) -> list[dict[str, Any]]:
        self.log.flush()
        return self.store.lines()

    def verify(self) -> VerificationReport:
        self.log.flush()
        return verify(self.store, self.session.session_id)

    def close(self) -> None:
        """End of session: the following intent ends (T8), the subscription is closed (the
        environment restores what the agent changed) and the log is flushed."""
        self.engine.close()
        if self.session.bound:
            self.session.close()
            self._restoration_turns()
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
        self._restoration_turns()
        return turn

    def _restoration_turns(self) -> None:
        for r in self._restorations:
            self.turns.append(Turn("restoration", text=describe_restoration(r), restoration=r))
        self._restorations.clear()


def format_state(state: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in state.items())


def describe_restoration(r: Restoration) -> str:
    """One line for the chat, e.g. "Environment restored lamp_hallway to default
    (person left hallway)"."""
    why = f"person left {r.zone_id}" if r.reason == "person_left_zone" else "session closed"
    return f"Environment restored {r.device_id} to default ({why})"


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


def catalogue_queries(turn: Turn) -> list[str]:
    """The listDevices calls of the Plan state in this turn and what the environment
    answered, one line each."""
    lines = []
    for t in turn.transitions:
        for q in t.queries:
            a = q.call.args
            answer = [d["deviceId"] for d in q.result.state] if q.result.ok else q.result.error
            zone = a.zone_id or "every zone of the scope"
            lines.append(
                f"{q.call.operation}(zone={zone}, property={a.controlled_property}) -> {answer}"
            )
    return lines


# Interpret outcomes reached without asking the environment to interpret.
_NOT_INTERPRETED = {"request_unintelligible", "zone_confidence_low"}


def interpretation_note(turn: Turn, interpreter: str) -> str | None:
    """Who interpreted the request: the environment's service, or nobody (and why)."""
    row = turn.interpretation
    if row is None or row.outcome in _NOT_INTERPRETED:
        return None
    if row.outcome == "interpretation_refused:out_of_scope":
        return "The environment refused to interpret here: the zone is outside the scope"
    return f"Interpreted by the environment (interpreter: {interpreter})"


def result_summary(turn: Turn) -> str:
    """Intent fields, or the reason the request did not reach a plan."""
    row = turn.interpretation
    if row is None:
        return "-"
    if row.intent is not None and row.target == State.PLAN:
        i = row.intent.model_dump(mode="json", exclude_none=True)
        return "intent: " + ", ".join(f"{k}={v}" for k, v in i.items())
    return f"no intent: {row.outcome}"
