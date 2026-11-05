"""Grid search of Grounder C's threshold and margin, on the dev split only.

Run:  python -m cpsagent.eval.tune_embedding   (writes results/embedding_grid_dev.csv)

Each dev case is embedded and ranked once; then every (threshold, margin) of the grid
re-decides it (`EmbeddingGrounder.decide`) and is scored with the evaluation metrics.
Choice: highest strict accuracy, ties broken by outcome accuracy, then by the smallest
threshold and margin (first in grid order). The test split is never loaded here.
"""

import csv
import sys
from pathlib import Path

from cpsagent.grounding.embedding import EmbeddingGrounder, SentenceTransformerEmbedder
from cpsagent.grounding.keyword import screen

from .dataset import bind_scenario, load_cases
from .metrics import score
from .run import build_request

THRESHOLDS = [round(0.20 + 0.025 * i, 3) for i in range(21)]  # 0.20 .. 0.70
MARGINS = [round(0.01 * i, 2) for i in range(13)]  # 0.00 .. 0.12
OUT = Path("results/embedding_grid_dev.csv")


def grid(grounder, cases, session) -> list[dict]:
    prepared = []
    for case in cases:
        request = build_request(case, session)
        early = screen(request.text.lower(), request, absent=False)
        prepared.append((case, request, early, None if early else grounder.rank(request)))
    rows = []
    for t in THRESHOLDS:
        for m in MARGINS:
            scored = [
                score(c, 0, early or grounder.decide(req, rk, threshold=t, margin=m), session)
                for c, req, early, rk in prepared
            ]
            rows.append(
                {
                    "threshold": t,
                    "margin": m,
                    "strict": sum(s.strict for s in scored),
                    "outcome": sum(s.outcome_ok for s in scored),
                    "n": len(scored),
                }
            )
    return rows


def best(rows: list[dict]) -> dict:
    return max(rows, key=lambda r: (r["strict"], r["outcome"], -r["threshold"], -r["margin"]))


def main() -> int:
    cases, errors = load_cases()
    if errors:
        raise SystemExit(f"dataset has {len(errors)} invalid cases")
    dev = [c for c in cases if c.split == "dev"]
    grounder = EmbeddingGrounder(SentenceTransformerEmbedder())
    rows = grid(grounder, dev, bind_scenario())
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    b = best(rows)
    ties = [r for r in rows if (r["strict"], r["outcome"]) == (b["strict"], b["outcome"])]
    print(f"{len(dev)} dev cases, {len(rows)} grid points -> {OUT}")
    print(
        f"best: threshold={b['threshold']} margin={b['margin']} "
        f"strict={b['strict']}/{b['n']} outcome={b['outcome']}/{b['n']} ({len(ties)} ties)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
