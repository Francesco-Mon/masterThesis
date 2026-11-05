"""OpenRouter client, offline: rate limiter, cache, call log, spending cap, errors."""

import json

import pytest
from fake_transport import FakeOpenRouter

from cpsagent.grounding.openrouter import (
    AuthError,
    BudgetExceededError,
    LLMCallError,
    MissingApiKeyError,
    OpenRouterClient,
    RateLimiter,
    cache_key,
)

MESSAGES = [{"role": "user", "content": "hi"}]
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
SECRET = "sk-or-test-SECRET-123"


def client(fake, tmp_path, **kw):
    kw.setdefault("api_key", SECRET)
    return OpenRouterClient(
        "test/model",
        cache_dir=tmp_path / "cache",
        calls_log=tmp_path / "calls.jsonl",
        http_client=fake.http_client(),
        max_http_retries=0,
        **kw,
    )


def log_rows(tmp_path):
    return [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]


def test_call_sends_json_schema_and_logs_usage(tmp_path):
    fake = FakeOpenRouter(['{"a": "x"}'], cost=0.002)
    c = client(fake, tmp_path)
    r = c.chat(MESSAGES, SCHEMA, schema_name="s", attempt=2)
    assert r.content == '{"a": "x"}' and not r.cache_hit
    sent = fake.requests[0]
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["schema"] == SCHEMA
    assert sent["temperature"] == 0.0
    [row] = log_rows(tmp_path)
    assert row["model"] == "test/model" and row["status"] == "ok"
    assert row["provider"] == r.provider == "FakeProvider"
    assert (row["promptTokens"], row["completionTokens"]) == (100, 20)
    assert row["costUsd"] == row["spentUsd"] == 0.002
    assert row["attempt"] == 2 and row["cacheHit"] is False and row["latencyS"] >= 0
    assert c.spent_usd == pytest.approx(0.002)


def test_cache_hit_costs_nothing_and_is_logged(tmp_path):
    fake = FakeOpenRouter(['{"a": "x"}'])
    client(fake, tmp_path).chat(MESSAGES, SCHEMA)
    c2 = client(fake, tmp_path)  # a new run, same cache directory
    r = c2.chat(MESSAGES, SCHEMA)
    assert r.cache_hit and r.content == '{"a": "x"}'
    assert len(fake.requests) == 1  # second call never reached the network
    assert c2.spent_usd == 0.0
    first, second = log_rows(tmp_path)
    assert second["cacheHit"] is True and second["spentUsd"] == 0.0
    assert second["costUsd"] == first["costUsd"]  # original measurement kept
    assert second["provider"] == "FakeProvider"


def test_cache_key_covers_model_messages_schema_temperature():
    base = cache_key("m", MESSAGES, SCHEMA, 0.0)
    assert base == cache_key("m", MESSAGES, SCHEMA, 0.0)
    assert base != cache_key("m2", MESSAGES, SCHEMA, 0.0)
    assert base != cache_key("m", [{"role": "user", "content": "ho"}], SCHEMA, 0.0)
    assert base != cache_key("m", MESSAGES, {"type": "object"}, 0.0)
    assert base != cache_key("m", MESSAGES, SCHEMA, 0.7)


def test_spending_cap_stops_the_run(tmp_path):
    fake = FakeOpenRouter(['{"a": "1"}', '{"a": "2"}', '{"a": "3"}'], cost=0.3)
    c = client(fake, tmp_path, max_cost_usd=0.5)
    c.chat([{"role": "user", "content": "1"}], SCHEMA)
    c.chat([{"role": "user", "content": "2"}], SCHEMA)  # 0.3 < 0.5: allowed
    with pytest.raises(BudgetExceededError):
        c.chat([{"role": "user", "content": "3"}], SCHEMA)  # 0.6 >= 0.5: stop
    assert len(fake.requests) == 2
    # a cached answer is still served once the cap is reached (it costs nothing)
    assert c.chat([{"role": "user", "content": "1"}], SCHEMA).cache_hit


