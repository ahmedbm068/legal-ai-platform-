"""Phase A1 — Verifier service tests.

Verifies the ``grounded / partial / refused`` taxonomy, the never-refuse
rules for drafting & explanation intents, and the ``urn:lai:weak-grounding``
problem+json contract.
"""

from __future__ import annotations

import unittest

from backend.services.ai.verifier_service import (
    STATE_GROUNDED,
    STATE_PARTIAL,
    STATE_REFUSED,
    WEAK_GROUNDING_PROBLEM_TYPE,
    VerificationOutcome,
    build_weak_grounding_problem,
    verifier_service,
)


def _response(**overrides: object) -> dict[str, object]:
    """Build a minimal copilot response dict with sensible defaults."""
    base: dict[str, object] = {
        "answer": "x",
        "grounding": "Partial",
        "confidence": "medium",
        "sources": [],
        "mode": "default",
        "parsed_intent": "ask_global",
    }
    base.update(overrides)
    return base


class VerifierGroundedTests(unittest.TestCase):
    def test_case_grounded_with_one_source_is_grounded(self) -> None:
        outcome = verifier_service.verify(
            _response(
                grounding="Case-grounded",
                confidence="high",
                sources=[{"document_id": 1, "snippet": "..."}],
                mode="legal_search",
                parsed_intent="ask_case",
            )
        )
        self.assertEqual(outcome.state, STATE_GROUNDED)
        self.assertFalse(outcome.should_refuse)

    def test_case_grounded_label_in_ai_insight_is_recognized(self) -> None:
        outcome = verifier_service.verify(
            {
                "ai_insight": {"grounding_type": "Case-grounded (document-based)"},
                "sources": [{"document_id": 7}],
                "confidence": "high",
                "mode": "legal_search",
                "parsed_intent": "ask_case",
            }
        )
        self.assertEqual(outcome.state, STATE_GROUNDED)


class VerifierRefusalTests(unittest.TestCase):
    def test_legal_search_with_no_sources_low_confidence_refuses(self) -> None:
        outcome = verifier_service.verify(
            _response(
                grounding="Not grounded",
                confidence="low",
                sources=[],
                mode="legal_search",
                parsed_intent="ask_global",
            )
        )
        self.assertEqual(outcome.state, STATE_REFUSED)
        self.assertTrue(outcome.should_refuse)
        self.assertIn("grounded evidence", outcome.reason)

    def test_drafting_intent_never_refuses_even_when_ungrounded(self) -> None:
        outcome = verifier_service.verify(
            _response(
                grounding="Not grounded",
                confidence="low",
                sources=[],
                mode="default",
                parsed_intent="draft_client_email_case",
            )
        )
        self.assertEqual(outcome.state, STATE_PARTIAL)
        self.assertFalse(outcome.should_refuse)

    def test_summarize_intent_never_refuses(self) -> None:
        outcome = verifier_service.verify(
            _response(
                grounding="Not grounded",
                confidence="low",
                sources=[],
                mode="default",
                parsed_intent="summarize_case",
            )
        )
        self.assertEqual(outcome.state, STATE_PARTIAL)
        self.assertFalse(outcome.should_refuse)


class VerifierPartialTests(unittest.TestCase):
    def test_partial_grounding_yields_partial_state(self) -> None:
        outcome = verifier_service.verify(
            _response(
                grounding="Partial",
                confidence="medium",
                sources=[{"document_id": 1}],
                mode="legal_search",
            )
        )
        self.assertEqual(outcome.state, STATE_PARTIAL)
        self.assertFalse(outcome.should_refuse)

    def test_not_grounded_with_medium_confidence_is_partial_not_refused(self) -> None:
        outcome = verifier_service.verify(
            _response(
                grounding="Not grounded",
                confidence="medium",  # not low → not refusable
                sources=[],
                mode="legal_search",
            )
        )
        self.assertEqual(outcome.state, STATE_PARTIAL)
        self.assertFalse(outcome.should_refuse)

    def test_outcome_to_dict_round_trip(self) -> None:
        outcome = VerificationOutcome(state="grounded", reason="ok", should_refuse=False)
        payload = outcome.to_dict()
        self.assertEqual(payload, {"state": "grounded", "reason": "ok", "should_refuse": False})


class WeakGroundingProblemTests(unittest.TestCase):
    def test_problem_body_uses_urn_type(self) -> None:
        body = build_weak_grounding_problem(detail="too weak", instance="/ai/copilot")
        self.assertEqual(body["type"], WEAK_GROUNDING_PROBLEM_TYPE)
        self.assertEqual(body["type"], "urn:lai:weak-grounding")
        self.assertEqual(body["status"], 422)
        self.assertEqual(body["title"], "Weak grounding")
        self.assertEqual(body["detail"], "too weak")
        self.assertEqual(body["instance"], "/ai/copilot")

    def test_problem_body_omits_instance_when_blank(self) -> None:
        body = build_weak_grounding_problem(detail="x")
        self.assertNotIn("instance", body)

    def test_problem_body_includes_reason_when_provided(self) -> None:
        body = build_weak_grounding_problem(detail="x", reason="zero sources")
        self.assertEqual(body["reason"], "zero sources")


class VerifierDefensiveReadersTests(unittest.TestCase):
    def test_empty_response_falls_through_to_partial(self) -> None:
        outcome = verifier_service.verify({})
        self.assertEqual(outcome.state, STATE_PARTIAL)
        self.assertFalse(outcome.should_refuse)

    def test_unknown_intent_in_legal_search_with_signals_can_refuse(self) -> None:
        outcome = verifier_service.verify(
            {
                "grounding": "Not grounded",
                "confidence": "low",
                "sources": [],
                "mode": "legal_search",
                "parsed_intent": "totally_unknown_intent",
            }
        )
        self.assertEqual(outcome.state, STATE_REFUSED)


if __name__ == "__main__":
    unittest.main()
