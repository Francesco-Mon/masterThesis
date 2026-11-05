"""Candidate A: Intent Grounding with an LLM through OpenRouter (structured output).

ground(R7) -> R8 in four steps:
1. Checks that need no LLM: the user's zone must be a catalogued zone (in the agent's
   scope); otherwise `unsupported/out_of_scope` without spending a call.
2. Prompt = fixed system rules + one user message holding the request *as JSON data*
   (text, language, zone, catalogue, adjacency, history). The user's words never go into
   the system message, and JSON encoding means they cannot close a delimiter.
3. `response_format: json_schema` with WIRE_SCHEMA, a flat object derived from the C2
   enums (see `wire_schema`); the answer is mapped to the C2 GroundingResult and validated
   with Pydantic, with the catalogue's properties as validation context (an invented
   controlledProperty is rejected in code, whatever the schema said). A `targetZoneId`
   equal to the current zone is dropped; one outside the catalogue (= outside the scope,
   or not a zone at all) gives `unsupported/out_of_scope` at once, without retry.
4. Bounded retry: up to `max_retries` (2) more calls, each with the previous answer and
   its validation error appended. After that: `unsupported/capability_absent` if the last
   error was an off-catalogue property, otherwise `clarification/invalid_output`.

Provider failures (network, 5xx, 429 after backoff) end in `clarification/service_unavailable`.
AuthError, BudgetExceededError and MissingApiKeyError propagate: they stop the run.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from cpsagent.contracts import (
    Action,
    ClarificationReason,
    ClarificationResult,
    GroundingRequest,
    GroundingResult,
    GroundingResultAdapter,
    IntentResult,
    Persistence,
    Scope,
    UnsupportedReason,
    UnsupportedResult,
)

from .openrouter import LLMCallError, OpenRouterClient
from .prompts import PROMPT_VERSION, PROMPTS

SCHEMA_NAME = "grounding_result"
DEFAULT_MODEL = "openai/gpt-oss-120b"  # cheap paid development model (DECISIONS.md)


def default_model() -> str:
    """GROUNDER_MODEL_CHEAP from the environment / .env, else DEFAULT_MODEL."""
    load_dotenv()
    return os.getenv("GROUNDER_MODEL_CHEAP") or DEFAULT_MODEL


# Reasons the model may choose; invalid_output / service_unavailable are set by the code.
_MODEL_CLARIFICATION_REASONS = [
    r
    for r in ClarificationReason
    if r not in (ClarificationReason.INVALID_OUTPUT, ClarificationReason.SERVICE_UNAVAILABLE)
]


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _enum(values) -> dict[str, Any]:
    return {"type": "string", "enum": [v.value for v in values]}


def wire_schema() -> dict[str, Any]:
    """JSON Schema sent to the model, derived from the C2 enums.

    Flat (no oneOf/$defs, every field required, unused ones null) because that is the
    subset strict structured output accepts across providers; `to_contract` maps it back
    to the discriminated C2 GroundingResult, which is what gets validated.
    """
    props = {
        "kind": {"type": "string", "enum": ["intent", "clarification", "unsupported"]},
        "action": _nullable(_enum(Action)),
        "controlledProperty": _nullable({"type": "string"}),
        "scope": _nullable(_enum(Scope)),
        "persistence": _nullable(_enum(Persistence)),
        "confidence": _nullable({"type": "number"}),
        "targetZoneId": _nullable({"type": "string"}),
        "value": _nullable({"type": "number"}),
        "question": _nullable({"type": "string"}),
        "reason": _nullable(
            {
                "type": "string",
                "enum": [r.value for r in _MODEL_CLARIFICATION_REASONS]
                + [r.value for r in UnsupportedReason],
            }
        ),
    }
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


WIRE_SCHEMA = wire_schema()
_INTENT_FIELDS = ("action", "controlledProperty", "scope", "persistence", "confidence")
_OPTIONAL_INTENT_FIELDS = ("targetZoneId", "value")  # omitted from the contract when null


def to_contract(data: Any) -> dict[str, Any]:
    """Flat wire object -> C2 GroundingResult dict. Unknown keys are an error (the schema
    is strict); the null fields of the other kinds are dropped."""
    if not isinstance(data, dict):
        raise ValueError("the answer must be a JSON object")
    unknown = sorted(set(data) - set(WIRE_SCHEMA["properties"]))
    if unknown:
        raise ValueError(f"unknown fields {unknown}")
    kind = data.get("kind")
    if kind == "intent":
        intent = {f: data.get(f) for f in _INTENT_FIELDS}
        intent |= {f: data[f] for f in _OPTIONAL_INTENT_FIELDS if data.get(f) is not None}
        return {"kind": kind, "intent": intent}
    if kind == "clarification":
        return {"kind": kind, "question": data.get("question"), "reason": data.get("reason")}
    if kind == "unsupported":
        return {"kind": kind, "reason": data.get("reason")}
    raise ValueError(f"unknown kind {kind!r}")


SYSTEM_PROMPT = PROMPTS[PROMPT_VERSION]  # the default prompt (prompts.py)


def build_messages(
    request: GroundingRequest, system_prompt: str = SYSTEM_PROMPT
) -> list[dict[str, str]]:
    """System rules + the request as one JSON document (the user's text is a string value)."""
    data = {
        "request": request.text,
        "language": request.language,
        "zone": {
            "zoneId": request.zone.zone_id,
            "previousZoneId": request.zone.previous_zone_id,
        },
        "catalogue": [
            {
                "zoneId": z.zone_id,
                "devices": [
                    {
                        "deviceId": d.device_id,
                        "category": d.category,
                        "controlledProperty": d.controlled_property,
                        "supportedCommand": d.supported_command,
                    }
                    for d in z.devices
                ],
            }
            for z in request.catalogue
        ],
        "adjacency": request.adjacency,
        "history": request.history,
    }
    # Zone confidence and observation time are left out on purpose: the engine already
    # gated on the confidence, and the timestamp would defeat the cache.
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
    ]


