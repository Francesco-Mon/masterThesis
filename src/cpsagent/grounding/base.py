"""The one interface every Intent Grounding candidate implements (C2, R7/R8)."""

from typing import Protocol

from cpsagent.contracts import GroundingRequest, GroundingResult


class Grounder(Protocol):
    """A, C, ... are interchangeable: the engine only ever calls `ground`.

    Contract: parsing errors never escape. After the candidate's bounded retry the
    result is a ClarificationResult / UnsupportedResult with a `reason`.
    """

    def ground(self, request: GroundingRequest) -> GroundingResult: ...
