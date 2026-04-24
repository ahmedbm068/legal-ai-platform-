from __future__ import annotations

import unittest

from backend.services.ai.agents.claim_validation_agent import claim_validation_agent
from backend.services.ai.agents.article_applicability_agent import article_applicability_agent
from backend.services.ai.agents.strict_verifier_agent import strict_verifier_agent
from backend.services.ai.legal_trust_service import legal_trust_service
from backend.services.ai.output_contract_validator import MANDATORY_LEGAL_SECTION_TITLES, output_contract_validator


class LegalTrustEngineTests(unittest.TestCase):
    def test_claim_validation_agent_maps_sentence_to_source_chunk(self) -> None:
        result = claim_validation_agent.validate(
            answer="Payment is due net 30 from invoice date.",
            sources=[
                {
                    "document_id": 7,
                    "chunk_id": 44,
                    "filename": "msa.pdf",
                    "chunk_index": 2,
                    "chunk_text": "The agreement says payment is due net 30 from invoice date.",
                    "score": 0.91,
                }
            ],
        )

        self.assertTrue(result.success)
        payload = result.payload
        self.assertEqual(payload["citation_coverage"], 1.0)
        self.assertEqual(payload["hallucination_rate"], 0.0)
        mapping = payload["sentence_to_source_mapping"][0]
        self.assertEqual(mapping["document_id"], 7)
        self.assertEqual(mapping["chunk_id"], 44)
        self.assertIn(mapping["evidence_strength"], {"STRONG", "MEDIUM"})

    def test_output_contract_validator_requires_all_mandatory_sections(self) -> None:
        sections = [
            {
                "title": title,
                "content": "Not found in provided documents" if title == "Applicable Rule / Law" else "Supported content.",
                "confidence_score": 0.7,
                "citation_coverage": 1.0,
            }
            for title in MANDATORY_LEGAL_SECTION_TITLES
        ]
        validation = output_contract_validator.validate_trust_panel(
            {
                "answer": "structured answer",
                "confidence_score": 0.7,
                "evidence_strength": "STRONG",
                "verified_claims": [],
                "unsupported_claims": [],
                "sentence_to_source_mapping": [
                    {
                        "sentence": "Supported content.",
                        "source_label": "contract.pdf - chunk 1",
                        "document_id": 1,
                        "chunk_id": 2,
                        "chunk_index": 1,
                        "exact_quote_span": "0:18",
                        "quote": "Supported content.",
                        "evidence_strength": "STRONG",
                    }
                ],
                "contradictions": [],
                "missing_information": [],
                "risk_summary": {"client": "Client risk.", "opposing_party": "Opposing risk."},
                "legal_reasoning_sections": sections,
                "metrics": {"citation_coverage": 1.0, "hallucination_rate": 0.0},
            }
        )

        self.assertTrue(validation.is_valid)
        self.assertEqual(validation.errors, [])

    def test_legal_trust_service_builds_mandatory_answer_and_panel(self) -> None:
        result = {
            "answer": "The contract requires payment within 30 days.",
            "confidence": "high",
            "sources": [
                {
                    "document_id": 5,
                    "chunk_id": 9,
                    "filename": "contract.pdf",
                    "chunk_index": 1,
                    "snippet": "The contract requires payment within 30 days.",
                    "score": 0.95,
                }
            ],
            "citations": [],
        }
        output_contract = {
            "legal_issue": "Whether payment is due.",
            "governing_rule": "Payment is due within 30 days under the contract.",
            "application": "The contract requires payment within 30 days.",
            "counter_analysis": "",
            "missing_facts": ["Invoice delivery proof."],
            "next_steps": ["Confirm invoice delivery date."],
            "client_risk_summary": {"summary": "Late payment exposure may exist.", "legal_risk": "Medium"},
            "confidence": "high",
            "relevant_sources": result["sources"],
        }

        trust_result = legal_trust_service.enforce_response(
            result=result,
            output_contract=output_contract,
            case_context={},
            force_structured_answer=True,
        )

        self.assertIn("1. Issue Identification", trust_result.answer)
        self.assertIn("8. Recommended Next Steps", trust_result.answer)
        self.assertTrue(trust_result.trust_panel["legal_reasoning_sections"])
        self.assertTrue(trust_result.validation["is_valid"])

    def test_strict_verifier_rejects_unsupported_sentence(self) -> None:
        result = strict_verifier_agent.verify(
            answer="The contract requires payment within 30 days. Nova paid a 50000 TND penalty.",
            sources=[
                {
                    "document_id": 5,
                    "chunk_id": 9,
                    "filename": "contract.pdf",
                    "chunk_index": 1,
                    "chunk_text": "The contract requires payment within 30 days.",
                    "score": 0.95,
                }
            ],
            min_citation_coverage=0.70,
            reject_unsupported=True,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.payload["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("unsupported_claims_present", result.payload["fail_reasons"])

    def test_legal_trust_service_returns_fail_safe_when_evidence_is_missing(self) -> None:
        trust_result = legal_trust_service.enforce_response(
            result={"answer": "The claim is valid under general legal principles.", "confidence": "high", "sources": []},
            output_contract={
                "legal_issue": "Is the claim valid?",
                "governing_rule": "General principles apply.",
                "application": "The claim is valid.",
                "counter_analysis": "",
                "missing_facts": [],
                "next_steps": [],
                "confidence": "high",
                "relevant_sources": [],
            },
            case_context={},
            force_structured_answer=True,
        )

        self.assertEqual(trust_result.trust_panel["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(trust_result.answer, "Not enough grounded evidence to produce a reliable legal analysis.")
        self.assertIn("contract", trust_result.trust_panel["required_documents"])

    def test_article_applicability_agent_classifies_article_sources(self) -> None:
        result = article_applicability_agent.review(
            issue="Does the civil obligation article apply to contract payment breach?",
            application="The contract payment obligation was not paid within 30 days.",
            sources=[
                {
                    "document_id": 11,
                    "chunk_id": 21,
                    "filename": "code_civil_obligations.pdf",
                    "chunk_index": 3,
                    "chunk_text": "Article 123 provides that contractual payment obligations must be performed according to agreed terms.",
                }
            ],
        )

        self.assertTrue(result.success)
        self.assertEqual(result.payload["status"], "ARTICLE_SOURCES_FOUND")
        self.assertEqual(result.payload["applicable_articles"][0]["article_id"], "123")
        self.assertEqual(result.payload["applicable_articles"][0]["code_family"], "civil_obligations")


if __name__ == "__main__":
    unittest.main()
