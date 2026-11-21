"""Qualitative run: articulated, multi-action and hard messages through the whole agent.

Run:
  python -m cpsagent.bench.qualitative --interpreter keyword|embedding [--out results/qualitative]
  python -m cpsagent.bench.qualitative --interpreter llm --model M [--provider P] [--no-cache]
      [--max-cost USD]
  python -m cpsagent.bench.qualitative --compare RUN_DIR [RUN_DIR ...] --out DIR

For each message of `data/qualitative/requests.jsonl` (its SHA-256 is checked against the
set's metadata.json) a fresh UI session is started in memory (`ui.session.AgentSession`,
the wiring of the Streamlit page) with the chosen interpreter as the environment's
interpreter; the person is walked to `start_zone` and settles there as in the UI, then the
message is sent as typed text in its language. Recorded per message: the reply, every
interpretation the environment made (the whole message, then each part when the engine
split it) with the grounder's raw result and the result after the environment's check, the
parts and whether each was done, the transitions, the commands sent with their results,
and the final device states.

Scoring (fixed in data/qualitative/metadata.json before the first run): executed = the
commands whose result is ok, as a multiset of (deviceId, command, value); correct =
expected and executed, missed = expected not executed, wrong = executed not expected;
full success = nothing missed, nothing wrong and the observed reply kind as expected.

The grounder is built by the evaluation runner's own `make_grounder`, so its settings are
those of the evaluation (embedding threshold and margin, LLM prompt version, cache).
"""

import argparse
import csv
import hashlib
import json
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cpsagent.contracts import GroundingResultAdapter, ToolResult
from cpsagent.eval.dataset import repo_relative
from cpsagent.eval.run import make_grounder
from cpsagent.ui.session import AgentSession

from . import meta as runmeta

DATA = runmeta.ROOT / "data" / "qualitative" / "requests.jsonl"
SET_META = runmeta.ROOT / "data" / "qualitative" / "metadata.json"


def _dump(result) -> dict[str, Any]:
    return GroundingResultAdapter.dump_python(result, mode="json", exclude_none=True)


