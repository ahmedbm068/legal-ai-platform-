"""Tests for CopilotCaseAnalysisMixin._looks_like_prompt_template_noise
and _normalize_risk_items."""

import unittest

from backend.services.ai.copilot_case_analysis_service import CopilotCaseAnalysisMixin

noise = CopilotCaseAnalysisMixin._looks_like_prompt_template_noise
normalize = CopilotCaseAnalysisMixin._normalize_risk_items


class TestLooksLikePromptTemplateNoise(unittest.TestCase):
    # ── Should be detected as noise ─────────────────────────────────────────
    def test_return_valid_json(self):
        self.assertTrue(noise("Return valid JSON only."))

    def test_use_only_provided_evidence(self):
        self.assertTrue(noise("Use only the provided evidence and context."))

    def test_do_not_invent(self):
        self.assertTrue(noise("Do not invent legal conclusions, statutes, or deadlines."))

    def test_schema_key(self):
        self.assertTrue(noise('"overview": "string"'))

    def test_you_are_agent(self):
        self.assertTrue(noise("You are the Case Reasoning Agent inside a legal AI platform."))

    def test_task_colon(self):
        self.assertTrue(noise("Task: reason over case evidence"))

    def test_rules_colon(self):
        self.assertTrue(noise("Rules:\n- Use only the provided case intelligence."))

    def test_jurisdiction_guardrails(self):
        self.assertTrue(noise("Jurisdiction guardrails: apply Tunisian law first."))

    def test_schema_standalone_key(self):
        self.assertTrue(noise("legal_risks"))

    def test_json_fragment(self):
        self.assertTrue(noise('{"overview": "string", "main_issues": []}'))

    def test_empty_string(self):
        self.assertFalse(noise(""))

    def test_none_coerced(self):
        self.assertFalse(noise(None))  # type: ignore[arg-type]

    # ── Should NOT be detected as noise (real legal risks) ──────────────────
    def test_sla_breach_risk(self):
        self.assertFalse(noise("SLA breach risk due to 99.7% availability failure"))

    def test_data_loss_regulatory(self):
        self.assertFalse(noise("Data loss may trigger regulatory notification duties under Tunisian law"))

    def test_contract_enforceability(self):
        self.assertFalse(noise("Contract enforceability requires Tunisian mandatory law review"))

    def test_limitation_period(self):
        self.assertFalse(noise("Limitation period for contractual claims may be 10 years under Tunisian COC"))

    def test_jurisdiction_specific_review(self):
        # Real risk item that starts with "Jurisdiction" but is NOT the guardrail header
        self.assertFalse(noise("Jurisdiction-specific review required: Due process and procedural fairness (Tunisia)"))

    def test_payment_default(self):
        self.assertFalse(noise("Failure to pay SLA credits by May 20 constitutes a secondary breach"))


class TestNormalizeRiskItems(unittest.TestCase):
    def test_filters_prompt_noise(self):
        items = [
            "Return valid JSON only.",
            "SLA breach risk due to 99.7% availability failure",
            "Use only the provided evidence.",
        ]
        result = normalize(items)
        self.assertEqual(result, ["SLA breach risk due to 99.7% availability failure"])

    def test_handles_none_values(self):
        result = normalize([None, "", "  ", "Data loss risk"])  # type: ignore[list-item]
        self.assertEqual(result, ["Data loss risk"])

    def test_handles_dict_items(self):
        result = normalize([{"risk": "Contract enforceability review needed"}])
        self.assertEqual(result, ["Contract enforceability review needed"])

    def test_handles_non_list_input(self):
        # Single string — should be wrapped
        result = normalize("SLA breach risk")  # type: ignore[arg-type]
        self.assertEqual(result, ["SLA breach risk"])

    def test_handles_empty_input(self):
        self.assertEqual(normalize([]), [])
        self.assertEqual(normalize(None), [])  # type: ignore[arg-type]

    def test_deduplicates(self):
        result = normalize(["SLA breach risk", "SLA breach risk"])
        self.assertEqual(result, ["SLA breach risk"])

    def test_capitalises_first_letter(self):
        result = normalize(["data loss may trigger regulatory duties"])
        self.assertTrue(result[0][0].isupper())

    def test_handles_numbered_list_in_single_string(self):
        result = normalize(["1) SLA breach risk 2) Data loss risk"])
        self.assertIn("SLA breach risk", result)

    def test_handles_non_list_non_string_gracefully(self):
        # Should not crash; integers coerced to string and processed
        result = normalize([42, 3.14])  # type: ignore[list-item]
        self.assertIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
