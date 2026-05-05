"""Week 1 DoD coverage — LLM call metrics (tokens, cost, latency)."""
from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace

from backend.services.ai.llm_metrics import (
    LLMUsage,
    compute_cost_usd,
    extract_usage,
    record_llm_call,
)


class LLMMetricsTests(unittest.TestCase):
    def test_extract_usage_handles_responses_api_shape(self) -> None:
        response = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=100, output_tokens=50, total_tokens=150)
        )
        usage = extract_usage(response)
        self.assertEqual(usage.input_tokens, 100)
        self.assertEqual(usage.output_tokens, 50)
        self.assertEqual(usage.total_tokens, 150)

    def test_extract_usage_handles_chat_completions_shape(self) -> None:
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=80, completion_tokens=40, total_tokens=120)
        )
        usage = extract_usage(response)
        self.assertEqual(usage.input_tokens, 80)
        self.assertEqual(usage.output_tokens, 40)

    def test_extract_usage_handles_dict_shape(self) -> None:
        response = {"usage": {"prompt_tokens": 12, "completion_tokens": 8}}
        usage = extract_usage(response)
        self.assertEqual(usage.input_tokens, 12)
        self.assertEqual(usage.output_tokens, 8)
        self.assertEqual(usage.total_tokens, 20)  # computed when missing

    def test_extract_usage_returns_zeros_on_garbage(self) -> None:
        for value in (None, object(), {}, SimpleNamespace()):
            usage = extract_usage(value)
            self.assertTrue(usage.is_empty)

    def test_compute_cost_known_model(self) -> None:
        usage = LLMUsage(input_tokens=1000, output_tokens=1000, total_tokens=2000)
        cost = compute_cost_usd(model="gpt-4o-mini", usage=usage)
        # 1k in @ 0.00015 + 1k out @ 0.00060 = 0.00075
        self.assertAlmostEqual(cost, 0.00075, places=6)

    def test_compute_cost_unknown_model_returns_zero(self) -> None:
        usage = LLMUsage(input_tokens=500, output_tokens=500, total_tokens=1000)
        self.assertEqual(compute_cost_usd(model="some-future-model", usage=usage), 0.0)

    def test_compute_cost_strips_provider_prefix(self) -> None:
        usage = LLMUsage(input_tokens=1000, output_tokens=0, total_tokens=1000)
        cost = compute_cost_usd(model="openai/gpt-4o-mini", usage=usage)
        self.assertAlmostEqual(cost, 0.00015, places=6)

    def test_compute_cost_empty_usage_is_zero(self) -> None:
        self.assertEqual(compute_cost_usd(model="gpt-4o", usage=LLMUsage(0, 0, 0)), 0.0)

    def test_record_llm_call_emits_structured_log(self) -> None:
        response = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, total_tokens=15)
        )
        with self.assertLogs("llm.metrics", level="INFO") as captured:
            record = record_llm_call(
                model="gpt-4o-mini",
                response=response,
                duration_ms=123.4,
                api="responses",
            )
        self.assertEqual(record["input_tokens"], 10)
        self.assertEqual(record["output_tokens"], 5)
        self.assertEqual(record["api"], "responses")
        self.assertGreater(record["cost_usd"], 0.0)
        joined = "\n".join(captured.output)
        self.assertIn("model=gpt-4o-mini", joined)
        self.assertIn("duration_ms=123.4", joined)

    def test_record_llm_call_never_raises(self) -> None:
        # Garbage input must not break the LLM response path.
        result = record_llm_call(
            model=None,
            response="not a real response object",
            duration_ms=0.0,
        )
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
