"""
LLM call metrics — token usage, latency, and USD cost.

Single source of truth for:
  • extracting `usage` from any provider response (OpenAI, Groq, OpenRouter)
  • computing USD cost from a centralized pricing table
  • emitting a structured log line per LLM call

This module is intentionally side-effect-light: it never raises and never blocks
the response path. Used by `LLMGateway._ResponsesCompat.create` to instrument
every LLM call without touching call sites.

Pricing table is conservative — if a model is unknown, cost falls back to 0.0
and the call is still logged with token counts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_logger = logging.getLogger("llm.metrics")


# ──────────────────────────────────────────────────────────────────────────────
# Pricing table — USD per 1K tokens (input, output)
# Last refreshed: 2026-05-05. Update via scripts/refresh_llm_pricing.py.
# ──────────────────────────────────────────────────────────────────────────────
_PRICING_USD_PER_1K: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o":              (0.0025, 0.0100),
    "gpt-4o-mini":         (0.00015, 0.00060),
    "gpt-4.1":             (0.0020, 0.0080),
    "gpt-4.1-mini":        (0.00040, 0.00160),
    "o1":                  (0.01500, 0.06000),
    "o1-mini":             (0.00300, 0.01200),
    # Groq (community pricing — verify before billing)
    "llama-3.3-70b-versatile":  (0.00059, 0.00079),
    "llama-3.1-70b-versatile":  (0.00059, 0.00079),
    "llama-3.1-8b-instant":     (0.00005, 0.00008),
    "mixtral-8x7b-32768":       (0.00024, 0.00024),
    # OpenRouter — pricing varies; default to 0 unless overridden
}


def _normalize_model_key(model: str | None) -> str:
    """Return a lowercased, prefix-stripped model identifier for table lookup."""
    raw = (model or "").strip().lower()
    if not raw:
        return ""
    # Strip provider prefixes like "openai/", "groq/", "openrouter/anthropic/"
    if "/" in raw:
        raw = raw.rsplit("/", 1)[-1]
    return raw


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int

    @property
    def is_empty(self) -> bool:
        return self.total_tokens == 0


def extract_usage(response: Any) -> LLMUsage:
    """Extract token usage from a provider response. Never raises.

    Handles:
      • OpenAI Responses API:    response.usage.input_tokens / output_tokens
      • OpenAI Chat Completions: response.usage.prompt_tokens / completion_tokens
      • Dict-shaped responses:   response["usage"]["..."]
    """
    try:
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        if usage is None:
            return LLMUsage(0, 0, 0)

        def _read(obj: Any, *keys: str) -> int:
            for key in keys:
                value = getattr(obj, key, None)
                if value is None and isinstance(obj, dict):
                    value = obj.get(key)
                if isinstance(value, (int, float)) and value > 0:
                    return int(value)
            return 0

        input_tokens = _read(usage, "input_tokens", "prompt_tokens")
        output_tokens = _read(usage, "output_tokens", "completion_tokens")
        total_tokens = _read(usage, "total_tokens") or (input_tokens + output_tokens)
        return LLMUsage(input_tokens, output_tokens, total_tokens)
    except Exception:
        return LLMUsage(0, 0, 0)


def compute_cost_usd(*, model: str | None, usage: LLMUsage) -> float:
    """Return USD cost for the given model + usage. Unknown models → 0.0."""
    if usage.is_empty:
        return 0.0
    pricing = _PRICING_USD_PER_1K.get(_normalize_model_key(model))
    if pricing is None:
        return 0.0
    in_price, out_price = pricing
    return round(
        (usage.input_tokens / 1000.0) * in_price
        + (usage.output_tokens / 1000.0) * out_price,
        6,
    )


def record_llm_call(
    *,
    model: str | None,
    response: Any,
    duration_ms: float,
    api: str = "responses",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit a structured log line for an LLM call. Returns the recorded dict.

    Format:
        [LLM] call | model=... api=... duration_ms=... in=... out=... total=... cost_usd=...

    Never raises — instrumentation must not break the response path.
    """
    try:
        usage = extract_usage(response)
        cost = compute_cost_usd(model=model, usage=usage)
        record: dict[str, Any] = {
            "model": model or "unknown",
            "api": api,
            "duration_ms": round(float(duration_ms), 1),
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "cost_usd": cost,
        }
        if extra:
            record.update({k: v for k, v in extra.items() if v is not None})
        _logger.info(
            "[LLM] call | model=%s api=%s duration_ms=%.1f in=%d out=%d total=%d cost_usd=%.6f",
            record["model"], record["api"], record["duration_ms"],
            record["input_tokens"], record["output_tokens"], record["total_tokens"],
            record["cost_usd"],
        )
        return record
    except Exception:
        # Instrumentation must never break the caller.
        return {}
