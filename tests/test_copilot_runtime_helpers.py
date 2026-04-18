import unittest
from typing import Any

from backend.services.ai.agents.copilot_intent_execution_agent import (
    CopilotIntentExecutionAgent,
    CopilotIntentExecutionContext,
)
from backend.services.ai.copilot_service import CopilotService


class CopilotFieldExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CopilotService.__new__(CopilotService)

    def test_extract_field_value_handles_quotes_and_following_fields(self) -> None:
        message = 'update case #12 set title to "Major Breach Escalation" and description to "Need urgent action"'
        extracted = self.service._extract_field_value(
            message,
            ["case title", "title"],
            stop_labels=["description", "status", "client", "jurisdiction", "country"],
        )
        self.assertEqual(extracted, "Major Breach Escalation")

    def test_extract_field_value_handles_compound_set_statement(self) -> None:
        message = "client #8 set phone to +21626002544 and email to legal@example.com"
        extracted = self.service._extract_field_value(
            message,
            ["phone", "mobile", "telephone"],
            stop_labels=["name", "email", "address"],
        )
        self.assertEqual(extracted, "+21626002544")


class CopilotIntentExecutionAgentTests(unittest.TestCase):
    def _build_context(self, parsed: dict[str, Any]) -> CopilotIntentExecutionContext:
        return CopilotIntentExecutionContext(
            db=None,  # type: ignore[arg-type]
            tenant_id=1,
            user_id=5,
            user_role="lawyer",
            message="test message",
            top_k=5,
            use_external_research=False,
            workspace_case_id=None,
            resolved_query="test message",
            parsed=parsed,
            preoptimized_query=None,
            normalized_allowed_case_ids=None,
            normalized_allowed_document_ids=None,
        )

    def test_unknown_intent_returns_runtime_fallback(self) -> None:
        class Runtime:
            def _unsupported_intent_response(self) -> dict[str, Any]:
                return {"answer": "unsupported"}

        agent = CopilotIntentExecutionAgent()
        result = agent.execute(intent="nonexistent_intent", runtime=Runtime(), ctx=self._build_context(parsed={}))
        self.assertEqual(result.get("answer"), "unsupported")

    def test_update_case_uses_target_id_when_case_id_missing(self) -> None:
        class Runtime:
            def __init__(self) -> None:
                self.received_case_id = None

            def _unsupported_intent_response(self) -> dict[str, Any]:
                return {"answer": "unsupported"}

            def _update_case_action(self, **kwargs: Any) -> dict[str, Any]:
                self.received_case_id = kwargs.get("case_id")
                return {"answer": "ok"}

        runtime = Runtime()
        agent = CopilotIntentExecutionAgent()
        result = agent.execute(
            intent="update_case",
            runtime=runtime,
            ctx=self._build_context(parsed={"target_id": 77}),
        )
        self.assertEqual(result.get("answer"), "ok")
        self.assertEqual(runtime.received_case_id, 77)


class CopilotChatModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CopilotService.__new__(CopilotService)
        self.service.client = None  # type: ignore[assignment]
        self.service.model = "test-model"  # type: ignore[assignment]

    def test_looks_like_conversational_opening_detects_greeting(self) -> None:
        self.assertTrue(self.service._looks_like_conversational_opening("hi"))
        self.assertTrue(self.service._looks_like_conversational_opening("hello there"))
        self.assertFalse(self.service._looks_like_conversational_opening("explain force majeure in contract law"))

    def test_chat_mode_returns_professional_greeting_for_short_opening(self) -> None:
        result = self.service._respond_in_chat_mode(
            question="hi",
            user_role="lawyer",
            conversation_history=[],
        )
        self.assertIn("Legal AI assistant", result.get("answer", ""))
        self.assertEqual(result.get("used_fallback"), False)
        self.assertEqual(result.get("confidence"), "high")

    def test_chat_mode_uses_non_llm_fallback_when_provider_missing(self) -> None:
        result = self.service._respond_in_chat_mode(
            question="Can you help me plan a legal strategy memo for a client meeting?",
            user_role="lawyer",
            conversation_history=[],
        )
        self.assertEqual(result.get("used_fallback"), True)
        self.assertEqual(result.get("fallback_reason"), "No LLM provider API key is configured")
        self.assertIn("legal reasoning", result.get("answer", "").lower())


if __name__ == "__main__":
    unittest.main()