class RecordingInterpreter:
    """The environment's interpreter, unchanged, with every call recorded: the text it was
    given and its raw answer (before the environment's check)."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    def __getattr__(self, name):  # e.g. last_trace, system_prompt
        return getattr(self.inner, name)

    def ground(self, request):
        start = time.perf_counter_ns()
        result = self.inner.ground(request)
        call = {
            "text": request.text,
            "language": request.language,
            "zone": request.zone.zone_id,
            "raw": _dump(result),
            "latency_ns": time.perf_counter_ns() - start,
        }
        trace = getattr(self.inner, "last_trace", None)
        if trace is not None:  # LLM: answers of every attempt, tokens, cost
            call["llm"] = {
                "attempts": [a.content for a in trace.attempts],
                "errors": [a.error for a in trace.attempts],
                "cacheHits": trace.cache_hits,
                "costUsd": trace.cost_usd,
                "latencyS": trace.latency_s,
                "promptTokens": trace.prompt_tokens,
                "completionTokens": trace.completion_tokens,
                "model": trace.model,
                "provider": trace.provider,
            }
        self.calls.append(call)
        return result


def _transition(t) -> dict[str, Any]:
    outcome = t.outcome
    if isinstance(outcome, ToolResult):
        outcome = outcome.model_dump(mode="json", exclude_none=True)
    return {
        "from": t.source.value,
        "to": t.target.value,
        "guard": t.guard.value,
        "zone": t.zone.zone_id if t.zone else None,
        "intent": t.intent.model_dump(mode="json", exclude_none=True) if t.intent else None,
        "action": t.action.model_dump(mode="json", exclude_none=True) if t.action else None,
        "outcome": outcome,
        "queries": [
            {
                "zoneId": q.call.args.zone_id,
                "controlledProperty": q.call.args.controlled_property,
                "devices": [d["deviceId"] for d in q.result.state] if q.result.ok else None,
            }
            for q in t.queries
        ],
    }


def effect_key(e: dict[str, Any]) -> tuple[str, str, float | None]:
    v = e.get("value")
    return (e["deviceId"], e["command"], None if v is None else float(v))


def observed_reply(turn, parts, interpretations) -> str:
    """Observed reply kind (definition in data/qualitative/metadata.json)."""
    if parts is not None:
        done = [s for _, s in parts if s == "done"]
        if len(done) == len(parts):
            return "done"
        if done:
            return "partial"
        part_results = [c["checked"] for c in interpretations[1:]]
        if any(r["kind"] == "clarification" for r in part_results):
            return "clarification"
        return "refusal"
    if turn.reply is not None and turn.reply.status in ("done", "following"):
        return "done"
    if any(t.guard.value == "T12" and t.outcome == "clarification_asked" for t in turn.transitions):
        return "clarification"
    return "refusal"


def score(case: dict[str, Any], executed: list[dict[str, Any]], reply: str) -> dict[str, Any]:
    expected = Counter(effect_key(e) for e in case["expected"])
    got = Counter(effect_key(e) for e in executed)
    correct = expected & got
    missed = expected - got
    wrong = got - expected
    return {
        "expectedN": sum(expected.values()),
        "executedN": sum(got.values()),
        "correctN": sum(correct.values()),
        "missedN": sum(missed.values()),
        "wrongN": sum(wrong.values()),
        "missed": [list(k) for k in missed.elements()],
        "wrong": [list(k) for k in wrong.elements()],
        "observedReply": reply,
        "replyOk": reply == case["expected_reply"],
        "fullSuccess": not missed and not wrong and reply == case["expected_reply"],
    }


def run_message(grounder, case: dict[str, Any], log_dir: str) -> dict[str, Any]:
    recording = RecordingInterpreter(grounder)
    session = AgentSession(recording, start_zone=case["start_zone"], log_dir=log_dir)
    env = session.env
    checked: list[dict[str, Any]] = []
    original = env.interpret

    def interpret(*args, **kwargs):  # the environment's answer, after its own check
        result = original(*args, **kwargs)
        checked.append(_dump(result))
        return result

    env.interpret = interpret
    placed = session.localization.estimate()
    recording.calls.clear()  # nothing is interpreted while walking, but keep it exact
    start = time.perf_counter_ns()
    turn = session.say(case["text"], case["language"])
    latency = time.perf_counter_ns() - start
    states = env.device_states()
    interpretations = [{**c, "checked": r} for c, r in zip(recording.calls, checked, strict=True)]
    commands = []
    for t in turn.commands:
        a = t.action.args
        commands.append({
            "deviceId": a.device_id, "command": a.command, "value": a.value,
            "ok": t.outcome.ok, "error": t.outcome.error,
        })  # fmt: skip
    executed = [c for c in commands if c["ok"]]
    parts = session.engine.last_parts
    reply = observed_reply(turn, parts, interpretations)
    session.close()
    whole = interpretations[0]["checked"] if interpretations else None
    return {
        "id": case["id"],
        "pair_id": case["pair_id"],
        "language": case["language"],
        "category": case["category"],
        "subcategory": case["subcategory"],
        "k_actions": case["k_actions"],
        "start_zone": case["start_zone"],
        "text": case["text"],
        "placedZone": placed.zone_id if placed else None,
        "placedConfidence": round(placed.confidence, 3) if placed else None,
        "latency_ns": latency,
        "reply": {"status": turn.reply.status, "message": turn.reply.message},
        "whole": whole,
        "split": parts is not None,
        "parts": [{"text": p, "status": s} for p, s in parts] if parts else None,
        "interpretations": interpretations,
        "transitions": [_transition(t) for t in turn.transitions],
        "commands": commands,
        "finalStates": states,
        "expected": case["expected"],
        "expected_reply": case["expected_reply"],
        **score(case, executed, reply),
    }


def _kind(result: dict[str, Any] | None) -> str:
    if result is None:
        return "none"
    return result["kind"] if result["kind"] == "intent" else f"{result['kind']}:{result['reason']}"


def summarize(rows: list[dict[str, Any]], interpreter: str) -> list[list[Any]]:
    """One row per group: interpreter x language x category x k, and the marginals."""
    keys = {
        "language x category x k": lambda r: (r["language"], r["category"], r["k_actions"]),
        "category x k": lambda r: ("all", r["category"], r["k_actions"]),
        "language x category": lambda r: (r["language"], r["category"], "all"),
        "language": lambda r: (r["language"], "all", "all"),
        "all": lambda r: ("all", "all", "all"),
    }
    out = []
    for grouping, key in keys.items():
        groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            groups[key(r)].append(r)
        for (language, category, k), items in sorted(groups.items(), key=lambda x: str(x[0])):
            n = len(items)
            expected = sum(r["expectedN"] for r in items)
            out.append([
                interpreter, grouping, language, category, k, n,
                sum(r["fullSuccess"] for r in items),
                round(sum(r["fullSuccess"] for r in items) / n, 4),
                expected, sum(r["executedN"] for r in items), sum(r["correctN"] for r in items),
                sum(r["missedN"] for r in items), sum(r["wrongN"] for r in items),
                round(sum(r["correctN"] for r in items) / expected, 4) if expected else "",
                sum(r["replyOk"] for r in items), sum(r["split"] for r in items),
                round(sum(r["executedN"] for r in items) / n, 3),
                round(sum(r["correctN"] for r in items) / n, 3),
            ])  # fmt: skip
    return out


SUMMARY_HEADER = [
    "interpreter", "grouping", "language", "category", "k", "messages", "full_success",
    "full_success_rate", "expected_effects", "executed", "correct", "missed", "wrong",
    "recall", "reply_kind_ok", "split", "executed_per_message", "correct_per_message",
]  # fmt: skip
PAIR_HEADER = [
    "interpreter", "pair_id", "category", "k", "en_executed", "it_executed", "same_effects",
    "en_reply", "it_reply", "same_reply", "en_full_success", "it_full_success",
    "both_full_success",
]  # fmt: skip


def pairs(rows: list[dict[str, Any]], interpreter: str) -> list[list[Any]]:
    by_pair: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        by_pair[r["pair_id"]][r["language"]] = r
    out = []
    for pair_id, langs in sorted(by_pair.items()):
        en, it = langs.get("en"), langs.get("it")
        if en is None or it is None:
            continue

        def eff(r):
            return sorted(effect_key(c) for c in r["commands"] if c["ok"])

        out.append([
            interpreter, pair_id, en["category"], en["k_actions"],
            json.dumps(eff(en)), json.dumps(eff(it)), int(eff(en) == eff(it)),
            en["observedReply"], it["observedReply"],
            int(en["observedReply"] == it["observedReply"]),
            int(en["fullSuccess"]), int(it["fullSuccess"]),
            int(en["fullSuccess"] and it["fullSuccess"]),
        ])  # fmt: skip
    return out


def mechanism(rows: list[dict[str, Any]], interpreter: str) -> list[list[Any]]:
    """How many actions each multi-action message carried out, and why."""
    out = []
    for r in rows:
        parts = r["parts"] or []
        out.append([
            interpreter, r["id"], r["category"], r["k_actions"], _kind(r["whole"]),
            int(r["split"]), len(parts), sum(p["status"] == "done" for p in parts),
            "; ".join(_kind(c["checked"]) for c in r["interpretations"][1:]),
            r["executedN"], r["correctN"], r["missedN"], r["wrongN"], r["observedReply"],
        ])  # fmt: skip
    return out


MECHANISM_HEADER = [
    "interpreter", "id", "category", "k", "whole_result", "split", "parts", "parts_done",
    "part_results", "executed", "correct", "missed", "wrong", "observed_reply",
]  # fmt: skip


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def print_summary(rows: list[dict[str, Any]], interpreter: str) -> None:
    print(f"\n{interpreter}: {len(rows)} messages")
    for line in summarize(rows, interpreter):
        if line[1] in ("category x k", "language", "all"):
            print(f"  {line[2]:>3} {line[3]:<13} k={line[4]!s:<3} n={line[5]:<3} "
                  f"full {line[6]:>2}/{line[5]:<3} effects {line[10]}/{line[8]} "
                  f"wrong {line[12]} split {line[15]}")  # fmt: skip
    p = pairs(rows, interpreter)
    print(f"  EN-IT pairs: same effects {sum(x[6] for x in p)}/{len(p)}, "
          f"same reply {sum(x[9] for x in p)}/{len(p)}")  # fmt: skip


def compare(runs: list[Path], out: Path) -> int:
    """Concatenate the summaries of saved runs into one table per kind."""
    out.mkdir(parents=True, exist_ok=True)
    for name in ("summary.csv", "pairs.csv", "mechanism.csv"):
        rows, header = [], None
        for run in runs:
            with (run / name).open(encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader)
                rows += list(reader)
        write_csv(out / name, header, rows)
    print(f"written to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="python -m cpsagent.bench.qualitative")
    parser.add_argument("--interpreter", choices=["keyword", "embedding", "llm"])
    parser.add_argument("--model")
    parser.add_argument("--provider")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--max-cost", type=float)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", type=Path, default=runmeta.ROOT / "results" / "qualitative")
    parser.add_argument("--compare", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if args.compare:
        return compare(args.compare, args.out)
    if args.interpreter is None:
        parser.error("--interpreter is required")
    if args.interpreter == "llm":
        if not args.model:
            parser.error("--model is required with --interpreter llm")
        from cpsagent.grounding.prompts import PROMPT_VERSION

        args.prompt = args.prompt or PROMPT_VERSION

    data = args.data.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    set_meta = json.loads(SET_META.read_text()) if args.data == DATA else {}
    if args.data == DATA and set_meta.get("sha256") != sha:
        raise SystemExit(f"{args.data} does not match the SHA-256 of {SET_META}")
    cases = [json.loads(x) for x in data.decode("utf-8").splitlines()][: args.limit]

    grounder_args = argparse.Namespace(
        grounder=args.interpreter, model=args.model, provider=args.provider,
        temperature=args.temperature, prompt=args.prompt, no_cache=args.no_cache,
        max_cost=args.max_cost,
    )  # fmt: skip
    load_start = time.perf_counter()
    grounder, client = make_grounder(grounder_args)
    load_s = time.perf_counter() - load_start

    now = datetime.now(UTC)
    slug = (args.model or args.interpreter).replace("/", "-").replace(":", "-")
    run_id = f"{now:%Y%m%d-%H%M%S}_{args.interpreter}_{slug}"
    out = args.out / run_id
    out.mkdir(parents=True, exist_ok=False)
    info: dict[str, Any] = {
        "runId": run_id,
        "dataset": repo_relative(args.data),
        "datasetSha256": sha,
        "messages": len(cases),
        "interpreter": args.interpreter,
        "interpreterLoadS": round(load_s, 3),
        "store": "memory",
        "session": "ui.session.AgentSession, seed 0, one fresh session per message",
    }
    if args.interpreter == "embedding":
        from cpsagent.grounding import embedding

        info |= {
            "embeddingModel": embedding.MODEL_ID,
            "embeddingRevision": embedding.MODEL_REVISION,
            "threshold": grounder.threshold,
            "margin": grounder.margin,
            "descriptionsSha256": embedding.descriptions_sha(),
        }
    if args.interpreter == "llm":
        from cpsagent.grounding.llm import WIRE_SCHEMA

        info |= {
            "model": args.model,
            "provider": args.provider,
            "temperature": args.temperature,
            "promptVersion": args.prompt,
            "promptSha256": hashlib.sha256(grounder.system_prompt.encode()).hexdigest()[:16],
            "schemaSha256": hashlib.sha256(
                json.dumps(WIRE_SCHEMA, sort_keys=True).encode()
            ).hexdigest()[:16],
            "cache": not args.no_cache,
            "callsLogRunId": getattr(client, "run_id", None),
        }
    record = runmeta.run_metadata("cpsagent.bench.qualitative", argv, **info)
    runmeta.write(out / "metadata.json", record)

    rows = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as logs, (out / "messages.jsonl").open("w") as f:
        for i, case in enumerate(cases, start=1):
            row = run_message(grounder, case, logs)
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"\r{i}/{len(cases)}", end="", flush=True)
    print()
    record["durationS"] = round(time.perf_counter() - started, 3)
    if client is not None:
        record["spentUsd"] = getattr(client, "spent_usd", None)
    record["costUsd"] = sum(
        c.get("llm", {}).get("costUsd") or 0 for r in rows for c in r["interpretations"]
    )
    runmeta.write(out / "metadata.json", record)
    write_csv(out / "summary.csv", SUMMARY_HEADER, summarize(rows, args.interpreter))
    write_csv(out / "pairs.csv", PAIR_HEADER, pairs(rows, args.interpreter))
    write_csv(out / "mechanism.csv", MECHANISM_HEADER, mechanism(rows, args.interpreter))
    print_summary(rows, args.interpreter)
    print(f"saved in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
