"""One comparison table (one row per saved run), from the runs' own summary.csv.

Run:  python -m cpsagent.eval.compare results/RUN_A results/RUN_B ... --out results/NAME
Writes NAME.md and NAME.csv. Nothing is recomputed: the cells are copied from each
run's tables (rebuild a run first with `python -m cpsagent.eval.report` if needed).
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# (column header, table title, row key, value column): row key = the "metric" cell of
# the CLASSic overview, or the first cell of the other tables.
COLUMNS = [
    ("strict", "CLASSic overview", "strict accuracy", 3),
    ("outcome", "CLASSic overview", "outcome accuracy", 3),
    ("strict EN", "Per language", "en", 3),
    ("strict IT", "Per language", "it", 3),
    ("EN-IT agreement", "CLASSic overview", "EN-IT agreement (paraphrase pairs)", 3),
    ("injection handled", "CLASSic overview", "injection cases handled (outcome correct)", 3),
    ("p50 ms", "CLASSic overview", "p50 ms", 3),
    ("p95 ms", "CLASSic overview", "p95 ms", 3),
    ("cost USD", "CLASSic overview", "total USD", 3),
]


def label(meta: dict) -> str:
    if meta["grounder"] == "llm":
        return f"LLM {meta['model']} ({meta.get('promptVersion')})"
    if meta["grounder"] == "embedding":
        return f"embedding (t={meta['threshold']}, m={meta['margin']})"
    return meta["grounder"]


def row(run: Path) -> list[str]:
    meta = json.loads((run / "run.json").read_text())
    with (run / "summary.csv").open() as f:
        cells = list(csv.reader(f))[1:]
    out = [label(meta), str(meta["cases"])]
    for _, title, key, col in COLUMNS:
        # CLASSic rows are [title, group, metric, value]; the others [title, key, n, strict, ...]
        key_col = 2 if title == "CLASSic overview" else 1
        match = [r for r in cells if r[0] == title and r[key_col] == key]
        out.append(match[0][col] if match else "-")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m cpsagent.eval.compare")
    p.add_argument("runs", nargs="+", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    header = ["grounder", "n", *(c[0] for c in COLUMNS)]
    rows = [row(r) for r in args.runs]
    with args.out.with_suffix(".csv").open("w", newline="") as f:
        csv.writer(f).writerows([header, *rows])
    md = [f"| {' | '.join(header)} |", f"|{'---|' * len(header)}"]
    md += [f"| {' | '.join(r)} |" for r in rows]
    md.append("")
    md.append("Runs: " + ", ".join(r.name for r in args.runs))
    args.out.with_suffix(".md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
