"""Orchestration Engine (F4-F6): Perceive -> Interpret -> Plan -> Act -> Observe -> [Recover].

The engine owns the per-request data (zone in force, intent, plan, counters) and runs
the activity of each state; *which* transition fires is always decided by the table in
`transitions.py`. It talks to the other components only through their contracts:
  R5/R6  Localization: `estimate()` and zone_changed events (C1)
  R7/R8  Interpretation: a service of the environment, reached through the BoundSession
                       (`interpret`): the engine sends the text, the language, its zone
                       estimate and its recent history and gets a GroundingResult (C2),
                       once per request. The catalogue stays in the environment.
  R10    Binding:      the BoundSession (bound flag, scope, adjacency known from the
                       neighbourhoods the environment pushed)
  R12    Interface:    `execute(ToolCall) -> ToolResult` (C3); in the Plan state the engine
                       asks it for the devices offering the intent's property (listDevices)
  R16    recorder:     called once per transition, must not block (the Event Log queues)

External events (a request, a zone change, closing) are queued and handled one at a
time; each runs the machine until it reaches Perceive or waits in Observe.

Several actions in one message. When the environment refuses the whole message or asks a
clarification about it, the engine cuts it into parts (`splitter.py`) and asks the
environment to interpret each part. The parts that give an intent are carried out one
after the other, each as its own request cycle with its own records (the first in the
cycle already open, the next ones as queued requests that reuse the interpretation they
got); the user gets one reply saying which parts were done and which were not, and why. A
message understood as a whole is never split. Safety: a whole message refused as
`out_of_scope` (which includes attempts to override the rules) is not split, and if any
part is refused as `out_of_scope` nothing is carried out. A part that asks to be followed
(persistence `following`) is not combined with other parts: the user is asked to send it
on its own.
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
    DeviceDescriptor,
    GroundingResult,
    Guard,
    IntentResult,
    Persistence,
    PlanStep,
    State,
    StructuredIntent,
    ToolCall,
    ToolResult,
    ZoneCatalogue,
    ZoneChangedEvent,
    ZoneEstimate,
)
from cpsagent.contracts.tool import (
    InvokeCommandArgs,
    InvokeCommandCall,
    ListDevicesArgs,
    ListDevicesCall,
)
from cpsagent.environment import OutOfScopeError

from . import replies
from .config import EngineConfig
from .planner import catalogue_queries, explain_no_step, make_plan
from .splitter import split_message
from .transitions import Context, Row, Trigger, select


class Localization(Protocol):
    def estimate(self) -> ZoneEstimate | None: ...  # R5
    def subscribe(self, listener: Callable[[ZoneChangedEvent], None]) -> None: ...  # R6


class Interface(Protocol):
    def execute(self, call: ToolCall) -> ToolResult: ...  # R12


@dataclass(frozen=True)
class CatalogueQuery:
    """One listDevices call made in the Plan state and the environment's answer."""

    time: datetime
    call: ListDevicesCall
    result: ToolResult


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
    # Catalogue queries of the Plan state this row leaves (empty for other rows). Shown by
    # the UI and checked by the tests; not part of the event record (C4 is unchanged).
    queries: tuple[CatalogueQuery, ...] = ()

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


_DESCRIPTOR_KEYS = ("deviceId", "category", "controlledProperty", "supportedCommand")


@dataclass
class _Split:
    """A message carried out in parts: every part with the environment's answer to it, and
    the reply of each part that ran its own cycle."""

    text: str
    language: str
    parts: list[tuple[str, GroundingResult]]
    replies: dict[int, Reply]
    current: int | None = None


def _refusal(result: GroundingResult) -> str | None:
    """`kind:reason` of a result that is not an intent (None for an intent)."""
    return None if isinstance(result, IntentResult) else f"{result.kind}:{result.reason}"


def _step_key(step: PlanStep) -> tuple[str, str, Any]:
    return (step.device_id, step.command, step.value)


