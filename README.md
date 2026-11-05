# cps-agent

Prototype for the master's thesis
**"Techniques for Autonomous Resource Orchestration for CPS Mediated by Agentic AI"**.

A *Person Agent* mediates between a user (voice or text) and an intelligent environment (a smart
building). The thesis defines the full architecture; this repository implements a **reduced,
emulated version** of it and evaluates one component in depth: **Intent Grounding**, the step
that turns a natural-language request into a structured intent checked against the building's
capability catalogue.

Reference scenario, "follow the user with light": the user says something implicit such as
*"I want to walk in the light"*; the agent knows the user's zone from localization, grounds the
request to a `StructuredIntent`, plans guarded steps (hallway lamp now, corridor lamp on arrival),
executes them through the Environment Interface, re-plans when the user moves and logs every
transition in a verifiable event log.

## What is implemented

- **Emulated environment** (`Building`, `Zone`, `Device`, `PositioningSignal`, as in thesis Ch. 5)
  and a mobility simulator along scripted paths; zone-level localization with hysteresis.
- **Orchestration Engine**: an explicit state machine
  Perceive -> Interpret -> Plan -> Act -> Observe -> [Recover], with bounded steps and retries.
- **Intent Grounding** behind one interface, with interchangeable candidates:
  - `llm`: LLM through OpenRouter with structured output, Pydantic validation and bounded retry;
  - `embedding`: sentence-embedding matching against the capability descriptions (no training);
  - `keyword`: a rule-based baseline;
  - `fake`: deterministic and scriptable, used by the offline tests.
- **Event log**: JSONL records with salted commitments, a hash chain and a verifier.
  Ledger anchoring is designed in the thesis but not implemented here.
- **Streamlit UI** with local speech-to-text (faster-whisper).
- **Evaluation**: labelled request set, runner and CLASSic metrics (Cost, Latency, Accuracy,
  Security, Stability); speech-to-text latency is measured separately from grounding.

## Repository layout

```
docs/
  SPEC.md                 entities, binding, action interface, state machine, event record
  CONTRACTS.md            the four contracts between components, with JSON examples
  EVAL_POLICY.md          how the evaluation set is labelled and scored
  DECISIONS.md            design decisions: what, why, alternatives dropped
  schemas/                JSON Schemas exported from the contracts
src/cpsagent/
  contracts/              Pydantic models of the contracts (single source of truth)
  environment/            emulated building, devices, commands, mobility simulator
  localization/           zone estimator
  binding/                Environment Binding: enumeration and capability catalogue
  interface/              Environment Interface: the allowed operations and allow-list
  grounding/              grounder interface and candidates (llm, embedding, keyword, fake)
  engine/                 state machine, planner, guards
  eventlog/               record builder, commitments, hash chain, store, verifier
  ui/                     Streamlit app, speech-to-text wrapper, clip recorder
  eval/                   dataset loader, runner, metrics, reports, STT measurement
  demo.py, demo_agent.py  command-line demos
tests/                    offline test suite (mirrors src/)
data/                     scenario.yaml, evaluation set, STT sentence sets
results/                  raw outputs of the runs (JSONL) and the tables derived from them
```

## Installation

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui,embeddings]"
cp .env.example .env               # then set OPENROUTER_API_KEY (needed only for real LLM calls)
```

The core (`pip install -e .`) includes the OpenRouter client and runs the demos and the
evaluation runner. The extras are: `dev` (pytest, ruff), `embeddings` (sentence-transformers),
`ui` (Streamlit, faster-whisper, audio I/O). `pip install -e ".[dev]"` is enough for the offline
test suite: the tests that need an extra are skipped without it. Installing the extras downloads
packages only, not models.

The `.env` file is git-ignored; the key is read from the environment and never printed or logged.
The first use of the embedding model and of the speech model (`Systran/faster-whisper-small`)
downloads them into the Hugging Face cache, outside the repository.

## Running

Run all commands from the repository root with the virtual environment active.

| What | Command |
|---|---|
| Offline tests (no network, no real model) | `pytest` |
| Tests with the real LLM (key + network) | `pytest -m live` |
| Tests with the real embedding model | `pytest -m embeddings` |
| Tests with the real speech-to-text model | `pytest -m stt` |
| Lint | `ruff check .` |
| Demo: binding, catalogue, localization, interface | `python -m cpsagent.demo` (or `--path doorway_linger --seed 3`) |
| Demo: engine + event log ("I want to walk in the light") | `python -m cpsagent.demo_agent` (log in `logs/demo_agent.jsonl`) |
| Ground a single request with the LLM | `python -m cpsagent.grounding.try "it's too dark here" --zone hallway` |
| Evaluation run of a grounder | `python -m cpsagent.eval.run --grounder keyword\|embedding\|llm --split dev` |
| Rebuild the tables of a saved run | `python -m cpsagent.eval.report results/RUN_ID` |
| STT measurement on synthetic audio (macOS `say`) | `python -m cpsagent.eval.stt` |
| Record clips for the STT measurement | `python -m cpsagent.ui.record_clips` |
| STT measurement on recorded clips | `python -m cpsagent.eval.stt --source recorded` |
| Re-export the JSON Schemas | `python -m cpsagent.contracts.export_schemas` |
| **Streamlit UI** | `streamlit run src/cpsagent/ui/app.py` |

By default `pytest` excludes the `live`, `embeddings` and `stt` markers, so the suite runs
offline using the fake grounder and stub transports.

### Streamlit UI

`streamlit run src/cpsagent/ui/app.py` opens the page at http://localhost:8501.

- **Sidebar, Agent**: grounder (keyword, embedding, or LLM with an OpenRouter model id),
  speech language, start zone, "New session".
- **Sidebar, Movement**: walk to a zone along the adjacency, or play a scripted path tick by tick.
  The true position is shown; the agent only sees the localization estimate.
- **Chat**: type a request, record it with the microphone, or upload an audio file. Each turn
  shows the transcript (with STT latency), the zone estimate, the intent or the reason there is
  none, the plan, the commands sent and the reply; moving shows the re-planning.
- **Panels**: device states, the event chain and its verification. UI logs go to `logs/`
  (git-ignored).

## Data and results

- `data/scenario.yaml` is the building every test, demo and evaluation refers to.
- `data/requests.jsonl` is the evaluation set (210 cases, English and Italian), labelled with the
  rules in `docs/EVAL_POLICY.md`: a **dev split** (54 cases) used for development and tuning, and a
  **test split** (156 cases, including 30 requests written by the author) that is **frozen**:
  prompts, thresholds and baselines were chosen on dev only, and test is reserved for the final run.
- `results/` holds the raw outputs of each run (`run.json` with model id, provider, temperature,
  split and commit; per-case predictions; summary and error tables) and `llm_calls.jsonl`, one line
  per LLM call with latency, tokens and cost as reported by OpenRouter. Every table in `results/`
  is regenerated from these files; no figure is estimated by hand.

## AI assistance

Parts of the code, of the documentation and of the evaluation set were developed with the help of
AI tools. Of the 210 evaluation requests in `data/requests.jsonl`, 180 were generated with a
language model (150 English requests and their 30 Italian paraphrases, `source: llm`); the other
30 were written by hand by the author and are marked `source: human`. The thesis describes in
detail how these tools were used.
