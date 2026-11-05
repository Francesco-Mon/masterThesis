"""C2 - grounding request (R7), StructuredIntent, grounding result (R8), ActionPlan."""

import pytest
from pydantic import ValidationError

from cpsagent.contracts import (
    ActionPlan,
    ClarificationResult,
    GroundingRequest,
    GroundingResultAdapter,
    IntentResult,
    OnEnterZoneGuard,
    Scope,
    StructuredIntent,
    UnsupportedResult,
)

ZONE = {"zoneId": "hallway", "confidence": 0.87, "observedAt": "2026-11-10T09:30:12Z"}

REQUEST = {
    "text": "I want to walk in the light",
    "language": "en",
    "zone": ZONE,
    "catalogue": [
        {
            "zoneId": "hallway",
            "devices": [
                {
                    "deviceId": "lamp_hallway",
                    "category": "lamp",
                    "controlledProperty": "light",
                    "supportedCommand": ["on", "off", "dim"],
                }
            ],
        },
        {
            "zoneId": "corridor",
            "devices": [
                {
                    "deviceId": "lamp_corridor",
                    "category": "lamp",
                    "controlledProperty": "light",
                    "supportedCommand": ["on", "off"],
                }
            ],
        },
    ],
    "adjacency": {"hallway": ["livingroom", "corridor"]},
    "history": [],
}

INTENT = {
    "action": "activate",
    "controlledProperty": "light",
    "scope": "path",
    "persistence": "following",
    "confidence": 0.9,
}


# --- R7 request ---------------------------------------------------------------


def test_valid_request_and_catalogue_properties():
    request = GroundingRequest.model_validate(REQUEST)
    assert request.catalogue_properties() == {"light"}
    GroundingRequest.model_validate({**REQUEST, "language": "it", "history": ["too dark"]})
    GroundingRequest.model_validate({**REQUEST, "catalogue": [], "adjacency": {}})


@pytest.mark.parametrize(
    "change",
    [
        {"text": ""},
        {"language": "english"},
        {"zone": {**ZONE, "confidence": 2}},
        {"catalogue": [{"zoneId": "hallway", "devices": [{"deviceId": "x"}]}]},
    ],
)
def test_invalid_request(change):
    with pytest.raises(ValidationError):
        GroundingRequest.model_validate({**REQUEST, **change})


def test_request_missing_zone():
    data = {k: v for k, v in REQUEST.items() if k != "zone"}
    with pytest.raises(ValidationError):
        GroundingRequest.model_validate(data)


# --- R8 result ----------------------------------------------------------------

VALID_RESULTS = [
    ({"kind": "intent", "intent": INTENT}, IntentResult),
    (
        {"kind": "clarification", "question": "Which room?", "reason": "ambiguous_target"},
        ClarificationResult,
    ),
    ({"kind": "unsupported", "reason": "capability_absent"}, UnsupportedResult),
    (
        {"kind": "intent", "intent": {**INTENT, "scope": "current_zone", "persistence": "one_off"}},
        IntentResult,
    ),
]

INVALID_RESULTS = [
    {"kind": "intent", "intent": {**INTENT, "confidence": 1.5}},  # confidence out of [0,1]
    {"kind": "intent", "intent": {**INTENT, "action": "teleport"}},  # action not in enum
    {"kind": "intent", "intent": {**INTENT, "scope": "building"}},  # scope not in enum
    {"kind": "intent", "intent": {**INTENT, "persistence": "forever"}},
    {"kind": "intent", "intent": {k: v for k, v in INTENT.items() if k != "scope"}},  # missing
    {"kind": "clarification", "reason": "ambiguous_target"},  # question missing
    {"kind": "unsupported", "reason": "no_idea"},  # reason not in enum
    {"kind": "maybe", "reason": "capability_absent"},  # unknown kind
    {"intent": INTENT},  # discriminator missing
]


@pytest.mark.parametrize(("data", "expected_type"), VALID_RESULTS)
def test_valid_grounding_result(data, expected_type):
    assert isinstance(GroundingResultAdapter.validate_python(data), expected_type)


@pytest.mark.parametrize("data", INVALID_RESULTS)
def test_invalid_grounding_result(data):
    with pytest.raises(ValidationError):
        GroundingResultAdapter.validate_python(data)


