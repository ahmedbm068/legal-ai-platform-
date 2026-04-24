import unittest
from types import SimpleNamespace

from backend.core.config import settings
from backend.services.ai.agents.legal_workflow_agent_pack import (
    ClientRiskAgent,
    ContradictionAgent,
    FactExtractionAgent,
    RuleSynthesisAgent,
    StrategyAgent,
    VerifierAgent,
    legal_workflow_agent_pack,
)
from backend.services.ai.runtime_copilot_orchestrator import RuntimeCopilotOrchestrator


class _StubResponses:
    def __init__(self, *, output_text: str = "", should_raise: bool = False) -> None:
        self._output_text = output_text
        self._should_raise = should_raise

    def create(self, **_: object) -> SimpleNamespace:
        if self._should_raise:
            raise RuntimeError("stub failure")
        return SimpleNamespace(output_text=self._output_text)


class _StubClient:
    def __init__(self, *, output_text: str = "", should_raise: bool = False) -> None:
        self.responses = _StubResponses(output_text=output_text, should_raise=should_raise)


class LegalWorkflowAgentPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_llm_setting = settings.LEGAL_WORKFLOW_LLM_AGENTS_ENABLED
        settings.LEGAL_WORKFLOW_LLM_AGENTS_ENABLED = True

    def tearDown(self) -> None:
        settings.LEGAL_WORKFLOW_LLM_AGENTS_ENABLED = self._original_llm_setting

    def test_agent_pack_builds_structured_outputs_and_composed_answer(self) -> None:
        workflow_plan = {
            "workflow_template": "civil_dispute_analysis",
            "agent_sequence": [
                "matter_classification_agent",
                "fact_extraction_agent",
                "retrieval_agent",
                "rule_synthesis_agent",
                "application_agent",
                "missing_facts_agent",
                "counter_analysis_agent",
                "verifier_agent",
                "memo_drafting_agent",
            ],
            "user_goal": "Assess whether the counterparty is in contractual breach.",
            "matter_type": "civil obligation",
            "workflow_kind": "legal_analysis",
            "likely_code_family": "code_civil",
            "legal_dimension": "substantive",
            "recommended_output_format": "structured_legal_analysis",
            "source_needs": ["Full contract and breach notice"],
            "trust_level": "medium",
        }
        output_contract = {
            "confirmed_facts": ["A contract exists between the parties.", "A breach notice was sent on 2026-04-10."],
            "inferred_facts": ["The counterparty may have missed a cure deadline."],
            "missing_facts": ["The signed contract annexes are missing."],
            "legal_issue": "Whether the known facts support a contractual breach position.",
            "relevant_sources": [
                {
                    "label": "Article 12 Code Civil",
                    "snippet": "Contractual obligations must be performed in good faith.",
                    "url": "https://example.org/article-12",
                }
            ],
            "governing_rule": "Contractual obligations must be performed according to governing law and agreed terms.",
            "application": "Known facts may support breach, but annexes and cure-period evidence remain necessary.",
            "counter_analysis": "Counterparty may argue notice defects or unresolved cure period.",
            "contradictions": [{"description": "Cure-period end date is not fully confirmed.", "impact": "medium", "sources": ["notice_letter.pdf"]}],
            "confidence": "medium",
            "verification_status": "partial",
            "next_steps": ["Verify cure period.", "Request signed annexes."],
        }
        case_context = {
            "timeline": [
                {"date": "2026-04-10", "label": "Breach notice sent"},
                {"date": "2026-04-14", "label": "Counterparty response received"},
            ]
        }
        result = {
            "confidence": "medium",
            "sources": [],
            "citations": [
                {
                    "label": "Article 12 Code Civil",
                    "snippet": "Contractual obligations must be performed in good faith.",
                    "url": "https://example.org/article-12",
                }
            ],
        }

        payload = legal_workflow_agent_pack.run(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            case_context=case_context,
            result=result,
        )

        self.assertIn("fact_extraction", payload)
        self.assertIn("retrieval", payload)
        self.assertIn("verification", payload)
        self.assertIn("memo_drafting", payload)
        self.assertIn("final_output_composer", payload)
        self.assertIn("position_strength", payload)
        self.assertIn("recommended_strategy", payload)
        self.assertIn("evidence_strength", payload)
        self.assertIn("client_risk_summary", payload)
        answer = payload["final_output_composer"]["answer"]
        self.assertIn("1. Matter Understood", answer)
        self.assertIn("6. Preliminary Application", answer)
        self.assertIn("8. Counter-Analysis", answer)
        self.assertIn("10. Lawyer Review Note", answer)
        self.assertIn("11. Position Strength", answer)
        self.assertIn("12. Recommended Strategy", answer)
        self.assertIn("13. Evidence Strength", answer)
        self.assertIn("14. Contradictions", answer)
        self.assertIn("15. Client Risk Summary", answer)

    def test_fact_extraction_llm_valid_json(self) -> None:
        agent = FactExtractionAgent()
        agent.client = _StubClient(
            output_text="""
            {
              "confirmed_facts": ["Contract signed on 2026-01-01"],
              "inferred_facts": ["Counterparty may be in delay"],
              "missing_facts": ["Proof of delivery"],
              "fact_chronology": [{"date": "2026-01-01", "event": "Signature", "source": "contract.pdf"}],
              "parties": ["Seller", "Buyer"],
              "amounts": ["1000 TND"],
              "dates": ["2026-01-01"],
              "procedural_posture": "Pre-litigation review",
              "confidence": "medium"
            }
            """
        )
        workflow_plan = {"workflow_kind": "legal_analysis", "matter_type": "civil obligation", "confirmed_facts": ["Contract exists"]}
        output_contract = {"confirmed_facts": ["Contract exists"], "missing_facts": []}
        case_context = {"timeline": []}

        result = agent.extract(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            case_context=case_context,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.payload["parties"], ["Seller", "Buyer"])
        self.assertEqual(result.payload["confidence"], "medium")
        self.assertEqual(result.payload["fact_chronology"][0]["event"], "Signature")

    def test_fact_extraction_fallback_when_llm_json_invalid(self) -> None:
        agent = FactExtractionAgent()
        agent.client = _StubClient(output_text="not json")
        workflow_plan = {"workflow_kind": "legal_analysis", "matter_type": "civil obligation", "confirmed_facts": ["Contract exists"]}
        output_contract = {"confirmed_facts": ["Contract exists"], "missing_facts": ["Delivery proof missing"]}
        case_context = {"timeline": [{"date": "2026-01-01", "label": "Contract signed"}]}

        result = agent.extract(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            case_context=case_context,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.payload["confirmed_facts"], ["Contract exists"])
        self.assertIn("Delivery proof missing", result.payload["missing_facts"])

    def test_rule_synthesis_llm_valid_json(self) -> None:
        agent = RuleSynthesisAgent()
        agent.client = _StubClient(
            output_text="""
            {
              "governing_rule": "Obligations must be performed in good faith.",
              "rule_summary": "Good-faith performance is required.",
              "scope_conditions": ["Applies to contractual obligations."],
              "limits_or_ambiguities": ["Depends on proven non-performance."],
              "source_references": ["Article 12 Code Civil"],
              "confidence": "high"
            }
            """
        )
        workflow_plan = {"workflow_kind": "legal_analysis", "matter_type": "civil obligation", "likely_code_family": "code_civil"}
        output_contract = {"verification_status": "verified", "governing_rule": ""}
        retrieval_payload = {"ranked_sources": [{"article_or_section_reference": "Article 12 Code Civil"}]}

        result = agent.synthesize(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            retrieval_payload=retrieval_payload,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.payload["governing_rule"], "Obligations must be performed in good faith.")
        self.assertEqual(result.payload["confidence"], "high")

    def test_rule_synthesis_fallback_when_llm_fails(self) -> None:
        agent = RuleSynthesisAgent()
        agent.client = _StubClient(should_raise=True)
        workflow_plan = {"workflow_kind": "legal_analysis", "matter_type": "civil obligation", "likely_code_family": "code_civil", "legal_dimension": "substantive"}
        output_contract = {"verification_status": "partial", "governing_rule": "Deterministic rule"}
        retrieval_payload = {"ranked_sources": [{"article_or_section_reference": "Article 12 Code Civil"}]}

        result = agent.synthesize(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            retrieval_payload=retrieval_payload,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.payload["governing_rule"], "Deterministic rule")

    def test_verifier_evidence_strength_grading(self) -> None:
        agent = VerifierAgent()
        workflow_plan = {"workflow_kind": "legal_analysis", "matter_type": "civil obligation"}
        output_contract = {"verification_status": "partial"}
        retrieval_payload = {
            "ranked_sources": [
                {"article_or_section_reference": "Article 12 Code Civil", "source_type": "statute", "short_relevant_excerpt": "Obligations"},
                {"article_or_section_reference": "Cassation 2023/12", "source_type": "jurisprudence", "short_relevant_excerpt": "Interpretation"},
                {"article_or_section_reference": "Email Record", "source_type": "indirect", "short_relevant_excerpt": "Possible admission"},
            ]
        }
        rule_payload = {"governing_rule": "Obligations must be performed."}
        application_payload = {"preliminary_application": "Facts may indicate non-performance."}
        counter_payload = {"opposing_reading": ["Notice may be defective."]}

        result = agent.verify(
            workflow_plan=workflow_plan,
            output_contract=output_contract,
            retrieval_payload=retrieval_payload,
            rule_payload=rule_payload,
            application_payload=application_payload,
            counter_payload=counter_payload,
        )
        evidence_strength = result.payload["evidence_strength"]
        self.assertIn("Article 12 Code Civil", evidence_strength["strong"])
        self.assertIn("Cassation 2023/12", evidence_strength["medium"])
        self.assertIn("Email Record", evidence_strength["weak"])

    def test_position_strength_scoring_strong_arguable_weak(self) -> None:
        strong = legal_workflow_agent_pack.position_strength_agent.score(
            fact_payload={"confirmed_facts": ["A", "B", "C"], "missing_facts": []},
            verification_payload={"verification_status": "verified", "evidence_strength": {"strong": ["Art1", "Art2"], "medium": [], "weak": []}},
            contradiction_payload={"contradictions": []},
            counter_payload={"opposing_reading": []},
        ).payload["position_strength"]
        arguable = legal_workflow_agent_pack.position_strength_agent.score(
            fact_payload={"confirmed_facts": ["A"], "missing_facts": ["M1"]},
            verification_payload={"verification_status": "partial", "evidence_strength": {"strong": ["Art1"], "medium": ["Case1"], "weak": []}},
            contradiction_payload={"contradictions": [{"description": "Minor mismatch", "impact": "low", "sources": []}]},
            counter_payload={"opposing_reading": ["Alternative interpretation exists."]},
        ).payload["position_strength"]
        weak = legal_workflow_agent_pack.position_strength_agent.score(
            fact_payload={"confirmed_facts": [], "missing_facts": ["M1", "M2", "M3"]},
            verification_payload={"verification_status": "unverified", "evidence_strength": {"strong": [], "medium": [], "weak": ["Email"]}},
            contradiction_payload={"contradictions": [{"description": "Major mismatch", "impact": "high", "sources": []}]},
            counter_payload={"opposing_reading": ["X", "Y", "Z"]},
        ).payload["position_strength"]

        self.assertEqual(strong["label"], "strong")
        self.assertEqual(arguable["label"], "arguable")
        self.assertEqual(weak["label"], "weak")

    def test_strategy_agent_behavior(self) -> None:
        agent = StrategyAgent()
        base_workflow = {"matter_type": "civil obligation"}
        base_output = {"missing_facts": ["Missing annex"], "confidence": "medium", "verification_status": "partial"}
        gather = agent.recommend(
            workflow_plan=base_workflow,
            output_contract=base_output,
            position_payload={"position_strength": {"score": 45, "label": "arguable"}},
            verification_payload={"verification_status": "partial"},
            contradiction_payload={"contradictions": []},
            timeline_payload={"timeline_legal_impact": []},
        ).payload["recommended_strategy"]
        self.assertEqual(gather["type"], "gather_evidence")

        strong_case = agent.recommend(
            workflow_plan={"matter_type": "civil obligation"},
            output_contract={"missing_facts": [], "confidence": "high", "verification_status": "verified"},
            position_payload={"position_strength": {"score": 82, "label": "strong"}},
            verification_payload={"verification_status": "verified"},
            contradiction_payload={"contradictions": []},
            timeline_payload={"timeline_legal_impact": [{"event": "Deadline", "risk": "high"}]},
        ).payload["recommended_strategy"]
        self.assertIn(strong_case["type"], {"escalate", "litigate"})

        negotiable = agent.recommend(
            workflow_plan={"matter_type": "civil obligation"},
            output_contract={"missing_facts": [], "confidence": "medium", "verification_status": "verified"},
            position_payload={"position_strength": {"score": 56, "label": "arguable"}},
            verification_payload={"verification_status": "verified"},
            contradiction_payload={"contradictions": []},
            timeline_payload={"timeline_legal_impact": []},
        ).payload["recommended_strategy"]
        self.assertEqual(negotiable["type"], "negotiate")

    def test_contradiction_agent_detects_contradiction(self) -> None:
        agent = ContradictionAgent()
        result = agent.detect(
            output_contract={"contradictions": []},
            fact_payload={
                "fact_chronology": [
                    {"date": "2026-01-01", "event": "Notice sent"},
                    {"date": "2026-01-03", "event": "Notice sent"},
                ]
            },
            verification_payload={"unsupported_claims": ["Claim not grounded"], "claim_to_source_map": [{"claim": "x", "source": "Article 12", "support": "missing"}]},
        )
        contradictions = result.payload["contradictions"]
        self.assertTrue(any("multiple dates" in item["description"] for item in contradictions))
        self.assertTrue(any(item.get("sources") for item in contradictions))

    def test_client_risk_agent_returns_summary(self) -> None:
        agent = ClientRiskAgent()
        result = agent.summarize(
            workflow_plan={"matter_type": "civil obligation"},
            output_contract={},
            position_payload={"position_strength": {"score": 48, "label": "arguable"}},
            strategy_payload={"recommended_strategy": {"risk_level": "medium"}},
            timeline_payload={"timeline_legal_impact": [{"event": "Notice", "risk": "medium"}]},
        )
        summary = result.payload["client_risk_summary"]
        self.assertIn("financial_risk", summary)
        self.assertIn("legal_risk", summary)
        self.assertIn(summary["urgency"], {"low", "medium", "high"})

    def test_workflow_templates_cover_priority_flows(self) -> None:
        self.assertEqual(
            RuntimeCopilotOrchestrator._workflow_template_for_matter(
                workflow_kind="legal_analysis",
                matter_type="civil obligation",
            ),
            "civil_dispute_analysis",
        )
        self.assertEqual(
            RuntimeCopilotOrchestrator._workflow_template_for_matter(
                workflow_kind="legal_analysis",
                matter_type="succession",
            ),
            "succession_analysis",
        )
        self.assertEqual(
            RuntimeCopilotOrchestrator._workflow_template_for_matter(
                workflow_kind="legal_analysis",
                matter_type="international private law",
            ),
            "international_private_law_screening",
        )
        sequence = RuntimeCopilotOrchestrator._workflow_agent_sequence(
            workflow_template="article_applicability_review",
            workflow_kind="legal_analysis",
        )
        self.assertIn("rule_synthesis_agent", sequence)
        self.assertIn("application_agent", sequence)
        self.assertIn("verifier_agent", sequence)

    def test_global_output_contract_is_enriched_with_decision_support_fields(self) -> None:
        base_contract = {
            "verification_status": "partial",
            "confidence": "medium",
            "contradictions": [{"description": "Timeline conflict remains unresolved.", "impact": "medium", "sources": []}],
        }
        agent_pack_payload = {
            "verification": {
                "verification_status": "unverified",
                "evidence_strength": {"strong": ["Article 12 Code Civil"], "medium": [], "weak": []},
            },
            "position_strength": {"score": 42, "label": "weak", "reason": "Support remains incomplete."},
            "recommended_strategy": {"type": "gather_evidence", "reason": "Support remains incomplete.", "risk_level": "high"},
            "contradictions": [{"description": "Claim-evidence mismatch.", "impact": "high", "sources": ["Article 12 Code Civil"]}],
            "client_risk_summary": {
                "financial_risk": "Exposure remains provisional.",
                "legal_risk": "Liability remains disputed.",
                "urgency": "medium",
                "summary": "Further verification is needed.",
            },
            "feedback_loop": {"enabled": True, "correction_capture_ready": True},
        }

        enriched = RuntimeCopilotOrchestrator._enrich_global_output_contract_with_agent_pack(
            output_contract=base_contract,
            agent_pack_payload=agent_pack_payload,
        )

        self.assertEqual(enriched["verification_status"], "unverified")
        self.assertEqual(enriched["position_strength"]["score"], 42)
        self.assertEqual(enriched["recommended_strategy"]["type"], "gather_evidence")
        self.assertEqual(enriched["evidence_strength"]["strong"], ["Article 12 Code Civil"])
        self.assertEqual(enriched["contradiction_analysis"][0]["impact"], "high")
        self.assertEqual(enriched["contradictions"][0]["sources"], ["Article 12 Code Civil"])
        self.assertEqual(enriched["client_risk_summary"]["urgency"], "medium")
        self.assertTrue(enriched["feedback_loop"]["enabled"])

    def test_casual_request_does_not_get_bloated_composed_answer(self) -> None:
        result = {"answer": "Short drafting answer", "structured_result": {}}
        RuntimeCopilotOrchestrator._apply_composed_legal_answer_if_needed(
            result=result,
            workflow_plan={"workflow_kind": "drafting"},
            effective_mode="default",
            agent_pack_payload={"final_output_composer": {"answer": "Long legal structure"}},
        )
        self.assertEqual(result["answer"], "Short drafting answer")


