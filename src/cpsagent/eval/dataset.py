"""Evaluation set: one EvalCase per JSONL line, labelled by docs/EVAL_POLICY.md.

Run: python -m cpsagent.eval.dataset [data/requests.jsonl] [--show N --seed S --source S]
Validates every case (format, gold against C2 and the scenario catalogue, consistency
with the planner) and prints counts per category, split and language. Exit code 1 if
any case is invalid. `--show N` also prints N random cases (spot check).

The checks that need the scenario run against a bound session of the emulator, i.e. the
same catalogue (zones in scope only) and adjacency the engine and the grounders see.
"""

import argparse
import json
import os
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from cpsagent.binding import BoundSession, EnvironmentBinding
from cpsagent.contracts import (
    Action,
    ClarificationReason,
    GroundingResult,
    GroundingResultAdapter,
    IntentResult,
    UnsupportedReason,
    UnsupportedResult,
    ZoneEstimate,
)
from cpsagent.contracts.base import Confidence
from cpsagent.engine import make_plan
from cpsagent.environment import EmulatedEnvironment

ROOT = Path(__file__).resolve().parents[3]  # repository root
DEFAULT_PATH = ROOT / "data" / "requests.jsonl"
THETA = 0.6  # EngineConfig.theta: below it the engine never calls the grounder


def repo_relative(path: Path) -> str:
    """Path as stored in run.json: relative to the repository root, POSIX separators,
    never absolute (results are committed and must not reveal the author's machine)."""
    return Path(os.path.relpath(Path(path).resolve(), ROOT)).as_posix()


def from_repo(stored: str) -> Path:
    """Inverse of `repo_relative`: the stored path resolved against the repository root."""
    return ROOT / stored


class Category(StrEnum):
    EXPLICIT = "explicit"  # names property and action ("turn on the light")
    EXPLICIT_OTHER_ZONE = "explicit_other_zone"  # names another zone (targetZoneId)
    IMPLICIT = "implicit"  # states a need ("it's too dark here")
    ZONE_DEPENDENT = "zone_dependent"  # same words, gold depends on the zone
    FOLLOWING = "following"  # along the user's path (scope path)
    ENVIRONMENT = "environment"  # the whole building
    AMBIGUOUS = "ambiguous"  # gold is a clarification
    UNSUPPORTED = "unsupported"  # capability or command absent
    OUT_OF_SCOPE = "out_of_scope"  # zone missing or outside the agent's scope
    ADVERSARIAL = "adversarial"  # injection / off-catalogue action


ACCEPTABLE_KINDS = (
    {"clarification", "unsupported"}
    | {f"clarification:{r}" for r in ClarificationReason}
    | {f"unsupported:{r}" for r in UnsupportedReason}
)


class CaseZone(BaseModel):
    """Where the request is said (the fields of ZoneEstimate that matter here)."""

    model_config = ConfigDict(extra="forbid")

    zoneId: str = Field(min_length=1)
    previousZoneId: str | None = None
    confidence: Confidence


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    language: Literal["en", "it"]
    zone: CaseZone
    category: Category
    gold: GroundingResult
    acceptable_actions: list[Action] = []
    # other results also counted correct: "clarification" / "unsupported" (any reason) or
    # "kind:reason" ("turn everything off": clarification too; EVAL_POLICY.md rule 7)
    acceptable_kinds: list[str] = []
    split: Literal["dev", "test"]
    source: Literal["llm", "human"]
    note: str = ""
    # Italian paraphrases: id of the English case with the same gold (EN vs IT stability)
    paraphrase_of: str | None = None

    @field_validator("acceptable_kinds")
    @classmethod
    def _known_kinds(cls, values: list[str]) -> list[str]:
        for v in values:
            if v not in ACCEPTABLE_KINDS:
                raise ValueError(f"acceptable kind {v!r} is not one of {sorted(ACCEPTABLE_KINDS)}")
        return values

    def accepts(self, kind: str, reason: str | None) -> bool:
        """True if a non-intent result (kind, reason) is listed in `acceptable_kinds`."""
        return kind in self.acceptable_kinds or f"{kind}:{reason}" in self.acceptable_kinds

    def zone_estimate(self) -> ZoneEstimate:
        """The ZoneEstimate the runner passes to the grounder (fixed time: cacheable)."""
        return ZoneEstimate(
            zone_id=self.zone.zoneId,
            confidence=self.zone.confidence,
            observed_at=datetime(2026, 11, 10, 9, 30, tzinfo=UTC),
            previous_zone_id=self.zone.previousZoneId,
        )


