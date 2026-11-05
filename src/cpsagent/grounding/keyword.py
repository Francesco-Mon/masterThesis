"""Baseline without an LLM: Intent Grounding by keyword rules (English and Italian).

It gives the lower bound the LLM candidates are compared with, through the same
interface (`ground(R7) -> R8`). Deliberately simple and readable, no tuning on the test
split: word lists for properties, actions, scopes and zone names, plus numbers.

Order of the rules:
1. user's zone outside the catalogue -> unsupported/out_of_scope;
2. injection markers or non-building topics -> unsupported/out_of_scope;
3. absent capabilities (music, fan, humidity, colour, windows, doors) -> capability_absent;
4. zone names: Italian "corridoio" -> clarification; a place not in the catalogue ->
   out_of_scope; a catalogued zone other than the current one -> targetZoneId;
5. exactly one property keyword, otherwise clarification/ambiguous_target;
6. action from verbs and numbers, scope/persistence from scope words;
7. the planner must find a step to run now, otherwise clarification (property only in
   other zones, no zone named) or unsupported (capability/command absent there).
"""

import re

from pydantic import ValidationError

from cpsagent.contracts import (
    ClarificationResult,
    GroundingRequest,
    GroundingResult,
    GroundingResultAdapter,
    IntentResult,
    StructuredIntent,
    UnsupportedResult,
)
from cpsagent.engine import explain_no_step, make_plan

INJECTION = "|".join(
    ["ignore", "disregard", "system", "prompt", "admin", "developer mode", "pretend"]
    + ["instructions", "istruzioni", "sistema", r"\{", "</"]
)
OFF_TOPIC = r"weather|tempo farà|email|e-mail|joke|barzelletta|translate|traduci"
ABSENT = "|".join(
    ["music", "volume", "sound", "ventila", r"fan\b", "humid", "umid", "colou?r", "warm white"]
    + ["window", "finestra", "door", "porta", "unlock", "sblocca"]
)

PROPERTIES = {
    "light": r"light|lamp|dark|bright|dim\b|see|luc[ei]|lampad|buio|buoi|ci vedo",
    "shading": r"blind|shade|sun\b|daylight|tend[ae]|tapparell|sole",
    "temperature": "|".join(
        ["temperat", "thermostat", "heating", "warm", "cold", "hot", "freez", "chilly", "cool"]
        + ["degree", "sweat", "boiling", "termostat", "riscaldament", "cald", "fredd", "grad[io]"]
    ),
}
ZONES = {
    "lobby": r"lobby|ingresso",
    "hallway": r"hallway",
    "corridor": r"corridor\b",
    "office": r"office|ufficio",
    "meeting_room": r"meeting room|meeting|sala riunioni",
    "kitchen": r"kitchen|cucina",
    "storage": r"storage|magazzino",
}
ELSEWHERE = (
    r"server room|sala server|garden|giardino|garage|parking|bathroom|bagno|terrace|terrazz|rooftop"
)

ENVIRONMENT = (
    r"\ball\b|every(?!.*\benter)|everywhere|whole building|building|\btutt[eio]\b|ovunque|edificio"
)
FOLLOW_ROOMS = r"wherever|each room|every room|ovunque io vada|ogni stanza"
PATH = r"\bway\b|walk|path|follow|ahead|guide|in front of me|accompagn|seguimi|cammin|strada"

OFF = r"\boff\b|spegn|spento|no need for light"
ON = r"\bon\b|accend|can't see|non ci vedo|dark|buio|buoi|black"
UP = r"warm|up\b|more|brighten|increase|freez|cold|chilly|alza|aument|di più|fredd|need more"
DOWN = r"down|cool|hot|boiling|sweat|lower temp|dim|blinding|too bright|abbass|\bcald|bass"
CLOSE = r"close|lower|chiud|abbass|sun\b|sole"
OPEN = r"open|raise|apri|alza|daylight"
NUMBER = re.compile(r"(\d+(?:[.,]\d+)?)")


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


def _clarify(question: str, reason: str = "ambiguous_target") -> ClarificationResult:
    return ClarificationResult(question=question, reason=reason)


# The lexical rules below are shared with Candidate C (`grounding/embedding.py`), so the
# two differ only in how the (action, controlledProperty) pair is chosen.


