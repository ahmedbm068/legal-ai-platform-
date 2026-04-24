import unittest

from backend.services.ai.agents.matter_classification_agent import MatterClassificationAgent


class MatterClassificationAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = MatterClassificationAgent()

    def test_classifies_succession_with_code_family(self) -> None:
        result = self.agent.classify_matter(
            user_prompt="Analyze succession rights of heirs and testament limits.",
            case_context={"case": {"title": "Estate dispute", "jurisdiction_country": "tunisia"}},
            available_document_summaries=["Testament and heirs declarations are under review."],
        )
        self.assertTrue(result.success)
        self.assertEqual(result.payload.get("matter_type"), "succession")
        self.assertEqual(result.payload.get("likely_code_family"), "code_succession")
        self.assertEqual(result.payload.get("task_type"), "analysis")

    def test_marks_mixed_when_private_law_signals_conflict(self) -> None:
        result = self.agent.classify_matter(
            user_prompt=(
                "Assess contract breach obligations and cross-border conflict of laws for inheritance claims."
            ),
            case_context={"case": {"title": "Mixed dispute"}},
            available_document_summaries=[],
        )
        self.assertTrue(result.success)
        self.assertEqual(result.payload.get("matter_type"), "mixed private law matter")
        self.assertEqual(result.payload.get("confidence"), "low")
        self.assertTrue(str(result.payload.get("ambiguity_note") or "").strip())

    def test_detects_drafting_task(self) -> None:
        result = self.agent.classify_matter(
            user_prompt="Draft a client-ready memo explaining the likely contractual exposure.",
            case_context={},
            available_document_summaries=[],
        )
        self.assertTrue(result.success)
        self.assertEqual(result.payload.get("task_type"), "drafting")

    def test_detects_procedural_dimension(self) -> None:
        result = self.agent.classify_matter(
            user_prompt="Research filing deadline and jurisdiction competence for exequatur.",
            case_context={},
            available_document_summaries=[],
        )
        self.assertTrue(result.success)
        self.assertIn(result.payload.get("legal_dimension"), {"procedural", "mixed"})


if __name__ == "__main__":
    unittest.main()
