"""FakeGrounder: deterministic and scriptable, so engine, state machine and log are
testable offline (tests run without network and without a real LLM)."""

from collections.abc import Mapping
from typing import Any

from cpsagent.contracts import (
    ClarificationReason,
    ClarificationResult,
    GroundingRequest,
    GroundingResult,
    GroundingResultAdapter,
)

_FALLBACK = ClarificationResult(
    question="Sorry, could you rephrase that?", reason=ClarificationReason.MISSING_INFORMATION
)


def _key(text: str) -> str:
    return " ".join(text.lower().split())


class FakeGrounder:
    def __init__(
        self,
        script: Mapping[str, GroundingResult | dict[str, Any]] | None = None,
        default: GroundingResult | dict[str, Any] | None = None,
    ) -> None:
        """`script`: request text -> R8 result (model or JSON-like dict, validated here).

        Matching ignores case and extra spaces. Unscripted text gets `default`, or a
        clarification (missing_information) if no default is given.
        """
        self._script = {
            _key(t): GroundingResultAdapter.validate_python(r) for t, r in (script or {}).items()
        }
        self._default = GroundingResultAdapter.validate_python(default) if default else _FALLBACK
        self.calls: list[GroundingRequest] = []  # every R7 received, for tests

    def ground(self, request: GroundingRequest) -> GroundingResult:
        self.calls.append(request)
        return self._script.get(_key(request.text), self._default)
