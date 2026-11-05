"""`python -m cpsagent.grounding.try` and `demo_agent --grounder llm`, offline."""

import importlib
import json
import sys

from fake_transport import FakeOpenRouter

from cpsagent import demo_agent
from cpsagent.grounding import openrouter

try_script = importlib.import_module("cpsagent.grounding.try")  # `try` is a keyword

WALK = json.dumps(
    {
        "kind": "intent",
        "action": "activate",
        "controlledProperty": "light",
        "scope": "path",
        "persistence": "following",
        "confidence": 0.9,
        "targetZoneId": None,
        "question": None,
        "reason": None,
    }
)


def fake_client_factory(fake, tmp_path, seen):
    real = openrouter.OpenRouterClient

    def factory(model, **kw):
        seen.append(model)
        return real(
            model,
            api_key="test-key",
            cache_dir=tmp_path / "cache",
            calls_log=tmp_path / "calls.jsonl",
            http_client=fake.http_client(),
            max_http_retries=0,
        )

    return factory


def test_try_script_prints_result_and_measurements(monkeypatch, capsys, tmp_path):
    seen = []
    factory = fake_client_factory(FakeOpenRouter([WALK]), tmp_path, seen)
    monkeypatch.setattr(try_script, "OpenRouterClient", factory)
    monkeypatch.setattr(
        sys, "argv", ["try", "I want to walk in the light", "--zone", "hallway", "--model", "m/x"]
    )
    try_script.main()
    result, trace = capsys.readouterr().out.strip().splitlines()
    assert json.loads(result)["intent"]["scope"] == "path"
    assert json.loads(trace)["provider"] == "FakeProvider" and seen == ["m/x"]


def test_demo_agent_with_llm_grounder(monkeypatch, capsys, tmp_path):
    seen = []
    factory = fake_client_factory(FakeOpenRouter([WALK]), tmp_path, seen)
    monkeypatch.setattr(openrouter, "OpenRouterClient", factory)
    log = tmp_path / "demo.jsonl"
    argv = ["demo_agent", "--log", str(log), "--grounder", "llm", "--model", "m/x"]
    monkeypatch.setattr(sys, "argv", argv)
    demo_agent.main()
    out = capsys.readouterr().out
    assert "invokeCommand(lamp_corridor, on)" in out and "chain VERIFIED" in out
    assert seen == ["m/x"]
