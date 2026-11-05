"""C2 - Intent Grounding request (R7) and result (R8)."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationInfo, field_validator, model_validator

from .base import Confidence, Contract
from .zone import ZoneEstimate, ZoneId


class DeviceDescriptor(Contract):
    """One catalogue entry: what a device can do (read from `supportedCommand`)."""

    device_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    controlled_property: str = Field(min_length=1)
    supported_command: list[str] = Field(min_length=1)


class ZoneCatalogue(Contract):
    """Capability catalogue for one zone (the catalogue is indexed by zone)."""

    zone_id: ZoneId = Field(min_length=1)
    devices: list[DeviceDescriptor]


class GroundingRequest(Contract):
    """R7: what the engine passes to any Intent Grounding candidate."""

    text: str = Field(min_length=1)
    language: str = Field(pattern=r"^[a-z]{2}$")  # ISO 639-1, e.g. "en", "it"
    zone: ZoneEstimate
    catalogue: list[ZoneCatalogue]
    adjacency: dict[ZoneId, list[ZoneId]]
    history: list[str] = []  # previous user utterances in this session, oldest first

    def catalogue_properties(self) -> set[str]:
        """Every `controlledProperty` offered by at least one device in the catalogue."""
        return {d.controlled_property for z in self.catalogue for d in z.devices}

    def catalogue_zones(self) -> set[str]:
        """Zones in the catalogue = the zones in the agent's scope."""
        return {z.zone_id for z in self.catalogue}


class Action(StrEnum):
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    INCREASE = "increase"
    DECREASE = "decrease"
    SET = "set"
    QUERY = "query"


class Scope(StrEnum):
    CURRENT_ZONE = "current_zone"
    PATH = "path"
    ENVIRONMENT = "environment"


class Persistence(StrEnum):
    ONE_OFF = "one_off"
    FOLLOWING = "following"


class StructuredIntent(Contract):
    """What the user wants, independent of devices: verb + property + where + how long.

    `controlledProperty` must exist in the catalogue, and `targetZoneId` (if given) must
    be a catalogued zone. The model cannot know the catalogue by itself, so these checks
    run only when the caller passes it as validation context:
    `model_validate(data, context={"catalogue_properties": {...}, "catalogue_zones": {...}})`.

    `targetZoneId` is set only when the user names a zone other than the current one
    ("turn on the kitchen light" said in the hallway); it then replaces the current zone,
    so it is allowed only with scope `current_zone`.

    `value` is the number the user asks for, in the property's unit: percent for light
    (brightness) and shading (0 = blinds open, 100 = closed, so it grows with the
    property as `increase` does), degrees Celsius for temperature. It is present exactly
    when `action` is `set` ("set the thermostat to 22", "dim the lamp to 40%"). Ranges
    are checked by the environment, not here.
    """

    action: Action
    controlled_property: str = Field(min_length=1)
    scope: Scope
    persistence: Persistence
    confidence: Confidence
    target_zone_id: ZoneId | None = Field(default=None, min_length=1)
    value: float | None = None

    @field_validator("controlled_property")
    @classmethod
    def _property_in_catalogue(cls, value: str, info: ValidationInfo) -> str:
        allowed = (info.context or {}).get("catalogue_properties")
        if allowed is not None and value not in allowed:
            raise ValueError(f"controlledProperty '{value}' is not in the capability catalogue")
        return value

    @field_validator("target_zone_id")
    @classmethod
    def _target_zone_in_catalogue(cls, value: str | None, info: ValidationInfo) -> str | None:
        allowed = (info.context or {}).get("catalogue_zones")
        if value is not None and allowed is not None and value not in allowed:
            raise ValueError(f"targetZoneId '{value}' is not a catalogued zone (out of scope)")
        return value

    @model_validator(mode="after")
    def _target_zone_needs_current_zone_scope(self) -> "StructuredIntent":
        if self.target_zone_id is not None and self.scope != Scope.CURRENT_ZONE:
            raise ValueError("targetZoneId is allowed only with scope current_zone")
        return self

    @model_validator(mode="after")
    def _value_iff_set(self) -> "StructuredIntent":
        if (self.value is not None) != (self.action == Action.SET):
            raise ValueError("value is required with action set and allowed only with it")
        return self


class ClarificationReason(StrEnum):
    AMBIGUOUS_TARGET = "ambiguous_target"
    AMBIGUOUS_ACTION = "ambiguous_action"
    MISSING_INFORMATION = "missing_information"
    LOW_CONFIDENCE = "low_confidence"
    INVALID_OUTPUT = "invalid_output"  # grounder output still invalid after bounded retry
    SERVICE_UNAVAILABLE = "service_unavailable"  # grounder backend failed (network, 5xx, 429)


class UnsupportedReason(StrEnum):
    CAPABILITY_ABSENT = "capability_absent"  # no device offers the property
    COMMAND_ABSENT = "command_absent"  # property exists but not the needed command
    OUT_OF_SCOPE = "out_of_scope"  # not a request about the environment (incl. injection)


class IntentResult(Contract):
    kind: Literal["intent"] = "intent"
    intent: StructuredIntent


class ClarificationResult(Contract):
    kind: Literal["clarification"] = "clarification"
    question: str = Field(min_length=1)
    reason: ClarificationReason


class UnsupportedResult(Contract):
    kind: Literal["unsupported"] = "unsupported"
    reason: UnsupportedReason


# R8: discriminated on `kind`. Every grounder returns exactly one of these.
GroundingResult = Annotated[
    IntentResult | ClarificationResult | UnsupportedResult, Field(discriminator="kind")
]
GroundingResultAdapter: TypeAdapter[GroundingResult] = TypeAdapter(GroundingResult)
