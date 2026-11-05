"""Parameters of the transition table (SPEC section 6)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineConfig:
    theta: float = 0.6  # minimum confidence of ZoneEstimate and StructuredIntent (T2/T3)
    step_limit: int = 8  # max commands invoked per request, retries included (T6/T7)
    retry_limit: int = 2  # max retries of a failed command (T10/T11)
