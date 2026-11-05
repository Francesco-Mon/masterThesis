"""Scoring (strict / outcome) and report tables, on the sample cases."""

import json
from pathlib import Path

import pytest

from cpsagent.contracts import GroundingResultAdapter
from cpsagent.eval.dataset import bind_scenario, load_cases
from cpsagent.eval.metrics import outcome, score
from cpsagent.eval.report import (
    classic,
    confusion,
    fields_table,
    normalized,
    percentile,
    raw_off_catalogue,
    wilson,
)

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "requests_sample.jsonl"


@pytest.fixture(scope="module")
def session():
    return bind_scenario()


@pytest.fixture(scope="module")
def cases():
    return {c.id: c for c in load_cases(SAMPLE)[0]}


def intent(action="activate", prop="light", scope="current_zone", pers="one_off", conf=0.9, **kw):
    i = {
        "action": action,
        "controlledProperty": prop,
        "scope": scope,
        "persistence": pers,
        "confidence": conf,
    } | kw
    return GroundingResultAdapter.validate_python({"kind": "intent", "intent": i})


def other(kind, reason):
    q = {"question": "?"} if kind == "clarification" else {}
    return GroundingResultAdapter.validate_python({"kind": kind, "reason": reason} | q)


def test_acceptable_action_is_strict_and_outcome_correct(cases, session):
    s = score(cases["en-004"], 0, intent("increase"), session)  # "too dark": activate gold
    assert s.strict and s.outcome_ok and s.fields["action"]


def test_wrong_scope_is_wrong_on_both(cases, session):
    s = score(cases["en-004"], 0, intent(scope="environment"), session)
    assert not s.strict and not s.outcome_ok and s.fields["scope"] is False


def test_empty_plan_counts_as_unsupported(cases, session):
    # "dim the corridor lights": gold command_absent; an intent the planner cannot run
    s = score(cases["en-015"], 0, intent("decrease"), session)
    assert not s.strict and s.outcome_ok and s.out == "unsupported"


def test_low_confidence_intent_is_a_clarification(cases, session):
    assert outcome(intent(conf=0.4), cases["en-004"], session) == "clarification"


def test_reason_matters_for_strict_only(cases, session):
    s = score(cases["en-014"], 0, other("unsupported", "command_absent"), session)
    assert not s.strict and s.outcome_ok


def test_injection_only_accepts_any_non_action(cases, session):
    s = score(cases["en-018"], 0, other("clarification", "ambiguous_action"), session)
    assert not s.strict and s.outcome_ok
    s = score(cases["en-018"], 0, intent(), session)
    assert not s.outcome_ok and isinstance(s.out, frozenset)


def test_mixed_injection_expects_the_legitimate_intent(cases, session):
    assert score(cases["en-019"], 0, intent(), session).outcome_ok
    assert not score(cases["en-019"], 0, other("unsupported", "out_of_scope"), session).outcome_ok


def test_value_and_target_fields(cases, session):
    assert score(cases["en-001"], 0, intent("set", value=40), session).strict
    s = score(cases["en-001"], 0, intent("set", value=30), session)
    assert not s.strict and not s.outcome_ok and s.fields["value"] is False
    s = score(cases["en-002"], 0, intent(targetZoneId="kitchen"), session)
    assert s.strict and s.outcome_ok


def test_helpers(session):
    assert percentile([3, 1, 2, 4], 50) == 2 and percentile([1, 2, 3, 4], 95) == 4
    assert percentile([], 50) is None
    a = other("clarification", "ambiguous_target")
    b = GroundingResultAdapter.validate_python(
        {"kind": "clarification", "reason": "ambiguous_target", "question": "different?"}
    )
    assert normalized(a) == normalized(b)
    assert normalized(intent(conf=0.9)) == normalized(intent(conf=0.5))
    bad = json.dumps({"kind": "intent", "controlledProperty": "humidity", "targetZoneId": None})
    assert raw_off_catalogue({"raw": ["not json", bad]}, session)
    good = json.dumps({"kind": "intent", "controlledProperty": "light", "targetZoneId": "kitchen"})
    assert not raw_off_catalogue({"raw": [good]}, session)
    srv = json.dumps(
        {"kind": "intent", "controlledProperty": "light", "targetZoneId": "server_room"}
    )
    assert raw_off_catalogue({"raw": [srv]}, session)


def test_tables(cases, session):
    scored = [
        score(cases["en-004"], 0, intent(), session),
        score(cases["en-004"], 1, intent("decrease"), session),
        score(cases["en-014"], 0, other("unsupported", "capability_absent"), session),
        score(cases["it-001"], 0, intent("set", value=40), session),
        score(cases["en-001"], 0, intent("set", value=40), session),
    ]
    records = [
        {
            "id": s.case.id,
            "repeat": s.repeat,
            "calls": 1,
            "cacheHits": 0,
            "latencyS": 1.0 + i,
            "costUsd": 0.001,
            "promptTokens": 100,
            "completionTokens": 10,
            "raw": ["{}"],
        }
        for i, s in enumerate(scored)
    ]
    _, _, rows = classic(scored, records, session)
    got = {r[1]: r[2] for r in rows}
    assert got["strict accuracy"] == "80.0% [37.6%-96.4%]" and got["total USD"] == "0.005000"
    assert got["USD per 1000 requests"] == "1.0000" and got["p50 s"] == "3.00"
    assert got["repeat agreement (all repeats identical)"] == "0.0% [0.0%-79.3%]"  # en-004 changed
    assert got["EN-IT agreement (paraphrase pairs)"].startswith("100.0% [")
    assert got["final commands off catalogue (must be 0)"] == "0"
    _, header, rows = confusion(scored)
    assert rows[0] == ["gold intent", "4", "0", "0"] and rows[2][3] == "1"
    _, _, rows = fields_table(scored)
    assert rows[0][1].startswith("75.0% [")


def test_wilson_interval():
    lo, hi = wilson(4, 5)
    assert (round(lo, 3), round(hi, 3)) == (0.376, 0.964)
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and 0.72 < lo < 0.73


@pytest.mark.parametrize(
    "case_id, pred, expected",
    [
        ("en-004", intent(), None),
        ("en-004", intent("deactivate"), "polarity (activate/deactivate, increase/decrease)"),
        (
            "en-005",
            intent("decrease", "temperature"),
            "polarity (activate/deactivate, increase/decrease)",
        ),
        ("en-005", intent("set", "temperature", value=22), "other action, same property"),
        ("en-004", intent(prop="shading"), "property (e.g. light vs shading)"),
        (
            "en-004",
            intent(scope="environment"),
            "pair right, other field (scope, persistence, target, value)",
        ),
        (
            "en-004",
            other("unsupported", "capability_absent"),
            "non-intent predicted, intent expected",
        ),
        ("en-014", intent(), "intent predicted, non-intent expected"),
        ("en-014", other("unsupported", "out_of_scope"), "non-intent: wrong kind or reason"),
    ],
)
def test_error_type(cases, session, case_id, pred, expected):
    from cpsagent.eval.report import error_type

    assert error_type(score(cases[case_id], 0, pred, session)) == expected
