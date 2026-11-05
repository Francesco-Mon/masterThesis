"""Orchestration Engine (F4-F6): Perceive -> Interpret -> Plan -> Act -> Observe -> [Recover].

The engine owns the per-request data (zone in force, intent, plan, counters) and runs
the activity of each state; *which* transition fires is always decided by the table in
`transitions.py`. It talks to the other components only through their contracts:
  R5/R6  Localization: `estimate()` and zone_changed events (C1)
  R7/R8  Grounder:     `ground(GroundingRequest) -> GroundingResult` (C2), once per request
  R10    Binding:      the BoundSession (catalogue, spatial model, bound flag)
  R12    Interface:    `execute(ToolCall) -> ToolResult` (C3)
  R16    recorder:     called once per transition, must not block (the Event Log queues)

External events (a request, a zone change, closing) are queued and handled one at a
time; each runs the machine until it reaches Perceive or waits in Observe.
"""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from cpsagent.binding import BoundSession
from cpsagent.contracts import (
    ActionPlan,
    ClarificationResult,
    GroundingRequest,
    Guard,
    IntentResult,
    Persistence,
    PlanStep,
    State,
    StructuredIntent,
    ToolCall,
    ToolResult,
    ZoneChangedEvent,
    ZoneEstimate,
)
from cpsagent.contracts.tool import InvokeCommandArgs, InvokeCommandCall
from cpsagent.grounding import Grounder

from .config import EngineConfig
from .planner import explain_no_step, make_plan
from .transitions import Context, Row, Trigger, select


class Localization(Protocol):
    def estimate(self) -> ZoneEstimate | None: ...  # R5
    def subscribe(self, listener: Callable[[ZoneChangedEvent], None]) -> None: ...  # R6


class Interface(Protocol):
    def execute(self, call: ToolCall) -> ToolResult: ...  # R12


