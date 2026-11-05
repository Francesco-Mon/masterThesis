"""Contracts C1-C4: the single source of truth for R5/R6, R7/R8, R12, R16 (docs/CONTRACTS.md)."""

from .base import Contract, UtcDatetime
from .event import TRANSITIONS, EventRecord, Guard, State, StoredRecord
from .grounding import (
    Action,
    ClarificationReason,
    ClarificationResult,
    DeviceDescriptor,
    GroundingRequest,
    GroundingResult,
    GroundingResultAdapter,
    IntentResult,
    Persistence,
    Scope,
    StructuredIntent,
    UnsupportedReason,
    UnsupportedResult,
    ZoneCatalogue,
)
from .plan import ActionPlan, NowGuard, OnEnterZoneGuard, PlanStep, StepGuard
from .tool import Operation, ToolCall, ToolCallAdapter, ToolError, ToolResult
from .zone import ZoneChangedEvent, ZoneEstimate

__all__ = [
    "TRANSITIONS",
    "Action",
    "ActionPlan",
    "ClarificationReason",
    "ClarificationResult",
    "Contract",
    "DeviceDescriptor",
    "EventRecord",
    "GroundingRequest",
    "GroundingResult",
    "GroundingResultAdapter",
    "Guard",
    "IntentResult",
    "NowGuard",
    "OnEnterZoneGuard",
    "Operation",
    "Persistence",
    "PlanStep",
    "Scope",
    "State",
    "StepGuard",
    "StoredRecord",
    "StructuredIntent",
    "ToolCall",
    "ToolCallAdapter",
    "ToolError",
    "ToolResult",
    "UnsupportedReason",
    "UnsupportedResult",
    "UtcDatetime",
    "ZoneCatalogue",
    "ZoneChangedEvent",
    "ZoneEstimate",
]
