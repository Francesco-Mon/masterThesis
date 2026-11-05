"""Evaluation runner, offline (fake OpenRouter transport)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "grounding"))
from fake_transport import FakeOpenRouter  # noqa: E402

from cpsagent.eval import run  # noqa: E402
from cpsagent.grounding import openrouter  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "requests_sample.jsonl"
LIGHT = json.dumps(
    {
        "kind": "intent",
        "action": "activate",
        "controlledProperty": "light",
        "scope": "current_zone",
        "persistence": "one_off",
        "confidence": 0.9,
        "targetZoneId": None,
        "value": None,
        "question": None,
        "reason": None,
    }
)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    fake = FakeOpenRouter([LIGHT], cost=0.001)
    real = openrouter.OpenRouterClient

    def factory(model, **kw):
        kw["cache_dir"] = None if kw["cache_dir"] is None else tmp_path / "cache"
        return real(
            model,
            api_key="test-key",
            calls_log=tmp_path / "calls.jsonl",
            http_client=fake.http_client(),
            max_http_retries=0,
            **{k: v for k, v in kw.items() if k != "calls_log"},
        )

    monkeypatch.setattr(openrouter, "OpenRouterClient", factory)
    monkeypatch.setattr(run, "CALLS_LOG", tmp_path / "calls.jsonl")
    return fake


def args(tmp_path, *extra):
    return [
        "--grounder",
        "llm",
        "--model",
        "m/x",
        "--data",
        str(SAMPLE),
        "--out",
        str(tmp_path / "out"),
        *extra,
    ]


def test_dev_run_writes_predictions_and_reports(fake, tmp_path, capsys):
    assert run.main(args(tmp_path, "--split", "dev", "--provider", "Prov")) == 0
    out = tmp_path / "out"
    preds = [json.loads(x) for x in (out / "predictions.jsonl").read_text().splitlines()]
    assert len(preds) == 6 and {p["repeat"] for p in preds} == {0}
    assert preds[0]["raw"] == [LIGHT] and preds[0]["provider"] == "FakeProvider"
    meta = json.loads((out / "run.json").read_text())
    assert meta["provider"] == "Prov" and meta["split"] == "dev" and meta["promptSha256"]
    assert meta["promptVersion"] == "v3"
    assert fake.requests[0]["provider"] == {"order": ["Prov"], "allow_fallbacks": False}
    for name in ("summary.md", "summary.csv", "errors.md", "errors.jsonl"):
        assert (out / name).exists()
    assert "strict accuracy" in capsys.readouterr().out


def test_run_json_stores_repo_relative_dataset_path(fake, tmp_path, monkeypatch):
    # --data is absolute here (SAMPLE) and the cwd is elsewhere: run.json must still say
    # data/..., because results/ is committed and must not reveal the author's machine.
    monkeypatch.chdir(tmp_path)
    assert run.main(args(tmp_path, "--split", "dev")) == 0
    meta = json.loads((tmp_path / "out" / "run.json").read_text())
    assert meta["dataset"] == "data/requests_sample.jsonl"
    assert not Path(meta["dataset"]).is_absolute()
    assert not any(isinstance(v, str) and v.startswith("/") for v in meta.values())


def test_test_split_needs_final(fake, tmp_path):
    with pytest.raises(SystemExit):
        run.main(args(tmp_path, "--split", "test"))
    assert fake.requests == []
    assert run.main(args(tmp_path, "--split", "test", "--final", "--limit", "2")) == 0


def test_repeats_are_separate_calls_and_cached(fake, tmp_path):
    assert run.main(args(tmp_path, "--split", "dev", "--repeats", "2", "--limit", "2")) == 0
    assert len(fake.requests) == 4
    assert run.main(args(tmp_path, "--split", "dev", "--repeats", "2", "--limit", "2")) == 0
    assert len(fake.requests) == 4  # second run fully cached
    assert run.main(args(tmp_path, "--split", "dev", "--limit", "2", "--no-cache")) == 0
    assert len(fake.requests) == 6


def test_expensive_run_asks_first(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run, "mean_cost_per_call", lambda model: 1.0)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert run.main(args(tmp_path, "--split", "dev")) == 1
    assert fake.requests == [] and "est. 6.0000 USD" in capsys.readouterr().out


def test_keyword_baseline_run(tmp_path):
    argv = ["--grounder", "keyword", "--split", "dev", "--data", str(SAMPLE)]
    assert run.main([*argv, "--out", str(tmp_path / "kw")]) == 0
    summary = (tmp_path / "kw" / "summary.md").read_text()
    assert "grounder=keyword" in summary
    assert "| Latency | requests measured (not cached) | 6 |" in summary


def test_report_is_rebuilt_from_saved_files(tmp_path):
    out = tmp_path / "kw"
    argv = ["--grounder", "keyword", "--split", "dev", "--data", str(SAMPLE), "--out", str(out)]
    assert run.main(argv) == 0
    first = (out / "summary.md").read_text()
    (out / "summary.md").unlink()
    from cpsagent.eval.report import rebuild

    rebuild(out)
    assert (out / "summary.md").read_text() == first


def test_prompt_version_is_selectable(fake, tmp_path):
    assert run.main(args(tmp_path, "--split", "dev", "--limit", "1", "--prompt", "v1")) == 0
    meta = json.loads((tmp_path / "out" / "run.json").read_text())
    from cpsagent.grounding.prompts import PROMPT_V1

    assert meta["promptVersion"] == "v1"
    assert fake.requests[-1]["messages"][0]["content"] == PROMPT_V1
    with pytest.raises(SystemExit):
        run.main(args(tmp_path, "--split", "dev", "--prompt", "v9"))


def test_retry_failed_replaces_only_service_failures(fake, tmp_path):
    fake.replies = [429, LIGHT]  # first call: provider rate limit, then answers
    assert run.main(args(tmp_path, "--split", "dev", "--limit", "2")) == 0
    out = tmp_path / "out"
    before = [json.loads(x) for x in (out / "predictions.jsonl").read_text().splitlines()]
    assert before[0]["prediction"]["reason"] == "service_unavailable"
    assert run.main(["--retry-failed", str(out)]) == 0
    after = [json.loads(x) for x in (out / "predictions.jsonl").read_text().splitlines()]
    assert after[0]["prediction"]["kind"] == "intent" and after[1] == before[1]
    meta = json.loads((out / "run.json").read_text())
    assert meta["retriedFailed"] == [{"id": before[0]["id"], "repeat": 0, "recovered": True}]


def test_compare_copies_cells_from_saved_runs(tmp_path):
    from cpsagent.eval import compare

    argv = ["--grounder", "keyword", "--split", "dev", "--data", str(SAMPLE)]
    assert run.main([*argv, "--out", str(tmp_path / "kw")]) == 0
    assert compare.main([str(tmp_path / "kw"), "--out", str(tmp_path / "cmp")]) == 0
    lines = (tmp_path / "cmp.csv").read_text().splitlines()
    assert lines[0].startswith("grounder,n,strict,outcome,strict EN,strict IT")
    assert lines[1].startswith("keyword,") and "-" not in lines[1].split(",")[2:4]