@dataclass(frozen=True)
class Transition:
    """One fired row with the data in force; becomes one C4 event record (R16)."""

    time: datetime
    source: State
    target: State
    guard: Guard
    zone: ZoneEstimate | None
    intent: StructuredIntent | None
    action: ToolCall | None
    outcome: ToolResult | str | None

    def record_fields(self) -> dict[str, Any]:
        """EventRecord fields except `seq` and `session`, which the Event Log adds."""
        return {
            "time": self.time,
            "from": self.source,
            "to": self.target,
            "guard": self.guard,
            "zone": self.zone,
            "intent": self.intent,
            "action": self.action,
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class Reply:
    """R3: what the user is told."""

    status: Literal["done", "following", "recovered", "rejected"]
    message: str


def _step_key(step: PlanStep) -> tuple[str, str, Any]:
    return (step.device_id, step.command, step.value)


class OrchestrationEngine:
    def __init__(
        self,
        session: BoundSession,
        localization: Localization,
        grounder: Grounder,
        interface: Interface,
        *,
        config: EngineConfig | None = None,
        recorder: Callable[[Transition], None] | None = None,
        notify: Callable[[Reply], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config or EngineConfig()
        self._session = session
        self._localization = localization
        self._grounder = grounder
        self._interface = interface
        self._recorder = recorder
        self._notify = notify
        self._clock = clock or (lambda: datetime.now(UTC))
        self.state = State.PERCEIVE
        self.trace: list[Transition] = []  # every transition, in order (tests, demo)
        self.history: list[str] = []  # user utterances of this session (R7 `history`)
        # Full plan of the last Plan state, done steps included; survives the end of the
        # request (UI). `_plan` drops the steps already done in this zone.
        self.last_plan: ActionPlan | None = None
        self._events: deque[tuple[str, Any]] = deque()
        self._busy = False
        self._reply: Reply | None = None
        self._reset_request()
        localization.subscribe(self.on_zone_changed)

    def _reset_request(self) -> None:
        self._text = ""
        self._language = "en"
        self._zone: ZoneEstimate | None = None
        self._intent: StructuredIntent | None = None
        self._plan: ActionPlan | None = None
        self._done: set[tuple[str, str, Any]] = set()  # steps done since the last zone change
        self._step_count = 0
        self._retries = 0
        self._last: tuple[InvokeCommandCall, ToolResult] | None = None
        self._recover_reason = ""
        self._question: str | None = None

    # --- external events (R2, R6, end of session) ----------------------------------------

    def handle_request(self, text: str, language: str = "en") -> Reply:
        """R2 in, R3 out."""
        self._reply = None
        self._post("request", (text, language))
        return self._reply or Reply("rejected", "Request not handled.")

    def on_zone_changed(self, event: ZoneChangedEvent) -> None:
        """R6 listener, registered on Localization at construction."""
        self._post("zone_changed", event.estimate)

    def close(self) -> None:
        """End of session: a following intent ends here (T8)."""
        self._post("close", None)

    def _post(self, kind: str, payload: Any) -> None:
        self._events.append((kind, payload))
        if self._busy:  # re-entrant call (e.g. a zone change during Act): handled later
            return
        self._busy = True
        try:
            while self._events:
                self._dispatch(*self._events.popleft())
        finally:
            self._busy = False

    def _dispatch(self, kind: str, payload: Any) -> None:
        if kind == "zone_changed":
            if self.state == State.OBSERVE:  # elsewhere a zone change triggers nothing
                self._zone = payload
                self._done = set()
                if self._observe(zone_event=True):
                    self._run()
            return
        if self.state == State.OBSERVE:  # a following intent is waiting: it ends here
            reason = "superseded_by_request" if kind == "request" else "session_closed"
            self._fire(
                self._observe_context(intent_ended=True), Trigger.OUTCOME_RECEIVED, outcome=reason
            )
            self._reset_request()
        if kind == "request":
            self._perceive(*payload)
            self._run()

    # --- the machine ----------------------------------------------------------------------

    def _run(self) -> None:
        """Run state activities until the machine is back in Perceive or waits in Observe."""
        while self.state != State.PERCEIVE:
            if self.state == State.INTERPRET:
                self._interpret()
            elif self.state == State.PLAN:
                self._plan_steps()
            elif self.state == State.ACT:
                self._act()
            elif self.state == State.OBSERVE:
                if not self._observe():
                    return  # waiting for an event
            elif self.state == State.RECOVER:
                self._recover()

    def _fire(
        self,
        ctx: Context,
        trigger: Trigger,
        *,
        action: ToolCall | None = None,
        outcome: ToolResult | str | dict[Guard, ToolResult | str] | None = None,
    ) -> Row | None:
        """Ask the table which row fires; if one does, take it and record it."""
        row = select(self.state, trigger, ctx)
        if row is None:
            return None
        if isinstance(outcome, dict):  # outcome depends on which row fired
            outcome = outcome.get(row.id)
        transition = Transition(
            time=self._clock(),
            source=row.source,
            target=row.target,
            guard=row.id,
            zone=self._zone,
            intent=self._intent,
            action=action,
            outcome=outcome,
        )
        self.state = row.target
        self.trace.append(transition)
        if row.target == State.RECOVER:
            self._recover_reason = outcome if isinstance(outcome, str) else str(outcome)
        if self._recorder is not None:
            self._recorder(transition)  # R16: enqueue only, never waits for the log
        return row

    def _ctx(self, **values: Any) -> Context:
        return Context(config=self.config, **values)

    # --- state activities -----------------------------------------------------------------

    def _perceive(self, text: str, language: str) -> None:
        self._reset_request()
        self._text, self._language = text, language
        if self._fire(self._ctx(session_bound=self._session.bound), Trigger.REQUEST_RECEIVED):
            return
        self._say("rejected", "No environment session is bound.")

    def _interpret(self) -> None:
        zone = self._localization.estimate()  # R5
        self._zone = zone
        intent_confidence, reason = 0.0, None
        if not self._text.strip():
            reason = "request_unintelligible"  # empty text: e.g. an unreliable transcription
        elif zone is None or zone.confidence < self.config.theta:
            reason = "zone_confidence_low"  # do not spend a grounding call on a bad zone
        else:
            result = self._grounder.ground(  # R7 -> R8, once per request
                GroundingRequest(
                    text=self._text,
                    language=self._language,
                    zone=zone,
                    catalogue=self._session.catalogue,
                    adjacency=self._session.spatial_model.adjacency,
                    history=self.history[-5:],
                )
            )
            if isinstance(result, IntentResult):
                intent = result.intent
                catalogued_zones = {c.zone_id for c in self._session.catalogue}
                if intent.controlled_property not in self._session.catalogue_properties():
                    reason = "unsupported:capability_absent"  # never trust the grounder
                elif intent.target_zone_id not in catalogued_zones | {None}:
                    reason = "unsupported:out_of_scope"
                else:
                    self._intent = intent
                    intent_confidence = intent.confidence
                    if intent_confidence < self.config.theta:
                        reason = "intent_confidence_low"
            else:
                reason = f"{result.kind}:{result.reason}"
                if isinstance(result, ClarificationResult):
                    self._question = result.question
        if self._text.strip():
            self.history.append(self._text)
        ctx = self._ctx(
            zone_confidence=zone.confidence if zone else 0.0,
            intent_confidence=intent_confidence,
        )
        self._fire(ctx, Trigger.ZONE_ESTIMATE_AVAILABLE, outcome=reason)

    def _plan_steps(self) -> None:
        assert self._intent is not None and self._zone is not None
        plan = make_plan(
            self._intent,
            self._zone,
            self._session.catalogue,
            self._session.spatial_model.adjacency,
        )
        # Steps already done in this zone are not repeated (re-plan after "steps_pending").
        steps = [s for s in plan.steps if _step_key(s) not in self._done]
        self._plan = ActionPlan(steps=steps, valid_for=self._zone)
        self.last_plan = plan
        step = self._next_step()
        if step is not None:
            self._fire(
                self._ctx(has_applicable_step=True), Trigger.PLAN_PRODUCED, action=self._call(step)
            )
        else:
            reason = explain_no_step(self._intent, self._zone, self._session.catalogue)
            self._fire(self._ctx(), Trigger.NO_APPLICABLE_STEP, outcome=reason)

    def _act(self) -> None:
        step = self._next_step()
        assert step is not None  # Act is entered only with a pending applicable step
        ctx = self._ctx(step_count=self._step_count)  # commands invoked so far
        if self._step_count >= self.config.step_limit:  # the limit is checked before sending
            self._fire(ctx, Trigger.COMMAND_INVOKED, outcome="step_limit_reached")
            return
        call = self._call(step)
        self._step_count += 1
        result = self._interface.execute(call)  # R12
        self._last = (call, result)
        self._fire(ctx, Trigger.COMMAND_INVOKED, action=call, outcome=result)

    def _observe_context(self, **values: Any) -> Context:
        zone_changed = (
            self._plan is not None
            and self._zone is not None
            and self._zone.zone_id != self._plan.valid_for.zone_id
        )
        following = self._intent is not None and self._intent.persistence == Persistence.FOLLOWING
        return self._ctx(
            has_applicable_step=self._next_step() is not None,
            zone_changed=zone_changed,
            following=following,
            **values,
        )

    def _observe(self, zone_event: bool = False) -> bool:
        """Evaluate the last outcome (or a zone change). False = no row fired: wait."""
        if zone_event:
            return (
                self._fire(
                    self._observe_context(), Trigger.OUTCOME_RECEIVED, outcome="zone_changed"
                )
                is not None
            )
        assert self._last is not None
        call, result = self._last
        if not result.ok:
            row = self._fire(
                self._ctx(retries=self._retries),
                Trigger.COMMAND_FAILED,
                action=call,
                outcome={Guard.T10: result, Guard.T11: f"retry_limit_reached:{result.error}"},
            )
            if row is not None and row.id == Guard.T10:
                self._retries += 1
            return True
        args = call.args
        self._done.add((args.device_id, args.command, args.value))
        self._retries = 0
        ctx = self._observe_context()
        row = self._fire(
            ctx, Trigger.OUTCOME_RECEIVED, outcome={Guard.T8: result, Guard.T9: "steps_pending"}
        )
        if row is None:
            self._say("following", "Done. I will keep doing it as you move.")
            return False
        if row.id == Guard.T8:
            self._say("done", "Done.")
            self._reset_request()
        return True

    def _recover(self) -> None:
        reason = self._recover_reason
        if self._question:
            message, fallback = self._question, "clarification_asked"
        elif reason == "request_unintelligible":
            message, fallback = (
                "Sorry, I did not catch that. Could you say it again?",
                ("clarification_asked"),
            )
        elif reason == "zone_confidence_low":
            message, fallback = (
                "I am not sure where you are. Which room are you in?",
                ("clarification_asked"),
            )
        else:
            message, fallback = f"I could not do that ({reason}).", "user_informed"
        self._say("recovered", message)
        self._fire(self._ctx(), Trigger.FALLBACK_APPLIED, outcome=fallback)
        self._reset_request()

    # --- helpers --------------------------------------------------------------------------

    def _next_step(self) -> PlanStep | None:
        """First step of the plan not yet done whose guard holds in the current zone."""
        if self._plan is None or self._zone is None:
            return None
        for step in self._plan.steps:
            if _step_key(step) in self._done:
                continue
            if step.guard.type == "now" or step.guard.zone_id == self._zone.zone_id:
                return step
        return None

    @staticmethod
    def _call(step: PlanStep) -> InvokeCommandCall:
        return InvokeCommandCall(
            operation="invokeCommand",
            args=InvokeCommandArgs(
                device_id=step.device_id, command=step.command, value=step.value
            ),
        )

    def _say(self, status: str, message: str) -> None:
        reply = Reply(status, message)  # type: ignore[arg-type]
        self._reply = reply
        if self._notify is not None:
            self._notify(reply)
