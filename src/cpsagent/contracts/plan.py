"""ActionPlan: ordered guarded steps plus the ZoneEstimate it was computed against."""

from typing import Annotated, Literal

from pydantic import Field

from .base import Contract
from .zone import ZoneEstimate, ZoneId

CommandValue = str | int | float | bool | None


class NowGuard(Contract):
    """Execute the step immediately."""

    type: Literal["now"] = "now"


class OnEnterZoneGuard(Contract):
    """Execute the step when the user arrives in `zoneId`."""

    type: Literal["on_enter_zone"] = "on_enter_zone"
    zone_id: ZoneId = Field(min_length=1)


StepGuard = Annotated[NowGuard | OnEnterZoneGuard, Field(discriminator="type")]


class PlanStep(Contract):
    device_id: str = Field(min_length=1)
    command: str = Field(min_length=1)
    value: CommandValue = None
    guard: StepGuard


class ActionPlan(Contract):
    """Output of the Plan state.

    `steps` may be empty: an empty plan is how the planner says "no applicable
    step", which the engine maps to Plan -> Recover (T5). `validFor` going stale
    (user changed zone) triggers Observe -> Plan (T9).
    """

    steps: list[PlanStep]
    valid_for: ZoneEstimate