def test_spending_cap_default_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_COST_USD", "0.25")
    assert client(FakeOpenRouter([]), tmp_path).max_cost_usd == 0.25
    monkeypatch.delenv("MAX_COST_USD")
    assert client(FakeOpenRouter([]), tmp_path).max_cost_usd == 0.5


def test_rate_limiter_sleeps_when_window_is_full():
    now, slept = [0.0], []

    def sleep(s):
        slept.append(s)
        now[0] += s

    limiter = RateLimiter(rpm=2, clock=lambda: now[0], sleep=sleep)
    limiter.acquire()
    now[0] = 10.0
    limiter.acquire()
    now[0] = 20.0
    limiter.acquire()  # third call within 60 s of the first: wait until t=60
    assert slept == [pytest.approx(40.0)]
    now[0] = 75.0
    limiter.acquire()  # window now holds t=60 only (t=10 expired): no wait
    assert len(slept) == 1


def test_rate_limiter_is_used_for_real_calls_only(tmp_path):
    calls = []

    class Counting(RateLimiter):
        def acquire(self):
            calls.append(1)

    fake = FakeOpenRouter(['{"a": "x"}'])
    c = client(fake, tmp_path, limiter=Counting(1))
    c.chat(MESSAGES, SCHEMA)
    c.chat(MESSAGES, SCHEMA)  # cache hit: no slot used
    assert len(calls) == 1


def test_missing_key_gives_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("cpsagent.grounding.openrouter.load_dotenv", lambda: None)
    with pytest.raises(MissingApiKeyError, match="OPENROUTER_API_KEY"):
        client(FakeOpenRouter([]), tmp_path, api_key=None)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_error_is_reported_without_the_key(tmp_path, status):
    c = client(FakeOpenRouter([status]), tmp_path)
    with pytest.raises(AuthError) as exc:
        c.chat(MESSAGES, SCHEMA)
    assert SECRET not in str(exc.value)
    [row] = log_rows(tmp_path)
    assert row["status"] == "error" and row["httpStatus"] == status


def test_server_error_raises_call_error_and_is_logged(tmp_path):
    c = client(FakeOpenRouter([500]), tmp_path)
    with pytest.raises(LLMCallError):
        c.chat(MESSAGES, SCHEMA)
    assert log_rows(tmp_path)[0]["httpStatus"] == 500


def test_key_never_written_to_log_or_cache(tmp_path):
    fake = FakeOpenRouter(['{"a": "x"}'])
    client(fake, tmp_path).chat(MESSAGES, SCHEMA)
    assert fake.headers[0]["authorization"] == f"Bearer {SECRET}"  # sent only to the API
    for path in [tmp_path / "calls.jsonl", *(tmp_path / "cache").iterdir()]:
        assert SECRET not in path.read_text()


def test_pinned_provider_is_sent_and_keys_the_cache(tmp_path):
    fake = FakeOpenRouter(['{"a": "x"}'])
    c = client(fake, tmp_path, provider="Parasail")
    c.chat(MESSAGES, SCHEMA)
    assert fake.requests[0]["provider"] == {"order": ["Parasail"], "allow_fallbacks": False}
    assert log_rows(tmp_path)[0]["requestedProvider"] == "Parasail"
    assert not client(fake, tmp_path).is_cached(MESSAGES, SCHEMA, 0.0)  # other provider
    assert c.is_cached(MESSAGES, SCHEMA, 0.0)
    assert cache_key("m", MESSAGES, SCHEMA, 0.0, None, 0) == cache_key("m", MESSAGES, SCHEMA, 0.0)


def test_repeat_index_is_a_separate_cached_call(tmp_path):
    fake = FakeOpenRouter(['{"a": "x"}', '{"a": "y"}'])
    c = client(fake, tmp_path)
    assert c.chat(MESSAGES, SCHEMA).content == '{"a": "x"}'
    assert c.chat(MESSAGES, SCHEMA, repeat=1).content == '{"a": "y"}'
    assert c.chat(MESSAGES, SCHEMA, repeat=1).cache_hit and len(fake.requests) == 2
    assert "provider" not in fake.requests[0]