def test_controlled_property_checked_against_catalogue():
    context = {
        "catalogue_properties": GroundingRequest.model_validate(REQUEST).catalogue_properties()
    }
    StructuredIntent.model_validate(INTENT, context=context)
    bad = {**INTENT, "controlledProperty": "temperature"}
    with pytest.raises(ValidationError, match="not in the capability catalogue"):
        StructuredIntent.model_validate(bad, context=context)
    with pytest.raises(ValidationError):
        GroundingResultAdapter.validate_python({"kind": "intent", "intent": bad}, context=context)
    # without context the contract alone cannot know the catalogue
    StructuredIntent.model_validate(bad)


def test_grounding_result_from_json_string():
    # LLM output arrives as a JSON string
    result = GroundingResultAdapter.validate_json(
        '{"kind":"intent","intent":{"action":"activate","controlledProperty":"light",'
        '"scope":"path","persistence":"following","confidence":0.9}}'
    )
    assert result.intent.scope is Scope.PATH


# --- ActionPlan ---------------------------------------------------------------

VALID_PLANS = [
    {
        "steps": [
            {"deviceId": "lamp_hallway", "command": "on", "value": None, "guard": {"type": "now"}},
            {
                "deviceId": "lamp_corridor",
                "command": "on",
                "guard": {"type": "on_enter_zone", "zoneId": "corridor"},
            },
        ],
        "validFor": ZONE,
    },
    {
        "steps": [
            {"deviceId": "lamp_hallway", "command": "dim", "value": 40, "guard": {"type": "now"}}
        ],
        "validFor": ZONE,
    },
    {"steps": [], "validFor": ZONE},  # "no applicable step" -> engine goes to Recover
]

INVALID_PLANS = [
    {"steps": [{"deviceId": "l", "command": "on", "guard": {"type": "later"}}], "validFor": ZONE},
    {
        "steps": [{"deviceId": "l", "command": "on", "guard": {"type": "on_enter_zone"}}],
        "validFor": ZONE,
    },  # zoneId missing
    {"steps": [{"deviceId": "l", "command": "on"}], "validFor": ZONE},  # guard missing
    {"steps": []},  # validFor missing
]


@pytest.mark.parametrize("data", VALID_PLANS)
def test_valid_plan(data):
    ActionPlan.model_validate(data)


@pytest.mark.parametrize("data", INVALID_PLANS)
def test_invalid_plan(data):
    with pytest.raises(ValidationError):
        ActionPlan.model_validate(data)


def test_plan_guard_types():
    plan = ActionPlan.model_validate(VALID_PLANS[0])
    assert isinstance(plan.steps[1].guard, OnEnterZoneGuard)
    assert plan.steps[1].guard.zone_id == "corridor"
    assert plan.model_dump(mode="json")["validFor"]["zoneId"] == "hallway"


def test_target_zone_is_optional_and_checked_against_catalogue_zones():
    assert StructuredIntent.model_validate(INTENT).target_zone_id is None
    assert "targetZoneId" not in StructuredIntent.model_validate(INTENT).model_dump(
        by_alias=True, exclude_none=True
    )
    request = GroundingRequest.model_validate(REQUEST)
    context = {"catalogue_zones": request.catalogue_zones()}
    named = {**INTENT, "scope": "current_zone", "targetZoneId": "corridor"}
    assert StructuredIntent.model_validate(named, context=context).target_zone_id == "corridor"
    with pytest.raises(ValidationError, match="not a catalogued zone"):
        StructuredIntent.model_validate({**named, "targetZoneId": "garden"}, context=context)
    StructuredIntent.model_validate({**named, "targetZoneId": "garden"})  # no context


@pytest.mark.parametrize("scope", ["path", "environment"])
def test_target_zone_only_with_current_zone_scope(scope):
    with pytest.raises(ValidationError, match="only with scope current_zone"):
        StructuredIntent.model_validate({**INTENT, "scope": scope, "targetZoneId": "corridor"})


def test_value_is_present_exactly_with_action_set():
    data = {**INTENT, "action": "set", "controlledProperty": "temperature", "value": 22}
    assert StructuredIntent.model_validate(data).value == 22
    assert "value" not in StructuredIntent.model_validate(INTENT).model_dump(
        by_alias=True, exclude_none=True
    )
    with pytest.raises(ValidationError, match="value is required with action set"):
        StructuredIntent.model_validate({**data, "value": None})  # "set" without a number
    with pytest.raises(ValidationError, match="value is required with action set"):
        StructuredIntent.model_validate({**INTENT, "value": 40})  # value with another action
    with pytest.raises(ValidationError):
        StructuredIntent.model_validate({**data, "value": "warm"})