class OrchestrationEngine:
    def __init__(
        self,
        session: BoundSession,
        localization: Localization,
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
        self._split: _Split | None = None  # the message being carried out in parts
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
        self._given: tuple[int, GroundingResult] | None = None  # a part already interpreted

    # --- external events (R2, R6, end of session) ----------------------------------------

    def handle_request(self, text: str, language: str = "en") -> Reply:
        """R2 in, R3 out."""
        self._reply = None
        self._post("request", (text, language))
        if self._split is not None and not self._busy:  # every part has run its cycle
            self._reply = self._split_reply(self._split)
            self._split = None
            if self._notify is not None:
                self._notify(self._reply)
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
        elif kind == "part":  # the next part of a split message, already interpreted
            index, text, language, result = payload
            if self._split is not None:
                self._split.current = index  # its reply belongs to this part
            self._perceive(text, language)
            self._given = (index, result)
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
        queries: tuple[CatalogueQuery, ...] = (),
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
            queries=queries,
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
        self._say("rejected", replies.fixed("not_bound", language))

    def _interpret(self) -> None:
        zone = self._localization.estimate()  # R5
        self._zone = zone
        intent_confidence, reason = 0.0, None
        result: GroundingResult | None = None
        if not self._text.strip():
            reason = "request_unintelligible"  # empty text: e.g. an unreliable transcription
        elif zone is None or zone.confidence < self.config.theta:
            reason = "zone_confidence_low"  # do not spend a grounding call on a bad zone
        elif self._given is not None:  # a part of a split message: interpreted already
            result = self._given[1]
        else:
            try:  # R7 -> R8, once per request, interpreted by the environment
                result = self._session.interpret(
                    self._text, self._language, zone, self.history[-5:]
                )
            except OutOfScopeError:  # the environment refused to interpret here
                reason = "interpretation_refused:out_of_scope"
            if result is not None and not isinstance(result, IntentResult):
                result, split_reason = self._try_parts(result, zone)
                reason = reason or split_reason
        # The environment checks its interpretation against its own catalogue. The agent
        # has none: an intent naming something absent would end in Plan, with an empty
        # listDevices answer (T5).
        if isinstance(result, IntentResult):
            self._intent = result.intent
            intent_confidence = result.intent.confidence
            if intent_confidence < self.config.theta:
                reason = "intent_confidence_low"
        elif result is not None:
            reason = f"{result.kind}:{result.reason}"
            if isinstance(result, ClarificationResult):
                self._question = result.question
        if self._text.strip() and self._given is None:  # a split message counts once
            self.history.append(self._split.text if self._split else self._text)
        ctx = self._ctx(
            zone_confidence=zone.confidence if zone else 0.0,
            intent_confidence=intent_confidence,
        )
        self._fire(ctx, Trigger.ZONE_ESTIMATE_AVAILABLE, outcome=reason)

    def _ask_catalogue(self) -> tuple[list[ZoneCatalogue], tuple[CatalogueQuery, ...]]:
        """Ask the environment (listDevices) for the devices offering the intent's property
        in the target zones. The answer is used for this plan only; a refused call or an
        empty answer means capability absent there."""
        assert self._intent is not None and self._zone is not None
        prop = self._intent.controlled_property
        adjacency = self._session.known_adjacency
        by_zone: dict[str, list[DeviceDescriptor]] = {}
        queries = []
        for zone_id in catalogue_queries(
            self._intent, self._zone, adjacency, self._session.scope_zones
        ):
            call = ListDevicesCall(
                operation="listDevices",
                args=ListDevicesArgs(zone_id=zone_id, controlled_property=prop),
            )
            result = self._interface.execute(call)  # R12, observation only
            queries.append(CatalogueQuery(self._clock(), call, result))
            if zone_id is not None:
                by_zone.setdefault(zone_id, [])
            for d in result.state if result.ok else []:
                # the plan needs what a device can do, not its zone or its defaultState
                descriptor = {k: d[k] for k in _DESCRIPTOR_KEYS}
                by_zone.setdefault(d["refZone"], []).append(
                    DeviceDescriptor.model_validate(descriptor)
                )
        catalogue = [ZoneCatalogue(zone_id=z, devices=ds) for z, ds in by_zone.items()]
        return catalogue, tuple(queries)

    def _plan_steps(self) -> None:
        assert self._intent is not None and self._zone is not None
        catalogue, queries = self._ask_catalogue()
        plan = make_plan(self._intent, self._zone, catalogue, self._session.known_adjacency)
        # Steps already done in this zone are not repeated (re-plan after "steps_pending").
        steps = [s for s in plan.steps if _step_key(s) not in self._done]
        self._plan = ActionPlan(steps=steps, valid_for=self._zone)
        self.last_plan = plan
        step = self._next_step()
        if step is not None:
            self._fire(
                self._ctx(has_applicable_step=True),
                Trigger.PLAN_PRODUCED,
                action=self._call(step),
                queries=queries,
            )
        else:
            reason = explain_no_step(self._intent, self._zone, catalogue)
            self._fire(self._ctx(), Trigger.NO_APPLICABLE_STEP, outcome=reason, queries=queries)

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
            self._say("following", replies.fixed("following", self._language))
            return False
        if row.id == Guard.T8:
            self._say("done", replies.fixed("done", self._language))
            self._reset_request()
        return True

    def _recover(self) -> None:
        reason, language = self._recover_reason, self._language
        if self._question:
            message, fallback = self._question, "clarification_asked"
        elif reason == "request_unintelligible":
            message, fallback = replies.fixed("unintelligible", language), "clarification_asked"
        elif reason == "zone_confidence_low":
            message, fallback = replies.fixed("zone_unknown", language), "clarification_asked"
        else:
            zone_id = self._zone.zone_id if self._zone else None
            message = replies.explain(reason, language, self._intent, zone_id)
            fallback = "user_informed"
        self._say("recovered", message)
        self._fire(self._ctx(), Trigger.FALLBACK_APPLIED, outcome=fallback)
        self._reset_request()

    # --- several actions in one message ---------------------------------------------------

    def _try_parts(
        self, whole: GroundingResult, zone: ZoneEstimate
    ) -> tuple[GroundingResult | None, str | None]:
        """The environment did not understand the whole message: ask it about each part.
        Returns the result this cycle goes on with and, when the parts cannot be carried
        out together, the reason recorded instead. Queues the other parts with an intent."""
        unchanged = (whole, None)
        if _refusal(whole) == "unsupported:out_of_scope":
            return unchanged  # e.g. an attempt to override the rules: never split
        texts = split_message(self._text, self._language)
        if len(texts) < 2:
            return unchanged
        history = self.history[-5:]
        parts = [(t, self._session.interpret(t, self._language, zone, history)) for t in texts]
        if any(_refusal(r) == "unsupported:out_of_scope" for _, r in parts):
            return unchanged  # one part is not allowed: nothing of the message is done
        intents = [i for i, (_, r) in enumerate(parts) if isinstance(r, IntentResult)]
        if not intents:
            return unchanged  # no part understood: the answer for the whole message stands
        following = [
            t
            for t, r in parts
            if isinstance(r, IntentResult) and r.intent.persistence == Persistence.FOLLOWING
        ]
        if following:  # cannot be combined: ask for it on its own, nothing is done
            self._question = replies.fixed("following_alone", self._language, part=following[0])
            return None, "split:following_not_combined"
        self._split = _Split(self._text, self._language, parts, {}, current=intents[0])
        for i in reversed(intents[1:]):  # before any other queued event
            self._events.appendleft(("part", (i, parts[i][0], self._language, parts[i][1])))
        return parts[intents[0]][1], None

    @staticmethod
    def _split_reply(split: _Split) -> Reply:
        """One reply for a message carried out in parts: what was done, what was not, why."""
        lines, all_done = [], True
        for i, (text, result) in enumerate(split.parts):
            reply = split.replies.get(i)
            if reply is not None and reply.status == "done":
                lines.append(replies.fixed("part_done", split.language, part=text))
                continue
            all_done = False
            if reply is not None:
                why = reply.message
            elif isinstance(result, ClarificationResult):
                why = result.question
            else:
                why = replies.explain(_refusal(result) or "", split.language)
            lines.append(replies.fixed("part_not_done", split.language, part=text, why=why))
        return Reply("done" if all_done else "recovered", " ".join(lines))

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
        if self._split is not None and self._split.current is not None:
            self._split.replies[self._split.current] = reply  # told once, at the end
            return
        self._reply = reply
        if self._notify is not None:
            self._notify(reply)
