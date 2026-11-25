# Fresh set: the grounders on 60 held-out requests

The keyword baseline's vocabulary was written knowing the vocabulary of `data/requests.jsonl`,
test split included, so its accuracy on that split is not a held-out measure. This folder
holds the runs of every grounder on a second, independent test set written after all
grounders were frozen.

## How the set was produced

- **Generator**: Google Gemini 4 Hydrogen, through Google AI Studio, default settings, one
  request and one answer on 25 November 2026. No model of this family was used anywhere else
  in the project. The generator saw only a description of the building (zones, adjacency,
  devices and their commands, what nothing in the building can do) and of the ten
  categories, without access to the repository, its sets or its grounders. The prompt, with
  when and how it was given, is in `docs/fresh_set_prompt.md`.
- **Raw answer**: `data/fresh/gemini_raw.jsonl`, unchanged.
- **Set**: `data/fresh/requests_fresh.jsonl`, the same 60 requests (6 per category, 4 in
  English and 2 in Italian) in the format of `data/requests.jsonl`, `split = "test"`,
  `source = "llm"`. Texts, zones and categories are the generator's, unchanged. The gold
  labels were assigned by the author with `docs/EVAL_POLICY.md` **before any grounder was run
  on the set**. SHA-256
  `d9d844afd5805e970c12778a632e48efeca95720d886dbf20e457261c5dfe2b5`, checked before the
  runs; each `run.json` records its first 16 hex digits (`datasetSha256`). Gold kinds: 33
  intents, 10 clarifications, 17 unsupported.

## Runs

Same settings as the final test runs in `results/final/` (prompt v3, prompt hash
`79825ef66d95b2e3`, schema hash `d00987ca62e50c53`, temperature 0, no response cache for the
language models, 3 repeats for them and 1 run for keyword and embedding, embedding threshold
0.40 and margin 0.0), code at commit `790ef61`. 58 of the 60 cases are in an in-scope zone;
the 2 said in the server room are answered without a call, so each language-model run made
174 first-attempt calls.

| grounder | run id | calls | cost (USD) |
|---|---|---|---|
| keyword | `20261125-141822_keyword_keyword_test` | 0 | 0 |
| embedding | `20261125-141822_embedding_embedding_test` | 0 | 0 |
| nemotron (`nvidia/nemotron-3.5-super-vl:free`, not pinned, served by Nvidia) | `20261125-142031_llm_nvidia-nemotron-3.5-super-vl-free_test` | 174, all ok | 0 |
| gpt-oss-120b (`openai/gpt-oss-120b`, pinned to DeepInfra) | `20261125-141858_llm_openai-gpt-oss-120b_test_deepinfra` | 174 + 165 retried, 165 HTTP 429 | 0.020 |
| mistral-large-4 (`mistralai/mistral-large-4-0`, pinned to `mistral/zdr`) | `20261125-142031_llm_mistralai-mistral-large-4-0_test` | 174, all ok | 0.516 |

Total 0.536 USD. Every call is in `results/llm_calls.jsonl`.

Command (the output folder given so the runs land here):

```bash
python -m cpsagent.eval.run --grounder keyword --split test --final \
  --data data/fresh/requests_fresh.jsonl --out results/fresh/RUN_ID
python -m cpsagent.eval.run --grounder embedding --split test --final \
  --data data/fresh/requests_fresh.jsonl --out results/fresh/RUN_ID
python -m cpsagent.eval.run --grounder llm --model MODEL [--provider PROVIDER] --split test --final \
  --data data/fresh/requests_fresh.jsonl --prompt v3 --temperature 0 --no-cache --repeats 3 \
  --yes --max-cost CAP --out results/fresh/RUN_ID
```

Caps: 0.3 USD for gpt-oss-120b, 1.5 for mistral-large-4, 0.1 for nemotron (total under 2
USD; estimated beforehand at 0.59 USD from the measured cost per call).

Notes on the runs:

- **Rate limiting on DeepInfra.** 83 of the 174 calls of gpt-oss-120b got HTTP 429 from the
  pinned provider (scattered at first, then almost every call after 15:10 UTC), which the
  runner records as `service_unavailable`, an infrastructure failure and not a grounding
  answer. They were re-grounded with the runner's own `--retry-failed`, which uses the
  settings of `run.json` (same model, provider, prompt, temperature, no cache): at 15:23 UTC
  (13 of 83 recovered), 15:50 (58 of 70) and 16:08 (12 of 12). No record is left as
  `service_unavailable`; `run.json` lists every retried record (`retriedFailed`), and the
  retries' calls are in the call log under their own run ids (`2a3923cc5a31`,
  `9d7b8aa1e925`, `85cc4d222ef4`; the run's own is `9ad470c2db0d`). Unlike the 5 empty
  responses of the final gpt-oss-120b test run, which were left unretried, these calls never
  reached the model.
