import unittest

from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter


class AgentOutputFormatterTests(unittest.TestCase):
    def test_quality_guidance_includes_legal_copilot_guardrails(self) -> None:
        guidance = AgentOutputFormatter.build_quality_guidance(
            task="reason over legal evidence",
            structured_json=True,
        ).lower()
        self.assertIn("not as a final decision-maker", guidance)
        self.assertIn("separate confirmed facts", guidance)
        self.assertIn("never fabricate authority", guidance)
        self.assertIn("professional legal review", guidance)


if __name__ == "__main__":
    unittest.main()