def bind_scenario() -> BoundSession:
    env = EmulatedEnvironment()
    return EnvironmentBinding({env.endpoint: env}).bind(env.endpoint, "person-agent", "user-1")


def _check(case: EvalCase, session: BoundSession, building_zones: set[str]) -> list[str]:
    """Consistency of one case with the scenario and EVAL_POLICY.md; [] if fine."""
    errors = []
    zone, adjacency = case.zone, session.spatial_model.adjacency
    if zone.zoneId not in building_zones:
        return [f"zone {zone.zoneId!r} is not in the building"]
    if zone.previousZoneId is not None and zone.previousZoneId not in adjacency[zone.zoneId]:
        errors.append(f"previousZoneId {zone.previousZoneId!r} is not adjacent to {zone.zoneId!r}")
    if zone.confidence < THETA:
        errors.append(f"zone confidence {zone.confidence} < theta {THETA}")

    # gold against C2 *and* the catalogue (properties and zones in scope)
    context = {
        "catalogue_properties": session.catalogue_properties(),
        "catalogue_zones": {c.zone_id for c in session.catalogue},
    }
    try:
        GroundingResultAdapter.validate_python(case.gold.model_dump(), context=context)
    except ValidationError as e:
        errors.append(f"gold not valid against the catalogue: {e.errors()[0]['msg']}")
        return errors

    in_scope = zone.zoneId in context["catalogue_zones"]
    if not in_scope and case.gold != UnsupportedResult(reason="out_of_scope"):
        errors.append("zone out of scope: gold must be unsupported/out_of_scope (rule 5)")
    if case.acceptable_actions and not isinstance(case.gold, IntentResult):
        errors.append("acceptable_actions only make sense with an intent gold")
    if not isinstance(case.gold, IntentResult) and case.accepts(case.gold.kind, case.gold.reason):
        errors.append("acceptable_kinds repeats the gold")
    if case.source == "human" and case.split != "test":
        errors.append("human cases are always in test")
    if not isinstance(case.gold, IntentResult) or not in_scope:
        return errors

    intent = case.gold.intent
    if intent.target_zone_id == zone.zoneId:
        errors.append("targetZoneId equal to the current zone (rule 1)")
    estimate = case.zone_estimate()
    plan = make_plan(intent, estimate, session.catalogue, adjacency)
    if not any(s.guard.type == "now" for s in plan.steps):
        errors.append("intent gold but the planner has no step to run now (rules 2/3a/8)")
    for action in case.acceptable_actions:
        if action == intent.action:
            errors.append(f"acceptable action {action} repeats the gold action")
            continue
        other = intent.model_copy(update={"action": action})
        if make_plan(other, estimate, session.catalogue, adjacency).steps != plan.steps:
            errors.append(f"acceptable action {action} gives different commands (rule 7)")
    return errors


