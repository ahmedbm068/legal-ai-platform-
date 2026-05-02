import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from backend.core.config import settings
from backend.services.ai.agents.copilot_intent_execution_agent import (
    CopilotIntentExecutionAgent,
    CopilotIntentExecutionContext,
)
from backend.services.ai.runtime_copilot_orchestrator import RuntimeCopilotOrchestrator
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

    def test_case_document_breakdown_is_opt_in(self) -> None:
        self.assertFalse(
            self.service._wants_case_document_breakdown(
                "summarize the case with the main contract and healthcare operations issues"
            )
        )
        self.assertTrue(
            self.service._wants_case_document_breakdown(
                "summarize the case with a document-by-document breakdown"
            )
        )

    def test_build_case_people_role_lines_extracts_roles_from_uploaded_docs(self) -> None:
        documents = [
            SimpleNamespace(
                filename="01_equipment_maintenance_agreement.pdf",
                extracted_text="Parties: MedCare Clinics SARL and BioServe Medical Systems SARL.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                filename="10_management_call_summary.pdf",
                extracted_text="Participants: MedCare CEO, MedCare Legal, BioServe Director, BioServe Service Lead.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
        ]
        lines = self.service._build_case_people_role_lines(
            documents=documents,  # type: ignore[arg-type]
            reasoning_parties=[],
        )
        joined = "\n".join(lines)
        self.assertIn("MedCare Clinics SARL: client", joined)
        self.assertIn("BioServe Medical Systems SARL: medical equipment maintenance provider", joined)
        self.assertIn("MedCare CEO: management-level participant", joined)
        self.assertIn("BioServe Director: management-level BioServe participant", joined)

    def test_case_brief_summary_uses_numbered_template(self) -> None:
        lines = self.service._build_case_brief_summary_lines(
            case=SimpleNamespace(
                id=29,
                title="MedCare v BioServe - Medical Equipment Maintenance Dispute",
                jurisdiction_country="Tunisia",
            ),  # type: ignore[arg-type]
            jurisdiction_context={"country_display_name": "Tunisia"},
            overview="MedCare and BioServe dispute medical equipment maintenance performance.",
            people_role_lines=["MedCare Clinics SARL: client. [source: 01_equipment_maintenance_agreement.pdf]"],
            key_takeaways=["Invoice quantum is contested around 64,380 TND."],
            key_dates=[{"label": "Incident Date", "value": "March 21, 2026"}],
            evidence_sources=[
                "01_equipment_maintenance_agreement.pdf",
                "03_client_breach_notice.pdf",
                "04_bioserve_response_letter.pdf",
                "05_invoice_and_reconciliation_sheet.pdf",
            ],
            document_resume_lines=[],
            wants_document_breakdown=False,
            recommended_steps=[],
            wants_next_steps=False,
        )
        rendered = "\n".join(lines)
        self.assertIn("CASE BRIEF / SUMMARY", rendered)
        self.assertIn("1. Name of Case & Source Record", rendered)
        self.assertIn("3. Main Persons / Roles", rendered)
        self.assertIn("5. Issue(s)", rendered)
        self.assertIn("8. Important Dates / Deadlines", rendered)
        self.assertNotIn("Documents Summary", rendered)

    def test_party_position_contradiction_answer_focuses_on_disputes(self) -> None:
        documents = [
            SimpleNamespace(
                id=1,
                case_id=29,
                filename="03_client_breach_notice.pdf",
                extracted_text="MedCare Clinics SARL alleges BioServe Medical Systems SARL failed the critical onsite response standard and disputes Invoice BS-INV-2026-0317: claimed 64,380 TND, accepted 39,750 TND, disputed 24,630 TND.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=2,
                case_id=29,
                filename="04_bioserve_response_letter.pdf",
                extracted_text="BioServe Medical Systems SARL denies material breach and says the response clock starts at 09:10. BioServe maintains the invoice is payable in full and offers a 6,500 TND credit note.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
        ]
        result = self.service._build_party_position_contradiction_answer(
            case=SimpleNamespace(id=29, title="MedCare v BioServe"),  # type: ignore[arg-type]
            documents=documents,  # type: ignore[arg-type]
        )
        self.assertIsNotNone(result)
        answer, sources = result or ("", [])
        self.assertIn("CONTRADICTIONS BETWEEN MEDCARE AND BIOSERVE POSITIONS", answer)
        self.assertIn("SLA response clock", answer)
        self.assertIn("Invoice amount and payment obligation", answer)
        self.assertNotIn("Comparison overview", answer)
        self.assertGreaterEqual(len(sources), 1)

    def test_medcare_evidence_strength_answer_is_party_aware(self) -> None:
        documents = [
            SimpleNamespace(
                id=1,
                case_id=29,
                filename="01_equipment_maintenance_agreement.pdf",
                extracted_text="Equipment Maintenance and Service Agreement EMSA with service level and SLA terms.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=2,
                case_id=29,
                filename="03_client_breach_notice.pdf",
                extracted_text="MedCare Clinics SARL sends breach notice and payment reservation to BioServe Medical Systems SARL.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=3,
                case_id=29,
                filename="05_invoice_and_reconciliation_sheet.pdf",
                extracted_text="Invoice BS-INV-2026-0317 claimed 64,380 TND, accepted 39,750 TND, disputed 24,630 TND.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=4,
                case_id=29,
                filename="07_patient_operations_impact_summary.pdf",
                extracted_text="Patient operations summary lists delayed appointments, external referrals, and external scan costs.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
        ]
        result = self.service._build_medcare_evidence_strength_answer(
            case=SimpleNamespace(id=29, title="MedCare v BioServe"),  # type: ignore[arg-type]
            documents=documents,  # type: ignore[arg-type]
            objective="What are the strongest and weakest pieces of evidence for MedCare?",
        )
        self.assertIsNotNone(result)
        answer, sources = result or ("", [])
        self.assertIn("EVIDENCE STRENGTH FOR MEDCARE", answer)
        self.assertIn("Evidence Matrix", answer)
        self.assertEqual(answer.count("| Strength | Evidence |"), 1)
        self.assertIn("64,380 TND", answer)
        self.assertIn("Exact SLA clock start", answer)
        self.assertGreaterEqual(len(sources), 1)

    def test_bioserve_evidence_strength_answer_uses_defense_view(self) -> None:
        documents = [
            SimpleNamespace(
                id=1,
                case_id=29,
                filename="04_bioserve_response_letter.pdf",
                extracted_text="BioServe denies material breach and says the response clock starts at 09:10 when the complete ticket was accepted.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=2,
                case_id=29,
                filename="06_service_logs_extract.pdf",
                extracted_text="Service logs include ticket acceptance and technician arrival records.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=3,
                case_id=29,
                filename="07_patient_operations_impact_summary.pdf",
                extracted_text="Patient operations summary lists delayed appointments and external referrals.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
        ]
        result = self.service._build_party_evidence_strength_answer(
            case=SimpleNamespace(id=29, title="MedCare v BioServe"),  # type: ignore[arg-type]
            documents=documents,  # type: ignore[arg-type]
            objective="What are the strongest and weakest pieces of evidence for BioServe?",
        )
        self.assertIsNotNone(result)
        answer, _sources = result or ("", [])
        self.assertIn("EVIDENCE STRENGTH FOR BIOSERVE", answer)
        self.assertIn("Response-clock defense", answer)
        self.assertIn("Patient impact and outage duration", answer)
        self.assertNotIn("EVIDENCE STRENGTH FOR MEDCARE", answer)

    def test_medcare_ranked_legal_risks_answer_is_risk_matrix(self) -> None:
        documents = [
            SimpleNamespace(
                id=1,
                case_id=29,
                filename="01_equipment_maintenance_agreement.pdf",
                extracted_text="MedCare and BioServe agreement with SLA terms.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=2,
                case_id=29,
                filename="04_bioserve_response_letter.pdf",
                extracted_text="BioServe disputes material breach and says the response clock starts at 09:10.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=3,
                case_id=29,
                filename="05_invoice_and_reconciliation_sheet.pdf",
                extracted_text="Invoice total is 64,380 TND with 24,630 TND disputed.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
        ]
        result = self.service._build_medcare_ranked_legal_risks_answer(
            case=SimpleNamespace(id=29, title="MedCare v BioServe"),  # type: ignore[arg-type]
            documents=documents,  # type: ignore[arg-type]
        )
        self.assertIsNotNone(result)
        answer, sources = result or ("", [])
        self.assertIn("RANKED LEGAL RISKS", answer)
        self.assertIn("| Level | Legal risk | Why it matters | Evidence behind it |", answer)
        self.assertIn("Material breach / missed SLA response", answer)
        self.assertIn("Invoice withholding / late-payment exposure", answer)
        self.assertNotIn("Dear Client", answer)
        self.assertGreaterEqual(len(sources), 1)

    def test_medcare_rights_preserving_client_email_is_substantive(self) -> None:
        documents = [
            SimpleNamespace(
                id=1,
                case_id=29,
                filename="03_client_breach_notice.pdf",
                extracted_text="MedCare Clinics SARL reserves rights and disputes BioServe invoice support.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=2,
                case_id=29,
                filename="05_invoice_and_reconciliation_sheet.pdf",
                extracted_text="Invoice BS-INV-2026-0317 total 64,380 TND; 39,750 TND undisputed; 24,630 TND disputed.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=3,
                case_id=29,
                filename="07_patient_operations_impact_summary.pdf",
                extracted_text="Patient operations impact includes delayed appointments and external referrals.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
        ]
        result = self.service._build_medcare_rights_preserving_client_email(
            case=SimpleNamespace(id=29, title="MedCare v BioServe"),  # type: ignore[arg-type]
            documents=documents,  # type: ignore[arg-type]
            client_name="MedCare Clinics SARL",
            lawyer_name="Ahmed Ben Ali",
        )
        self.assertIsNotNone(result)
        answer, sources = result or ("", [])
        self.assertIn("Subject: MedCare v BioServe", answer)
        self.assertIn("Dear MedCare Clinics SARL", answer)
        self.assertIn("Ahmed Ben Ali", answer)
        self.assertIn("24,630 TND", answer)
        self.assertIn("all of which are expressly reserved", answer)
        self.assertGreaterEqual(len(sources), 1)

    def test_medcare_without_prejudice_strategy_is_case_grounded(self) -> None:
        documents = [
            SimpleNamespace(
                id=1,
                case_id=29,
                filename="04_bioserve_response_letter.pdf",
                extracted_text="BioServe offered a 6,500 TND credit note and denied material breach.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=2,
                case_id=29,
                filename="09_without_prejudice_settlement_offer.pdf",
                extracted_text="MedCare settlement offer seeks 14,000 TND credit note without prejudice.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
            SimpleNamespace(
                id=3,
                case_id=29,
                filename="10_management_call_summary.pdf",
                extracted_text="Management call discusses possible flexibility up to 10,000 TND.",
                redacted_text=None,
                summary=None,
                summary_short=None,
            ),
        ]
        result = self.service._build_medcare_without_prejudice_strategy(
            case=SimpleNamespace(id=29, title="MedCare v BioServe"),  # type: ignore[arg-type]
            documents=documents,  # type: ignore[arg-type]
            objective="Draft a without-prejudice negotiation strategy for the April 9 settlement call",
        )
        self.assertIsNotNone(result)
        answer, sources = result or ("", [])
        self.assertIn("WITHOUT-PREJUDICE NEGOTIATION STRATEGY", answer)
        self.assertIn("14,000 TND", answer)
        self.assertIn("6,500 TND", answer)
        self.assertIn("10,000 TND", answer)
        self.assertNotIn("Here's a proposed approach", answer)
        self.assertGreaterEqual(len(sources), 1)


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
            reasoning_level="medium",
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

    def test_evaluate_case_evidence_intent_executes_runtime_method(self) -> None:
        class Runtime:
            def __init__(self) -> None:
                self.received_objective = None

            def _unsupported_intent_response(self) -> dict[str, Any]:
                return {"answer": "unsupported"}

            def _evaluate_case_evidence(self, **kwargs: Any) -> dict[str, Any]:
                self.received_objective = kwargs.get("objective")
                return {"answer": "evidence ok"}

        runtime = Runtime()
        agent = CopilotIntentExecutionAgent()
        result = agent.execute(
            intent="evaluate_case_evidence",
            runtime=runtime,
            ctx=self._build_context(
                parsed={
                    "case_id": 29,
                    "clean_query": "What are the strongest and weakest pieces of evidence for MedCare?",
                }
            ),
        )
        self.assertEqual(result.get("answer"), "evidence ok")
        self.assertIn("strongest and weakest", str(runtime.received_objective))


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
        self.assertIn("what are we working on", result.get("answer", "").lower())
        self.assertEqual(result.get("used_fallback"), True)
        self.assertEqual(result.get("fallback_reason"), "No LLM provider API key is configured")
        self.assertEqual(result.get("confidence"), "medium")

    def test_chat_mode_uses_non_llm_fallback_when_provider_missing(self) -> None:
        result = self.service._respond_in_chat_mode(
            question="Can you help me plan a legal strategy memo for a client meeting?",
            user_role="lawyer",
            conversation_history=[],
        )
        self.assertEqual(result.get("used_fallback"), True)
        self.assertEqual(result.get("fallback_reason"), "No LLM provider API key is configured")
        self.assertIn("normal assistant", result.get("answer", "").lower())

    def test_chat_mode_can_answer_jokes_without_rag_or_trust(self) -> None:
        result = self.service._respond_in_chat_mode(
            question="give me a joke",
            user_role="lawyer",
            conversation_history=[],
        )

        self.assertEqual(result.get("used_fallback"), True)
        self.assertIn("higher level", result.get("answer", "").lower())
        self.assertEqual(result.get("sources"), [])
        self.assertEqual(result.get("citations"), [])
        self.assertNotIn("trust_panel", result)

    def test_trust_engine_only_activates_for_selected_legal_search_modes(self) -> None:
        self.assertTrue(
            self.service._should_use_trust_engine(
                normalized_mode="legal_search",
                intent="ask_case",
                agent_mode=False,
            )
        )
        self.assertTrue(
            self.service._should_use_trust_engine(
                normalized_mode="external",
                intent="ask_document",
                agent_mode=False,
            )
        )
        self.assertFalse(
            self.service._should_use_trust_engine(
                normalized_mode="default",
                intent="ask_case",
                agent_mode=False,
            )
        )
        self.assertFalse(
            self.service._should_use_trust_engine(
                normalized_mode="legal_search",
                intent="create_case",
                agent_mode=True,
            )
        )

    def test_strip_trust_artifacts_removes_trust_payload_from_simple_modes(self) -> None:
        result = self.service._strip_trust_artifacts(
            {
                "answer": "hello",
                "trust_panel": {"status": "verified"},
                "unsupported_claims": ["x"],
                "structured_result": {
                    "trust_panel": {"status": "verified"},
                    "claim_validation": {"unsupported_claims": ["x"]},
                    "safe": True,
                },
            }
        )

        self.assertNotIn("trust_panel", result)
        self.assertNotIn("unsupported_claims", result)
        self.assertNotIn("trust_panel", result["structured_result"])
        self.assertNotIn("claim_validation", result["structured_result"])
        self.assertTrue(result["structured_result"]["safe"])

    def test_strip_heavy_trust_diagnostics_keeps_light_rag_fields(self) -> None:
        result = self.service._strip_heavy_trust_diagnostics(
            {
                "answer": "Clause 4 mentions notice.",
                "confidence": "medium",
                "scope": "document",
                "sources": [{"label": "contract.pdf"}],
                "citations": [{"label": "Clause 4"}],
                "trust_panel": {"status": "verified"},
                "contradictions": [{"severity": "high"}],
                "risk_panel": {"client": "high"},
                "structured_result": {
                    "verification_details": {"status": "verified"},
                    "legal_audit": {"trace": []},
                    "safe": True,
                },
            }
        )

        self.assertEqual(result.get("answer"), "Clause 4 mentions notice.")
        self.assertEqual(result.get("confidence"), "medium")
        self.assertEqual(result.get("scope"), "document")
        self.assertTrue(result.get("sources"))
        self.assertTrue(result.get("citations"))
        self.assertNotIn("trust_panel", result)
        self.assertNotIn("contradictions", result)
        self.assertNotIn("risk_panel", result)
        self.assertNotIn("verification_details", result["structured_result"])
        self.assertNotIn("legal_audit", result["structured_result"])

    def test_chat_mode_rag_detector_keeps_general_legal_questions_conversational(self) -> None:
        self.assertFalse(
            self.service._chat_mode_needs_rag(
                question="yo",
                intent="ask_global",
                case_id=24,
                document_id=None,
            )
        )
        self.assertFalse(
            self.service._chat_mode_needs_rag(
                question="give me a joke",
                intent="ask_global",
                case_id=24,
                document_id=8,
            )
        )
        self.assertFalse(
            self.service._chat_mode_needs_rag(
                question="another one",
                intent="ask_case",
                case_id=24,
                document_id=8,
            )
        )
        self.assertFalse(
            self.service._chat_mode_needs_rag(
                question="3asslema",
                intent="ask_case",
                case_id=24,
                document_id=None,
            )
        )
        self.assertFalse(
            self.service._chat_mode_needs_rag(
                question="wtf",
                intent="ask_case",
                case_id=24,
                document_id=None,
            )
        )
        self.assertFalse(
            self.service._chat_mode_needs_rag(
                question="What is a contract?",
                intent="ask_global",
                case_id=None,
                document_id=None,
            )
        )
        self.assertFalse(
            self.service._chat_mode_needs_rag(
                question="Explain breach of contract simply",
                intent="ask_global",
                case_id=None,
                document_id=None,
            )
        )

    def test_chat_mode_rag_detector_uses_workspace_context_for_case_or_document_questions(self) -> None:
        self.assertTrue(
            self.service._chat_mode_needs_rag(
                question="What does document #8 say?",
                intent="ask_global",
                case_id=None,
                document_id=None,
            )
        )
        self.assertTrue(
            self.service._chat_mode_needs_rag(
                question="Find the SLA clause",
                intent="ask_global",
                case_id=24,
                document_id=None,
            )
        )
        self.assertTrue(
            self.service._chat_mode_needs_rag(
                question="summarize",
                intent="summarize_document",
                case_id=None,
                document_id=8,
            )
        )

    def test_normalize_trust_state_forces_consistent_insufficient_evidence(self) -> None:
        result = self.service._normalize_trust_state(
            {
                "answer": "Not enough evidence, but confidence high.",
                "confidence": "high",
                "fallback_reason": "no_direct_legal_source",
                "trust_panel": {
                    "confidence": "high",
                    "evidence_strength": "STRONG",
                    "metrics": {"citation_coverage": 0.9},
                },
            }
        )

        self.assertEqual(result.get("status"), "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result.get("confidence"), "low")
        self.assertEqual(result.get("verification_status"), "failed")
        self.assertEqual(result.get("evidence_strength"), "insufficient")
        self.assertEqual(result.get("position_strength"), "not_assessable")
        self.assertEqual(result.get("citation_coverage"), 0)
        self.assertEqual(result.get("unsupported_rate"), 100)
        self.assertEqual((result.get("trust_panel") or {}).get("evidence_strength"), "insufficient")


class RuntimeIntentArbitrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = RuntimeCopilotOrchestrator.__new__(RuntimeCopilotOrchestrator)

    def test_low_confidence_arbitration_promotes_case_scope_intent(self) -> None:
        raw_parse = {
            "intent": "ask_case",
            "confidence": "medium",
            "confidence_score": 0.66,
        }
        parsed = {
            "intent": "ask_global",
            "confidence": "low",
            "confidence_score": 0.41,
            "low_confidence": True,
            "case_id": 42,
            "document_id": None,
            "arbitration_candidates": ["ask_global", "ask_case"],
        }

        resolved, metadata = self.orchestrator._arbitrate_low_confidence_intent(
            raw_parse=raw_parse,
            parsed=parsed,
            workspace_case_id=42,
            workspace_document_id=None,
        )

        self.assertEqual(resolved.get("intent"), "ask_case")
        self.assertTrue(metadata.get("activated"))
        self.assertIn(metadata.get("reason"), {"scope_adjusted", "raw_parse_confidence_dominant"})

    def test_low_confidence_arbitration_skips_when_not_required(self) -> None:
        raw_parse = {
            "intent": "summarize_case",
            "confidence": "high",
            "confidence_score": 0.91,
        }
        parsed = {
            "intent": "summarize_case",
            "confidence": "high",
            "confidence_score": 0.91,
            "low_confidence": False,
            "case_id": 9,
            "document_id": None,
            "arbitration_candidates": ["summarize_case"],
        }

        resolved, metadata = self.orchestrator._arbitrate_low_confidence_intent(
            raw_parse=raw_parse,
            parsed=parsed,
            workspace_case_id=9,
            workspace_document_id=None,
        )

        self.assertEqual(resolved.get("intent"), "summarize_case")
        self.assertFalse(metadata.get("activated"))
        self.assertEqual(metadata.get("reason"), "not_required")


class RuntimeWorkflowPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = RuntimeCopilotOrchestrator.__new__(RuntimeCopilotOrchestrator)

    def test_workflow_plan_detects_succession_and_low_trust_without_case_scope(self) -> None:
        plan = self.orchestrator._build_legal_workflow_plan(
            message="Analyze succession rights and heir shares.",
            parsed={
                "intent": "ask_global",
                "clean_query": "Analyze succession rights and heir shares.",
                "confidence": "low",
            },
            case_context={"scope": "global", "case": None, "timeline": [], "risk_signals": []},
            requested_mode="default",
            legal_search_code_scope=["code_succession"],
        )

        self.assertEqual(plan.get("matter_type"), "succession")
        self.assertEqual(plan.get("workflow_kind"), "legal_analysis")
        self.assertEqual(plan.get("trust_level"), "low")
        missing = " ".join(plan.get("missing_facts") or []).lower()
        self.assertIn("no active case context", missing)

    def test_workflow_routing_promotes_client_explanation_to_drafting_intent(self) -> None:
        parsed, metadata = self.orchestrator._apply_workflow_routing(
            parsed={"intent": "ask_case", "case_id": 77, "clean_query": "Explain this to client in plain language."},
            workflow_plan={
                "workflow_kind": "client_explanation",
                "matter_type": "civil obligation",
                "trust_level": "medium",
            },
            workspace_case_id=77,
            workspace_document_id=None,
        )

        self.assertEqual(parsed.get("intent"), "draft_client_email_case")
        self.assertTrue(metadata.get("intent_overridden"))
        self.assertEqual(metadata.get("reason"), "client_explanation_route")

    def test_workflow_routing_preserves_explicit_risk_analysis_intent(self) -> None:
        parsed, metadata = self.orchestrator._apply_workflow_routing(
            parsed={
                "intent": "analyze_risks_case",
                "case_id": 29,
                "clean_query": "Rank the legal risks from high to low and explain the evidence behind each one.",
            },
            workflow_plan={
                "workflow_kind": "client_explanation",
                "matter_type": "civil obligation",
                "trust_level": "medium",
            },
            workspace_case_id=29,
            workspace_document_id=None,
        )

        self.assertEqual(parsed.get("intent"), "analyze_risks_case")
        self.assertFalse(metadata.get("intent_overridden"))
        self.assertEqual(metadata.get("reason"), "explicit_analysis_intent_preserved")

    def test_resolve_effective_mode_does_not_auto_promote_default_to_legal_search(self) -> None:
        mode = self.orchestrator._resolve_effective_mode(
            requested_mode="default",
            workflow_plan={
                "workflow_kind": "legal_analysis",
                "trust_level": "low",
                "matter_type": "international private law",
            },
        )
        self.assertEqual(mode, "default")

    def test_resolve_effective_mode_preserves_explicit_legal_search(self) -> None:
        mode = self.orchestrator._resolve_effective_mode(
            requested_mode="legal_search",
            workflow_plan={
                "workflow_kind": "legal_analysis",
                "trust_level": "low",
                "matter_type": "international private law",
            },
        )
        self.assertEqual(mode, "legal_search")

    def test_workflow_routing_aligns_global_analysis_to_document_scope_when_available(self) -> None:
        parsed, metadata = self.orchestrator._apply_workflow_routing(
            parsed={"intent": "ask_global", "document_id": 18, "clean_query": "Which article applies here?"},
            workflow_plan={
                "workflow_kind": "legal_analysis",
                "matter_type": "article applicability review",
                "trust_level": "medium",
            },
            workspace_case_id=None,
            workspace_document_id=18,
        )

        self.assertEqual(parsed.get("intent"), "ask_document")
        self.assertTrue(metadata.get("intent_overridden"))
        self.assertEqual(metadata.get("reason"), "structured_document_scope_route")

    def test_workflow_plan_prefers_explicit_matter_classification_payload(self) -> None:
        plan = self.orchestrator._build_legal_workflow_plan(
            message="Need cross-border recognition strategy.",
            parsed={"intent": "ask_case", "clean_query": "Need cross-border recognition strategy.", "confidence": "medium", "case_id": 55},
            case_context={"case": {"id": 55, "document_count": 4, "jurisdiction_country": "tunisia"}, "timeline": [], "risk_signals": []},
            requested_mode="default",
            legal_search_code_scope=[],
            matter_classification={
                "matter_type": "international private law",
                "subtopic": "cross-border conflict of laws and recognition",
                "likely_code_family": "code_international_prive",
                "task_type": "research",
                "legal_dimension": "mixed",
                "urgency_sensitivity": {"urgency": "high", "sensitivity": "high"},
                "confidence": "high",
            },
        )

        self.assertEqual(plan.get("matter_type"), "international private law")
        self.assertEqual(plan.get("likely_code_family"), "code_international_prive")
        self.assertEqual(plan.get("task_type"), "research")
        self.assertEqual(plan.get("workflow_kind"), "legal_analysis")
        self.assertEqual((plan.get("urgency_sensitivity") or {}).get("urgency"), "high")

    def test_extract_available_document_summaries_collects_context_and_snapshot(self) -> None:
        summaries = self.orchestrator._extract_available_document_summaries(
            case_context={
                "timeline": [{"event_type": "document_uploaded", "label": "contract.pdf"}],
                "risk_signals": ["Missing notice clause evidence"],
            },
            snapshot_payload={
                "summary_text": "Case summary text",
                "reasoning": {"overview": "Reasoning overview", "main_issues": ["Issue A"]},
                "citations": [{"label": "Article 12", "snippet": "Excerpt"}],
            },
        )
        joined = " ".join(summaries)
        self.assertIn("contract.pdf", joined)
        self.assertIn("Case summary text", joined)
        self.assertIn("Article 12", joined)


class RuntimeGlobalOutputContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = RuntimeCopilotOrchestrator.__new__(RuntimeCopilotOrchestrator)

    def test_build_global_output_contract_returns_required_keys(self) -> None:
        result = {
            "answer": (
                "3. Legal Issue\nWhether succession shares are affected by testament limits.\n\n"
                "5. Rule Summary\nApplicable succession provisions govern reserved shares.\n\n"
                "6. Application to Known Facts\nBased on currently available facts, testament scope may be limited.\n\n"
                "8. Counter-Analysis / Alternative Interpretation\nAn alternative interpretation may apply if heir status is disputed.\n\n"
                "9. Practical Next Steps\n1. Verify testament validity.\n2. Confirm family relationship documents."
            ),
            "used_fallback": False,
            "confidence": "high",
            "citations": [{"label": "Article 12", "snippet": "Reserved share rule", "url": None}],
            "structured_result": {},
            "jurisdiction": {"country_code": "tunisia", "country_display_name": "Tunisia"},
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
        case_context = {
            "case": {"id": 42, "jurisdiction_country": "tunisia"},
            "risk_signals": [],
        }

        contract = self.orchestrator._build_global_output_contract(
            result=result,
            workflow_plan=workflow_plan,
            case_context=case_context,
            parsed_intent="ask_case",
            user_query="Assess succession distribution.",
        )

        expected_keys = {
            "matter_type",
            "user_intent",
            "jurisdiction",
            "confirmed_facts",
            "inferred_facts",
            "missing_facts",
            "legal_issue",
            "relevant_sources",
            "governing_rule",
            "application",
            "counter_analysis",
            "contradictions",
            "position_strength",
            "recommended_strategy",
            "evidence_strength",
            "client_risk_summary",
            "confidence",
            "verification_status",
            "next_steps",
            "lawyer_review_note",
        }
        self.assertEqual(set(contract.keys()), expected_keys)
        self.assertEqual(contract.get("matter_type"), "succession")
        self.assertEqual(contract.get("user_intent"), "ask_case")
        self.assertIn(contract.get("confidence"), {"low", "medium", "high"})
        self.assertIn(contract.get("verification_status"), {"unverified", "partial", "verified"})

    def test_apply_global_output_contract_injects_structured_result_payload(self) -> None:
        result = {"structured_result": {"existing": "value"}}
        contract = {
            "matter_type": "civil obligation",
            "user_intent": "ask_case",
            "jurisdiction": "tunisia",
            "confirmed_facts": [],
            "inferred_facts": [],
            "missing_facts": [],
            "legal_issue": "",
            "relevant_sources": [],
            "governing_rule": "",
            "application": "",
            "counter_analysis": "",
            "contradictions": [],
            "position_strength": {"score": 0, "label": "weak", "reason": "preview"},
            "recommended_strategy": {"type": "gather_evidence", "reason": "preview", "risk_level": "medium"},
            "evidence_strength": {"strong": [], "medium": [], "weak": []},
            "client_risk_summary": {
                "financial_risk": "",
                "legal_risk": "",
                "urgency": "medium",
                "summary": "",
            },
            "confidence": "low",
            "verification_status": "unverified",
            "next_steps": [],
            "lawyer_review_note": "review",
        }

        self.orchestrator._apply_global_output_contract(result=result, output_contract=contract)
        structured = result.get("structured_result") or {}
        self.assertIn("global_output_contract", structured)
        self.assertEqual((structured.get("global_output_contract") or {}).get("matter_type"), "civil obligation")

    def test_derive_verification_status_uses_evidence_signals(self) -> None:
        verified = self.orchestrator._derive_verification_status(
            explicit_status=None,
            used_fallback=False,
            confidence="high",
            relevant_sources=[{"label": "Article 1"}],
            governing_rule="Rule text",
            application="Application text",
        )
        unverified = self.orchestrator._derive_verification_status(
            explicit_status=None,
            used_fallback=True,
            confidence="low",
            relevant_sources=[],
            governing_rule="",
            application="",
        )
        self.assertEqual(verified, "verified")
        self.assertEqual(unverified, "unverified")


class CopilotHighReasoningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CopilotService.__new__(CopilotService)
        self.service.client = None  # type: ignore[assignment]
        self.service.model = "test-model"  # type: ignore[assignment]

    def test_high_reasoning_disabled_keeps_base_answer(self) -> None:
        original_flag = settings.ENABLE_HIGH_REASONING_MULTI_ANSWER
        try:
            settings.ENABLE_HIGH_REASONING_MULTI_ANSWER = False
            payload = {
                "answer": "base grounded answer",
                "used_fallback": False,
                "fallback_reason": None,
                "sources": [{"filename": "contract.pdf", "chunk_index": 1, "snippet": "payment terms"}],
                "citations": [{"label": "contract.pdf - chunk 1", "snippet": "payment terms"}],
            }
            result = self.service._finalize_reasoning_payload(
                payload=payload,
                reasoning_level="high",
                intent="ask_case",
                question="What are payment obligations?",
            )
            self.assertEqual(result.get("answer"), "base grounded answer")
            reasoning_result = result.get("reasoning_result") or {}
            self.assertEqual(reasoning_result.get("activated"), False)
            self.assertEqual(reasoning_result.get("winner_reason"), "high_reasoning_disabled")
        finally:
            settings.ENABLE_HIGH_REASONING_MULTI_ANSWER = original_flag

    def test_high_reasoning_non_eligible_intent_skips_activation(self) -> None:
        original_flag = settings.ENABLE_HIGH_REASONING_MULTI_ANSWER
        try:
            settings.ENABLE_HIGH_REASONING_MULTI_ANSWER = True
            payload = {
                "answer": "base grounded answer",
                "used_fallback": False,
                "fallback_reason": None,
                "sources": [],
                "citations": [],
            }
            result = self.service._finalize_reasoning_payload(
                payload=payload,
                reasoning_level="high",
                intent="create_case",
                question="Create case",
            )
            reasoning_result = result.get("reasoning_result") or {}
            self.assertEqual(reasoning_result.get("activated"), False)
            self.assertEqual(reasoning_result.get("winner_reason"), "intent_not_eligible")
        finally:
            settings.ENABLE_HIGH_REASONING_MULTI_ANSWER = original_flag

    def test_high_reasoning_timeout_sets_explicit_fallback_reason(self) -> None:
        original_flag = settings.ENABLE_HIGH_REASONING_MULTI_ANSWER
        original_log_flag = settings.HIGH_REASONING_LOG_SCORES
        try:
            settings.ENABLE_HIGH_REASONING_MULTI_ANSWER = True
            settings.HIGH_REASONING_LOG_SCORES = False
            self.service.client = object()  # type: ignore[assignment]

            payload = {
                "answer": "base grounded answer",
                "used_fallback": False,
                "fallback_reason": None,
                "sources": [{"filename": "contract.pdf", "chunk_index": 1, "snippet": "payment terms"}],
                "citations": [{"label": "contract.pdf - chunk 1", "snippet": "payment terms"}],
            }

            with patch.object(
                self.service,
                "_generate_high_reasoning_candidate",
                side_effect=TimeoutError("high_reasoning_timeout"),
            ):
                result = self.service._finalize_reasoning_payload(
                    payload=payload,
                    reasoning_level="high",
                    intent="ask_case",
                    question="What are payment obligations?",
                )

            self.assertEqual(result.get("used_fallback"), True)
            self.assertEqual(result.get("fallback_reason"), "high_reasoning_timeout_or_error")
            reasoning_result = result.get("reasoning_result") or {}
            self.assertEqual(reasoning_result.get("activated"), False)
            self.assertIn("high_reasoning_failed", str(reasoning_result.get("winner_reason") or ""))
        finally:
            settings.ENABLE_HIGH_REASONING_MULTI_ANSWER = original_flag
            settings.HIGH_REASONING_LOG_SCORES = original_log_flag

    def test_high_reasoning_ranks_candidates_and_selects_winner(self) -> None:
        original_flag = settings.ENABLE_HIGH_REASONING_MULTI_ANSWER
        original_log_flag = settings.HIGH_REASONING_LOG_SCORES
        original_top2_flag = settings.HIGH_REASONING_SHOW_TOP_2
        original_max_candidates = settings.HIGH_REASONING_MAX_CANDIDATES
        try:
            settings.ENABLE_HIGH_REASONING_MULTI_ANSWER = True
            settings.HIGH_REASONING_LOG_SCORES = False
            settings.HIGH_REASONING_SHOW_TOP_2 = True
            settings.HIGH_REASONING_MAX_CANDIDATES = 3
            self.service.client = object()  # type: ignore[assignment]

            payload = {
                "answer": "base grounded answer",
                "used_fallback": False,
                "fallback_reason": None,
                "sources": [{"filename": "contract.pdf", "chunk_index": 1, "snippet": "payment terms"}],
                "citations": [{"label": "contract.pdf - chunk 1", "snippet": "payment terms"}],
            }

            with patch.object(
                self.service,
                "_generate_high_reasoning_candidate",
                side_effect=["candidate factual", "candidate risk", "candidate strategic"],
            ):
                with patch.object(
                    self.service,
                    "_judge_high_reasoning_candidates",
                    return_value={
                        "winner_index": 0,
                        "decision_reason": "Candidate 0 is best grounded.",
                        "scores": [
                            {
                                "index": 0,
                                "grounding_score": 0.95,
                                "citation_score": 0.90,
                                "factual_consistency_score": 0.92,
                                "legal_usefulness_score": 0.80,
                                "actionability_score": 0.70,
                                "clarity_score": 0.78,
                                "overall_score": 0.91,
                                "decision_reason": "Most grounded and factual.",
                            },
                            {
                                "index": 1,
                                "grounding_score": 0.82,
                                "citation_score": 0.81,
                                "factual_consistency_score": 0.84,
                                "legal_usefulness_score": 0.85,
                                "actionability_score": 0.86,
                                "clarity_score": 0.83,
                                "overall_score": 0.84,
                                "decision_reason": "Good but less grounded.",
                            },
                            {
                                "index": 2,
                                "grounding_score": 0.75,
                                "citation_score": 0.74,
                                "factual_consistency_score": 0.76,
                                "legal_usefulness_score": 0.88,
                                "actionability_score": 0.90,
                                "clarity_score": 0.86,
                                "overall_score": 0.80,
                                "decision_reason": "Actionable but lower factual grounding.",
                            },
                        ],
                    },
                ):
                    result = self.service._finalize_reasoning_payload(
                        payload=payload,
                        reasoning_level="high",
                        intent="ask_case",
                        question="What are payment obligations?",
                    )

            self.assertEqual(result.get("answer"), "candidate factual")
            self.assertEqual(result.get("used_fallback"), False)

            reasoning_result = result.get("reasoning_result") or {}
            self.assertEqual(reasoning_result.get("activated"), True)
            self.assertEqual(reasoning_result.get("winner_index"), 0)
            self.assertEqual(reasoning_result.get("second_best_index"), 1)
            self.assertEqual(reasoning_result.get("winner_reason"), "Candidate 0 is best grounded.")

            candidates = reasoning_result.get("candidates") or []
            self.assertEqual(len(candidates), 3)
            self.assertEqual(candidates[0].get("rank"), 1)
            self.assertEqual(candidates[0].get("answer"), "candidate factual")
            self.assertEqual(candidates[1].get("rank"), 2)
            self.assertEqual(candidates[1].get("answer"), "candidate risk")
        finally:
            settings.ENABLE_HIGH_REASONING_MULTI_ANSWER = original_flag
            settings.HIGH_REASONING_LOG_SCORES = original_log_flag
            settings.HIGH_REASONING_SHOW_TOP_2 = original_top2_flag
            settings.HIGH_REASONING_MAX_CANDIDATES = original_max_candidates

    def test_high_reasoning_rollout_percentage_blocks_tenant(self) -> None:
        original_percentage = settings.HIGH_REASONING_ROLLOUT_PERCENTAGE
        original_allowlist = settings.HIGH_REASONING_TENANT_ALLOWLIST
        try:
            settings.HIGH_REASONING_ROLLOUT_PERCENTAGE = 0
            settings.HIGH_REASONING_TENANT_ALLOWLIST = ""
            allowed, reason, bucket = self.service._is_high_reasoning_rollout_eligible(tenant_id=13)
            self.assertFalse(allowed)
            self.assertEqual(reason, "rollout_percentage_zero")
            self.assertIsNone(bucket)
        finally:
            settings.HIGH_REASONING_ROLLOUT_PERCENTAGE = original_percentage
            settings.HIGH_REASONING_TENANT_ALLOWLIST = original_allowlist

    def test_high_reasoning_rollout_allowlist_overrides_percentage(self) -> None:
        original_percentage = settings.HIGH_REASONING_ROLLOUT_PERCENTAGE
        original_allowlist = settings.HIGH_REASONING_TENANT_ALLOWLIST
        try:
            settings.HIGH_REASONING_ROLLOUT_PERCENTAGE = 0
            settings.HIGH_REASONING_TENANT_ALLOWLIST = "13, 14"
            allowed, reason, bucket = self.service._is_high_reasoning_rollout_eligible(tenant_id=13)
            self.assertTrue(allowed)
            self.assertEqual(reason, "allowlist")
            self.assertIsNone(bucket)
        finally:
            settings.HIGH_REASONING_ROLLOUT_PERCENTAGE = original_percentage
            settings.HIGH_REASONING_TENANT_ALLOWLIST = original_allowlist


if __name__ == "__main__":
    unittest.main()
