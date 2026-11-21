"""Breakdown of saved evaluation runs, for the results chapter and the error analysis.

Run: python -m cpsagent.bench.breakdown RUN_DIR [RUN_DIR ...] --out results/final/breakdown

It reads each run's run.json and predictions.jsonl and scores them again with the frozen
evaluation code (`cpsagent.eval.metrics.score`, the same function the runner uses), so the
numbers equal those of the run's own summary. It changes nothing in the runs. It writes:

  overall.csv     per run: cases, strict and outcome accuracy with 95% Wilson intervals
  by_group.csv    per run and per category, language, source, and category x language
  pairs.csv       every English-Italian paraphrase pair whose two cases are in the run:
                  both predictions, strict and outcome correctness of each, and whether
                  the two predictions agree (as in the runner: `confidence` and the
                  free-text question ignored) and whether the two outcomes agree
  pairs_summary.csv  per run: pairs, prediction agreement, outcome agreement, both correct
  errors.csv      every case wrong on the strict or on the outcome metric: text, zone,
                  category, language, gold, prediction, outcome of each, error type
  errors.md       the same errors, readable

Rows of a run with repeats > 1 are scored per repeat; pairs and agreement use repeat 0.
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from cpsagent.contracts import GroundingResultAdapter
from cpsagent.eval.dataset import bind_scenario, from_repo, load_cases
from cpsagent.eval.metrics import Scored, outcome, score
from cpsagent.eval.report import error_type, normalized, wilson


def label(meta: dict[str, Any]) -> str:
    model = meta.get("model")
    return meta["grounder"] if not model else f"{meta['grounder']}:{model}"


def acc(hits: int, n: int) -> list[str]:
    if not n:
        return ["", "", ""]
    lo, hi = wilson(hits, n)
    return [f"{hits / n:.4f}", f"{lo:.4f}", f"{hi:.4f}"]


def brief(result) -> str:
    return json.dumps(
        GroundingResultAdapter.dump_python(result, mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
    )


def show_outcome(out) -> str:
    if isinstance(out, str):
        return out
    return "; ".join(f"{d} {c}{'' if v is None else ' ' + str(v)}" for d, c, v, _ in sorted(out))


def load_run(run: Path, session) -> tuple[dict[str, Any], list[Scored]]:
    meta = json.loads((run / "run.json").read_text())
    cases = {c.id: c for c in load_cases(from_repo(meta["dataset"]))[0]}
    scored = []
    for line in (run / "predictions.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        pred = GroundingResultAdapter.validate_python(rec["prediction"])
        scored.append(score(cases[rec["id"]], rec["repeat"], pred, session))
    return meta, scored


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cpsagent.bench.breakdown")
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    session = bind_scenario()

    overall, groups, pairs, pair_summary, errors = [], [], [], [], []
    md = ["# Errors of the saved runs", ""]
    for run in args.runs:
        meta, scored = load_run(run, session)
        name = label(meta)
        n = len(scored)
        overall.append(
            [run.name, name, meta["split"], meta["repeats"], n]
            + acc(sum(s.strict for s in scored), n)
            + acc(sum(s.outcome_ok for s in scored), n)
        )
        keys = {
            "category": lambda s: s.case.category,
            "language": lambda s: s.case.language,
            "source": lambda s: s.case.source,
            "category x language": lambda s: f"{s.case.category} {s.case.language}",
        }
        for key, get in keys.items():
            bucket: dict[str, list[Scored]] = defaultdict(list)
            for s in scored:
                bucket[str(get(s))].append(s)
            for value, items in sorted(bucket.items()):
                k = len(items)
                groups.append(
                    [run.name, name, key, value, k]
                    + acc(sum(s.strict for s in items), k)
                    + acc(sum(s.outcome_ok for s in items), k)
                )

        first = {s.case.id: s for s in scored if s.repeat == 0}
        agree = agree_out = both = 0
        run_pairs = [(first[s.case.paraphrase_of], s) for s in first.values()
                     if s.case.paraphrase_of in first]  # fmt: skip
        for en, it in run_pairs:
            same = normalized(en.pred) == normalized(it.pred)
            same_out = outcome(en.pred, en.case, session) == outcome(it.pred, it.case, session)
            agree += same
            agree_out += same_out
            both += en.strict and it.strict
            pairs.append([
                run.name, name, en.case.id, it.case.id, en.case.category, en.case.zone.zoneId,
                en.case.text, it.case.text, brief(en.pred), brief(it.pred),
                int(en.strict), int(it.strict), int(en.outcome_ok), int(it.outcome_ok),
                int(same), int(same_out),
            ])  # fmt: skip
        m = len(run_pairs)
        pair_summary.append([run.name, name, m] + acc(agree, m) + acc(agree_out, m) + acc(both, m))

        wrong = [s for s in scored if not (s.strict and s.outcome_ok)]
        md += [f"## {name} ({run.name}): {len(wrong)} of {n} cases wrong", ""]
        for s in wrong:
            gold_out = outcome(s.case.gold, s.case, session)
            errors.append([
                run.name, name, s.case.id, s.repeat, s.case.category, s.case.language,
                s.case.source, s.case.zone.zoneId, s.case.text, brief(s.case.gold),
                brief(s.pred), int(s.strict), int(s.outcome_ok), error_type(s) or "",
                show_outcome(gold_out), show_outcome(s.out), s.case.note or "",
            ])  # fmt: skip
            md += [
                f"- **{s.case.id}** ({s.case.category}, {s.case.language}, zone "
                f'{s.case.zone.zoneId}): "{s.case.text}"',
                f"  - gold: `{brief(s.case.gold)}` -> {show_outcome(gold_out)}",
                f"  - pred: `{brief(s.pred)}` -> {show_outcome(s.out)}",
                f"  - strict {'ok' if s.strict else 'wrong'}, outcome "
                f"{'ok' if s.outcome_ok else 'wrong'}; {error_type(s) or 'strict correct'}",
            ]
        md.append("")

    acc_cols = ["strict", "strict_lo", "strict_hi", "outcome", "outcome_lo", "outcome_hi"]
    write_csv(args.out / "overall.csv",
              ["run", "grounder", "split", "repeats", "n", *acc_cols], overall)  # fmt: skip
    write_csv(args.out / "by_group.csv", ["run", "grounder", "key", "value", "n", *acc_cols],
              groups)  # fmt: skip
    write_csv(args.out / "pairs.csv", [
        "run", "grounder", "en_id", "it_id", "category", "zone", "en_text", "it_text",
        "en_prediction", "it_prediction", "en_strict", "it_strict", "en_outcome", "it_outcome",
        "prediction_agree", "outcome_agree",
    ], pairs)  # fmt: skip
    write_csv(args.out / "pairs_summary.csv", [
        "run", "grounder", "pairs", "prediction_agree", "pa_lo", "pa_hi",
        "outcome_agree", "oa_lo", "oa_hi", "both_strict_correct", "bc_lo", "bc_hi",
    ], pair_summary)  # fmt: skip
    write_csv(args.out / "errors.csv", [
        "run", "grounder", "id", "repeat", "category", "language", "source", "zone", "text",
        "gold", "prediction", "strict_ok", "outcome_ok", "error_type", "gold_outcome",
        "predicted_outcome", "note",
    ], errors)  # fmt: skip
    (args.out / "errors.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    for row in overall:
        print(f"{row[1]:<40} n={row[4]:<4} strict {float(row[5]):.1%}  outcome {float(row[8]):.1%}")
    for row in pair_summary:
        print(f"{row[1]:<40} EN-IT pairs {row[2]}: predictions agree {float(row[3]):.1%}, "
              f"outcomes agree {float(row[6]):.1%}")  # fmt: skip
    print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
