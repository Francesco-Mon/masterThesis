"""OpenRouter client: one measured, cached, rate-limited, budget-capped chat call.

Every call (also a cache hit) appends one line to `results/llm_calls.jsonl`.
Cost is read from OpenRouter's `usage.cost`, never estimated.

Configuration (environment or `.env`, loaded with python-dotenv):
  OPENROUTER_API_KEY   required for real calls; never printed, logged or cached
  OPENROUTER_BASE_URL  default https://openrouter.ai/api/v1
  LLM_RPM              client-side requests per minute (default 20, the free-tier limit)
  MAX_COST_USD         spending cap per run = per client instance (default 0.5)
"""

import hashlib
import json
import os
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import openai
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_CACHE_DIR = Path(".llm_cache")
DEFAULT_CALLS_LOG = Path("results/llm_calls.jsonl")


class MissingApiKeyError(RuntimeError):
    pass


class AuthError(RuntimeError):
    """401/403 from OpenRouter: reported to the user, never worked around."""


class BudgetExceededError(RuntimeError):
    """The run has spent MAX_COST_USD: stop instead of calling again."""


class LLMCallError(RuntimeError):
    """Any other failed call (network, 429 after the SDK's retries, 5xx, empty answer)."""


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str  # model id returned by OpenRouter (may differ from the requested alias)
    provider: str | None  # who served the request (OpenRouter's `provider` field)
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float  # cost of the original call (also on a cache hit)
    latency_s: float  # latency of the original call (also on a cache hit)
    cache_hit: bool


