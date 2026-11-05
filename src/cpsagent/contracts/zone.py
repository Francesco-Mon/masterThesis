"""C1 - ZoneEstimate (R5 response) and zone-change event (R6)."""

from typing import Literal

from pydantic import Field

from .base import Confidence, Contract, UtcDatetime

ZoneId = str


class ZoneEstimate(Contract):
    """Where Localization believes the user is (zone level only).

    Whether `zoneId` exists is checked against the bound spatial model, not here:
    the contract alone does not know the building.
    """

    zone_id: ZoneId = Field(min_length=1)
    confidence: Confidence
    observed_at: UtcDatetime
    previous_zone_id: ZoneId | None = None


class ZoneChangedEvent(Contract):
    """R6: pushed by Localization when the estimated zone changes."""

    type: Literal["zone_changed"] = "zone_changed"
    estimate: ZoneEstimate
