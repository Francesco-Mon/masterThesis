"""The prompt of the final run is frozen (and the older versions stay as they were).

If this test fails, the prompt text changed. Do not just update the constant: a change
to the frozen prompt needs an explicit decision in docs/DECISIONS.md (what, why, which
results it invalidates), and only then the new hash goes here.
"""

import hashlib

from cpsagent.grounding.llm import SYSTEM_PROMPT
from cpsagent.grounding.prompts import PROMPT_VERSION, PROMPTS

FROZEN_VERSION = "v3"
FROZEN_SHA256 = {
    "v1": "6552f9af276e7d3b2eec968c95ad137fdddbf8d049bb712702b3f61d5ffd460d",
    "v2": "ed79f0d9ef604551ffc3fde50c38afa399017ad4eba3f657414b4be64c5fd1ad",
    "v3": "79825ef66d95b2e36da8bd767b8bc2d98bc7520416aa986134f75b32d16fdfd8",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_frozen_prompt_is_the_default_and_unchanged():
    assert PROMPT_VERSION == FROZEN_VERSION
    assert sha(SYSTEM_PROMPT) == FROZEN_SHA256[FROZEN_VERSION]


def test_older_versions_unchanged_for_the_ablation():
    assert {v: sha(t) for v, t in PROMPTS.items()} == FROZEN_SHA256