def load_cases(path: Path = DEFAULT_PATH) -> tuple[list[EvalCase], list[str]]:
    """All valid cases and the list of errors ("line N: ..."); the caller decides."""
    session = bind_scenario()
    building_zones = set(session.spatial_model.adjacency)
    cases, errors, seen = [], [], set()
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = EvalCase.model_validate(json.loads(line))
        except (ValueError, ValidationError) as e:
            errors.append(f"line {n}: {e}")
            continue
        problems = _check(case, session, building_zones)
        if case.id in seen:
            problems.append(f"duplicate id {case.id!r}")
        seen.add(case.id)
        errors += [f"line {n} ({case.id}): {p}" for p in problems]
        cases.append(case)
    errors += _check_paraphrases(cases)
    return cases, errors


def _check_paraphrases(cases: list[EvalCase]) -> list[str]:
    """A paraphrase points to an existing English case, with the same gold and split
    (a paraphrase of a test case in dev would leak the frozen test set)."""
    by_id = {c.id: c for c in cases}
    errors = []
    for c in cases:
        if c.paraphrase_of is None:
            continue
        src = by_id.get(c.paraphrase_of)
        if src is None or src.language != "en":
            errors.append(f"{c.id}: paraphrase_of {c.paraphrase_of!r} is not an English case")
        elif (src.gold, src.zone, src.split) != (c.gold, c.zone, c.split):
            errors.append(f"{c.id}: gold, zone and split must equal those of {src.id}")
    return errors


def counts(cases: list[EvalCase]) -> str:
    """Markdown tables: category x split, plus totals per language and gold kind."""
    lines = ["| category | dev | test | total |", "|---|---|---|---|"]
    by = Counter((c.category, c.split) for c in cases)
    for cat in Category:
        dev, test = by[(cat, "dev")], by[(cat, "test")]
        lines.append(f"| {cat} | {dev} | {test} | {dev + test} |")
    dev = sum(c.split == "dev" for c in cases)
    lines.append(f"| **total** | {dev} | {len(cases) - dev} | {len(cases)} |")
    llm = [c for c in cases if c.source == "llm"]  # human cases are always in test
    share = f"{sum(c.split == 'dev' for c in llm) / len(llm):.0%}" if llm else "-"
    lines.append("")
    lines.append(f"dev share of llm cases: {share} (target 30%)")
    lines.append(f"language: {dict(sorted(Counter(c.language for c in cases).items()))}")
    lines.append(f"source: {dict(sorted(Counter(c.source for c in cases).items()))}")
    lines.append(f"gold kind: {dict(sorted(Counter(c.gold.kind for c in cases).items()))}")
    return "\n".join(lines)


def describe(case: EvalCase) -> str:
    """One readable block per case, for spot checks."""
    g = case.gold
    if isinstance(g, IntentResult):
        fields = g.intent.model_dump(mode="json", exclude_none=True, exclude={"confidence"})
        gold = "intent " + " ".join(f"{k}={v}" for k, v in fields.items())
    else:
        gold = f"{g.kind}/{g.reason}"
    extra = [f"+actions {[str(a) for a in case.acceptable_actions]}"] * bool(
        case.acceptable_actions
    ) + [f"+kinds {case.acceptable_kinds}"] * bool(case.acceptable_kinds)
    prev = f" (from {case.zone.previousZoneId})" if case.zone.previousZoneId else ""
    return "\n".join(
        [
            f"{case.id}  [{case.category}, {case.language}, {case.source}, {case.split}]",
            f"  zone : {case.zone.zoneId}{prev}",
            f"  text : {case.text}",
            f"  gold : {gold} {' '.join(extra)}".rstrip(),
            f"  note : {case.note}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cpsagent.eval.dataset")
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--show", type=int, default=0, help="print N random cases")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--source", choices=["llm", "human"])
    args = parser.parse_args(argv)
    cases, errors = load_cases(args.path)
    print(f"{args.path}: {len(cases)} cases\n")
    print(counts(cases))
    for e in errors:
        print("ERROR", e)
    if args.show:
        pool = [c for c in cases if args.source in (None, c.source)]
        for c in random.Random(args.seed).sample(pool, min(args.show, len(pool))):
            print("\n" + describe(c))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
