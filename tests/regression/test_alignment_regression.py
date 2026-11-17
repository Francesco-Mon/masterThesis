"""Regression against the baseline taken before the environment took control of discovery.

The binding protocol changed (no catalogue at binding, the environment follows the person
and enforces the scope), but the frozen evaluation must not notice: the zone-change events
of the scripted paths, the GroundingRequest of every dataset case and the offline dev
predictions are compared with `baseline.json`, recorded with the previous code.
"""

import hashlib
import json
from pathlib import Path

import pytest

from cpsagent.binding import EnvironmentBinding
from cpsagent.contracts import GroundingResultAdapter
from cpsagent.environment import EmulatedEnvironment
from cpsagent.environment.mobility import MobilitySimulator
from cpsagent.eval.dataset import bind_scenario, load_cases
from cpsagent.eval.run import build_request
from cpsagent.localization import ZoneEstimator

BASELINE = json.loads((Path(__file__).parent / "baseline.json").read_text(encoding="utf-8"))


def zone_events(path: str) -> list[list]:
    """(zone, previous zone, tick) of every R6 event, wired as the demos and the UI do."""
    env = EmulatedEnvironment()
    sim = MobilitySimulator(env.scenario, path, seed=0)
    tick_of = {t.time: t.index for t in sim.ticks()}
    binding = EnvironmentBinding({env.endpoint: env})
    session = binding.bind(env.endpoint, "person-agent", sim.subject)
    est = ZoneEstimator(dict(session.known_adjacency), sim.subject)
    session.on_neighbourhood(lambda n: est.add_adjacency(n.adjacency))
    session.subscription.add_listener(est.on_signal)
    events = []
    est.subscribe(
        lambda e: events.append(
            [e.estimate.zone_id, e.estimate.previous_zone_id, tick_of[e.estimate.observed_at]]
        )
    )
    MobilitySimulator(env.scenario, path, seed=0).run(env.publish)
    est.estimate()
    return events


@pytest.mark.parametrize("path", ["walk_in_the_light", "doorway_linger"])
def test_zone_change_events_match_the_baseline(path):
    assert zone_events(path) == BASELINE["zoneEvents"][path]


def _sha(request) -> str:
    data = request.model_dump(mode="json", by_alias=True)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def test_grounding_request_of_every_case_matches_the_baseline():
    cases, errors = load_cases()
    assert errors == []
    session = bind_scenario()
    got = {c.id: _sha(build_request(c, session)) for c in cases}
    assert got == BASELINE["groundingRequestSha256"]


def _dev_predictions(grounder) -> dict:
    cases, _ = load_cases()
    session = bind_scenario()
    out = {}
    for case in (c for c in cases if c.split == "dev"):
        result = grounder.ground(build_request(case, session))
        out[case.id] = GroundingResultAdapter.dump_python(result, mode="json", exclude_none=True)
    return out


def test_keyword_dev_predictions_match_the_baseline():
    from cpsagent.grounding.keyword import KeywordGrounder

    assert _dev_predictions(KeywordGrounder()) == BASELINE["devPredictions"]["keyword"]


@pytest.mark.embeddings
def test_embedding_dev_predictions_match_the_baseline():
    pytest.importorskip("sentence_transformers")
    from cpsagent.grounding.embedding import EmbeddingGrounder, SentenceTransformerEmbedder

    got = _dev_predictions(EmbeddingGrounder(SentenceTransformerEmbedder()))
    assert got == BASELINE["devPredictions"]["embedding"]
