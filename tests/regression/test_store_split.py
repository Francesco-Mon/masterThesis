"""Regression against the baseline taken before the environment was split into its control
logic and an entity store.

With the in-memory store, a run of each scripted path (keyword grounder, two seeds) must
give the same transition records, replies, zone changes, triggers, restorations, number of
forwarded signals and device states as `store_baseline.json`, recorded with the previous
code. The GroundingRequests, the dev predictions and the zone-change events are compared
with `baseline.json` by the other regression tests.
"""

import json
from pathlib import Path

import pytest

from cpsagent.bench.scenario import run_scenario
from cpsagent.environment import EmulatedEnvironment
from cpsagent.grounding.keyword import KeywordGrounder

BASELINE = json.loads((Path(__file__).parent / "store_baseline.json").read_text("utf-8"))


@pytest.mark.parametrize("key", sorted(BASELINE["runs"]))
def test_scenario_run_matches_the_baseline(key):
    path, seed = key.split("/")
    env = EmulatedEnvironment(interpreter=KeywordGrounder())
    got = run_scenario(env, path, seed=int(seed)).behaviour()
    assert json.loads(json.dumps(got)) == BASELINE["runs"][key]
