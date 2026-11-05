"""Evaluation set loader: format, gold vs C2 + catalogue, consistency with the planner."""

import json
from pathlib import Path

import pytest

from cpsagent.eval.dataset import load_cases, main

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "requests_sample.jsonl"

CASE = {
    "id": "en-x",
    "text": "turn on the light",
    "language": "en",
    "zone": {"zoneId": "hallway", "previousZoneId": "lobby", "confidence": 0.9},
    "category": "explicit",
    "gold": {
        "kind": "intent",
        "intent": {
            "action": "activate",
            "controlledProperty": "light",
            "scope": "current_zone",
            "persistence": "one_off",
            "confidence": 0.9,
        },
    },
    "acceptable_actions": ["increase"],
    "split": "test",
    "source": "llm",
    "note": "",
}


def write(tmp_path, *cases):
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases) + "\n")
    return path


def with_intent(**fields):
    return {**CASE, "gold": {"kind": "intent", "intent": CASE["gold"]["intent"] | fields}}


def test_sample_is_valid_and_counted(capsys):
    cases, errors = load_cases(SAMPLE)
    assert errors == [] and len(cases) == 20
    assert main([str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "| **total** | 6 | 14 | 20 |" in out and "'it': 1" in out


@pytest.mark.parametrize(
    "case, message",
    [
        (with_intent(controlledProperty="humidity"), "not valid against the catalogue"),
        (with_intent(scope="current_zone", targetZoneId="server_room"), "not valid against"),
        ({**CASE, "zone": {**CASE["zone"], "zoneId": "garden"}}, "not in the building"),
        ({**CASE, "zone": {**CASE["zone"], "previousZoneId": "office"}}, "not adjacent"),
        ({**CASE, "zone": {**CASE["zone"], "confidence": 0.5}}, "theta"),
        (
            {**CASE, "zone": {**CASE["zone"], "zoneId": "server_room", "previousZoneId": None}},
            "out of scope",
        ),
        ({**CASE, "source": "human", "split": "dev"}, "human cases are always in test"),
        (with_intent(targetZoneId="hallway"), "equal to the current zone"),
        (
            {**CASE, "zone": {**CASE["zone"], "zoneId": "storage", "previousZoneId": None}},
            "no step to run now",
        ),
        (
            {**with_intent(action="decrease"), "acceptable_actions": ["deactivate"]},
            "gives different commands",
        ),
        ({**CASE, "acceptable_actions": ["activate"]}, "repeats the gold action"),
        (
            {**CASE, "gold": {"kind": "unsupported", "reason": "capability_absent"}},
            "only make sense with an intent gold",
        ),
        (
            {
                **CASE,
                "acceptable_actions": [],
                "gold": {"kind": "unsupported", "reason": "capability_absent"},
                "acceptable_kinds": ["unsupported:capability_absent"],
            },
            "acceptable_kinds repeats the gold",
        ),
    ],
)
def test_invalid_case_is_reported(tmp_path, case, message):
    _, errors = load_cases(write(tmp_path, case))
    assert len(errors) == 1 and message in errors[0], errors


def test_bad_format_and_duplicates(tmp_path):
    _, errors = load_cases(write(tmp_path, CASE, CASE, {**CASE, "id": "en-y", "split": "train"}))
    assert any("duplicate id" in e for e in errors)
    assert any(e.startswith("line 3:") for e in errors)


def test_paraphrase_must_share_gold_zone_and_split(tmp_path):
    it = {
        **CASE,
        "id": "it-x",
        "language": "it",
        "text": "accendi la luce",
        "paraphrase_of": "en-x",
    }
    assert load_cases(write(tmp_path, CASE, it))[1] == []
    _, errors = load_cases(write(tmp_path, CASE, {**it, "split": "dev"}))
    assert errors == ["it-x: gold, zone and split must equal those of en-x"]
    _, errors = load_cases(write(tmp_path, CASE, {**it, "paraphrase_of": "en-missing"}))
    assert "is not an English case" in errors[0]


def test_acceptable_kinds(tmp_path):
    case = {**CASE, "acceptable_kinds": ["clarification", "unsupported:capability_absent"]}
    cases, errors = load_cases(write(tmp_path, case))
    assert errors == []
    assert cases[0].accepts("clarification", "low_confidence")
    assert cases[0].accepts("unsupported", "capability_absent")
    assert not cases[0].accepts("unsupported", "out_of_scope")
    _, errors = load_cases(write(tmp_path, {**case, "acceptable_kinds": ["maybe"]}))
    assert "is not one of" in errors[0]


def test_show_prints_random_cases(capsys):
    assert main([str(SAMPLE), "--show", "3", "--seed", "1", "--source", "llm"]) == 0
    out = capsys.readouterr().out
    assert out.count("  gold : ") == 3 and "[" in out
