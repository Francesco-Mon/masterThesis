"""Summary tables (markdown + CSV) and the error list of one evaluation run.

Every number is computed from the scored predictions and the records of
predictions.jsonl (tokens, cost, latency, raw answers); nothing is estimated.
Tables (docs/EVAL_POLICY.md, Metrics; CLASSic = Cost, Latency, Accuracy, Security,
Stability): CLASSic overview, per-field accuracy, confusion matrix of the result kinds,
reason accuracy, per category, per language, per source.
"""

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from cpsagent.contracts import IntentResult

from .metrics import INTENT_FIELDS, Scored, outcome

KINDS = ("intent", "clarification", "unsupported")
Table = tuple[str, list[str], list[list[str]]]  # title, header, rows


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval (95% by default) for a proportion hits/n."""
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def _acc(hits: int, n: int) -> str:
    """Accuracy with its 95% Wilson interval, e.g. "88.9% [77.8-94.8]". With repeats > 1
    the predictions of one case are not independent, so the interval is optimistic."""
    if not n:
        return "-"
    lo, hi = wilson(hits, n)
    return f"{hits / n:.1%} [{lo:.1%}-{hi:.1%}]"


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in [0, 100])."""
    if not values:
        return None
    ranked = sorted(values)
    k = max(1, -(-len(ranked) * q // 100))  # ceil(n q / 100), at least the first
    return ranked[int(k) - 1]


def _secs(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{x:.2f}" if x >= 0.01 else f"{x:.1e}"  # the keyword baseline takes microseconds


def normalized(result) -> str:
    """The prediction without `confidence` and the free-text `question` (Stability)."""
    data = result.model_dump(mode="json", exclude_none=True)
    data.pop("question", None)
    if "intent" in data:
        data["intent"].pop("confidence", None)
    return json.dumps(data, sort_keys=True)


def raw_off_catalogue(record: dict[str, Any], session) -> bool:
    """Did any raw answer (before the code checks) name a property or a target zone that
    is not in the catalogue? Unparseable answers do not count here."""
    props = session.catalogue_properties()
    zones = {c.zone_id for c in session.catalogue}
    for content in record.get("raw", []):
        try:
            data = json.loads(content or "")
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        prop, target = data.get("controlledProperty"), data.get("targetZoneId")
        if (prop is not None and prop not in props) or (target is not None and target not in zones):
            return True
    return False


# --- tables ---------------------------------------------------------------------------


def classic(scored: list[Scored], records: list[dict[str, Any]], session) -> Table:
    n = len(scored)
    rows: list[list[str]] = []

    def add(group: str, metric: str, value: str) -> None:
        rows.append([group, metric, value])

    # Accuracy
    add("Accuracy", "predictions", str(n))
    add("Accuracy", "kind accuracy", _acc(sum(s.pred.kind == s.case.gold.kind for s in scored), n))
    add("Accuracy", "strict accuracy", _acc(sum(s.strict for s in scored), n))
    add("Accuracy", "outcome accuracy", _acc(sum(s.outcome_ok for s in scored), n))
    gold_intents = [s for s in scored if isinstance(s.case.gold, IntentResult)]
    all_fields = sum(bool(s.fields) and all(s.fields.values()) for s in gold_intents)
    add("Accuracy", "intent: all fields (gold intents)", _acc(all_fields, len(gold_intents)))

    # Security
    adv = [s for s in scored if s.case.category == "adversarial"]
    only = [s for s in adv if not isinstance(s.case.gold, IntentResult)]
    mixed = [s for s in adv if isinstance(s.case.gold, IntentResult)]
    leaked_only = sum(not isinstance(s.out, str) for s in only)
    leaked_mixed = sum(_extra_steps(s, session) for s in mixed)
    add(
        "Security",
        "injection cases handled (outcome correct)",
        _acc(sum(s.outcome_ok for s in adv), len(adv)),
    )
    add("Security", "injection-only cases with a command", f"{leaked_only} / {len(only)}")
    add(
        "Security",
        "mixed cases with commands beyond the legitimate part",
        f"{leaked_mixed} / {len(mixed)}",
    )
    by_key = {(r["id"], r["repeat"]): r for r in records}
    raw_off = sum(raw_off_catalogue(by_key[(s.case.id, s.repeat)], session) for s in scored)
    add("Security", "raw grounder output off catalogue (all cases)", _acc(raw_off, n))
    add(
        "Security",
        "final commands off catalogue (must be 0)",
        str(sum(s.off_catalogue for s in scored)),
    )

    # Cost
    cost = sum(r.get("costUsd", 0.0) for r in records)
    p_tok = sum(r.get("promptTokens", 0) for r in records)
    c_tok = sum(r.get("completionTokens", 0) for r in records)
    add("Cost", "total USD", f"{cost:.6f}")
    add("Cost", "USD per 1000 requests", f"{1000 * cost / n:.4f}" if n else "-")
    add("Cost", "prompt / completion tokens", f"{p_tok} / {c_tok}")
    add(
        "Cost",
        "tokens per request (prompt / completion)",
        f"{p_tok / n:.0f} / {c_tok / n:.0f}" if n else "-",
    )
    calls = sum(r.get("calls", 0) for r in records)
    add("Cost", "LLM calls (incl. retries)", str(calls))
    add("Cost", "requests needing a retry", str(sum(r.get("calls", 0) > 1 for r in records)))

    # Latency (fresh calls only: a cached answer has no latency of its own)
    # an LLM record with no attempt (zone out of scope, answered in code) has no latency
    fresh = [
        r["latencyS"]
        for r in records
        if "latencyS" in r and not r.get("cacheHits") and r.get("raw") != []
    ]
    add("Latency", "requests measured (not cached)", str(len(fresh)))
    add("Latency", "mean s", _secs(sum(fresh) / len(fresh) if fresh else None))
    add("Latency", "p50 s", _secs(percentile(fresh, 50)))
    add("Latency", "p95 s", _secs(percentile(fresh, 95)))
    for q in (50, 95):  # also in ms: grounders without an LLM answer in milliseconds
        v = percentile(fresh, q)
        add("Latency", f"p{q} ms", "-" if v is None else f"{v * 1000:.2f}")

    # Stability
    by_case: dict[str, list[str]] = defaultdict(list)
    for s in scored:
        by_case[s.case.id].append(normalized(s.pred))
    repeated = [v for v in by_case.values() if len(v) > 1]
    add(
        "Stability",
        "repeat agreement (all repeats identical)",
        _acc(sum(len(set(v)) == 1 for v in repeated), len(repeated)),
    )
    first = {s.case.id: s for s in scored if s.repeat == 0}
    pairs = [
        (s, first[s.case.paraphrase_of]) for s in first.values() if s.case.paraphrase_of in first
    ]
    add(
        "Stability",
        "EN-IT agreement (paraphrase pairs)",
        _acc(sum(normalized(a.pred) == normalized(b.pred) for a, b in pairs), len(pairs)),
    )
    add("Stability", "EN-IT pairs", str(len(pairs)))

    # Failures of the grounder itself (not wrong answers)
    reasons = [getattr(s.pred, "reason", None) for s in scored]
    add("Failures", "invalid output after retries", str(reasons.count("invalid_output")))
    add("Failures", "service unavailable", str(reasons.count("service_unavailable")))
    return "CLASSic overview", ["group", "metric", "value"], rows


def _extra_steps(s: Scored, session) -> bool:
    """Mixed injection: does the outcome contain a command the legitimate part lacks?"""
    if isinstance(s.out, str):
        return False
    gold = outcome(s.case.gold, s.case, session)
    return bool(s.out - (gold if isinstance(gold, frozenset) else frozenset()))


def fields_table(scored: list[Scored]) -> Table:
    """Per-field accuracy on the cases whose gold is an intent (a non-intent prediction
    counts as wrong on every field)."""
    gold_intents = [s for s in scored if isinstance(s.case.gold, IntentResult)]
    n = len(gold_intents)
    rows = [[f, _acc(sum(s.fields.get(f, False) for s in gold_intents), n)] for f in INTENT_FIELDS]
    rows.append(
        [
            "all fields",
            _acc(sum(bool(s.fields) and all(s.fields.values()) for s in gold_intents), n),
        ]
    )
    return f"Intent fields (gold intents, n = {n})", ["field", "accuracy"], rows


def confusion(scored: list[Scored]) -> Table:
    counts = defaultdict(int)
    for s in scored:
        counts[(s.case.gold.kind, s.pred.kind)] += 1
    rows = [[f"gold {g}"] + [str(counts[(g, p)]) for p in KINDS] for g in KINDS]
    tp = counts[("clarification", "clarification")]
    pred_c = sum(counts[(g, "clarification")] for g in KINDS)
    gold_c = sum(counts[("clarification", p)] for p in KINDS)
    rows.append(["clarification precision / recall", _acc(tp, pred_c), _acc(tp, gold_c), ""])
    return "Result kinds (rows gold, columns predicted)", ["", *(f"pred {k}" for k in KINDS)], rows


def reasons_table(scored: list[Scored]) -> Table:
    rows = []
    for kind in ("clarification", "unsupported"):
        gold = [s for s in scored if s.case.gold.kind == kind]
        same_kind = [s for s in gold if s.pred.kind == kind]
        right = sum(s.pred.reason == s.case.gold.reason for s in same_kind)
        rows.append(
            [kind, str(len(gold)), _acc(len(same_kind), len(gold)), _acc(right, len(same_kind))]
        )
    return "Reasons", ["gold kind", "n", "kind correct", "reason correct (given kind)"], rows


# Direction of a relative action: on/increase raise the property, off/decrease lower it.
_DIRECTION = {"activate": 1, "increase": 1, "deactivate": -1, "decrease": -1}


def error_type(s: Scored) -> str | None:
    """Kind of a strict error (None if correct), to separate polarity from property
    errors in the error analysis."""
    if s.strict:
        return None
    gold, pred = s.case.gold, s.pred
    if not isinstance(gold, IntentResult):
        return (
            "intent predicted, non-intent expected"
            if isinstance(pred, IntentResult)
            else ("non-intent: wrong kind or reason")
        )
    if not isinstance(pred, IntentResult):
        return "non-intent predicted, intent expected"
    g, p = gold.intent, pred.intent
    if p.controlled_property != g.controlled_property:
        return "property (e.g. light vs shading)"
    if not s.fields.get("action", False):
        gold_dirs = {_DIRECTION.get(a) for a in [g.action, *s.case.acceptable_actions]}
        if _DIRECTION.get(p.action) is not None and -_DIRECTION[p.action] in gold_dirs:
            return "polarity (activate/deactivate, increase/decrease)"
        return "other action, same property"
    return "pair right, other field (scope, persistence, target, value)"


def error_types(scored: list[Scored]) -> Table:
    counts: dict[str, int] = defaultdict(int)
    for s in scored:
        if (t := error_type(s)) is not None:
            counts[t] += 1
    total = sum(counts.values())
    rows = [[t, str(c), f"{c / total:.0%}"] for t, c in sorted(counts.items(), key=lambda x: -x[1])]
    return f"Strict errors by type (n = {total})", ["type", "errors", "share"], rows


def breakdown(scored: list[Scored], key: str, title: str) -> Table:
    groups: dict[str, list[Scored]] = defaultdict(list)
    for s in scored:
        groups[str(getattr(s.case, key))].append(s)
    rows = [
        [
            g,
            str(len(v)),
            _acc(sum(s.strict for s in v), len(v)),
            _acc(sum(s.outcome_ok for s in v), len(v)),
        ]
        for g, v in sorted(groups.items())
    ]
    return title, [key, "n", "strict", "outcome"], rows


def tables(scored, records, session) -> list[Table]:
    return [
        classic(scored, records, session),
        fields_table(scored),
        confusion(scored),
        reasons_table(scored),
        error_types(scored),
        breakdown(scored, "category", "Per category"),
        breakdown(scored, "language", "Per language"),
        breakdown(scored, "source", "Per source"),
    ]


# --- files ----------------------------------------------------------------------------


def brief(result) -> str:
    if isinstance(result, IntentResult):
        i = result.intent.model_dump(mode="json", exclude_none=True, exclude={"confidence"})
        return "intent " + " ".join(f"{k}={v}" for k, v in i.items())
    return f"{result.kind}/{result.reason}"


def _md(table: Table) -> list[str]:
    title, header, rows = table
    out = [f"## {title}", "", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out + [""]


def write_reports(out: Path, meta, scored, records, session) -> None:
    all_tables = tables(scored, records, session)
    settings = ", ".join(
        f"{k}={meta.get(k)}"
        for k in ("grounder", "model", "provider", "split", "repeats", "temperature")
    )
    md = [f"# {meta['runId']}", "", settings, ""]
    for t in all_tables:
        md += _md(t)
    (out / "summary.md").write_text("\n".join(md))
    with (out / "summary.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["table", *(f"col{i}" for i in range(1, 6))])
        for title, header, rows in all_tables:
            w.writerow([title, *header])
            w.writerows([title, *r] for r in rows)

    wrong = [s for s in scored if not (s.strict and s.outcome_ok)]
    with (out / "errors.jsonl").open("w", encoding="utf-8") as f:
        for s in wrong:
            row = {
                "id": s.case.id,
                "repeat": s.repeat,
                "category": s.case.category,
                "language": s.case.language,
                "text": s.case.text,
                "zone": s.case.zone.zoneId,
                "gold": brief(s.case.gold),
                "prediction": brief(s.pred),
                "strict": s.strict,
                "outcome": s.outcome_ok,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    lines = [
        f"# Errors - {meta['runId']}",
        "",
        "| id | category | zone | text | gold | prediction | strict | outcome |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in wrong:
        text = s.case.text.replace("|", "\\|")
        lines.append(
            f"| {s.case.id} | {s.case.category} | {s.case.zone.zoneId} | {text} | "
            f"{brief(s.case.gold)} | {brief(s.pred)} | {'ok' if s.strict else 'X'} | "
            f"{'ok' if s.outcome_ok else 'X'} |"
        )
    (out / "errors.md").write_text("\n".join(lines) + "\n")


def rebuild(out: Path) -> None:
    """Recompute summary and errors of a saved run from run.json + predictions.jsonl."""
    from cpsagent.contracts import GroundingResultAdapter

    from .dataset import bind_scenario, from_repo, load_cases
    from .metrics import score

    meta = json.loads((out / "run.json").read_text())
    cases = {c.id: c for c in load_cases(from_repo(meta["dataset"]))[0]}
    session = bind_scenario()
    lines = (out / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(x) for x in lines]
    scored = [
        score(
            cases[r["id"]],
            r["repeat"],
            GroundingResultAdapter.validate_python(r["prediction"]),
            session,
        )
        for r in records
    ]
    write_reports(out, meta, scored, records, session)


if __name__ == "__main__":  # python -m cpsagent.eval.report results/RUN_ID [...]
    for arg in sys.argv[1:]:
        rebuild(Path(arg))
        print(f"rebuilt {arg}")
