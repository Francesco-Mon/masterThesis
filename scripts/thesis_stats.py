"""Statistics of Chapter 7 that are not in the per-run reports.

Run from the repository root: python scripts/thesis_stats.py
Needs the package installed (pip install -e .) and scipy.

Test split: majority answer of the three repeats of each language model (Wilson
intervals on 156 requests), mean over repeats, exact McNemar tests, accuracy by
category, source and language, correctness of the commands issued, predictions
below the intent threshold, repeatability. Development split: Fisher's exact test of
the keyword baseline, development against test. Call log: tokens per call of the test
runs and latency of the calls of the load runs.
"""
import collections
import json
import statistics as st
from pathlib import Path

from scipy.stats import binomtest, fisher_exact

from cpsagent.contracts import GroundingResultAdapter, IntentResult
from cpsagent.eval.dataset import bind_scenario, from_repo, load_cases
from cpsagent.eval.metrics import score
from cpsagent.eval.report import normalized, wilson

FINAL = Path("results/final")
TEST_RUNS = {
    "keyword": "20261121-131024_keyword_keyword_test",
    "embedding": "20261121-131024_embedding_embedding_test",
    "nemotron": "20261121-152330_llm_nvidia-nemotron-3.5-super-vl-free_test",
    "gpt-oss-120b": "20261121-154439_llm_openai-gpt-oss-120b_test_deepinfra",
    "mistral-large-4": "20261121-155508_llm_mistralai-mistral-large-4-0_test",
}
THETA = 0.6


def pct(h, n):
    lo, hi = wilson(h, n)
    return f"{100 * h / n:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}] ({h}/{n})"


def mcnemar(a, b):
    only_a = sum(1 for i in a if a[i] and not b[i])
    only_b = sum(1 for i in a if b[i] and not a[i])
    p = binomtest(only_a, only_a + only_b, 0.5).pvalue if only_a + only_b else 1.0
    return only_a, only_b, p


session = bind_scenario()
per_run = {}
for g, d in TEST_RUNS.items():
    meta = json.loads((FINAL / d / "run.json").read_text())
    cases = {c.id: c for c in load_cases(from_repo(meta["dataset"]))[0]}
    per = collections.defaultdict(list)
    for line in (FINAL / d / "predictions.jsonl").read_text().splitlines():
        rec = json.loads(line)
        pred = GroundingResultAdapter.validate_python(rec["prediction"])
        per[rec["id"]].append(score(cases[rec["id"]], rec["repeat"], pred, session))
    per_run[g] = per

maj = {}
print("== Test split (majority answer; Wilson 95% on 156 requests) ==")
for g, per in per_run.items():
    ids = sorted(per)
    n = len(ids)
    ms = {i: sum(s.strict for s in per[i]) * 2 > len(per[i]) for i in ids}
    mo = {i: sum(s.outcome_ok for s in per[i]) * 2 > len(per[i]) for i in ids}
    maj[g] = (ms, mo)
    all_s = [s for i in ids for s in per[i]]
    print(f"\n{g} (repeats: {len(per[ids[0]])})")
    print("  strict ", pct(sum(ms.values()), n), f" mean over repeats {100 * sum(s.strict for s in all_s) / len(all_s):.1f}%")
    print("  outcome", pct(sum(mo.values()), n), f" mean over repeats {100 * sum(s.outcome_ok for s in all_s) / len(all_s):.1f}%")
    for key in ("category", "source", "language"):
        groups = collections.defaultdict(list)
        for i in ids:
            groups[getattr(per[i][0].case, key)].append(ms[i])
        print(f"  strict by {key}:", ", ".join(f"{k} {sum(v)}/{len(v)}" for k, v in sorted(groups.items())))
    acting = [s for s in all_s if not isinstance(s.out, str) and len(s.out) > 0]
    print(f"  commands right when acting: {100 * sum(s.outcome_ok for s in acting) / len(acting):.1f}% of {len(acting)} predictions")
    low = sum(1 for s in all_s if isinstance(s.pred, IntentResult) and s.pred.intent.confidence < THETA)
    print(f"  intents below theta={THETA}: {low}")
    if len(per[ids[0]]) > 1:
        same = sum(1 for i in ids if len({normalized(s.pred) for s in per[i]}) == 1)
        print(f"  repeatability (all repeats identical): {100 * same / n:.1f}% ({same}/{n})")

print("\n== Exact McNemar tests (majority answers) ==")
for k, name in ((0, "strict"), (1, "outcome")):
    for g in TEST_RUNS:
        if g != "keyword":
            a, b, p = mcnemar(maj["keyword"][k], maj[g][k])
            print(f"  {name}: keyword only {a}, {g} only {b}, p = {p:.4f}")
for g1, g2 in (("mistral-large-4", "nemotron"), ("mistral-large-4", "gpt-oss-120b"), ("nemotron", "gpt-oss-120b")):
    a, b, p = mcnemar(maj[g1][0], maj[g2][0])
    print(f"  strict: {g1} only {a}, {g2} only {b}, p = {p:.4f}")

print("\n== Keyword baseline, development against test (strict) ==")
dev = json.loads(next(Path("results").glob("*_keyword_keyword_dev/run.json")).read_text())
dev_dir = Path("results") / dev["runId"]
dev_cases = {c.id: c for c in load_cases(from_repo(dev["dataset"]))[0]}
dev_ok = [score(dev_cases[r["id"]], r["repeat"], GroundingResultAdapter.validate_python(r["prediction"]), session).strict
          for r in map(json.loads, (dev_dir / "predictions.jsonl").read_text().splitlines())]
test_ok = list(maj["keyword"][0].values())
table = [[sum(dev_ok), len(dev_ok) - sum(dev_ok)], [sum(test_ok), len(test_ok) - sum(test_ok)]]
print(f"  dev {table[0][0]}/{len(dev_ok)}, test {table[1][0]}/{len(test_ok)}, Fisher p = {fisher_exact(table).pvalue:.3f}")

print("\n== Call log ==")
calls = [json.loads(l) for l in open("results/llm_calls.jsonl")]
def summary(run_id):
    ok = [c for c in calls if c["runId"] == run_id and c["status"] == "ok" and not c["cacheHit"]]
    return ok, (f"{len(ok)} calls, prompt {st.mean(c['promptTokens'] for c in ok):.0f}, completion "
                f"{st.mean(c['completionTokens'] for c in ok):.0f} tokens per call (max {max(c['completionTokens'] for c in ok)}), "
                f"latency median {st.median(c['latencyS'] for c in ok):.1f} s, providers {sorted({c['provider'] for c in ok})}")
for g, d in TEST_RUNS.items():
    meta = json.loads((FINAL / d / "run.json").read_text())
    if meta.get("callsLogRunId"):
        print(f"  test, {g}: {summary(meta['callsLogRunId'])[1]}")
for p in sorted(Path("results/load").glob("closed_memory_llm_*/metadata.json")):
    run_id = json.loads(p.read_text()).get("callsLogRunId")
    if run_id:
        print(f"  load, {p.parent.name}: {summary(run_id)[1]}")
