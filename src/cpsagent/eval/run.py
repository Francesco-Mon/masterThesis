"""Evaluation runner: ground every case of one split, save predictions and a summary.

Run:
  python -m cpsagent.eval.run --grounder llm --model openai/gpt-oss-120b --split dev \
      [--provider P] [--repeats N] [--no-cache] [--out results/RUN_ID] [--yes]
  python -m cpsagent.eval.run --grounder llm --model X --split test --final   (final run)
  python -m cpsagent.eval.run --grounder keyword|embedding --split dev   (no LLM)
  python -m cpsagent.eval.run --retry-failed results/RUN_ID   (re-ground the cases that
      ended in clarification/service_unavailable, e.g. a provider's 429, same settings)

Writes to results/RUN_ID/: run.json (settings, model, provider, dataset and prompt
hashes, git commit), predictions.jsonl (one line per case and repeat, with the raw model
answers), summary.md / summary.csv (tables for Chapter 7), errors.md / errors.jsonl.

Guards: the test split is frozen and needs --final (prompt tuning is done on dev only).
Before an LLM run the cost of the uncached calls is estimated from the measured cost per
call of the same model in results/llm_calls.jsonl; above 1 USD the runner asks first.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cpsagent.contracts import GroundingRequest, GroundingResultAdapter

from .dataset import (
    DEFAULT_PATH,
    EvalCase,
    bind_scenario,
    from_repo,
    load_cases,
    repo_relative,
)
from .metrics import score
from .report import write_reports

CONFIRM_ABOVE_USD = 1.0
CALLS_LOG = Path("results/llm_calls.jsonl")


def build_request(case: EvalCase, session) -> GroundingRequest:
    return GroundingRequest(
        text=case.text,
        language=case.language,
        zone=case.zone_estimate(),
        catalogue=session.catalogue,
        adjacency=session.spatial_model.adjacency,
    )


def mean_cost_per_call(model: str, log: Path = CALLS_LOG) -> float | None:
    """Measured mean cost of a real (uncached, successful) call to `model`."""
    if not log.exists():
        return None
    costs = [
        r["costUsd"]
        for r in map(json.loads, log.read_text(encoding="utf-8").splitlines())
        if r.get("requestedModel") == model and r.get("status") == "ok" and not r.get("cacheHit")
    ]
    return sum(costs) / len(costs) if costs else None


def make_grounder(args):
    """(grounder, client or None). Imported lazily: the LLM needs the `llm` extra."""
    if args.grounder == "llm":
        from cpsagent.grounding import openrouter
        from cpsagent.grounding.llm import LLMGrounder

        client = openrouter.OpenRouterClient(
            args.model,
            provider=args.provider,
            cache_dir=None if args.no_cache else openrouter.DEFAULT_CACHE_DIR,
            max_cost_usd=args.max_cost,
        )
        grounder = LLMGrounder(client, temperature=args.temperature, prompt_version=args.prompt)
        return grounder, client
    if args.grounder == "keyword":
        from cpsagent.grounding.keyword import KeywordGrounder

        return KeywordGrounder(), None
    if args.grounder == "embedding":
        from cpsagent.grounding.embedding import EmbeddingGrounder, SentenceTransformerEmbedder

        return EmbeddingGrounder(SentenceTransformerEmbedder()), None
    raise SystemExit(f"unknown grounder {args.grounder!r}")


def estimate_cost(grounder, client, cases, session, repeats) -> tuple[int, float | None]:
    """(uncached first-attempt calls, estimated USD or None if the model was never called).
    Retries are not counted: they are rare and the estimate is only a guard."""
    from cpsagent.grounding.llm import WIRE_SCHEMA, build_messages

    in_scope = {c.zone_id for c in session.catalogue}
    calls = sum(
        not client.is_cached(
            build_messages(build_request(c, session), grounder.system_prompt),
            WIRE_SCHEMA,
            grounder.temperature,
            r,
        )
        for r in range(repeats)
        for c in cases
        if c.zone.zoneId in in_scope  # out-of-scope zones are answered without a call
    )
    per_call = mean_cost_per_call(client.model)
    return calls, None if per_call is None else calls * per_call


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True)
        return out.stdout.decode().strip() or None
    except OSError:
        return None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def predict(grounder, case: EvalCase, session, repeat: int) -> dict[str, Any]:
    """Ground one case; the record keeps the raw answers for the safety metrics."""
    grounder.repeat = repeat
    request = build_request(case, session)
    start = time.perf_counter()
    result = grounder.ground(request)
    wall = time.perf_counter() - start
    record: dict[str, Any] = {
        "id": case.id,
        "repeat": repeat,
        "prediction": GroundingResultAdapter.dump_python(result, mode="json", exclude_none=True),
    }
    trace = getattr(grounder, "last_trace", None)
    if trace is not None:
        record |= {
            "raw": [a.content for a in trace.attempts],
            "attemptErrors": [a.error for a in trace.attempts],
            "calls": len(trace.attempts),
            "cacheHits": trace.cache_hits,
            "costUsd": trace.cost_usd,
            "latencyS": round(trace.latency_s, 4),
            "promptTokens": trace.prompt_tokens,
            "completionTokens": trace.completion_tokens,
            "model": trace.model,
            "provider": trace.provider,
        }
    else:  # no LLM: latency = wall time of ground()
        record |= {"calls": 0, "cacheHits": 0, "latencyS": round(wall, 6)}
    return record


def retry_failed(out: Path) -> int:
    """Re-ground, with the settings of run.json, the records of a saved run that ended in
    `service_unavailable` (an infrastructure failure, not a grounding answer). The run
    keeps its other records; run.json lists the retried ones."""
    from .report import rebuild

    meta = json.loads((out / "run.json").read_text())
    args = argparse.Namespace(
        grounder=meta["grounder"],
        model=meta["model"],
        provider=meta["provider"],
        prompt=meta.get("promptVersion"),
        temperature=meta["temperature"],
        no_cache=not meta["cache"],
        max_cost=None,
    )
    cases = {c.id: c for c in load_cases(from_repo(meta["dataset"]))[0]}
    session = bind_scenario()
    grounder, _ = make_grounder(args)
    path = out / "predictions.jsonl"
    records = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    retried = []
    for i, rec in enumerate(records):
        if rec["prediction"].get("reason") == "service_unavailable":
            records[i] = predict(grounder, cases[rec["id"]], session, rec["repeat"])
            ok = records[i]["prediction"].get("reason") != "service_unavailable"
            retried.append({"id": rec["id"], "repeat": rec["repeat"], "recovered": ok})
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    meta.setdefault("retriedFailed", []).extend(retried)
    (out / "run.json").write_text(json.dumps(meta, indent=2) + "\n")
    rebuild(out)
    print(f"retried {len(retried)}, recovered {sum(r['recovered'] for r in retried)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args_list = sys.argv[1:] if argv is None else argv
    if args_list[:1] == ["--retry-failed"]:
        return retry_failed(Path(args_list[1]))
    p = argparse.ArgumentParser(prog="python -m cpsagent.eval.run")
    p.add_argument("--grounder", required=True, choices=["llm", "keyword", "embedding"])
    p.add_argument("--model", help="OpenRouter model id (llm grounder)")
    p.add_argument("--provider", help="pin one OpenRouter provider, no fallbacks")
    p.add_argument("--prompt", default=None, help="system prompt version (llm; default latest)")
    p.add_argument("--split", required=True, choices=["dev", "test"])
    p.add_argument("--final", action="store_true", help="required for the frozen test split")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--max-cost", type=float, help="spending cap in USD (default MAX_COST_USD)")
    p.add_argument("--yes", action="store_true", help="do not ask before an expensive run")
    p.add_argument("--limit", type=int, help="only the first N cases (smoke test)")
    p.add_argument("--data", type=Path, default=DEFAULT_PATH)
    p.add_argument("--out", type=Path, help="output directory (default results/RUN_ID)")
    p.add_argument("--retry-failed", type=Path, help="see the module docstring")
    args = p.parse_args(args_list)

    if args.split == "test" and not args.final:
        p.error("the test split is frozen: use --final only for the final run")
    if args.grounder == "llm" and not args.model:
        p.error("--model is required with --grounder llm")
    if args.grounder == "llm":
        from cpsagent.grounding.prompts import PROMPT_VERSION, PROMPTS

        args.prompt = args.prompt or PROMPT_VERSION
        if args.prompt not in PROMPTS:
            p.error(f"--prompt must be one of {sorted(PROMPTS)}")
    cases, errors = load_cases(args.data)
    if errors:
        print("\n".join(errors[:10]), file=sys.stderr)
        p.error(f"{args.data} has {len(errors)} invalid cases")
    cases = [c for c in cases if c.split == args.split][: args.limit]
    session = bind_scenario()
    grounder, client = make_grounder(args)

    if client is not None:
        calls, usd = estimate_cost(grounder, client, cases, session, args.repeats)
        shown = "unknown (no measured call for this model)" if usd is None else f"{usd:.4f} USD"
        print(f"{len(cases)} cases x {args.repeats} repeats; {calls} uncached calls; est. {shown}")
        if usd is not None and usd > CONFIRM_ABOVE_USD and not args.yes:
            if input("Estimated cost above 1 USD. Proceed? [y/N] ").strip().lower() != "y":
                print("Aborted.")
                return 1
            client.max_cost_usd = max(client.max_cost_usd, 2 * usd)

    now = datetime.now(UTC)
    slug = (args.model or args.grounder).replace("/", "-").replace(":", "-")
    run_id = f"{now:%Y%m%d-%H%M%S}_{args.grounder}_{slug}_{args.split}"
    out = args.out or Path("results") / run_id
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "runId": out.name,
        "time": now.isoformat().replace("+00:00", "Z"),
        "grounder": args.grounder,
        "model": args.model,
        "provider": args.provider,
        "temperature": args.temperature,
        "split": args.split,
        "repeats": args.repeats,
        "cases": len(cases),
        "cache": not args.no_cache,
        "dataset": repo_relative(args.data),
        "datasetSha256": _sha(args.data.read_bytes()),
        "gitCommit": _git_commit(),
        "callsLogRunId": getattr(client, "run_id", None),
    }
    if args.grounder == "llm":
        from cpsagent.grounding.llm import WIRE_SCHEMA

        meta["promptVersion"] = args.prompt
        meta["promptSha256"] = _sha(grounder.system_prompt.encode())
        meta["schemaSha256"] = _sha(json.dumps(WIRE_SCHEMA, sort_keys=True).encode())
    if args.grounder == "embedding":
        from cpsagent.grounding import embedding

        meta["embeddingModel"] = embedding.MODEL_ID
        meta["embeddingRevision"] = embedding.MODEL_REVISION
        meta["threshold"], meta["margin"] = grounder.threshold, grounder.margin
        meta["descriptionsSha256"] = embedding.descriptions_sha()
        meta["modelLoadS"] = round(grounder.embedder.load_s, 3)  # not in the latency
    (out / "run.json").write_text(json.dumps(meta, indent=2) + "\n")

    records, scored = [], []
    with (out / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for r in range(args.repeats):
            for i, case in enumerate(cases, start=1):
                rec = predict(grounder, case, session, r)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()  # a stopped run keeps what it did
                records.append(rec)
                pred = GroundingResultAdapter.validate_python(rec["prediction"])
                scored.append(score(case, r, pred, session))
                print(f"\r[{r + 1}/{args.repeats}] {i}/{len(cases)}", end="", flush=True)
    print()
    write_reports(out, meta, scored, records, session)
    print((out / "summary.md").read_text())
    print(f"saved in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
