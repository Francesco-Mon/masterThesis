"""C4 - Event record (R16) and its stored, hash-chained form."""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from .base import Contract, UtcDatetime
from .grounding import StructuredIntent
from .tool import ToolCall, ToolResult
from .zone import ZoneEstimate


class State(StrEnum):
    PERCEIVE = "Perceive"
    INTERPRET = "Interpret"
    PLAN = "Plan"
    ACT = "Act"
    OBSERVE = "Observe"
    RECOVER = "Recover"


class Guard(StrEnum):
    """Row id of the transition table (SPEC section 6, thesis Table 5.3)."""

    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"
    T7 = "T7"
    T8 = "T8"
    T9 = "T9"
    T10 = "T10"
    T11 = "T11"
    T12 = "T12"


# Source and target state of each row. The engine uses the same table.
TRANSITIONS: dict[Guard, tuple[State, State]] = {
    Guard.T1: (State.PERCEIVE, State.INTERPRET),  # request received, session bound
    Guard.T2: (State.INTERPRET, State.PLAN),  # zone confidence >= theta
    Guard.T3: (State.INTERPRET, State.RECOVER),  # zone confidence < theta
    Guard.T4: (State.PLAN, State.ACT),  # plan non-empty
    Guard.T5: (State.PLAN, State.RECOVER),  # capability absent
    Guard.T6: (State.ACT, State.OBSERVE),  # step count < limit
    Guard.T7: (State.ACT, State.RECOVER),  # step count >= limit
    Guard.T8: (State.OBSERVE, State.PERCEIVE),  # intent satisfied
    Guard.T9: (State.OBSERVE, State.PLAN),  # validFor stale
    Guard.T10: (State.OBSERVE, State.ACT),  # command failed, retries < limit
    Guard.T11: (State.OBSERVE, State.RECOVER),  # command failed, retries >= limit
    Guard.T12: (State.RECOVER, State.PERCEIVE),  # fallback applied
}


class EventRecord(Contract):
    """One record per transition, exactly one. `from` is a Python keyword, hence `from_`."""

    seq: int = Field(ge=1)
    time: UtcDatetime
    session: str = Field(min_length=1)
    from_: State = Field(alias="from")
    to: State
    guard: Guard
    zone: ZoneEstimate | None = None
    intent: StructuredIntent | None = None
    action: ToolCall | None = None
    outcome: ToolResult | str | None = None  # operation result, or reason for recovery

    @model_validator(mode="after")
    def _guard_matches_states(self) -> Self:
        expected = TRANSITIONS[self.guard]
        if (self.from_, self.to) != expected:
            raise ValueError(
                f"guard {self.guard} is {expected[0]} -> {expected[1]}, "
                f"not {self.from_} -> {self.to}"
            )
        return self


# SHA-256 digest or 32-byte salt, lowercase hex.
Hex64 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StoredRecord(Contract):
    """One JSONL line of the local event store.

    After erasure, `record` and `salt` are null while `commitment` and `link`
    stay, so the chain still verifies and the position is reported as erased.
    """

    record: EventRecord | None
    salt: Hex64 | None
    commitment: Hex64
    link: Hex64

    @model_validator(mode="after")
    def _record_and_salt_together(self) -> Self:
        if (self.record is None) != (self.salt is None):
            raise ValueError("record and salt are erased together or kept together")
        return self

    @property
    def erased(self) -> bool:
        return self.record is None