class RateLimiter:
    """Sliding window: at most `rpm` calls in any 60 s. Clock and sleep are injectable."""

    def __init__(
        self,
        rpm: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rpm < 1:
            raise ValueError("rpm must be >= 1")
        self.rpm, self._clock, self._sleep = rpm, clock, sleep
        self._sent: deque[float] = deque()

    def acquire(self) -> None:
        now = self._clock()
        while self._sent and now - self._sent[0] >= 60.0:
            self._sent.popleft()
        if len(self._sent) >= self.rpm:
            self._sleep(60.0 - (now - self._sent[0]))
            self._sent.popleft()
            now = self._clock()
        self._sent.append(now)


def cache_key(
    model: str,
    messages: list[dict],
    schema: dict,
    temperature: float,
    provider: str | None = None,
    repeat: int = 0,
) -> str:
    """Key = (model, messages, schema, temperature): rerunning the same test costs nothing.
    A fixed provider and a repeat index > 0 (Stability runs: same request, separate
    calls) are part of the key only when set, so older cache entries stay valid."""
    data = {"model": model, "messages": messages, "schema": schema, "temperature": temperature}
    data |= {"provider": provider} if provider else {}
    data |= {"repeat": repeat} if repeat else {}
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


class OpenRouterClient:
    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        rpm: int | None = None,
        max_cost_usd: float | None = None,
        cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
        calls_log: Path | str | None = DEFAULT_CALLS_LOG,
        http_client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        max_http_retries: int = 2,
        timeout_s: float = 60.0,
        provider: str | None = None,
    ) -> None:
        """`http_client` lets tests inject an httpx.MockTransport (no network).
        `cache_dir=None` disables the cache, `calls_log=None` disables the call log.
        `provider` pins one OpenRouter provider (`order: [provider]`, no fallbacks)."""
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise MissingApiKeyError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and put the key "
                "there (the file is git-ignored)."
            )
        self.model, self.provider = model, provider
        self.max_cost_usd = (
            max_cost_usd if max_cost_usd is not None else float(os.getenv("MAX_COST_USD", "0.5"))
        )
        self.spent_usd = 0.0  # actual spend of this run (cache hits are free)
        self.run_id = uuid.uuid4().hex[:12]
        self._limiter = limiter or RateLimiter(rpm or int(os.getenv("LLM_RPM", "20")))
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._calls_log = Path(calls_log) if calls_log is not None else None
        self._sdk = openai.OpenAI(
            api_key=api_key,
            base_url=base_url or os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
            http_client=http_client,
            max_retries=max_http_retries,  # SDK backoff on 429/5xx, inside one logged call
            timeout=timeout_s,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        schema_name: str = "result",
        temperature: float = 0.0,
        attempt: int = 1,
        repeat: int = 0,
    ) -> LLMResponse:
        """One chat completion with `response_format: json_schema`. `attempt` is the
        caller's retry counter (1 = first try), recorded in the call log; `repeat` is the
        repetition index of a Stability run (0 = first)."""
        key = cache_key(self.model, messages, schema, temperature, self.provider, repeat)
        cached = self._cache_get(key)
        if cached is not None:
            self._log(cached, temperature, attempt, schema_name)
            return cached

        if self.spent_usd >= self.max_cost_usd:
            raise BudgetExceededError(
                f"Spending cap reached: {self.spent_usd:.4f} USD >= MAX_COST_USD "
                f"{self.max_cost_usd} USD for this run."
            )
        self._limiter.acquire()
        start = time.perf_counter()
        try:
            completion = self._sdk.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
                extra_body=self._extra_body(),
            )
        except (openai.AuthenticationError, openai.PermissionDeniedError) as e:
            self._log_error(e.status_code, temperature, attempt, schema_name, start)
            raise AuthError(
                f"OpenRouter refused the key (HTTP {e.status_code}). Check OPENROUTER_API_KEY "
                "in .env and the account's credits/limits."
            ) from None
        except openai.APIError as e:
            status = getattr(e, "status_code", None)
            self._log_error(status, temperature, attempt, schema_name, start)
            raise LLMCallError(f"OpenRouter call failed ({type(e).__name__}, {status})") from e
        latency = time.perf_counter() - start

        usage = completion.usage.model_dump() if completion.usage else {}
        cost = float(usage.get("cost") or 0.0)
        self.spent_usd += cost
        choice = completion.choices[0] if completion.choices else None
        content = choice.message.content if choice and choice.message else None
        response = LLMResponse(
            content=content or "",
            model=completion.model or self.model,
            provider=(completion.model_extra or {}).get("provider"),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=cost,
            latency_s=latency,
            cache_hit=False,
        )
        self._log(response, temperature, attempt, schema_name, "ok" if content else "empty")
        if not content:
            raise LLMCallError("OpenRouter returned an empty answer")
        self._cache_put(key, response)
        return response

    def _extra_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"usage": {"include": True}}  # ask OpenRouter for usage.cost
        if self.provider:
            body["provider"] = {"order": [self.provider], "allow_fallbacks": False}
        return body

    def is_cached(
        self, messages: list[dict], schema: dict, temperature: float, repeat: int = 0
    ) -> bool:
        """Whether this call would be served from the cache (for cost estimates)."""
        if self._cache_dir is None:
            return False
        key = cache_key(self.model, messages, schema, temperature, self.provider, repeat)
        return (self._cache_dir / f"{key}.json").exists()

    # --- cache --------------------------------------------------------------------------

    def _cache_get(self, key: str) -> LLMResponse | None:
        if self._cache_dir is None:
            return None
        path = self._cache_dir / f"{key}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return LLMResponse(**{**data, "cache_hit": True})

    def _cache_put(self, key: str, response: LLMResponse) -> None:
        if self._cache_dir is None:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        data = {k: v for k, v in response.__dict__.items() if k != "cache_hit"}
        tmp = self._cache_dir / f"{key}.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._cache_dir / f"{key}.json")

    # --- call log -----------------------------------------------------------------------

    def _write(self, row: dict[str, Any]) -> None:
        if self._calls_log is None:
            return
        self._calls_log.parent.mkdir(parents=True, exist_ok=True)
        with self._calls_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _base_row(self, temperature: float, attempt: int, schema_name: str) -> dict[str, Any]:
        return {
            "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "runId": self.run_id,
            "requestedModel": self.model,
            "requestedProvider": self.provider,
            "temperature": temperature,
            "schema": schema_name,
            "attempt": attempt,
        }

    def _log(
        self,
        r: LLMResponse,
        temperature: float,
        attempt: int,
        schema_name: str,
        status: str = "ok",
    ) -> None:
        # On a cache hit, tokens/cost/latency are those of the original call (so a rerun
        # reproduces the measurements); `spentUsd` is what this line actually cost.
        self._write(
            self._base_row(temperature, attempt, schema_name)
            | {
                "model": r.model,
                "provider": r.provider,
                "status": status,
                "cacheHit": r.cache_hit,
                "promptTokens": r.prompt_tokens,
                "completionTokens": r.completion_tokens,
                "costUsd": r.cost_usd,
                "spentUsd": 0.0 if r.cache_hit else r.cost_usd,
                "latencyS": round(r.latency_s, 4),
            }
        )

    def _log_error(
        self, status: int | None, temperature: float, attempt: int, schema_name: str, start: float
    ) -> None:
        self._write(
            self._base_row(temperature, attempt, schema_name)
            | {
                "model": None,
                "provider": None,
                "status": "error",
                "httpStatus": status,
                "cacheHit": False,
                "spentUsd": 0.0,
                "latencyS": round(time.perf_counter() - start, 4),
            }
        )