@dataclass
class Attempt:
    content: str | None
    error: str | None  # None = valid


@dataclass
class GroundingTrace:
    """What happened in the last ground() call (for the evaluation and the try script)."""

    attempts: list[Attempt] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_s: float = 0.0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str | None = None
    provider: str | None = None


class LLMGrounder:
    def __init__(
        self,
        client: OpenRouterClient,
        temperature: float = 0.0,
        max_retries: int = 2,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self.client, self.temperature, self.max_retries = client, temperature, max_retries
        self.prompt_version, self.system_prompt = prompt_version, PROMPTS[prompt_version]
        self.repeat = 0  # repetition index, set by the evaluation runner (Stability)
        self.last_trace = GroundingTrace()

    def ground(self, request: GroundingRequest) -> GroundingResult:
        self.last_trace = trace = GroundingTrace()
        if request.zone.zone_id not in request.catalogue_zones():
            return UnsupportedResult(reason=UnsupportedReason.OUT_OF_SCOPE)

        context = {"catalogue_properties": request.catalogue_properties()}
        messages = build_messages(request, self.system_prompt)
        off_catalogue = False
        for attempt in range(1, self.max_retries + 2):
            try:
                response = self.client.chat(
                    messages,
                    WIRE_SCHEMA,
                    schema_name=SCHEMA_NAME,
                    temperature=self.temperature,
                    attempt=attempt,
                    repeat=self.repeat,
                )
            except LLMCallError as e:
                trace.attempts.append(Attempt(None, f"service: {e}"))
                return ClarificationResult(
                    question="Sorry, I cannot process requests right now. Please try again.",
                    reason=ClarificationReason.SERVICE_UNAVAILABLE,
                )
            trace.cost_usd += response.cost_usd
            trace.latency_s += response.latency_s
            trace.cache_hits += response.cache_hit
            trace.prompt_tokens += response.prompt_tokens
            trace.completion_tokens += response.completion_tokens
            trace.model, trace.provider = response.model, response.provider
            try:
                data = to_contract(json.loads(response.content))
                result = GroundingResultAdapter.validate_python(data, context=context)
            except (ValueError, ValidationError) as e:  # JSONDecodeError is a ValueError
                error = _short_error(e)
                off_catalogue = "not in the capability catalogue" in error
                trace.attempts.append(Attempt(response.content, error))
                messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {
                        "role": "user",
                        "content": f"Your answer was invalid: {error}. Answer again with "
                        "one JSON object that follows the schema and the rules.",
                    },
                ]
                continue
            trace.attempts.append(Attempt(response.content, None))
            return _check_target_zone(result, request)

        if off_catalogue:  # the model kept asking for a property no device offers
            return UnsupportedResult(reason=UnsupportedReason.CAPABILITY_ABSENT)
        return ClarificationResult(
            question="Sorry, I did not understand. Could you rephrase that?",
            reason=ClarificationReason.INVALID_OUTPUT,
        )


def _check_target_zone(result: GroundingResult, request: GroundingRequest) -> GroundingResult:
    """targetZoneId: dropped if it is the current zone, out_of_scope if not catalogued."""
    if not isinstance(result, IntentResult) or result.intent.target_zone_id is None:
        return result
    target = result.intent.target_zone_id
    if target == request.zone.zone_id:  # "present only if different from the current zone"
        return IntentResult(intent=result.intent.model_copy(update={"target_zone_id": None}))
    if target not in request.catalogue_zones():
        return UnsupportedResult(reason=UnsupportedReason.OUT_OF_SCOPE)
    return result


def _short_error(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
        )
    if isinstance(e, json.JSONDecodeError):
        return f"not valid JSON ({e.msg})"
    return str(e)