- The three language-model runs ran at the same time, each on a different provider (no
  provider served two runs at once). Time windows (UTC, 25 Nov 2026): nemotron 14:20 to
  14:47, mistral-large-4 14:20 to 15:39, gpt-oss-120b 14:19 to 15:22 plus the retries.
- All 174 calls of mistral-large-4 were served by `mistral/zdr`: each call's cost matches its
  price (0.70 / 2.10 USD per M input/output tokens, with 0, 1024 or 1536 prompt tokens
  charged at a tenth by the provider's own prompt cache).
- No `metadata.json`: the runner was called directly, not through `cpsagent.bench.record`.
  `run.json` records settings, hashes and commit; the machine and library versions are those
  of the final runs.

## Results

Computed by `python scripts/thesis_stats.py` (section "Fresh set"). For the language models
the case's answer is the **majority answer of its three repeats**; intervals are Wilson 95% on
60 requests. "Commands right when acting" counts every prediction (all repeats) whose outcome
contains at least one command.

### Accuracy

| grounder | strict (majority) | outcome (majority) | strict, mean over repeats | outcome, mean over repeats | commands right when acting |
|---|---|---|---|---|---|
| keyword | 73.3% [61.0, 82.9] (44/60) | 76.7% [64.6, 85.6] (46/60) | 73.3% | 76.7% | 80.0% of 30 |
| embedding | 56.7% [44.1, 68.4] (34/60) | 61.7% [49.0, 72.9] (37/60) | 56.7% | 61.7% | 60.6% of 33 |
| nemotron | 96.7% [88.6, 99.1] (58/60) | 98.3% [91.1, 99.7] (59/60) | 96.1% | 97.8% | 97.1% of 102 |
| gpt-oss-120b | 91.7% [81.9, 96.4] (55/60) | 100.0% [94.0, 100.0] (60/60) | 90.6% | 98.9% | 98.9% of 95 |
| mistral-large-4 | 96.7% [88.6, 99.1] (58/60) | 100.0% [94.0, 100.0] (60/60) | 96.1% | 99.4% | 100.0% of 95 |

### By category and language (strict / outcome, majority answers)

| group | n | keyword | embedding | nemotron | gpt-oss-120b | mistral-large-4 |
|---|---|---|---|---|---|---|
| explicit | 6 | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 |
| explicit_other_zone | 6 | 5 / 5 | 5 / 5 | 6 / 6 | 6 / 6 | 6 / 6 |
| implicit | 6 | 4 / 5 | 2 / 3 | 6 / 6 | 6 / 6 | 6 / 6 |
| zone_dependent | 6 | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 |
| following | 6 | 3 / 3 | 3 / 3 | 6 / 6 | 5 / 6 | 6 / 6 |
| environment | 6 | 6 / 6 | 3 / 3 | 6 / 6 | 6 / 6 | 6 / 6 |
| ambiguous | 6 | 3 / 3 | 2 / 3 | 6 / 6 | 6 / 6 | 6 / 6 |
| unsupported | 6 | 6 / 6 | 2 / 2 | 4 / 5 | 4 / 6 | 5 / 6 |
| out_of_scope | 6 | 3 / 3 | 3 / 4 | 6 / 6 | 6 / 6 | 6 / 6 |
| adversarial | 6 | 2 / 3 | 2 / 2 | 6 / 6 | 4 / 6 | 5 / 6 |
| English | 40 | 30 / 32 | 23 / 26 | 38 / 39 | 36 / 40 | 38 / 40 |
| Italian | 20 | 14 / 14 | 11 / 11 | 20 / 20 | 19 / 20 | 20 / 20 |

### Exact McNemar tests against the keyword baseline (majority answers)

"keyword only" = cases right for the keyword baseline and wrong for the other grounder, and
the other way round.

| grounder | strict: keyword only / other only, p | outcome: keyword only / other only, p |
|---|---|---|
| embedding | 10 / 0, p = 0.0020 | 10 / 1, p = 0.0117 |
| nemotron | 2 / 16, p = 0.0013 | 1 / 14, p = 0.0010 |
| gpt-oss-120b | 3 / 14, p = 0.0127 | 0 / 14, p = 0.0001 |
| mistral-large-4 | 1 / 15, p = 0.0005 | 0 / 14, p = 0.0001 |

### Keyword baseline: fresh set against the test split

| set | strict |
|---|---|
| test split of `data/requests.jsonl` | 143/156 (91.7%) |
| fresh set | 44/60 (73.3%) |

Fisher's exact test: p = 0.001. For comparison, strict accuracy (majority) on the test split
against the fresh set: embedding 78.2% against 56.7%, nemotron 88.5% against 96.7%,
gpt-oss-120b 82.7% against 91.7%, mistral-large-4 90.4% against 96.7% (test-split figures
from the same script). The two sets are different samples (different generator, 60 cases
against 156), so only the keyword baseline is tested across them.