def screen(text: str, request: GroundingRequest, absent: bool = True) -> GroundingResult | None:
    """Rules 1-4 of the module docstring; None if the request passes them.
    `absent=False` skips the absent-capability word list (Candidate C decides that by
    similarity)."""
    if request.zone.zone_id not in request.catalogue_zones():
        return UnsupportedResult(reason="out_of_scope")
    if _has(INJECTION, text) or _has(OFF_TOPIC, text):
        return UnsupportedResult(reason="out_of_scope")
    if absent and _has(ABSENT, text):
        return UnsupportedResult(reason="capability_absent")
    if _has(r"corridoio", text):
        return _clarify("Do you mean the hallway or the corridor?")
    if _has(ELSEWHERE, text):
        return UnsupportedResult(reason="out_of_scope")
    return None


def scope_rules(text: str, here: str) -> tuple[str, str, str | None]:
    """(scope, persistence, targetZoneId) from scope words and zone names."""
    if _has(FOLLOW_ROOMS, text):
        scope, persistence = "current_zone", "following"
    elif _has(PATH, text):
        scope, persistence = "path", "following"
    elif _has(ENVIRONMENT, text):
        scope, persistence = "environment", "one_off"
    else:
        scope, persistence = "current_zone", "one_off"
    named = [z for z, pat in ZONES.items() if _has(pat, text) and z != here]
    target = named[0] if scope == "current_zone" and len(named) == 1 else None
    return scope, persistence, target


def set_value(text: str, prop: str) -> float | None:
    """The number of a `set` intent ("halfway" = 50 for blinds), None if there is none."""
    if prop == "shading" and _has(r"half|metà", text):
        return 50.0
    number = NUMBER.search(text)
    return float(number.group(1).replace(",", ".")) if number else None


def finish(intent: StructuredIntent, request: GroundingRequest) -> GroundingResult:
    """Rule 7: the planner must find a step to run now. The result is validated against
    C2 with the catalogue as context, like Candidate A's."""
    prop = intent.controlled_property
    plan = make_plan(intent, request.zone, request.catalogue, request.adjacency)
    if any(s.guard.type == "now" for s in plan.steps):
        result: GroundingResult = IntentResult(intent=intent)
    else:
        offered_elsewhere = any(
            d.controlled_property == prop for c in request.catalogue for d in c.devices
        )
        reason = explain_no_step(intent, request.zone, request.catalogue)
        if reason == "capability_absent" and intent.target_zone_id is None and offered_elsewhere:
            result = _clarify("Which room do you mean?")
        else:
            result = UnsupportedResult(reason=reason)
    context = {
        "catalogue_properties": request.catalogue_properties(),
        "catalogue_zones": request.catalogue_zones(),
    }
    try:
        return GroundingResultAdapter.validate_python(
            GroundingResultAdapter.dump_python(result, by_alias=True), context=context
        )
    except ValidationError:
        return _clarify("Sorry, could you rephrase that?", "invalid_output")


class KeywordGrounder:
    def ground(self, request: GroundingRequest) -> GroundingResult:
        text = request.text.lower()
        if (early := screen(text, request)) is not None:
            return early

        props = [p for p, pat in PROPERTIES.items() if _has(pat, text)]
        if len(props) != 1:
            return _clarify("What would you like me to change?")
        prop = props[0]
        scope, persistence, target = scope_rules(text, request.zone.zone_id)

        action, value = self._action(text, prop)
        if action is None:
            return _clarify("Which value would you like?", "missing_information")
        intent = StructuredIntent(
            action=action,
            controlled_property=prop,
            scope=scope,
            persistence=persistence,
            confidence=0.7,
            target_zone_id=target,
            value=value,
        )
        return finish(intent, request)

    @staticmethod
    def _action(text: str, prop: str) -> tuple[str | None, float | None]:
        """(action, value); action None means `set` without a number."""
        if (value := set_value(text, prop)) is not None:
            return "set", value
        if _has(r"\bset\b|imposta|metti", text) and not _has(OFF + "|" + ON, text):
            return None, None
        if prop == "shading":
            if _has(OPEN, text):
                return "deactivate", None
            return "activate", None  # close / lower / sun, and the default
        if _has(OFF, text):
            return "deactivate", None
        if prop == "light" and _has(ON, text):
            return "activate", None
        if _has(DOWN, text):
            return "decrease", None
        if _has(UP, text):
            return "increase", None
        return ("activate", None) if prop == "light" else (None, None)
