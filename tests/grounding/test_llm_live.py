"""Grounder A against the real OpenRouter API: 6 sample requests x 2 models.

Skipped by default; run with: pytest -m live tests/grounding/test_llm_live.py
Needs OPENROUTER_API_KEY in .env. Calls are cached in .llm_cache/ (a rerun costs
nothing) and logged in results/llm_calls.jsonl.
"""

import importlib

import pytest

from cpsagent.contracts import ClarificationResult, IntentResult, UnsupportedResult
from cpsagent.grounding.llm import LLMGrounder
from cpsagent.grounding.openrouter import OpenRouterClient

pytestmark = pytest.mark.live

build_request = importlib.import_module("cpsagent.grounding.try").build_request

# Development models (DECISIONS.md, "Development models").
MODELS = ["openai/gpt-oss-120b", "nvidia/nemotron-3.5-super-vl:free"]


def intent(result, **expected):
    assert isinstance(result, IntentResult), result
    got = result.intent.model_dump(by_alias=False)
    assert {k: got[k] for k in expected} == expected, got


# (category, text, zone, previous, check)
CASES = [
    (
        "explicit",
        "turn on the lamp in the hallway",
        lambda r: intent(
            r,
            action="activate",
            controlled_property="light",
            scope="current_zone",
            target_zone_id=None,
        ),
    ),
    (
        "explicit_other_zone",
        "turn on the kitchen light",
        lambda r: intent(
            r,
            action="activate",
            controlled_property="light",
            scope="current_zone",
            target_zone_id="kitchen",
        ),
    ),
    (
        "implicit",
        "it's too dark here",
        lambda r: intent(r, controlled_property="light", scope="current_zone"),
    ),
    (
        "contextual",
        "I want to walk in the light",
        lambda r: intent(
            r,
            action="activate",
            controlled_property="light",
            scope="path",
            persistence="following",
        ),
    ),
    (
        "unsupported",
        "play some music",
        lambda r: isinstance(r, UnsupportedResult) or pytest.fail(repr(r)),
    ),
    (
        "ambiguous",
        "make it warmer",
        lambda r: isinstance(r, ClarificationResult) or pytest.fail(repr(r)),
    ),
]


@pytest.fixture(scope="module", params=MODELS)
def grounder(request):
    return LLMGrounder(OpenRouterClient(request.param))


@pytest.mark.parametrize(("category", "text", "check"), CASES, ids=[c[0] for c in CASES])
def test_sample_request(grounder, category, text, check):
    result = grounder.ground(build_request(text, "hallway", "lobby", "en"))
    check(result)
