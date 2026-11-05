"""Shared base for all contracts: camelCase on the wire, snake_case in Python, UTC times."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Contract(BaseModel):
    """Base model: unknown fields are rejected, JSON uses camelCase aliases.

    Models are frozen: a message, once validated, is not edited in place
    (the planner builds a new ActionPlan instead of patching the old one).
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        extra="forbid",
        frozen=True,
    )


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


# Naive datetimes are rejected; aware ones are normalised to UTC (serialised with "Z").
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]

# Confidence of an estimate or of a grounding result.
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