class RuntimeGlobalContractAdvancedFieldTests(unittest.TestCase):
    def test_build_global_output_contract_includes_advanced_fields(self) -> None:
        orchestrator = RuntimeCopilotOrchestrator.__new__(RuntimeCopilotOrchestrator)
        result = {
            "answer": "3. Legal Issue\nIssue.\n\n5. Rule Summary\nRule.\n\n6. Preliminary Application\nApplication.\n\n9. Practical Next Steps\n- Step",
            "used_fallback": False,
            "confidence": "medium",
            "citations": [{"label": "Article 12", "snippet": "Reserved share rule", "url": None}],
            "structured_result": {},
        }
        workflow_plan = {
            "matter_type": "succession",
            "parsed_intent": "ask_case",
            "user_goal": "Assess succession distribution.",
            "confirmed_facts": ["Case context exists."],
            "missing_facts": ["Heir status not fully confirmed."],
            "source_needs": ["Code de succession articles."],
            "non_replacement_rule": "Final legal judgment remains with the lawyer.",
        }
        case_context = {"case": {"jurisdiction_country": "tunisia"}, "risk_signals": []}
        contract = orchestrator._build_global_output_contract(
            result=result,
            workflow_plan=workflow_plan,
            case_context=case_context,
            parsed_intent="ask_case",
            user_query="Assess succession distribution.",
        )
        self.assertIn("position_strength", contract)
        self.assertIn("recommended_strategy", contract)
        self.assertIn("evidence_strength", contract)
        self.assertIn("contradictions", contract)
        self.assertIn("client_risk_summary", contract)
        self.assertEqual(contract["recommended_strategy"]["type"], "gather_evidence")


if __name__ == "__main__":
    unittest.main()
