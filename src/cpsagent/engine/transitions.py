"""Transition table of the Orchestration Engine (SPEC section 6, thesis Table 5.3) as data.

Each row is (id, from, trigger, guard, to). A guard is a pure function of a `Context`, the
snapshot of everything the guards may look at, built by the engine before each decision.
The engine never branches on states by itself: it asks `select` which row fires.

The guards of rows with the same (from, trigger) are mutually exclusive by construction
(tested), so at most one row fires. When none fires the engine waits for the next event:
this happens only in Observe, while a `following` intent waits for the user to move.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from cpsagent.contracts import TRANSITIONS, Guard, State

from .config import EngineConfig


class Trigger(StrEnum):
    REQUEST_RECEIVED = "Request received"
    ZONE_ESTIMATE_AVAILABLE = "ZoneEstimate available"
    PLAN_PRODUCED = "Plan produced"
    NO_APPLICABLE_STEP = "No applicable step"
    COMMAND_INVOKED = "Command invoked"
    OUTCOME_RECEIVED = "Outcome received"
    COMMAND_FAILED = "Command failed"
    FALLBACK_APPLIED = "Fallback applied"


@dataclass(frozen=True)
class Context:
    """What the guards see. Fields not relevant to the current state keep their defaults."""

    config: EngineConfig
    session_bound: bool = True
    zone_confidence: float = 0.0  # 0 when no ZoneEstimate is available
    intent_confidence: float = 0.0  # 0 when grounding gave no (valid) intent
    has_applicable_step: bool = False  # the plan has a pending step whose guard holds now
    step_count: int = 0  # commands invoked for the current request
    retries: int = 0  # retries already spent on the current step
    zone_changed: bool = False  # current zone != plan.validFor.zoneId
    intent_ended: bool = False  # a following intent ends (new request, session closing)
    following: bool = False  # intent persistence == following


Condition = Callable[[Context], bool]


def _confident(c: Context) -> bool:
    return min(c.zone_confidence, c.intent_confidence) >= c.config.theta


def _plan_stale(c: Context) -> bool:
    # validFor no longer matches the world: the user moved, or (gap in Table 5.3, see
    # DECISIONS.md) the plan still has a step applicable now after a successful one.
    return c.zone_changed or c.has_applicable_step


def _intent_satisfied(c: Context) -> bool:
    if c.intent_ended:
        return True
    return not c.has_applicable_step and not c.following


@dataclass(frozen=True)
class Row:
    id: Guard
    source: State
    trigger: Trigger
    guard: str  # wording of Table 5.3
    condition: Condition
    target: State


def _row(gid: Guard, trigger: Trigger, guard: str, condition: Condition) -> Row:
    source, target = TRANSITIONS[gid]  # states come from the contract, not repeated here
    return Row(gid, source, trigger, guard, condition, target)


T = Trigger
TABLE: tuple[Row, ...] = (
    _row(Guard.T1, T.REQUEST_RECEIVED, "Session bound", lambda c: c.session_bound),
    _row(Guard.T2, T.ZONE_ESTIMATE_AVAILABLE, "confidence >= theta", _confident),
    _row(Guard.T3, T.ZONE_ESTIMATE_AVAILABLE, "confidence < theta", lambda c: not _confident(c)),
    _row(Guard.T4, T.PLAN_PRODUCED, "Plan non-empty", lambda c: c.has_applicable_step),
    _row(Guard.T5, T.NO_APPLICABLE_STEP, "Capability absent", lambda c: not c.has_applicable_step),
    _row(
        Guard.T6,
        T.COMMAND_INVOKED,
        "Step count < limit",
        lambda c: c.step_count < c.config.step_limit,
    ),
    _row(
        Guard.T7,
        T.COMMAND_INVOKED,
        "Step count >= limit",
        lambda c: c.step_count >= c.config.step_limit,
    ),
    _row(Guard.T8, T.OUTCOME_RECEIVED, "Intent satisfied", _intent_satisfied),
    _row(
        Guard.T9,
        T.OUTCOME_RECEIVED,
        "validFor stale",
        lambda c: not _intent_satisfied(c) and _plan_stale(c),
    ),
    _row(
        Guard.T10, T.COMMAND_FAILED, "Retries < limit", lambda c: c.retries < c.config.retry_limit
    ),
    _row(
        Guard.T11, T.COMMAND_FAILED, "Retries >= limit", lambda c: c.retries >= c.config.retry_limit
    ),
    _row(Guard.T12, T.FALLBACK_APPLIED, "-", lambda c: True),
)


def select(state: State, trigger: Trigger, ctx: Context) -> Row | None:
    """The row that fires for (state, trigger) in this context, or None (wait)."""
    rows = [r for r in TABLE if r.source == state and r.trigger == trigger and r.condition(ctx)]
    if len(rows) > 1:  # would be a bug in the table, never a runtime situation
        raise RuntimeError(f"ambiguous transition from {state} on {trigger}: {rows}")
    return rows[0] if rows else None
