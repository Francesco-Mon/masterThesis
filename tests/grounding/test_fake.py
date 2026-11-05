"""FakeGrounder: scripted, deterministic, records every R7 request."""

from datetime import UTC, datetime

from cpsagent.contracts import ClarificationResult, GroundingRequest, IntentResult, ZoneEstimate
from cpsagent.grounding import FakeGrounder

ZONE = ZoneEstimate(
    zone_id="hallway", confidence=0.9, observed_at=datetime(2026, 11, 10, tzinfo=UTC)
)
LIGHT_ON = {
    "kind": "intent",
    "intent": {
        "action": "activate",
        "controlledProperty": "light",
        "scope": "current_zone",
        "persistence": "one_off",
        "confidence": 0.9,
    },
}


def request(text):
    return GroundingRequest(text=text, language="en", zone=ZONE, catalogue=[], adjacency={})


def test_scripted_text_matches_ignoring_case_and_spaces():
    g = FakeGrounder({"Turn on the light": LIGHT_ON})
    result = g.ground(request("  turn ON   the light "))
    assert isinstance(result, IntentResult) and result.intent.controlled_property == "light"
    assert [r.text for r in g.calls] == ["  turn ON   the light "]


def test_unscripted_text_gets_a_clarification_or_the_default():
    assert isinstance(FakeGrounder().ground(request("??")), ClarificationResult)
    assert isinstance(FakeGrounder(default=LIGHT_ON).ground(request("??")), IntentResult)
