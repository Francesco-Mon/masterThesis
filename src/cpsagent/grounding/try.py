"""Ground one request with Grounder A and show the result, cost, latency and provider.

Run: python -m cpsagent.grounding.try "it's too dark here" --zone hallway \
         [--previous lobby] [--model openai/gpt-oss-120b] [--language en]

The catalogue and adjacency come from the emulated building (data/scenario.yaml), bound
exactly as the engine binds it. Calls go through the cache and the call log
(results/llm_calls.jsonl), so repeating the same command costs nothing.
"""

import argparse
import json
from datetime import UTC, datetime

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import GroundingRequest, GroundingResultAdapter, ZoneEstimate
from cpsagent.environment import EmulatedEnvironment
from cpsagent.grounding.llm import LLMGrounder, default_model
from cpsagent.grounding.openrouter import OpenRouterClient


def build_request(text: str, zone: str, previous: str | None, language: str) -> GroundingRequest:
    env = EmulatedEnvironment()
    session = EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")
    return GroundingRequest(
        text=text,
        language=language,
        # fixed time: the grounder does not send it, but keep the request reproducible
        zone=ZoneEstimate(
            zone_id=zone,
            confidence=0.9,
            observed_at=datetime(2026, 11, 10, 9, 30, tzinfo=UTC),
            previous_zone_id=previous,
        ),
        catalogue=session.catalogue,
        adjacency=session.spatial_model.adjacency,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("text")
    parser.add_argument("--zone", default="hallway")
    parser.add_argument("--previous", default=None, help="zone the user came from")
    parser.add_argument("--model", default=None)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    grounder = LLMGrounder(OpenRouterClient(args.model or default_model()))
    result = grounder.ground(build_request(args.text, args.zone, args.previous, args.language))
    t = grounder.last_trace
    print(GroundingResultAdapter.dump_json(result, exclude_none=True).decode())
    print(
        json.dumps(
            {
                "model": t.model,
                "provider": t.provider,
                "attempts": len(t.attempts),
                "errors": [a.error for a in t.attempts if a.error],
                "cacheHits": t.cache_hits,
                "costUsd": t.cost_usd,
                "latencyS": round(t.latency_s, 3),
            }
        )
    )


if __name__ == "__main__":
    main()
