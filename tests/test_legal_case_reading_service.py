import unittest
from types import SimpleNamespace

from backend.services.ai.document_insight_service import DocumentInsightService
from backend.services.ai.legal_case_reading_service import LegalCaseReadingService
from backend.services.ai.summarization_service import SummarizationService


CASE_TEXT = """
Caparo Industries plc v Dickman
[1990] UKHL 2
House of Lords
Before: Lord Bridge, Lord Roskill
Negligence - duty of care - auditors - shareholder reliance

The claimant bought shares in Fidelity plc after reviewing the company's audited accounts.
The defendant auditors had prepared the accounts for the company.
The claimant alleged that the accounts were inaccurate and brought a claim in negligence.
The issue was whether auditors owed a duty of care to potential investors relying on published accounts.
The House of Lords held that no duty of care was owed to investors for that purpose.
The court held that a duty of care requires foreseeability, proximity, and that it is fair, just and reasonable to impose the duty.
Lord Bridge said that if the facts involved a known recipient and known transaction, the result might be different.
"""


class LegalCaseReadingServiceTests(unittest.TestCase):
    def test_build_case_analysis_extracts_lawyer_case_brief_fields(self) -> None:
        analysis = LegalCaseReadingService().build_case_analysis(
            text=CASE_TEXT,
            document_type="court_judgment",
            filename="caparo-v-dickman.pdf",
        )

        self.assertIsNotNone(analysis)
        assert analysis is not None
        self.assertIn("Caparo Industries", analysis["case_name"])
        self.assertEqual(analysis["court_level"], "House of Lords")
        self.assertEqual(analysis["citation"], "[1990] UKHL 2")
        self.assertIn("negligence", analysis["catchwords"])
        self.assertTrue(analysis["fact_flowchart"])
        self.assertTrue(analysis["legal_issues"])
        self.assertTrue(analysis["holding"])
        self.assertTrue(analysis["ratio"])
        self.assertTrue(analysis["obiter"])

    def test_document_insights_attach_case_analysis_for_judgment(self) -> None:
        document = SimpleNamespace(
            filename="caparo-v-dickman.pdf",
            redacted_text=CASE_TEXT,
            extracted_text=None,
        )

        insights = DocumentInsightService().build_insights(document)

        self.assertEqual(insights["document_type"], "court_judgment")
        self.assertIn("legal_case_analysis", insights)
        self.assertEqual(insights["summary_version"], "v10_case_reading")

    def test_final_summary_includes_case_reading_brief(self) -> None:
        analysis = LegalCaseReadingService().build_case_analysis(
            text=CASE_TEXT,
            document_type="court_judgment",
            filename="caparo-v-dickman.pdf",
        )
        summary = SummarizationService()._build_final_summary({
            "document_type": "court_judgment",
            "general_summary": "This document is a court judgment.",
            "key_points": ["The duty of care issue controls the outcome."],
            "legal_case_analysis": analysis,
        })

        self.assertIn("Legal Case Reading Brief:", summary)
        self.assertIn("Fact Flowchart:", summary)
        self.assertIn("Ratio Decidendi:", summary)
        self.assertIn("Obiter Dicta:", summary)
        self.assertIn("Half-Page Case Summary:", summary)


if __name__ == "__main__":
    unittest.main()
