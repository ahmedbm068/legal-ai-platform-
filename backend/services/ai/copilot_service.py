# pyright: reportAssignmentType=false, reportArgumentType=false, reportOperatorIssue=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from __future__ import annotations

from datetime import datetime
import hashlib
import logging
import json
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import func

from backend.core.config import settings
from backend.models.appointment import Appointment
from backend.models.case import Case
from backend.models.client import Client
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.prompt_library_entry import PromptLibraryEntry
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.booking_agent import booking_agent
from backend.services.ai.agents.case_reasoning_agent import case_reasoning_agent
from backend.services.ai.agents.case_memory_agent import case_memory_agent
from backend.services.ai.agents.contract_redline_agent import contract_redline_agent
from backend.services.ai.agents.deadline_obligation_agent import deadline_obligation_agent
from backend.services.ai.agents.drafting_agent import drafting_agent
from backend.services.ai.agents.document_comparison_agent import document_comparison_agent
from backend.services.ai.agents.evidence_trace_agent import evidence_trace_agent
from backend.services.ai.agents.evidence_strength_agent import evidence_strength_agent
from backend.services.ai.agents.insight_agent import insight_agent
from backend.services.ai.agents.negotiation_strategy_agent import negotiation_strategy_agent
from backend.services.ai.agents.prompt_optimizer_agent import prompt_optimizer_agent
from backend.services.ai.agents.prompt_correction_agent import prompt_correction_agent
from backend.services.ai.agents.timeline_agent import timeline_agent
from backend.services.ai.agents.copilot_intent_execution_agent import (
    CopilotIntentExecutionContext,
    copilot_intent_execution_agent,
)
from backend.services.ai.artifact_versioning_service import artifact_versioning_service
from backend.services.ai.command_parsing_service import command_parsing_service
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.external_research_service import external_research_service
from backend.services.ai.jurisdiction_context_service import jurisdiction_context_service
from backend.services.ai.legal_search_mode_service import legal_search_mode_service
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.copilot_risk_analysis_mixin import CopilotRiskAnalysisMixin
from backend.services.ai import copilot_service_constants as copilot_constants
from backend.services.ai.rag_service import RagService
from backend.services.ai.summarization_service import summarization_service
from backend.services.calendar_service import build_ai_calendar_brief, normalize_appointment_type, normalize_scope, normalize_status, serialize_appointment


logger = logging.getLogger(__name__)


class CopilotService(CopilotRiskAnalysisMixin):
    READ_ONLY_ROLES = copilot_constants.READ_ONLY_ROLES
    CASE_WRITE_ROLES = copilot_constants.CASE_WRITE_ROLES
    CLIENT_ALLOWED_INTENTS = copilot_constants.CLIENT_ALLOWED_INTENTS
    CHAT_ASSISTANT_INTENTS = copilot_constants.CHAT_ASSISTANT_INTENTS
    CHAT_GREETING_PATTERN = copilot_constants.CHAT_GREETING_PATTERN
    CHAT_THANKS_PATTERN = copilot_constants.CHAT_THANKS_PATTERN
    CRUD_INTENTS = copilot_constants.CRUD_INTENTS
    ACTION_CATEGORY_BY_INTENT = copilot_constants.ACTION_CATEGORY_BY_INTENT
    MATERIAL_BREACH_QUERY_KEYWORDS = copilot_constants.MATERIAL_BREACH_QUERY_KEYWORDS
    LEGAL_SEARCH_ELIGIBLE_INTENTS = copilot_constants.LEGAL_SEARCH_ELIGIBLE_INTENTS
    NUMBER_WORDS = copilot_constants.NUMBER_WORDS
    FOLLOW_UP_COUNT_PATTERN = copilot_constants.FOLLOW_UP_COUNT_PATTERN
    FOLLOW_UP_HINT_PATTERN = copilot_constants.FOLLOW_UP_HINT_PATTERN
    SUMMARY_STOP_HEADERS = copilot_constants.SUMMARY_STOP_HEADERS
    CONTRACTUAL_SIGNAL_KEYWORDS = (
        "contract",
        "agreement",
        "sla",
        "service level",
        "payment terms",
        "draft_partner_strategy_note_case",
        "late payment",
        "invoice",
        "cure period",
        "formal notice",
        "material breach",
        "liability cap",
        "governing law",
        "dispute resolution",
        "arbitration",
        "mediation",
        "obligation",
    )
    LEGAL_RISK_KEYWORDS = (
        "breach",
        "termination",
        "liability",
        "arbitration",
        "mediation",
        "governing law",
        "notice",
        "cure",
        "damages",
        "dispute",
        "reservation of rights",
        "default",
        "non-compliance",
        "non compliance",
    )
    OPERATIONAL_RISK_KEYWORDS = (
        "sla",
        "service level",
        "kpi",
        "delivery",
        "lost package",
                    "draft_client_email_case",
                    "draft_internal_email_case",
        "route",
        "dashboard",
        "invoice",
        "reconciliation",
        "duplicate charge",
        "rate card",
        "proof-of-delivery",
        "proof of delivery",
        "complaint",
        "log",
        "methodology",
        "workflow",
    )
    HIGH_SEVERITY_RISK_KEYWORDS = (
        "material breach",
        "termination",
        "liability cap",
        "arbitration",
        "reservation of rights",
        "default",
        "two consecutive",
        "cure period",
        "cure",
    )
    MEDIUM_SEVERITY_RISK_KEYWORDS = (
        "dispute",
        "notice",
        "deadline",
        "non-compliance",
        "non compliance",
        "invoice",
        "payment",
        "force-majeure",
        "force majeure",
    )
    SUPPORTING_EVIDENCE_RISK_KEYWORDS = (
        "evidence",
        "documentation",
        "proof",
        "methodology",
        "incomplete",
        "duplicate",
        "reconciliation",
        "support logs",
        "supporting logs",
    )
    RISK_TOKEN_STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "be",
        "by",
        "case",
        "due",
        "for",
        "from",
        "high",
        "in",
        "into",
        "is",
        "legal",
        "low",
        "medium",
        "of",
        "on",
        "operational",
        "or",
        "over",
        "possible",
        "potential",
        "ranked",
        "remain",
        "remains",
        "risk",
        "risks",
        "that",
        "the",
        "this",
        "to",
        "under",
        "with",
    }
    HIGH_REASONING_ELIGIBLE_INTENTS = copilot_constants.HIGH_REASONING_ELIGIBLE_INTENTS
    HIGH_REASONING_STYLES = copilot_constants.HIGH_REASONING_STYLES

    def __init__(
        self,
        rag_service: RagService,
        document_pipeline: Optional[DocumentAIPipeline] = None,
    ):
        self.rag_service = rag_service
        self.document_pipeline = document_pipeline or DocumentAIPipeline(
            embedding_service=rag_service.embedding_service,
            vector_store=rag_service.vector_store,
        )
        self.client = llm_gateway.create_client()
        self.model = llm_gateway.default_model
        self.intent_execution_agent = copilot_intent_execution_agent

    @staticmethod
    def _normalize_role(value: str | None) -> str:
        normalized = str(value or "assistant").strip().lower()
        return normalized if normalized in {"admin", "lawyer", "assistant", "client"} else "assistant"

    @staticmethod
    def _normalize_mode(value: str | None) -> str:
        normalized = str(value or "default").strip().lower()
        return normalized or "default"

    @staticmethod
    def _normalize_reasoning_level(value: str | None) -> str:
        normalized = str(value or "medium").strip().lower()
        if normalized not in {"low", "medium", "high"}:
            return "medium"
        return normalized

    def _should_use_trust_engine(self, *, normalized_mode: str, intent: str, agent_mode: bool) -> bool:
        normalized = str(normalized_mode or "default").strip().lower()
        parsed_intent = str(intent or "").strip()
        if normalized == "legal_search" and parsed_intent in self.LEGAL_SEARCH_ELIGIBLE_INTENTS:
            return True
        if normalized == "external" and parsed_intent in self.LEGAL_SEARCH_ELIGIBLE_INTENTS:
            return True
        return False

    @staticmethod
    def _chat_mode_needs_rag(
        *,
        question: str,
        intent: str,
        case_id: Optional[int],
        document_id: Optional[int],
    ) -> bool:
        lowered = str(question or "").strip().lower()
        if not lowered:
            return False
        if CopilotService._looks_like_conversational_opening(lowered):
            return False
        if CopilotService.CHAT_THANKS_PATTERN.search(lowered):
            return False
        if any(token in lowered for token in ("joke", "funny", "make me laugh")) and not any(
            token in lowered for token in ("case", "document", "contract", "clause", "evidence")
        ):
            return False
        document_action_intents = {
            "summarize_document",
            "list_deadlines_case",
            "list_case_documents",
            "list_case_appointments",
            "trace_case_evidence",
            "compare_case_documents",
            "monitor_deadlines_case",
        }
        if intent in document_action_intents and (case_id is not None or document_id is not None):
            return True

        workspace_signals = [
            "case #",
            "this case",
            "current case",
            "document #",
            "this document",
            "uploaded",
            "file",
            "contract",
            "clause",
            "deadline",
            "notice",
            "invoice",
            "sla",
            "kpi",
            "summarize case",
            "summarize document",
            "what does the document say",
            "according to the document",
            "nova",
            "response",
            "counterparty",
        ]
        if not any(signal in lowered for signal in workspace_signals):
            return False

        explicit_workspace_anchors = [
            "case #",
            "this case",
            "current case",
            "document #",
            "this document",
            "uploaded",
            "file",
            "summarize case",
            "summarize document",
            "what does the document say",
            "according to the document",
            "in the document",
            "in this contract",
            "in the contract",
            "find the",
            "show me the",
            "extract",
            "deadlines in this case",
            "notice in this case",
            "what did",
            "what was said",
        ]
        if any(anchor in lowered for anchor in explicit_workspace_anchors):
            return True

        educational_starters = (
            "what is ",
            "what are ",
            "what does ",
            "explain ",
            "how do ",
            "how does ",
            "give me ",
            "tell me ",
            "write ",
            "make this ",
        )
        if lowered.startswith(educational_starters):
            return False

        return True

    @staticmethod
    def _strip_trust_artifacts(result: Dict[str, Any]) -> Dict[str, Any]:
        stripped = dict(result or {})
        for key in (
            "trust_panel",
            "trust_validation",
            "claim_validation",
            "contradiction_detection",
            "unsupported_claims",
            "verified_claims",
            "sentence_to_source_evidence",
            "sentence_to_source_mapping",
            "strict_verification",
            "article_applicability",
            "global_output_contract",
            "legal_workflow_agents",
            "final_answer_source",
            "original_answer_before_final_composer",
        ):
            stripped.pop(key, None)

        structured = stripped.get("structured_result")
        if isinstance(structured, dict):
            structured = dict(structured)
            for key in (
                "trust_panel",
                "trust_validation",
                "claim_validation",
                "contradiction_detection",
                "unsupported_claims",
                "verified_claims",
                "sentence_to_source_evidence",
                "sentence_to_source_mapping",
                "strict_verification",
                "article_applicability",
                "global_output_contract",
                "legal_workflow_agents",
                "final_answer_source",
                "original_answer_before_final_composer",
            ):
                structured.pop(key, None)
            stripped["structured_result"] = structured
        return stripped

    def _strip_heavy_trust_diagnostics(self, result: Dict[str, Any]) -> Dict[str, Any]:
        stripped = self._strip_trust_artifacts(result)
        for key in (
            "contradictions",
            "legal_audit",
            "verification_details",
            "risk_panel",
        ):
            stripped.pop(key, None)

        structured = stripped.get("structured_result")
        if isinstance(structured, dict):
            structured = dict(structured)
            for key in (
                "contradictions",
                "legal_audit",
                "verification_details",
                "risk_panel",
            ):
                structured.pop(key, None)
            stripped["structured_result"] = structured
        return stripped

    @staticmethod
    def _result_indicates_insufficient_evidence(result: Dict[str, Any]) -> bool:
        trust_panel = result.get("trust_panel") if isinstance(result.get("trust_panel"), dict) else {}
        status = str((trust_panel or {}).get("status") or result.get("status") or "").strip().lower()
        fallback_reason = str(result.get("fallback_reason") or "").strip().lower()
        answer = str(result.get("answer") or "").strip().lower()
        return (
            status == "insufficient_evidence"
            or fallback_reason in {"no_direct_legal_source", "insufficient_evidence"}
            or "not enough grounded evidence" in answer
            or "insufficient evidence" in answer
        )

    def _normalize_trust_state(self, result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(result or {})
        if not self._result_indicates_insufficient_evidence(normalized):
            trust_panel = normalized.get("trust_panel")
            if isinstance(trust_panel, dict):
                strength = str(trust_panel.get("evidence_strength") or "").strip().lower()
                confidence = str(normalized.get("confidence") or trust_panel.get("confidence") or "").strip().lower()
                status = str(trust_panel.get("status") or "").strip().lower()
                if "insufficient" in strength or status == "insufficient_evidence":
                    normalized["confidence"] = "low"
            return normalized

        message = "Not enough grounded evidence to produce a reliable legal analysis."
        normalized["status"] = "INSUFFICIENT_EVIDENCE"
        normalized["answer"] = message
        normalized["confidence"] = "low"
        normalized["verification_status"] = "failed"
        normalized["evidence_strength"] = "insufficient"
        normalized["position_strength"] = "not_assessable"
        normalized["citation_coverage"] = 0
        normalized["unsupported_rate"] = 100
        normalized["recommended_strategy"] = "gather_missing_evidence"
        normalized["risk_summary"] = "Risk cannot be assessed reliably from available evidence."
        normalized["used_fallback"] = True
        normalized["fallback_reason"] = "insufficient_evidence"

        trust_panel = normalized.get("trust_panel") if isinstance(normalized.get("trust_panel"), dict) else {}
        trust_panel = dict(trust_panel)
        metrics = trust_panel.get("metrics") if isinstance(trust_panel.get("metrics"), dict) else {}
        metrics = {
            **metrics,
            "citation_coverage": 0,
            "unsupported_rate": 100,
            "hallucination_rate": 1.0,
        }
        trust_panel.update(
            {
                "status": "INSUFFICIENT_EVIDENCE",
                "message": message,
                "answer": message,
                "confidence": "low",
                "confidence_score": 0.0,
                "verification_status": "failed",
                "evidence_strength": "insufficient",
                "position_strength": "not_assessable",
                "citation_coverage": 0,
                "unsupported_rate": 100,
                "recommended_strategy": "gather_missing_evidence",
                "risk_summary": {
                    "client": "Risk cannot be assessed reliably from available evidence.",
                    "opposing_party": "Risk cannot be assessed reliably from available evidence.",
                },
                "metrics": metrics,
            }
        )
        normalized["trust_panel"] = trust_panel

        structured = normalized.get("structured_result")
        if isinstance(structured, dict):
            structured = dict(structured)
            structured["trust_panel"] = trust_panel
            normalized["structured_result"] = structured
        return normalized

    def _permission_denied_response(self, *, user_role: str, action: str) -> Dict[str, Any]:
        return {
            "answer": f"Permission denied: your role '{user_role}' cannot perform '{action}'.",
            "used_fallback": True,
            "fallback_reason": "permission_denied",
            "confidence": "high",
            "scope": "global",
            "sources": [],
            "action_status": "denied",
            "permission_denied": True,
            "structured_result": {
                "action": action,
                "required_roles": sorted(self.CASE_WRITE_ROLES),
                "current_role": user_role,
            },
        }

    def _agent_mode_required_response(self, *, action: str) -> Dict[str, Any]:
        return {
            "answer": (
                f"Action '{action}' was detected but not executed. "
                "Enable Agent Mode to run write operations like create/update/upload actions."
            ),
            "used_fallback": True,
            "fallback_reason": "agent_mode_required",
            "confidence": "high",
            "scope": "global",
            "sources": [],
            "action_status": "requires_agent_mode",
            "structured_result": {
                "action": action,
                "requires_agent_mode": True,
            },
        }

    @staticmethod
    def _looks_like_conversational_opening(message: str) -> bool:
        lowered = str(message or "").strip().lower()
        if not lowered:
            return True

        compact = re.sub(r"\s+", " ", lowered)
        if CopilotService.CHAT_GREETING_PATTERN.search(compact):
            return True
        if compact in {
            "how are you",
            "who are you",
            "what can you do",
            "help",
            "can you help me",
            "i need help",
        }:
            return True
        return False

    @staticmethod
    def _build_chat_greeting_answer(*, user_role: str) -> str:
        role_hint = "lawyer" if user_role in {"admin", "lawyer", "assistant"} else "client"
        if role_hint == "lawyer":
            return (
                "Hey. I am your legal copilot, but we can talk normally too. "
                "I can help with jokes, explanations, brainstorming, writing, legal drafting, case strategy, and document questions.\n"
                "You can start with:\n"
                "1. Tell me a joke.\n"
                "2. Make this email more professional.\n"
                "3. Explain arbitration simply.\n"
                "4. Find the SLA clause in this document."
            )
        return (
            "Hey. I can chat normally and help with legal questions in plain language. "
            "Ask me for explanations, drafting help, brainstorming, or questions about your documents.\n"
            "You can start with:\n"
            "1. Explain this simply.\n"
            "2. Help me prepare questions for my lawyer.\n"
            "3. Summarize this document."
        )

    @staticmethod
    def _build_chat_fallback_answer(question: str) -> str:
        cleaned = str(question or "").strip()
        lowered = cleaned.lower()
        if not cleaned:
            return CopilotService._build_chat_greeting_answer(user_role="assistant")
        if any(token in lowered for token in ("joke", "funny", "make me laugh")):
            return (
                "Sure. Why did the lawyer bring a ladder to court?\n\n"
                "Because they wanted to take the case to a higher level."
            )
        if lowered in {"yo", "hi", "hello", "hey"}:
            return "Yo. What are we working on today?"
        if lowered.startswith(("write ", "draft ", "make this ", "rewrite ")):
            return (
                "Absolutely. Send me the text or the goal, and I can make it clearer, more professional, "
                "more persuasive, shorter, warmer, or more lawyerly."
            )
        if lowered.startswith(("explain ", "what is ", "what are ", "how do ", "how does ")):
            return (
                "I can explain that clearly. If you want a general explanation, ask normally; if you want me "
                "to use your case documents, mention the case, document, clause, or file."
            )
        return (
            "I can help with that. Chat Mode works like a normal assistant: we can brainstorm, draft, explain, joke, "
            "plan, or talk through legal work. If you want me to use uploaded documents, just point me to the case, "
            "document, clause, or file."
        )

    def _respond_in_chat_mode(
        self,
        *,
        question: str,
        user_role: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        normalized_question = str(question or "").strip()
        if not normalized_question:
            return {
                "answer": self._build_chat_greeting_answer(user_role=user_role),
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "global",
                "sources": [],
                "citations": [],
            }

        if not self.client:
            return {
                "answer": self._build_chat_fallback_answer(normalized_question),
                "used_fallback": True,
                "fallback_reason": "No LLM provider API key is configured",
                "confidence": "medium",
                "scope": "global",
                "sources": [],
                "citations": [],
            }

        history_lines: List[str] = []
        for item in (conversation_history or [])[-8:]:
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                history_lines.append(f"{role}: {content[:500]}")

        prompt = f"""
You are Legal AI, a professional conversational legal assistant for lawyers.

Default chat-mode behavior:
- Act like a normal ChatGPT-style assistant with legal productivity strengths.
- Be conversational, clear, and professional.
- You may answer jokes, general knowledge, writing, brainstorming, productivity, and everyday questions.
- Be concise by default, but add detail when the user asks.
- Answer greetings and follow-up questions naturally.
- If the user says "another one", "more", "again", or similar, infer what they want from the recent conversation.
- Provide practical legal insights when relevant.
- Do not execute CRUD operations or workflow tasks in this mode.
- If the user asks to execute actions, explain that Agent Mode is for execution and offer planning guidance.
- Do not invent legal authorities, case law, or statutes.
- Include a brief legal-support disclaimer only when the user asks for definitive legal advice or high-stakes decisions.
- Do not use courtroom-style verification, trust panels, or audit language in Chat Mode.
- Do not answer with "insufficient evidence" unless the user explicitly asked you to inspect case files/documents and they are unavailable.

Conversation so far:
{chr(10).join(history_lines) or "No prior messages."}

User message:
{normalized_question}
"""

        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            answer = llm_gateway.extract_output_text(response).strip()
            if answer:
                return {
                    "answer": answer,
                    "used_fallback": False,
                    "fallback_reason": None,
                    "confidence": "medium",
                    "scope": "global",
                    "sources": [],
                    "citations": [],
                }
        except Exception:
            pass

        return {
            "answer": self._build_chat_fallback_answer(normalized_question),
            "used_fallback": True,
            "fallback_reason": "chat_generation_failed",
            "confidence": "medium",
            "scope": "global",
            "sources": [],
            "citations": [],
        }

    @staticmethod
    def _normalize_status_value(value: str | None) -> str | None:
        normalized = str(value or "").strip().lower().replace(" ", "_")
        if normalized in {"open", "in_progress", "closed", "archived"}:
            return normalized
        return None

    def _apply_workspace_scope(
        self,
        *,
        parsed: Dict[str, Any],
        intent: str,
        workspace_case_id: Optional[int],
        workspace_document_id: Optional[int],
    ) -> Dict[str, Any]:
        next_parsed = dict(parsed)
        query_text = self._normalize_lookup_text(
            str(next_parsed.get("clean_query") or next_parsed.get("raw_message") or "")
        )

        if intent == "summarize_global" and isinstance(workspace_case_id, int):
            next_parsed["intent"] = "summarize_case"
            next_parsed["case_id"] = workspace_case_id
            next_parsed["target_type"] = "case"
            next_parsed["target_id"] = workspace_case_id

        if intent == "ask_global" and isinstance(workspace_case_id, int):
            if any(
                token in query_text
                for token in ["timeline", "chronology", "chronological", "sequence of events", "case events"]
            ):
                next_parsed["intent"] = "build_timeline_case"
                next_parsed["case_id"] = workspace_case_id
                next_parsed["target_type"] = "case"
                next_parsed["target_id"] = workspace_case_id
            elif any(
                token in query_text
                for token in [
                    "trace evidence",
                    "evidence trace",
                    "claim trace",
                    "claim to evidence",
                    "evidence map",
                    "source map",
                    "support this claim",
                    "supporting evidence",
                ]
            ):
                next_parsed["intent"] = "trace_case_evidence"
                next_parsed["case_id"] = workspace_case_id
                next_parsed["target_type"] = "case"
                next_parsed["target_id"] = workspace_case_id
            elif any(
                token in query_text
                for token in [
                    "case memory",
                    "memory snapshot",
                    "what are we missing",
                    "what am i missing",
                    "open proof gaps",
                    "missing documents",
                    "missing docs",
                    "what is missing",
                    "what's missing",
                    "case snapshot",
                ]
            ):
                next_parsed["intent"] = "generate_case_memory"
                next_parsed["case_id"] = workspace_case_id
                next_parsed["target_type"] = "case"
                next_parsed["target_id"] = workspace_case_id
            elif any(
                token in query_text
                for token in [
                    "risk",
                    "risks",
                    "legal risk",
                    "operational risk",
                    "exposure",
                    "exposures",
                    "liability",
                    "liabilities",
                ]
            ):
                next_parsed["intent"] = "analyze_risks_case"
                next_parsed["case_id"] = workspace_case_id
                next_parsed["target_type"] = "case"
                next_parsed["target_id"] = workspace_case_id
                if next_parsed.get("requested_count") is None:
                    next_parsed["requested_count"] = self._extract_count_hint(query_text)
            elif any(
                token in query_text
                for token in ["draft", "write", "prepare", "email", "mail", "client update", "posture", "status update"]
            ):
                next_parsed["intent"] = "draft_client_email_case"
                next_parsed["case_id"] = workspace_case_id
                next_parsed["target_type"] = "case"
                next_parsed["target_id"] = workspace_case_id

            if any(
                token in query_text
                for token in ["internal update", "supervising lawyer", "lawyer update", "internal memo", "team update", "partner update"]
            ):
                next_parsed["intent"] = "draft_internal_email_case"
                next_parsed["case_id"] = workspace_case_id
                next_parsed["target_type"] = "case"
                next_parsed["target_id"] = workspace_case_id

        if intent in {"list_cases", "list_clients", "create_case", "create_client"}:
            return next_parsed

        if next_parsed.get("case_id") is None and isinstance(workspace_case_id, int):
            next_parsed["case_id"] = workspace_case_id
            if next_parsed.get("target_type") is None:
                next_parsed["target_type"] = "case"
                next_parsed["target_id"] = workspace_case_id

        if next_parsed.get("document_id") is None and isinstance(workspace_document_id, int):
            if next_parsed.get("target_type") in {None, "document"}:
                next_parsed["document_id"] = workspace_document_id
                next_parsed["target_type"] = "document"
                next_parsed["target_id"] = workspace_document_id

        return next_parsed

    def _autocorrect_message(
        self,
        message: str,
        conversation_history: List[Dict[str, Any]] | None = None,
        *,
        allow_llm: bool = False,
    ) -> str:
        corrected = prompt_correction_agent.correct_query(
            raw_query=message,
            conversation_history=conversation_history or [],
            allow_llm=allow_llm,
        )
        candidate = corrected.payload.get("corrected_query") if corrected.success else None
        normalized = str(candidate or "").strip()
        return normalized or message

    def _extract_count_hint(self, message: str) -> Optional[int]:
        lowered = (message or "").strip().lower()
        if not lowered:
            return None

        # Remove scoped identifiers so inputs like "summarize case #23" do not become count=12.
        scrubbed = re.sub(r"\b(case|document|client)\s*#?\s*\d{1,5}\b", " ", lowered)
        scrubbed = re.sub(r"#\d{1,5}\b", " ", scrubbed)
        scrubbed = re.sub(r"\s+", " ", scrubbed).strip()

        match = self.FOLLOW_UP_COUNT_PATTERN.search(scrubbed)
        if not match:
            return None
        token = match.group(1).strip().lower()
        if token.isdigit():
            value = int(token)
        else:
            value = self.NUMBER_WORDS.get(token, 0)
        if value <= 0:
            return None
        return min(value, 12)

    def _build_history_context(self, conversation_history: List[Dict[str, Any]] | None) -> Dict[str, Any]:
        items = conversation_history or []
        last_case_id: Optional[int] = None
        last_document_id: Optional[int] = None
        last_intent: Optional[str] = None

        for item in reversed(items):
            if last_case_id is None:
                case_id = item.get("case_id")
                if isinstance(case_id, int):
                    last_case_id = case_id
            if last_document_id is None:
                document_id = item.get("document_id")
                if isinstance(document_id, int):
                    last_document_id = document_id

            if last_intent is None and item.get("role") == "assistant":
                parsed_intent = str(item.get("parsed_intent") or "").strip()
                if parsed_intent and parsed_intent not in {"request_error", "validation_error"}:
                    last_intent = parsed_intent
            if last_case_id is not None and last_document_id is not None and last_intent:
                break

        return {
            "last_case_id": last_case_id,
            "last_document_id": last_document_id,
            "last_intent": last_intent,
        }

    def _is_follow_up_message(self, message: str) -> bool:
        lowered = (message or "").strip().lower()
        if not lowered:
            return False
        if self._extract_count_hint(lowered):
            return True
        return bool(self.FOLLOW_UP_HINT_PATTERN.search(lowered))

    def _apply_conversation_memory(
        self,
        *,
        parsed: Dict[str, Any],
        original_message: str,
        history_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        updated = dict(parsed)
        if updated.get("intent") in {"create_case", "create_client"}:
            return updated

        if updated.get("case_id") is None and isinstance(history_context.get("last_case_id"), int):
            updated["case_id"] = history_context["last_case_id"]
            if updated.get("target_type") is None:
                updated["target_type"] = "case"
                updated["target_id"] = history_context["last_case_id"]

        if updated.get("document_id") is None and isinstance(history_context.get("last_document_id"), int):
            if updated.get("target_type") is None:
                updated["document_id"] = history_context["last_document_id"]
                updated["target_type"] = "document"
                updated["target_id"] = history_context["last_document_id"]

        count_hint = self._extract_count_hint(original_message)
        if count_hint and not updated.get("requested_count"):
            updated["requested_count"] = count_hint

        if (
            updated.get("intent") in {"ask_global", "summarize_global"}
            and self._is_follow_up_message(original_message)
            and isinstance(history_context.get("last_intent"), str)
        ):
            prior_intent = history_context["last_intent"]
            if prior_intent in {
                "summarize_and_analyze_risks_case",
                "summarize_case",
                "summarize_document",
                "list_deadlines_case",
                "build_timeline_case",
                "generate_case_insights",
                "generate_case_memory",
                "analyze_risks_case",
                "review_booking_case",
                "draft_client_email_case",
                "draft_partner_strategy_note_case",
                "trace_case_evidence",
                "compare_case_documents",
                "ask_case",
                "ask_document",
                "list_cases",
                "list_clients",
                "list_case_documents",
                "list_case_appointments",
                }:
                updated["intent"] = prior_intent

            if updated.get("requested_count") is None and count_hint is not None:
                updated["requested_count"] = count_hint

        return updated

    def handle_message(
        self,
        db: Session,
        tenant_id: int,
        user_id: Optional[int],
        user_role: str,
        message: str,
        top_k: int = 5,
        use_external_research: bool = True,
        mode: Optional[str] = None,
        legal_search_multilingual_output: bool = False,
        legal_search_code_scope: Optional[List[str]] = None,
        reasoning_level: str | None = None,
        agent_mode: bool = False,
        workspace_case_id: Optional[int] = None,
        workspace_document_id: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        preparsed_command: Optional[Dict[str, Any]] = None,
        skip_autocorrect: bool = False,
        preoptimized_query: Optional[str] = None,
        allowed_case_ids: Optional[List[int]] = None,
        allowed_document_ids: Optional[List[int]] = None,
        case_context: Dict[str, Any] | None = None,
        case_snapshot: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if isinstance(preparsed_command, dict):
            parsed = dict(preparsed_command)
        else:
            # Preserve explicit intent commands (e.g. "Optimize prompt: ...") before any correction pass.
            raw_parsed = command_parsing_service.parse(message)
            if raw_parsed.get("intent") == "optimize_prompt" or skip_autocorrect:
                parsed = raw_parsed
            else:
                corrected_message = self._autocorrect_message(
                    message=message,
                    conversation_history=conversation_history,
                    allow_llm=str(raw_parsed.get("confidence") or "").strip().lower() != "high",
                )
                parsed = command_parsing_service.parse(corrected_message)
                # Guardrail: keep strong raw case intents if correction pass accidentally dilutes intent.
                strong_case_intents = {
                    "create_case",
                    "create_client",
                    "create_prompt_library_entry",
                    "update_case",
                    "update_client",
                    "delete_case",
                    "delete_client",
                    "update_case_appointment",
                    "delete_case_appointment",
                    "update_prompt_library_entry",
                    "delete_prompt_library_entry",
                    "summarize_and_analyze_risks_case",
                    "summarize_case",
                    "analyze_risks_case",
                    "list_deadlines_case",
                    "build_timeline_case",
                    "generate_case_insights",
                    "generate_case_memory",
                    "review_booking_case",
                    "draft_client_email_case",
                    "draft_partner_strategy_note_case",
                    "trace_case_evidence",
                    "compare_case_documents",
                    "list_case_documents",
                    "list_case_appointments",
                    "request_document_upload",
                    "request_audio_upload",
                    "create_case_appointment",
                    "update_case_status",
                    "list_cases",
                    "list_clients",
                    "list_prompt_library",
                }
                if raw_parsed.get("intent") in strong_case_intents and parsed.get("intent") in {"ask_global", "summarize_global"}:
                    parsed = raw_parsed

        history_context = self._build_history_context(conversation_history)
        parsed = self._apply_conversation_memory(
            parsed=parsed,
            original_message=message,
            history_context=history_context,
        )
        intent = parsed["intent"]
        parsed = self._apply_workspace_scope(
            parsed=parsed,
            intent=intent,
            workspace_case_id=workspace_case_id,
            workspace_document_id=workspace_document_id,
        )
        intent = parsed["intent"]
        normalized_role = self._normalize_role(user_role)
        normalized_mode = self._normalize_mode(mode)
        normalized_reasoning_level = self._normalize_reasoning_level(reasoning_level)
        normalized_allowed_case_ids = self._normalize_allowed_ids(allowed_case_ids)
        normalized_allowed_document_ids = self._normalize_allowed_ids(allowed_document_ids)
        resolved_query = str(preoptimized_query or parsed.get("clean_query") or parsed.get("raw_message") or message).strip()
        if resolved_query:
            parsed["clean_query"] = resolved_query

        steps: List[str] = [
            f"Parsed intent: {intent}",
            f"Target: {parsed.get('target_type') or 'global'}",
            f"Role: {normalized_role}",
            f"Mode: {normalized_mode}",
            f"Reasoning: {normalized_reasoning_level}",
        ]

        if normalized_role == "client" and intent not in self.CLIENT_ALLOWED_INTENTS:
            return self._permission_denied_response(user_role=normalized_role, action=intent)

        scope_error = self._validate_scope_permissions(
            parsed=parsed,
            allowed_case_ids=normalized_allowed_case_ids,
            allowed_document_ids=normalized_allowed_document_ids,
        )
        if scope_error is not None:
            return scope_error

        execution_ctx = CopilotIntentExecutionContext(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=normalized_role,
            message=message,
            top_k=top_k,
            use_external_research=use_external_research,
            reasoning_level=normalized_reasoning_level,
            workspace_case_id=workspace_case_id,
            resolved_query=resolved_query,
            parsed=parsed,
            preoptimized_query=preoptimized_query,
            normalized_allowed_case_ids=normalized_allowed_case_ids,
            normalized_allowed_document_ids=normalized_allowed_document_ids,
            case_context=case_context,
            case_snapshot=case_snapshot,
        )

        use_trust_engine = self._should_use_trust_engine(
            normalized_mode=normalized_mode,
            intent=intent,
            agent_mode=agent_mode,
        )

        if use_trust_engine:
            result = legal_search_mode_service.run(
                db=db,
                tenant_id=tenant_id,
                user_role=normalized_role,
                message=resolved_query,
                top_k=top_k,
                case_id=parsed.get("case_id"),
                document_id=parsed.get("document_id"),
                conversation_history=conversation_history,
                intent=intent,
                target_type=parsed.get("target_type"),
                target_id=parsed.get("target_id"),
                retrieval_agent=self.rag_service.retrieval_agent,
                multilingual_output=legal_search_multilingual_output,
                code_scope=legal_search_code_scope,
            )
            result = self._normalize_trust_state(result)
        elif intent in self.CRUD_INTENTS and not agent_mode:
            result = self._agent_mode_required_response(action=intent)
        elif normalized_mode == "default" and not agent_mode:
            if self._chat_mode_needs_rag(
                question=resolved_query,
                intent=intent,
                case_id=parsed.get("case_id") if isinstance(parsed.get("case_id"), int) else workspace_case_id,
                document_id=(
                    parsed.get("document_id") if isinstance(parsed.get("document_id"), int) else workspace_document_id
                ),
            ):
                result = self.intent_execution_agent.execute(
                    intent=intent,
                    runtime=self,
                    ctx=execution_ctx,
                )
                result = self._strip_heavy_trust_diagnostics(result)
            else:
                result = self._respond_in_chat_mode(
                    question=resolved_query,
                    user_role=normalized_role,
                    conversation_history=conversation_history,
                )
        else:
            result = self.intent_execution_agent.execute(
                intent=intent,
                runtime=self,
                ctx=execution_ctx,
            )
        if not use_trust_engine:
            result = self._strip_heavy_trust_diagnostics(result)
        action_category = "legal_search" if use_trust_engine else self.ACTION_CATEGORY_BY_INTENT.get(intent, "analysis")
        action_status = str(result.pop("action_status", "")).strip() or ("fallback" if result.get("used_fallback") else "completed")
        permission_denied = bool(result.pop("permission_denied", False))
        structured_result = result.pop("structured_result", {})
        if agent_mode:
            steps.append(f"Action category: {action_category}")
            steps.append(f"Action status: {action_status}")

        return {
            "message": message,
            "parsed_intent": parsed["intent"],
            "target_type": parsed["target_type"],
            "target_id": parsed["target_id"],
            "mode": normalized_mode,
            "reasoning_level": normalized_reasoning_level,
            "agent_mode": bool(agent_mode),
            "action_category": action_category,
            "action_status": action_status,
            "permission_denied": permission_denied,
            "steps": steps if agent_mode else [],
            "structured_result": structured_result if isinstance(structured_result, dict) else {},
            **result
        }

    @staticmethod
    def _normalize_allowed_ids(values: Optional[List[int]]) -> set[int] | None:
        if values is None:
            return None
        normalized = {
            int(value)
            for value in values
            if isinstance(value, int) or (isinstance(value, str) and str(value).isdigit())
        }
        return normalized

    def _validate_scope_permissions(
        self,
        *,
        parsed: Dict[str, Any],
        allowed_case_ids: set[int] | None,
        allowed_document_ids: set[int] | None,
    ) -> Dict[str, Any] | None:
        case_id = parsed.get("case_id")
        document_id = parsed.get("document_id")

        if allowed_case_ids is not None and isinstance(case_id, int) and case_id not in allowed_case_ids:
            return {
                **self._permission_denied_response(user_role="client", action="access_case"),
                "answer": "This assistant can only access cases linked to your portal account.",
                "scope": "case",
                "structured_result": {
                    "requested_case_id": case_id,
                    "allowed_case_ids": sorted(allowed_case_ids),
                },
            }

        if (
            allowed_document_ids is not None
            and isinstance(document_id, int)
            and document_id not in allowed_document_ids
        ):
            return {
                **self._permission_denied_response(user_role="client", action="access_document"),
                "answer": "This assistant can only access documents linked to your portal account.",
                "scope": "document",
                "structured_result": {
                    "requested_document_id": document_id,
                    "allowed_document_ids": sorted(allowed_document_ids),
                },
            }

        return None

    def _unsupported_intent_response(self) -> Dict[str, Any]:
        return {
            "answer": "I could not understand the command clearly.",
            "used_fallback": True,
            "fallback_reason": "Unsupported intent",
            "confidence": "low",
            "scope": "global",
            "sources": []
        }

    @staticmethod
    def _normalize_lookup_text(value: str | None) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    @staticmethod
    def _build_refresh_triggers(*types_to_refresh: str) -> list[Dict[str, str]]:
        unique_types: list[str] = []
        for item in types_to_refresh:
            cleaned = str(item or "").strip().lower()
            if cleaned and cleaned not in unique_types:
                unique_types.append(cleaned)
        return [{"type": f"refresh_{item}"} for item in unique_types]

    @staticmethod
    def _strip_extracted_value(value: str) -> str:
        cleaned = str(value or "").splitlines()[0]
        quoted = re.match(r"^\s*([\"'])(.*?)\1", cleaned)
        if quoted:
            cleaned = quoted.group(2)
        else:
            cleaned = re.split(
                r"\s+\b(?:and|then)\b\s+(?=(?:set|update|change|modify|rename)\b)",
                cleaned,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
        cleaned = re.sub(r"\b(?:and|then)\s*$", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip(" ,;:-\"'")

    def _extract_field_value(
        self,
        message: str,
        labels: list[str],
        *,
        stop_labels: list[str] | None = None,
    ) -> Optional[str]:
        text = str(message or "")
        for label in labels:
            label_pattern = re.escape(label).replace(r"\ ", r"\s+")
            candidate: Optional[str] = None
            for pattern in (
                rf"(?<!\w)(?:set|update|change|modify|rename)\s+{label_pattern}(?!\w)\s*(?:is|=|:|to|as)?\s*",
                rf"(?<!\w){label_pattern}(?!\w)\s*(?:is|=|:|to|as)?\s*",
            ):
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    candidate = text[match.end():]
                    break

            if candidate is None:
                continue

            if stop_labels:
                stop_pattern = "|".join(
                    re.escape(stop_label).replace(r"\ ", r"\s+")
                    for stop_label in stop_labels
                )
                stop_match = re.search(
                    rf"(?:\b(?:and|then)\b\s+)?(?:(?:set|update|change|modify|rename)\s+)?(?:{stop_pattern})\s*(?:is|=|:|to|as)?\s*",
                    candidate,
                    re.IGNORECASE,
                )
                if stop_match:
                    candidate = candidate[:stop_match.start()]

            cleaned_candidate = self._strip_extracted_value(candidate)
            if cleaned_candidate:
                return cleaned_candidate[:4000]
        return None

    @staticmethod
    def _extract_boolean_value(message: str, labels: list[str]) -> Optional[bool]:
        lowered = str(message or "").lower()
        for label in labels:
            if label not in lowered:
                continue
            window = lowered[max(0, lowered.find(label) - 16) : lowered.find(label) + len(label) + 32]
            if any(negative in window for negative in ["not favorite", "not fav", "remove favorite", "unfavorite", "unstar", "without favorite"]):
                return False
            return True
        return None

    @staticmethod
    def _extract_datetime_value(message: str) -> Optional[datetime]:
        text = str(message or "").strip()
        if not text:
            return None

        iso_match = re.search(
            r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?(?:Z|[+-]\d{2}:?\d{2})?\b",
            text,
        )
        if iso_match:
            candidate = iso_match.group(0).replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                pass

        patterns = [
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%d/%m/%Y %H:%M",
            "%m/%d/%Y %H:%M",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]
        for pattern in patterns:
            try:
                return datetime.strptime(text[:32], pattern)
            except ValueError:
                continue

        return None

    def _find_client_by_name(
        self,
        *,
        db: Session,
        tenant_id: int,
        requested_client_name: str,
    ) -> Optional[Client]:
        needle = self._normalize_lookup_text(requested_client_name)
        if not needle:
            return None

        rows = (
            db.query(Client)
            .filter(
                Client.tenant_id == tenant_id,
                Client.deleted_at.is_(None),
            )
            .order_by(Client.created_at.desc(), Client.id.desc())
            .limit(400)
            .all()
        )
        if not rows:
            return None

        for row in rows:
            if self._normalize_lookup_text(row.name) == needle:
                return row

        for row in rows:
            normalized_name = self._normalize_lookup_text(row.name)
            if needle in normalized_name or normalized_name in needle:
                return row

        return None

    @staticmethod
    def _build_default_case_description(*, case_title: str, raw_message: str) -> str:
        lowered = str(raw_message or "").lower()
        if "random description" in lowered or "any description" in lowered:
            templates = [
                f"{case_title}: Initial legal intake created via agent mode. Documents and evidence collection to follow.",
                f"{case_title}: New matter opened for legal review. Scope, deadlines, and risk assessment pending document upload.",
                f"{case_title}: Client matter created from copilot action for structured legal analysis and workflow tracking.",
            ]
            index = sum(ord(char) for char in case_title) % len(templates)
            return templates[index]

        return "Case created by Copilot agent mode action."

    def _extract_client_name_from_message_fallback(self, *, raw_message: str) -> Optional[str]:
        match = re.search(
            r"\bclient\b(?:\s*(?:is|named|called|=))?\s*[:\-]?\s*['\"]?([^\"'\n,]{2,160})",
            raw_message,
            re.IGNORECASE,
        )
        if not match:
            return None
        candidate = match.group(1).strip()
        candidate = re.split(
            r"\s+\b(?:and|with|for|description|status)\b",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .,:;!?-\"'")
        return candidate[:160] if len(candidate) >= 2 else None

    def _resolve_case_creation_client(
        self,
        *,
        db: Session,
        tenant_id: int,
        requested_client_id: Optional[int],
        requested_client_name: Optional[str],
        workspace_case_id: Optional[int],
    ) -> tuple[Optional[Client], bool]:
        if isinstance(requested_client_id, int):
            existing_by_id = (
                db.query(Client)
                .filter(
                    Client.id == requested_client_id,
                    Client.tenant_id == tenant_id,
                    Client.deleted_at.is_(None),
                )
                .first()
            )
            if existing_by_id:
                return existing_by_id, False

        if requested_client_name:
            existing_by_name = self._find_client_by_name(
                db=db,
                tenant_id=tenant_id,
                requested_client_name=requested_client_name,
            )
            if existing_by_name:
                return existing_by_name, False

            client = Client(
                name=requested_client_name[:160],
                tenant_id=tenant_id,
            )
            db.add(client)
            db.flush()
            return client, True

        if isinstance(workspace_case_id, int):
            workspace_case = (
                db.query(Case)
                .filter(
                    Case.id == workspace_case_id,
                    Case.tenant_id == tenant_id,
                    Case.deleted_at.is_(None),
                )
                .first()
            )
            if workspace_case:
                workspace_client = (
                    db.query(Client)
                    .filter(
                        Client.id == workspace_case.client_id,
                        Client.tenant_id == tenant_id,
                        Client.deleted_at.is_(None),
                    )
                    .first()
                )
                if workspace_client:
                    return workspace_client, False

        latest_client = (
            db.query(Client)
            .filter(
                Client.tenant_id == tenant_id,
                Client.deleted_at.is_(None),
            )
            .order_by(Client.created_at.desc(), Client.id.desc())
            .first()
        )
        if latest_client:
            return latest_client, False
        return None, False

    def _create_client_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_role: str,
        requested_client_name: Optional[str],
        raw_message: str,
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="create_client")

        client_name = (requested_client_name or self._extract_client_name_from_message_fallback(raw_message=raw_message) or "").strip()
        if not client_name:
            return {
                "answer": "I can create a client, but I need the client name. Example: create client named Acme Logistics.",
                "used_fallback": True,
                "fallback_reason": "Missing client name",
                "confidence": "medium",
                "scope": "tenant",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"action": "create_client", "missing_fields": ["client_name"]},
            }

        existing_client = self._find_client_by_name(
            db=db,
            tenant_id=tenant_id,
            requested_client_name=client_name,
        )
        if existing_client:
            return {
                "answer": f"Client already exists: #{existing_client.id} {existing_client.name}.",
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "tenant",
                "sources": [],
                "action_status": "completed",
                "structured_result": {
                    "action": "create_client",
                    "created": False,
                    "client": {
                        "id": existing_client.id,
                        "name": existing_client.name,
                        "email": existing_client.email,
                        "phone": existing_client.phone,
                    },
                    "ui_triggers": [
                        {"type": "refresh_clients"},
                    ],
                },
            }

        client = Client(
            name=client_name[:160],
            tenant_id=tenant_id,
        )
        db.add(client)
        db.commit()
        db.refresh(client)

        return {
            "answer": f"Created new client #{client.id}: {client.name}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "create_client",
                "created": True,
                "client": {
                    "id": client.id,
                    "name": client.name,
                    "email": client.email,
                    "phone": client.phone,
                },
                "ui_triggers": [
                    {"type": "refresh_clients"},
                ],
            },
        }

    def _create_case_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_id: Optional[int],
        user_role: str,
        requested_case_title: Optional[str],
        requested_case_description: Optional[str],
        requested_client_id: Optional[int],
        requested_client_name: Optional[str],
        requested_jurisdiction_country: Optional[str],
        workspace_case_id: Optional[int],
        raw_message: str,
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="create_case")

        if not user_id:
            return {
                "answer": "I could not resolve the current user for case assignment.",
                "used_fallback": True,
                "fallback_reason": "Missing user id",
                "confidence": "low",
                "scope": "tenant",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"action": "create_case"},
            }

        case_title = (requested_case_title or "").strip()
        if not case_title:
            case_title = f"New legal matter {re.sub(r'[^0-9]', '', str(user_id)) or 'case'}"
        case_title = case_title[:200]

        client, client_created = self._resolve_case_creation_client(
            db=db,
            tenant_id=tenant_id,
            requested_client_id=requested_client_id,
            requested_client_name=requested_client_name,
            workspace_case_id=workspace_case_id,
        )
        if not client:
            return {
                "answer": "I could not resolve a client for the new case. Include a client name, for example: create case called Payment Dispute for client Atlas.",
                "used_fallback": True,
                "fallback_reason": "Missing client context",
                "confidence": "medium",
                "scope": "tenant",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"action": "create_case", "missing_fields": ["client"]},
            }

        case_description = (requested_case_description or "").strip()
        if case_description == "__AUTO_DESCRIPTION__":
            case_description = self._build_default_case_description(case_title=case_title, raw_message=raw_message)
        if not case_description:
            case_description = self._build_default_case_description(case_title=case_title, raw_message=raw_message)
        case_description = case_description[:4000]

        jurisdiction_country = "germany" if str(requested_jurisdiction_country or "").strip().lower() == "germany" else "tunisia"

        new_case = Case(
            title=case_title,
            description=case_description,
            status="open",
            jurisdiction_country=jurisdiction_country,
            tenant_id=tenant_id,
            lawyer_id=user_id,
            client_id=client.id,
        )
        db.add(new_case)
        db.commit()
        db.refresh(new_case)

        return {
            "answer": (
                f"Created case #{new_case.id}: {new_case.title} for client {client.name}. "
                f"Jurisdiction: {new_case.jurisdiction_country}. Status: {new_case.status}."
            ),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "create_case",
                "case": {
                    "id": new_case.id,
                    "title": new_case.title,
                    "status": new_case.status,
                    "jurisdiction_country": new_case.jurisdiction_country,
                    "client_id": new_case.client_id,
                },
                "client": {
                    "id": client.id,
                    "name": client.name,
                    "created": client_created,
                },
                "ui_triggers": [
                    {"type": "refresh_cases"},
                    {"type": "refresh_clients"},
                    {"type": "select_case", "case_id": new_case.id},
                ],
            },
        }

    def _request_document_upload_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Dict[str, Any]:
        case: Optional[Case] = None
        if case_id is not None:
            case = (
                db.query(Case)
                .filter(
                    Case.id == case_id,
                    Case.tenant_id == tenant_id,
                    Case.deleted_at.is_(None),
                )
                .first()
            )

        if case:
            answer = f"Ready to upload a document for case #{case.id} ({case.title})."
        else:
            answer = "Ready to upload a document. Select a case if you want it linked automatically."

        return {
            "answer": answer,
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "global" if case is None else "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "request_document_upload",
                "case_id": case.id if case else None,
                "ui_triggers": [
                    {
                        "type": "open_upload",
                        "target": "document",
                        "case_id": case.id if case else None,
                    }
                ],
            },
        }

    def _request_audio_upload_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Dict[str, Any]:
        case: Optional[Case] = None
        if case_id is not None:
            case = (
                db.query(Case)
                .filter(
                    Case.id == case_id,
                    Case.tenant_id == tenant_id,
                    Case.deleted_at.is_(None),
                )
                .first()
            )

        if case:
            answer = f"Ready to upload an audio note for case #{case.id} ({case.title})."
        else:
            answer = "Ready to upload an audio note. Select a case first for better routing."

        return {
            "answer": answer,
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "global" if case is None else "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "request_audio_upload",
                "case_id": case.id if case else None,
                "ui_triggers": [
                    {
                        "type": "open_upload",
                        "target": "audio",
                        "case_id": case.id if case else None,
                    }
                ],
            },
        }

    def _list_cases(
        self,
        *,
        db: Session,
        tenant_id: int,
        allowed_case_ids: set[int] | None = None,
    ) -> Dict[str, Any]:
        query = (
            db.query(Case)
            .filter(
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None),
            )
            .order_by(Case.updated_at.desc(), Case.id.desc())
        )
        if allowed_case_ids is not None:
            if not allowed_case_ids:
                return {
                    "answer": "No cases are currently linked to your portal account.",
                    "used_fallback": True,
                    "fallback_reason": "No accessible cases found",
                    "confidence": "medium",
                    "scope": "tenant",
                    "sources": [],
                    "structured_result": {"cases": []},
                }
            query = query.filter(Case.id.in_(sorted(allowed_case_ids)))

        rows = query.limit(40).all()

        if not rows:
            return {
                "answer": "No cases were found in your workspace.",
                "used_fallback": True,
                "fallback_reason": "No cases found",
                "confidence": "medium",
                "scope": "tenant",
                "sources": [],
                "structured_result": {"cases": []},
            }

        lines = ["Cases in your workspace:"]
        for row in rows[:12]:
            lines.append(
                f"- Case #{row.id}: {row.title} | status: {row.status} | jurisdiction: {row.jurisdiction_country}"
            )

        return {
            "answer": "\n".join(lines),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "structured_result": {
                "cases": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "status": row.status,
                        "jurisdiction_country": row.jurisdiction_country,
                        "updated_at": self._safe_isoformat(row.updated_at),
                    }
                    for row in rows[:12]
                ]
            },
        }

    def _list_clients(self, *, db: Session, tenant_id: int) -> Dict[str, Any]:
        rows = (
            db.query(Client)
            .filter(
                Client.tenant_id == tenant_id,
                Client.deleted_at.is_(None),
            )
            .order_by(Client.created_at.desc(), Client.id.desc())
            .limit(60)
            .all()
        )
        if not rows:
            return {
                "answer": "No clients were found in your workspace.",
                "used_fallback": True,
                "fallback_reason": "No clients found",
                "confidence": "medium",
                "scope": "tenant",
                "sources": [],
                "structured_result": {"clients": []},
            }

        lines = ["Clients in your workspace:"]
        for row in rows[:15]:
            email = row.email or "no-email"
            lines.append(f"- Client #{row.id}: {row.name} | {email}")

        return {
            "answer": "\n".join(lines),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "structured_result": {
                "clients": [
                    {
                        "id": row.id,
                        "name": row.name,
                        "email": row.email,
                        "phone": row.phone,
                    }
                    for row in rows[:15]
                ]
            },
        }

    def _list_prompt_library(self, *, db: Session, tenant_id: int) -> Dict[str, Any]:
        rows = (
            db.query(PromptLibraryEntry)
            .filter(PromptLibraryEntry.tenant_id == tenant_id)
            .order_by(
                PromptLibraryEntry.is_favorite.desc(),
                PromptLibraryEntry.updated_at.desc(),
                PromptLibraryEntry.id.desc(),
            )
            .limit(80)
            .all()
        )

        if not rows:
            return {
                "answer": "No prompt library entries were found in your workspace.",
                "used_fallback": True,
                "fallback_reason": "No prompt library entries found",
                "confidence": "medium",
                "scope": "tenant",
                "sources": [],
                "structured_result": {"entries": []},
            }

        lines = ["Prompt library entries:"]
        for row in rows[:20]:
            favorite_marker = "[favorite]" if bool(row.is_favorite) else ""
            category = row.category or "uncategorized"
            lines.append(f"- Prompt #{row.id}: {row.title} | {category} {favorite_marker}".rstrip())

        return {
            "answer": "\n".join(lines),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "structured_result": {
                "entries": [
                    {
                        "id": row.id,
                        "title": row.title,
                        "category": row.category,
                        "description": row.description,
                        "is_favorite": row.is_favorite,
                        "updated_at": self._safe_isoformat(row.updated_at),
                    }
                    for row in rows[:20]
                ],
            },
        }

    def _get_client_or_404(self, *, db: Session, tenant_id: int, client_id: Optional[int]) -> Client:
        if client_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Client id could not be detected from the message.")

        client = (
            db.query(Client)
            .filter(
                Client.id == client_id,
                Client.tenant_id == tenant_id,
                Client.deleted_at.is_(None),
            )
            .first()
        )
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
        return client

    def _get_appointment_or_404(self, *, db: Session, tenant_id: int, appointment_id: Optional[int]) -> Appointment:
        if appointment_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Appointment id could not be detected from the message.")

        appointment = (
            db.query(Appointment)
            .options(
                selectinload(Appointment.case),
                selectinload(Appointment.client),
                selectinload(Appointment.lawyer),
                selectinload(Appointment.consultation_request),
            )
            .filter(
                Appointment.id == appointment_id,
                Appointment.tenant_id == tenant_id,
            )
            .first()
        )
        if not appointment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")
        return appointment

    def _get_prompt_library_entry_or_404(self, *, db: Session, tenant_id: int, entry_id: Optional[int]) -> PromptLibraryEntry:
        if entry_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt library entry id could not be detected from the message.")

        entry = (
            db.query(PromptLibraryEntry)
            .filter(
                PromptLibraryEntry.id == entry_id,
                PromptLibraryEntry.tenant_id == tenant_id,
            )
            .first()
        )
        if not entry:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt library entry not found.")
        return entry

    def _update_case_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        user_role: str,
        user_id: Optional[int],
        raw_message: str,
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="update_case")

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        assigned_lawyer_id = self._coerce_optional_int(case.lawyer_id)
        if user_role == "lawyer" and user_id and assigned_lawyer_id not in {None, user_id}:
            return {
                **self._permission_denied_response(user_role=user_role, action="update_case"),
                "answer": f"Permission denied: you can only update cases assigned to you. Case #{case.id} is assigned to another lawyer.",
            }

        message = str(raw_message or "")
        lowered = message.lower()
        requested_title = self._extract_field_value(message, ["case title", "title"], stop_labels=["description", "status", "client", "jurisdiction", "country"])
        requested_description = self._extract_field_value(message, ["description", "desc", "details"], stop_labels=["title", "status", "client", "jurisdiction", "country"])
        requested_status = self._extract_field_value(message, ["status"], stop_labels=["title", "description", "client", "jurisdiction", "country"])
        if requested_title is None:
            rename_case_match = re.search(
                r"\b(?:rename|retitle)\s+case(?:\s*#?\s*\d+)?\s+(?:to|as)\s+(.+?)(?:\b(?:description|status|client|jurisdiction|country)\b|$)",
                message,
                re.IGNORECASE,
            )
            if rename_case_match:
                requested_title = self._strip_extracted_value(rename_case_match.group(1))
        requested_client_name = self._extract_client_name_from_message_fallback(raw_message=message)
        requested_jurisdiction_country = None
        if any(keyword in lowered for keyword in ["germany", "deutschland", "german", "deutsch"]):
            requested_jurisdiction_country = "germany"
        elif any(keyword in lowered for keyword in ["tunisia", "tunisian", "tunisie", "tunis"]):
            requested_jurisdiction_country = "tunisia"

        requested_client_id = None
        client_match = re.search(r"\bclient\s*#?\s*(\d+)\b", message, re.IGNORECASE)
        if client_match:
            requested_client_id = int(client_match.group(1))

        if requested_title is None and requested_description is None and requested_status is None and requested_client_id is None and requested_client_name is None and requested_jurisdiction_country is None:
            return {
                "answer": f"I can update case #{case.id}, but I need at least one field such as title, description, status, client, or jurisdiction.",
                "used_fallback": True,
                "fallback_reason": "Missing update fields",
                "confidence": "medium",
                "scope": "case",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"action": "update_case", "case_id": case.id, "missing_fields": ["update_fields"]},
            }

        previous_state = {
            "title": case.title,
            "description": case.description,
            "status": case.status,
            "client_id": case.client_id,
            "jurisdiction_country": case.jurisdiction_country,
        }

        if requested_title:
            case.title = requested_title[:200]
        if requested_description:
            case.description = requested_description[:4000]
        if requested_status:
            normalized_status = self._normalize_status_value(requested_status)
            if normalized_status:
                case.status = normalized_status
        if requested_client_id is not None:
            client = self._get_client_or_404(db=db, tenant_id=tenant_id, client_id=requested_client_id)
            case.client_id = client.id
        elif requested_client_name:
            client = self._find_client_by_name(db=db, tenant_id=tenant_id, requested_client_name=requested_client_name)
            if client:
                case.client_id = client.id
        if requested_jurisdiction_country is not None:
            case.jurisdiction_country = requested_jurisdiction_country

        db.commit()
        db.refresh(case)

        return {
            "answer": f"Updated case #{case.id}: {case.title}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "update_case",
                "case": {
                    "id": case.id,
                    "title": case.title,
                    "status": case.status,
                    "client_id": case.client_id,
                    "jurisdiction_country": case.jurisdiction_country,
                    "previous": previous_state,
                },
                "ui_triggers": self._build_refresh_triggers("cases", "case_context"),
            },
        }

    def _delete_case_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        user_role: str,
        user_id: Optional[int],
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="delete_case")

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        assigned_lawyer_id = self._coerce_optional_int(case.lawyer_id)
        if user_role == "lawyer" and user_id and assigned_lawyer_id not in {None, user_id}:
            return {
                **self._permission_denied_response(user_role=user_role, action="delete_case"),
                "answer": f"Permission denied: you can only delete cases assigned to you. Case #{case.id} is assigned to another lawyer.",
            }

        case.deleted_at = func.now()
        db.commit()

        return {
            "answer": f"Archived case #{case.id}: {case.title}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "delete_case",
                "case": {"id": case.id, "title": case.title, "archived": True},
                "ui_triggers": self._build_refresh_triggers("cases", "clients", "case_context"),
            },
        }

    def _update_client_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        client_id: Optional[int],
        user_role: str,
        raw_message: str,
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="update_client")

        client = self._get_client_or_404(db=db, tenant_id=tenant_id, client_id=client_id)
        message = str(raw_message or "")
        email_match = re.search(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", message, re.IGNORECASE)
        requested_name = self._extract_field_value(message, ["client name", "name"], stop_labels=["email", "phone", "address"])
        requested_phone = self._extract_field_value(message, ["phone", "mobile", "telephone"], stop_labels=["name", "email", "address"])
        requested_address = self._extract_field_value(message, ["address"], stop_labels=["name", "email", "phone"])
        if requested_name is None:
            rename_client_match = re.search(
                r"\b(?:rename|retitle|change)\s+client(?:\s*#?\s*\d+)?\s+(?:name\s+)?(?:to|as)\s+(.+?)(?:\b(?:email|phone|mobile|telephone|address)\b|$)",
                message,
                re.IGNORECASE,
            )
            if rename_client_match:
                requested_name = self._strip_extracted_value(rename_client_match.group(1))

        if requested_name is None and email_match is None and requested_phone is None and requested_address is None:
            return {
                "answer": f"I can update client #{client.id}, but I need at least one field such as name, email, phone, or address.",
                "used_fallback": True,
                "fallback_reason": "Missing update fields",
                "confidence": "medium",
                "scope": "tenant",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"action": "update_client", "client_id": client.id, "missing_fields": ["update_fields"]},
            }

        previous_state = {
            "name": client.name,
            "email": client.email,
            "phone": client.phone,
            "address": client.address,
        }

        if requested_name:
            client.name = requested_name[:160]
        if email_match:
            client.email = email_match.group(0)[:255]
        if requested_phone:
            client.phone = requested_phone[:40]
        if requested_address:
            client.address = requested_address[:255]

        db.commit()
        db.refresh(client)

        return {
            "answer": f"Updated client #{client.id}: {client.name}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "update_client",
                "client": {
                    "id": client.id,
                    "name": client.name,
                    "email": client.email,
                    "phone": client.phone,
                    "address": client.address,
                    "previous": previous_state,
                },
                "ui_triggers": self._build_refresh_triggers("clients", "cases"),
            },
        }

    def _delete_client_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        client_id: Optional[int],
        user_role: str,
    ) -> Dict[str, Any]:
        if user_role != "admin":
            return self._permission_denied_response(user_role=user_role, action="delete_client")

        client = self._get_client_or_404(db=db, tenant_id=tenant_id, client_id=client_id)
        client.deleted_at = func.now()
        db.commit()

        return {
            "answer": f"Archived client #{client.id}: {client.name}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "delete_client",
                "client": {"id": client.id, "name": client.name, "archived": True},
                "ui_triggers": self._build_refresh_triggers("clients", "cases"),
            },
        }

    def _create_prompt_library_entry_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_role: str,
        raw_message: str,
    ) -> Dict[str, Any]:
        if user_role == "client":
            return self._permission_denied_response(user_role=user_role, action="create_prompt_library_entry")

        message = str(raw_message or "")
        title = self._extract_field_value(message, ["title", "prompt title", "prompt name", "template title"])
        prompt_text = self._extract_field_value(message, ["prompt text", "text", "prompt", "content", "body"], stop_labels=["title", "description", "category", "favorite"])
        description = self._extract_field_value(message, ["description", "desc"], stop_labels=["title", "text", "prompt", "category", "favorite"])
        category = self._extract_field_value(message, ["category", "tag", "folder"], stop_labels=["title", "text", "description", "favorite"])
        is_favorite = self._extract_boolean_value(message, ["favorite", "favourite", "star", "pin"])

        if not title:
            title = message[:120].strip() or "New prompt"
        if not prompt_text:
            prompt_text = message[:12000].strip()
        if not prompt_text:
            return {
                "answer": "I can create a prompt library entry, but I need the prompt text.",
                "used_fallback": True,
                "fallback_reason": "Missing prompt text",
                "confidence": "medium",
                "scope": "tenant",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"action": "create_prompt_library_entry", "missing_fields": ["prompt_text"]},
            }

        entry = PromptLibraryEntry(
            tenant_id=tenant_id,
            created_by_user_id=None,
            title=title[:120],
            prompt_text=prompt_text[:12000],
            description=description[:500] if description else None,
            category=category[:80] if category else None,
            is_favorite=bool(is_favorite) if is_favorite is not None else False,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        return {
            "answer": f"Created prompt library entry #{entry.id}: {entry.title}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "create_prompt_library_entry",
                "entry": {
                    "id": entry.id,
                    "title": entry.title,
                    "category": entry.category,
                    "is_favorite": entry.is_favorite,
                },
                "ui_triggers": self._build_refresh_triggers("prompt_library"),
            },
        }

    def _update_prompt_library_entry_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        entry_id: Optional[int],
        user_role: str,
        raw_message: str,
    ) -> Dict[str, Any]:
        if user_role == "client":
            return self._permission_denied_response(user_role=user_role, action="update_prompt_library_entry")

        entry = self._get_prompt_library_entry_or_404(db=db, tenant_id=tenant_id, entry_id=entry_id)
        message = str(raw_message or "")
        title = self._extract_field_value(message, ["title", "prompt title", "prompt name", "template title"], stop_labels=["text", "description", "category", "favorite"])
        prompt_text = self._extract_field_value(message, ["prompt text", "text", "prompt", "content", "body"], stop_labels=["title", "description", "category", "favorite"])
        description = self._extract_field_value(message, ["description", "desc"], stop_labels=["title", "text", "prompt", "category", "favorite"])
        category = self._extract_field_value(message, ["category", "tag", "folder"], stop_labels=["title", "text", "description", "favorite"])
        is_favorite = self._extract_boolean_value(message, ["favorite", "favourite", "star", "pin"])
        if title is None:
            rename_prompt_match = re.search(
                r"\b(?:rename|retitle)\s+(?:prompt(?:\s+library\s+entry)?|template)(?:\s*#?\s*\d+)?\s+(?:to|as)\s+(.+?)(?:\b(?:text|description|category|favorite|favourite|star|pin)\b|$)",
                message,
                re.IGNORECASE,
            )
            if rename_prompt_match:
                title = self._strip_extracted_value(rename_prompt_match.group(1))

        if title is None and prompt_text is None and description is None and category is None and is_favorite is None:
            return {
                "answer": f"I can update prompt library entry #{entry.id}, but I need at least one field to change.",
                "used_fallback": True,
                "fallback_reason": "Missing update fields",
                "confidence": "medium",
                "scope": "tenant",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"action": "update_prompt_library_entry", "entry_id": entry.id, "missing_fields": ["update_fields"]},
            }

        previous_state = {
            "title": entry.title,
            "prompt_text": entry.prompt_text,
            "description": entry.description,
            "category": entry.category,
            "is_favorite": entry.is_favorite,
        }

        if title:
            entry.title = title[:120]
        if prompt_text:
            entry.prompt_text = prompt_text[:12000]
        if description is not None:
            entry.description = description[:500]
        if category is not None:
            entry.category = category[:80]
        if is_favorite is not None:
            entry.is_favorite = bool(is_favorite)

        db.commit()
        db.refresh(entry)

        return {
            "answer": f"Updated prompt library entry #{entry.id}: {entry.title}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "update_prompt_library_entry",
                "entry": {
                    "id": entry.id,
                    "title": entry.title,
                    "category": entry.category,
                    "is_favorite": entry.is_favorite,
                    "previous": previous_state,
                },
                "ui_triggers": self._build_refresh_triggers("prompt_library"),
            },
        }

    def _delete_prompt_library_entry_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        entry_id: Optional[int],
        user_role: str,
    ) -> Dict[str, Any]:
        if user_role == "client":
            return self._permission_denied_response(user_role=user_role, action="delete_prompt_library_entry")

        entry = self._get_prompt_library_entry_or_404(db=db, tenant_id=tenant_id, entry_id=entry_id)
        db.delete(entry)
        db.commit()

        return {
            "answer": f"Deleted prompt library entry #{entry.id}: {entry.title}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "tenant",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "delete_prompt_library_entry",
                "entry": {"id": entry.id, "title": entry.title, "deleted": True},
                "ui_triggers": self._build_refresh_triggers("prompt_library"),
            },
        }

    def _update_case_appointment_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        appointment_id: Optional[int],
        user_role: str,
        user_id: Optional[int],
        raw_message: str,
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="update_case_appointment")

        appointment = self._get_appointment_or_404(db=db, tenant_id=tenant_id, appointment_id=appointment_id)
        if user_role == "lawyer" and user_id and appointment.lawyer_id not in {None, user_id}:
            return {
                **self._permission_denied_response(user_role=user_role, action="update_case_appointment"),
                "answer": f"Permission denied: you can only update your own calendar appointments. Appointment #{appointment.id} is assigned to another lawyer.",
            }

        message = str(raw_message or "")
        lowered = message.lower()
        requested_title = self._extract_field_value(message, ["title", "appointment title", "subject"], stop_labels=["description", "type", "visibility", "status", "date", "time", "duration", "location", "timezone", "notes"])
        requested_description = self._extract_field_value(message, ["description", "details"], stop_labels=["title", "type", "visibility", "status", "date", "time", "duration", "location", "timezone", "notes"])
        requested_location = self._extract_field_value(message, ["location", "place"], stop_labels=["title", "description", "type", "visibility", "status", "date", "time", "duration", "timezone", "notes"])
        requested_timezone = self._extract_field_value(message, ["timezone", "time zone"], stop_labels=["title", "description", "type", "visibility", "status", "date", "time", "duration", "location", "notes"])
        requested_notes = self._extract_field_value(message, ["notes", "note"], stop_labels=["title", "description", "type", "visibility", "status", "date", "time", "duration", "location", "timezone"])
        requested_type = self._extract_field_value(message, ["type", "appointment type"], stop_labels=["title", "description", "visibility", "status", "date", "time", "duration", "location", "timezone", "notes"])
        requested_scope = self._extract_field_value(message, ["scope", "visibility", "visibility scope"], stop_labels=["title", "description", "type", "status", "date", "time", "duration", "location", "timezone", "notes"])
        requested_status = self._extract_field_value(message, ["status"], stop_labels=["title", "description", "type", "visibility", "date", "time", "duration", "location", "timezone", "notes"])
        requested_duration = self._extract_field_value(message, ["duration", "minutes", "duration minutes"], stop_labels=["title", "description", "type", "visibility", "status", "date", "time", "location", "timezone", "notes"])
        requested_date = self._extract_field_value(message, ["scheduled at", "scheduled", "date", "time", "when", "reschedule to", "move to"], stop_labels=["title", "description", "type", "visibility", "status", "duration", "location", "timezone", "notes"])
        if requested_date is None:
            reschedule_match = re.search(
                r"\b(?:reschedule|move)\s+(?:appointment|consultation)(?:\s*#?\s*\d+)?\s+(?:to\s+)?(.+?)(?:\b(?:title|description|type|visibility|status|duration|location|timezone|notes)\b|$)",
                message,
                re.IGNORECASE,
            )
            if reschedule_match:
                requested_date = self._strip_extracted_value(reschedule_match.group(1))

        if requested_title is None and requested_description is None and requested_location is None and requested_timezone is None and requested_notes is None and requested_type is None and requested_scope is None and requested_status is None and requested_duration is None and requested_date is None:
            return {
                "answer": f"I can update appointment #{appointment.id}, but I need at least one field to change.",
                "used_fallback": True,
                "fallback_reason": "Missing update fields",
                "confidence": "medium",
                "scope": "case",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"action": "update_case_appointment", "appointment_id": appointment.id, "missing_fields": ["update_fields"]},
            }

        previous_state = serialize_appointment(appointment)

        if requested_title:
            appointment.title = requested_title[:240]
        if requested_description is not None:
            appointment.description = requested_description[:4000]
        if requested_type:
            appointment.appointment_type = normalize_appointment_type(requested_type)
        if requested_scope:
            appointment.visibility_scope = normalize_scope(requested_scope)
        if requested_status:
            appointment.status = normalize_status(requested_status)
        if requested_date:
            parsed_date = self._extract_datetime_value(requested_date) or self._extract_datetime_value(message)
            if parsed_date is not None:
                appointment.scheduled_at = parsed_date
        if requested_duration:
            duration_match = re.search(r"\d{1,4}", requested_duration)
            if duration_match:
                appointment.duration_minutes = max(5, min(24 * 60, int(duration_match.group(0))))
        if requested_location is not None:
            appointment.location = requested_location[:240]
        if requested_timezone is not None:
            appointment.timezone_name = (requested_timezone or "UTC").strip() or "UTC"
        if requested_notes is not None:
            appointment.notes = requested_notes[:4000]

        brief = build_ai_calendar_brief(case=appointment.case, appointment=appointment)
        appointment.ai_summary = brief["ai_summary"]
        appointment.ai_recommendation = brief["ai_recommendation"]
        appointment.ai_confidence = brief["ai_confidence"]
        appointment.ai_source = brief["ai_source"]

        db.commit()
        db.refresh(appointment)
        appointment = self._get_appointment_or_404(db=db, tenant_id=tenant_id, appointment_id=appointment.id)

        return {
            "answer": f"Updated appointment #{appointment.id}: {appointment.title}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "update_case_appointment",
                "appointment": serialize_appointment(appointment),
                "previous": previous_state,
                "ui_triggers": self._build_refresh_triggers("case_context"),
            },
        }

    def _delete_case_appointment_action(
        self,
        *,
        db: Session,
        tenant_id: int,
        appointment_id: Optional[int],
        user_role: str,
        user_id: Optional[int],
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="delete_case_appointment")

        appointment = self._get_appointment_or_404(db=db, tenant_id=tenant_id, appointment_id=appointment_id)
        if user_role == "lawyer" and user_id and appointment.lawyer_id not in {None, user_id}:
            return {
                **self._permission_denied_response(user_role=user_role, action="delete_case_appointment"),
                "answer": f"Permission denied: you can only cancel your own calendar appointments. Appointment #{appointment.id} is assigned to another lawyer.",
            }

        appointment.status = normalize_status("cancelled")
        db.commit()
        db.refresh(appointment)
        appointment = self._get_appointment_or_404(db=db, tenant_id=tenant_id, appointment_id=appointment.id)

        return {
            "answer": f"Cancelled appointment #{appointment.id}: {appointment.title}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "action": "delete_case_appointment",
                "appointment": serialize_appointment(appointment),
                "ui_triggers": self._build_refresh_triggers("case_context"),
            },
        }

    def _list_case_documents(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        if not documents:
            return {
                "answer": f"Case #{case.id} has no uploaded documents yet.",
                "used_fallback": True,
                "fallback_reason": "No documents in case",
                "confidence": "medium",
                "scope": "case",
                "sources": [],
                "structured_result": {"case_id": case.id, "documents": []},
            }

        lines = [f"Documents for case #{case.id} ({case.title}):"]
        for row in documents[:15]:
            lines.append(f"- Document #{row.id}: {row.filename} | status: {row.processing_status}")

        return {
            "answer": "\n".join(lines),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [
                self._build_source(
                    document=row,
                    snippet=(row.summary_short or row.summary or row.filename),
                )
                for row in documents[:10]
            ],
            "structured_result": {
                "case_id": case.id,
                "documents": [
                    {
                        "id": row.id,
                        "filename": row.filename,
                        "status": row.processing_status,
                        "upload_timestamp": self._safe_isoformat(row.upload_timestamp),
                    }
                    for row in documents[:15]
                ],
            },
        }

    def _list_case_appointments(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)
        if not consultations:
            return {
                "answer": f"Case #{case.id} has no consultation requests yet.",
                "used_fallback": True,
                "fallback_reason": "No appointments in case",
                "confidence": "medium",
                "scope": "case",
                "sources": [],
                "structured_result": {"case_id": case.id, "appointments": []},
            }

        lines = [f"Consultation requests for case #{case.id}:"]
        for row in consultations[:12]:
            lines.append(
                f"- Request #{row.id}: status={row.status}, urgency={row.urgency_level}, preferred schedule={row.preferred_schedule or 'not provided'}"
            )

        return {
            "answer": "\n".join(lines),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [],
            "structured_result": {
                "case_id": case.id,
                "appointments": [
                    {
                        "id": row.id,
                        "status": row.status,
                        "urgency_level": row.urgency_level,
                        "preferred_schedule": row.preferred_schedule,
                        "issue_summary": row.issue_summary,
                    }
                    for row in consultations[:12]
                ],
            },
        }

    def _create_case_appointment(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        user_role: str,
        message: str,
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="create_case_appointment")

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        cleaned_message = str(message or "").strip() or f"Appointment requested for case #{case.id}."
        preferred_schedule = None
        schedule_match = re.search(r"(?:on|at|for)\s+(.+)$", cleaned_message, re.IGNORECASE)
        if schedule_match:
            preferred_schedule = schedule_match.group(1).strip()[:240]

        consultation = ConsultationRequest(
            case_id=case.id,
            tenant_id=tenant_id,
            booking_intent="requested",
            urgency_level="normal",
            preferred_schedule=preferred_schedule,
            issue_summary=cleaned_message[:900],
            extracted_case_description=cleaned_message[:1500],
            intake_notes="Created through copilot agent mode action.",
            status="submitted",
            extraction_source="copilot_agent_mode",
            source_channel="internal_agent",
        )
        db.add(consultation)
        db.commit()
        db.refresh(consultation)

        return {
            "answer": (
                f"Created consultation request #{consultation.id} for case #{case.id}."
                f" Preferred schedule: {consultation.preferred_schedule or 'not provided'}."
            ),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "appointment": {
                    "id": consultation.id,
                    "status": consultation.status,
                    "preferred_schedule": consultation.preferred_schedule,
                    "issue_summary": consultation.issue_summary,
                }
            },
        }

    def _update_case_status(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        user_role: str,
        user_id: Optional[int],
        requested_status: Optional[str],
    ) -> Dict[str, Any]:
        if user_role not in self.CASE_WRITE_ROLES:
            return self._permission_denied_response(user_role=user_role, action="update_case_status")

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        assigned_lawyer_id = self._coerce_optional_int(case.lawyer_id)
        if user_role == "lawyer" and user_id and assigned_lawyer_id not in {None, user_id}:
            return {
                **self._permission_denied_response(user_role=user_role, action="update_case_status"),
                "answer": f"Permission denied: you can only update cases assigned to you. Case #{case.id} is assigned to another lawyer.",
            }

        normalized_status = self._normalize_status_value(requested_status)
        if not normalized_status:
            return {
                "answer": "I could not determine the target status. Use one of: open, in progress, closed, archived.",
                "used_fallback": True,
                "fallback_reason": "Missing status value",
                "confidence": "medium",
                "scope": "case",
                "sources": [],
                "action_status": "failed",
                "structured_result": {"allowed_statuses": ["open", "in_progress", "closed", "archived"]},
            }

        previous_status = str(case.status or "")
        case.status = normalized_status
        db.commit()
        db.refresh(case)

        return {
            "answer": f"Updated case #{case.id} status from {previous_status or 'unknown'} to {case.status}.",
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high",
            "scope": "case",
            "sources": [],
            "action_status": "completed",
            "structured_result": {
                "case": {
                    "id": case.id,
                    "title": case.title,
                    "previous_status": previous_status,
                    "new_status": case.status,
                }
            },
        }

    def _optimize_prompt_intent(
        self,
        *,
        raw_prompt: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
    ) -> Dict[str, Any]:
        optimized = prompt_optimizer_agent.optimize_query(
            raw_query=raw_prompt,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
            allow_llm=True,
        )

        optimized_query = (
            optimized.payload.get("optimized_query")
            if optimized.success
            else raw_prompt
        )
        notes = optimized.payload.get("notes") if optimized.success else None

        answer_lines = [f"Optimized prompt: {optimized_query or raw_prompt}"]
        if notes:
            answer_lines.append("")
            answer_lines.append(f"Notes: {notes}")

        return {
            "answer": "\n".join(answer_lines).strip(),
            "used_fallback": not bool(optimized.payload.get("used_llm")) if optimized.success else True,
            "fallback_reason": None if optimized.success else (optimized.error or "Prompt optimization failed"),
            "confidence": "high" if optimized.success and optimized.payload.get("used_llm") else "medium" if optimized.success else "low",
            "scope": "global",
            "sources": [],
        }

    @staticmethod
    def _optimize_prompt_for_query(
        *,
        question: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
        allow_llm: bool = False,
    ) -> str:
        optimized = prompt_optimizer_agent.optimize_query(
            raw_query=question,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
            allow_llm=allow_llm,
        )
        candidate = optimized.payload.get("optimized_query") if optimized.success else ""
        return str(candidate or question).strip()

    @staticmethod
    def _coerce_unit_score(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if parsed > 1.0:
            parsed = parsed / 100.0
        return max(0.0, min(parsed, 1.0))

    @staticmethod
    def _parse_high_reasoning_allowlist(raw_allowlist: str | None) -> set[int]:
        if not raw_allowlist:
            return set()
        values: set[int] = set()
        for token in str(raw_allowlist).replace(";", ",").split(","):
            normalized = token.strip()
            if not normalized:
                continue
            if normalized.isdigit():
                values.add(int(normalized))
        return values

    @staticmethod
    def _stable_rollout_bucket(*, tenant_id: int, salt: str) -> int:
        digest = hashlib.sha256(f"{salt}:{tenant_id}".encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 100

    def _is_high_reasoning_rollout_eligible(self, *, tenant_id: int | None) -> tuple[bool, str, int | None]:
        allowlist = self._parse_high_reasoning_allowlist(settings.HIGH_REASONING_TENANT_ALLOWLIST)
        rollout_percentage = int(settings.HIGH_REASONING_ROLLOUT_PERCENTAGE or 0)
        rollout_percentage = max(0, min(rollout_percentage, 100))

        if tenant_id is None:
            if rollout_percentage >= 100 and not allowlist:
                return True, "global_full_rollout", None
            return False, "tenant_id_missing", None

        if tenant_id in allowlist:
            return True, "allowlist", None

        if rollout_percentage <= 0:
            return False, "rollout_percentage_zero", None
        if rollout_percentage >= 100:
            return True, "rollout_percentage_full", None

        salt = str(settings.HIGH_REASONING_ROLLOUT_SALT or "legal-ai-high-reasoning-v1").strip() or "legal-ai-high-reasoning-v1"
        bucket = self._stable_rollout_bucket(tenant_id=tenant_id, salt=salt)
        return bucket < rollout_percentage, "rollout_percentage", bucket

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {}
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            payload = json.loads(cleaned)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return {}
            try:
                payload = json.loads(match.group(0))
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}

    @staticmethod
    def _build_high_reasoning_evidence_block(
        *,
        sources: list[dict[str, Any]],
        citations: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = []
        for citation in citations[:10]:
            label = str(citation.get("label") or "Source").strip()
            snippet = str(citation.get("snippet") or "").strip()
            if label and snippet:
                lines.append(f"- [{label}] {snippet[:260]}")

        if not lines:
            for source in sources[:10]:
                filename = str(source.get("filename") or "Source").strip()
                chunk_index = source.get("chunk_index")
                snippet = str(source.get("snippet") or source.get("chunk_text") or "").strip()
                label = f"{filename} - chunk {chunk_index}" if chunk_index is not None else filename
                if snippet:
                    lines.append(f"- [{label}] {snippet[:260]}")

        return "\n".join(lines)

    def _generate_high_reasoning_candidate(
        self,
        *,
        question: str,
        base_answer: str,
        style_name: str,
        style_instruction: str,
        evidence_block: str,
        timeout_seconds: float,
    ) -> str:
        if not self.client:
            return ""

        prompt = f"""
You are a legal AI assistant generating one grounded candidate answer.

Style profile: {style_name}
Style instruction: {style_instruction}

Rules:
1) Use only evidence listed below.
2) Do not invent facts.
3) If evidence is missing, say so explicitly.
4) Keep legal precision and practical usefulness.
5) Include citation labels inline where relevant, e.g. [filename - chunk X].

Question:
{question}

Existing grounded baseline answer:
{base_answer}

Evidence:
{evidence_block}
""".strip()

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            timeout=max(1.0, timeout_seconds),
        )
        return llm_gateway.extract_output_text(response).strip()

    def _judge_high_reasoning_candidates(
        self,
        *,
        question: str,
        candidates: list[dict[str, Any]],
        evidence_block: str,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if not self.client:
            return {}

        candidates_block = "\n\n".join(
            f"Candidate {item['index']} ({item['style']}):\n{item['answer']}"
            for item in candidates
        )
        judge_prompt = f"""
You are a legal quality judge. Score each candidate against this rubric from 0 to 1:
- grounding_score
- citation_score
- factual_consistency_score
- legal_usefulness_score
- actionability_score
- clarity_score

Critical ranking rule:
Grounding, factual consistency, and citation quality must dominate fluency/style.

Compute overall_score with priority weighting:
overall_score =
  0.30*grounding_score +
  0.25*factual_consistency_score +
  0.20*citation_score +
  0.10*legal_usefulness_score +
  0.10*actionability_score +
  0.05*clarity_score

Question:
{question}

Evidence:
{evidence_block}

Candidates:
{candidates_block}

Return JSON only with this schema:
{{
  "winner_index": 0,
  "decision_reason": "...",
  "scores": [
    {{
      "index": 0,
      "grounding_score": 0.0,
      "citation_score": 0.0,
      "factual_consistency_score": 0.0,
      "legal_usefulness_score": 0.0,
      "actionability_score": 0.0,
      "clarity_score": 0.0,
      "overall_score": 0.0,
      "decision_reason": "..."
    }}
  ]
}}
""".strip()

        response = self.client.responses.create(
            model=self.model,
            input=judge_prompt,
            timeout=max(1.0, timeout_seconds),
        )
        return self._extract_json_object(llm_gateway.extract_output_text(response))

    def _finalize_reasoning_payload(
        self,
        *,
        payload: Dict[str, Any],
        reasoning_level: str,
        intent: str | None,
        question: str,
        tenant_id: int | None = None,
    ) -> Dict[str, Any]:
        normalized_level = self._normalize_reasoning_level(reasoning_level)
        if normalized_level != "high":
            return payload

        fallback_payload = dict(payload)
        if not settings.ENABLE_HIGH_REASONING_MULTI_ANSWER:
            fallback_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": "high_reasoning_disabled",
                "candidates": [],
            }
            return fallback_payload

        rollout_eligible, rollout_reason, rollout_bucket = self._is_high_reasoning_rollout_eligible(tenant_id=tenant_id)
        if not rollout_eligible:
            fallback_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": "high_reasoning_rollout_denied",
                "rollout_reason": rollout_reason,
                "rollout_bucket": rollout_bucket,
                "candidates": [],
            }
            return fallback_payload

        if str(intent or "") not in self.HIGH_REASONING_ELIGIBLE_INTENTS:
            fallback_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": "intent_not_eligible",
                "candidates": [],
            }
            return fallback_payload

        start = time.perf_counter()
        timeout_ms = max(1000, int(settings.HIGH_REASONING_TIMEOUT_MS or 12000))
        max_candidates = max(2, min(int(settings.HIGH_REASONING_MAX_CANDIDATES or 3), 3))
        sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
        evidence_block = self._build_high_reasoning_evidence_block(sources=sources, citations=citations)
        base_answer = str(payload.get("answer") or "").strip()

        if not base_answer or not evidence_block or not self.client:
            fallback_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": "insufficient_evidence_or_provider",
                "candidates": [],
            }
            return fallback_payload

        try:
            candidates: list[dict[str, Any]] = []
            for index, (style_name, style_instruction) in enumerate(self.HIGH_REASONING_STYLES[:max_candidates]):
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                remaining_ms = timeout_ms - elapsed_ms
                if remaining_ms <= 350:
                    raise TimeoutError("high_reasoning_timeout")

                candidate_answer = self._generate_high_reasoning_candidate(
                    question=question,
                    base_answer=base_answer,
                    style_name=style_name,
                    style_instruction=style_instruction,
                    evidence_block=evidence_block,
                    timeout_seconds=remaining_ms / 1000.0,
                )
                if not candidate_answer:
                    raise RuntimeError("high_reasoning_candidate_empty")

                candidates.append(
                    {
                        "index": index,
                        "style": style_name,
                        "answer": candidate_answer,
                    }
                )

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            remaining_ms = timeout_ms - elapsed_ms
            if remaining_ms <= 350:
                raise TimeoutError("high_reasoning_timeout")

            judge_payload = self._judge_high_reasoning_candidates(
                question=question,
                candidates=candidates,
                evidence_block=evidence_block,
                timeout_seconds=remaining_ms / 1000.0,
            )

            score_by_index: dict[int, dict[str, Any]] = {}
            for item in (judge_payload.get("scores") if isinstance(judge_payload, dict) else []) or []:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item.get("index"))
                except (TypeError, ValueError):
                    continue
                grounding = self._coerce_unit_score(item.get("grounding_score"))
                citation = self._coerce_unit_score(item.get("citation_score"))
                factual = self._coerce_unit_score(item.get("factual_consistency_score"))
                legal_usefulness = self._coerce_unit_score(item.get("legal_usefulness_score"))
                actionability = self._coerce_unit_score(item.get("actionability_score"))
                clarity = self._coerce_unit_score(item.get("clarity_score"))
                weighted_overall = (
                    0.30 * grounding
                    + 0.25 * factual
                    + 0.20 * citation
                    + 0.10 * legal_usefulness
                    + 0.10 * actionability
                    + 0.05 * clarity
                )
                score_by_index[idx] = {
                    "grounding_score": grounding,
                    "citation_score": citation,
                    "factual_consistency_score": factual,
                    "legal_usefulness_score": legal_usefulness,
                    "actionability_score": actionability,
                    "clarity_score": clarity,
                    "overall_score": max(
                        weighted_overall,
                        self._coerce_unit_score(item.get("overall_score")),
                    ),
                    "decision_reason": str(item.get("decision_reason") or "").strip(),
                }

            ranked_candidates: list[dict[str, Any]] = []
            for item in candidates:
                score = score_by_index.get(item["index"]) or {
                    "grounding_score": 0.0,
                    "citation_score": 0.0,
                    "factual_consistency_score": 0.0,
                    "legal_usefulness_score": 0.0,
                    "actionability_score": 0.0,
                    "clarity_score": 0.0,
                    "overall_score": 0.0,
                    "decision_reason": "Judge score unavailable.",
                }
                ranked_candidates.append(
                    {
                        "index": item["index"],
                        "style": item["style"],
                        "answer": item["answer"],
                        "score": score,
                    }
                )

            ranked_candidates.sort(key=lambda candidate: float(candidate["score"].get("overall_score", 0.0)), reverse=True)
            if not ranked_candidates:
                raise RuntimeError("high_reasoning_no_candidates")

            winner = ranked_candidates[0]
            second_best = ranked_candidates[1] if len(ranked_candidates) > 1 and settings.HIGH_REASONING_SHOW_TOP_2 else None
            winner_reason = str(judge_payload.get("decision_reason") or winner["score"].get("decision_reason") or "").strip()

            response_payload = dict(payload)
            response_payload["answer"] = winner["answer"]
            response_payload["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": True,
                "winner_index": int(winner["index"]),
                "second_best_index": int(second_best["index"]) if second_best else None,
                "winner_reason": winner_reason,
                "candidates": [
                    {
                        "rank": rank,
                        "style": candidate["style"],
                        "answer": candidate["answer"],
                        "score": candidate["score"],
                    }
                    for rank, candidate in enumerate(ranked_candidates, start=1)
                ],
            }

            if settings.HIGH_REASONING_LOG_SCORES:
                logger.info(
                    "high_reasoning_success intent=%s winner=%s second=%s latency_ms=%s scores=%s",
                    intent,
                    winner["index"],
                    second_best["index"] if second_best else None,
                    int((time.perf_counter() - start) * 1000),
                    [round(float(candidate["score"].get("overall_score", 0.0)), 4) for candidate in ranked_candidates],
                )

            return response_payload
        except Exception as exc:
            degraded = dict(payload)
            degraded["used_fallback"] = True
            degraded["fallback_reason"] = "high_reasoning_timeout_or_error"
            degraded["reasoning_result"] = {
                "reasoning_level": "high",
                "activated": False,
                "winner_reason": f"high_reasoning_failed: {exc}",
                "candidates": [],
            }
            if settings.HIGH_REASONING_LOG_SCORES:
                logger.warning("high_reasoning_fallback intent=%s reason=%s", intent, exc)
            return degraded

    def _answer_with_optional_external_research(
        self,
        *,
        db: Session,
        tenant_id: int,
        question: str,
        top_k: int,
        case_id: Optional[int],
        document_id: Optional[int],
        use_external_research: bool,
        reasoning_level: str,
        intent: str | None,
        target_type: str | None,
        target_id: int | None,
        already_optimized: bool = False,
    ) -> Dict[str, Any]:
        jurisdiction_context = self._resolve_jurisdiction_context(
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
        )
        jurisdiction_prompt_block = (
            jurisdiction_context_service.get_prompt_block(jurisdiction_context.get("country_code"))
            if jurisdiction_context
            else ""
        )

        normalized_question = str(question or "").strip()
        if not normalized_question:
            return {
                "answer": "I could not find enough detail in the request to run retrieval.",
                "used_fallback": True,
                "fallback_reason": "empty_query",
                "confidence": "low",
                "scope": "global",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        if case_id is not None and self._looks_like_material_breach_clause_question(normalized_question):
            return self._answer_material_breach_clause_question(
                db=db,
                tenant_id=tenant_id,
                case_id=case_id,
                question=normalized_question,
                jurisdiction_context=jurisdiction_context,
            )

        optimized_question = (
            normalized_question
            if already_optimized
            else self._optimize_prompt_for_query(
                question=normalized_question,
                intent=intent,
                target_type=target_type,
                target_id=target_id,
                allow_llm=False,
            )
        )

        base_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            question=optimized_question,
            top_k=top_k,
            case_id=case_id,
            document_id=document_id,
        )

        if not use_external_research:
            return self._finalize_reasoning_payload(
                payload={
                **base_result,
                "jurisdiction": jurisdiction_context,
                },
                reasoning_level=reasoning_level,
                intent=intent,
                question=normalized_question,
                tenant_id=tenant_id,
            )

        research = external_research_service.search(
            query=optimized_question,
            max_results=max(3, min(top_k, 8)),
        )
        if not research.get("used_external"):
            return self._finalize_reasoning_payload(
                payload={
                **base_result,
                "jurisdiction": jurisdiction_context,
                },
                reasoning_level=reasoning_level,
                intent=intent,
                question=normalized_question,
                tenant_id=tenant_id,
            )

        external_results = research.get("results") or []
        if not external_results:
            return self._finalize_reasoning_payload(
                payload={
                **base_result,
                "jurisdiction": jurisdiction_context,
                },
                reasoning_level=reasoning_level,
                intent=intent,
                question=normalized_question,
                tenant_id=tenant_id,
            )

        synthesized_answer = self._synthesize_answer_with_external_research(
            question=question,
            internal_answer=base_result.get("answer", ""),
            internal_sources=base_result.get("sources") or [],
            external_results=external_results,
            jurisdiction_prompt_block=jurisdiction_prompt_block,
        )
        if self._looks_like_prompt_template_noise(synthesized_answer):
            synthesized_answer = base_result.get("answer", "")

        merged_sources = list(base_result.get("sources") or [])
        merged_sources.extend(self._external_results_to_sources(external_results))
        merged_citations = list(base_result.get("citations") or [])
        merged_citations.extend(self._external_results_to_citations(external_results))

        return self._finalize_reasoning_payload(
            payload={
                "answer": synthesized_answer or base_result.get("answer", ""),
                "used_fallback": bool(base_result.get("used_fallback")),
                "fallback_reason": base_result.get("fallback_reason"),
                "confidence": base_result.get("confidence", "medium"),
                "scope": base_result.get("scope", "global"),
                "sources": merged_sources[:20],
                "citations": merged_citations[:12],
                "cache": base_result.get("cache", {"hit": False, "backend": "none"}),
                "jurisdiction": jurisdiction_context,
            },
            reasoning_level=reasoning_level,
            intent=intent,
            question=normalized_question,
            tenant_id=tenant_id,
        )

    def _answer_material_breach_clause_question(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int,
        question: str,
        jurisdiction_context: dict[str, Any] | None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet, so I cannot rank breach-supporting clauses.",
                "used_fallback": True,
                "fallback_reason": "No case documents found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "cache": {"hit": False, "backend": "none"},
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )
        evidence_result = evidence_strength_agent.evaluate_evidence_strength(
            case_id=case.id,
            case_title=case.title,
            objective=question,
            documents=documents,
            reasoning_payload=reasoning_payload,
        )
        evidence_payload = evidence_result.payload if evidence_result.success else {}

        clause_rows = self._build_material_breach_clause_rows(documents=documents)

        lines: List[str] = [f"Case #{case.id} strongest clauses supporting a material breach position:"]

        if clause_rows:
            top_clause_names = [self._normalize_text(row.get("clause")) for row in clause_rows[:3]]
            top_clause_names = [name for name in top_clause_names if name]
            if top_clause_names:
                lines.append("The clearest clause themes are " + ", ".join(top_clause_names) + ".")

        evidence_summary = self._normalize_text(evidence_payload.get("evidence_summary"))
        if evidence_summary:
            lines.extend(["", evidence_summary])

        if clause_rows:
            lines.extend(["", "Clause ranking:"])
            for row in clause_rows[:4]:
                clause = self._normalize_text(row.get("clause"))
                explanation = self._normalize_text(row.get("explanation"))
                supporting_documents = row.get("supporting_documents") or []
                source_text = ", ".join(
                    str(item).strip() for item in supporting_documents[:3] if str(item).strip()
                )

                if not clause:
                    continue

                line = f"- {clause}: {explanation or 'Relevant because it directly bears on breach, notice, or damages.'}"
                if source_text:
                    line += f" Sources: {source_text}."
                lines.append(line)
        else:
            lines.extend([
                "",
                "I found breach-related evidence, but not enough clause-level signals to rank specific clauses with confidence.",
            ])

        recommended_follow_up = evidence_payload.get("recommended_follow_up") or []
        follow_up = self._normalize_text(recommended_follow_up[0]) if recommended_follow_up else ""
        if not follow_up:
            follow_up = "If you want, I can trace the exact clause text next and map each clause to the supporting exhibit."

        lines.extend(["", "Next step:", f"- {follow_up}"])

        source_names: List[str] = []
        for row in clause_rows:
            for filename in row.get("supporting_documents") or []:
                name = str(filename or "").strip()
                if name and name not in source_names:
                    source_names.append(name)

        if not source_names:
            for item in evidence_payload.get("strongest_evidence") or []:
                name = str(item.get("filename") or "").strip()
                if name and name not in source_names:
                    source_names.append(name)

        sources: List[Dict[str, Any]] = []
        for document in documents:
            if document.filename not in source_names:
                continue
            snippet = self._normalize_text(document.summary_short or document.summary or "")
            if snippet:
                sources.append(self._build_source(document=document, snippet=snippet, score=1.0))
            if len(sources) >= 10:
                break

        used_llm = bool(evidence_result.payload.get("used_llm"))
        confidence = "high" if len(clause_rows) >= 3 else "medium" if clause_rows else str(evidence_payload.get("confidence") or "low")

        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used clause-ranking heuristic synthesis",
            "confidence": confidence,
            "scope": "case",
            "sources": sources,
            "cache": {"hit": False, "backend": "none"},
            "jurisdiction": jurisdiction_context,
            "structured_result": {
                "evidence_strength": evidence_payload,
                "clause_rows": clause_rows,
            },
        }

    def _build_material_breach_clause_rows(
        self,
        *,
        documents: List[Document],
    ) -> List[Dict[str, Any]]:
        clause_map: dict[str, dict[str, Any]] = {}

        def add_clause(clause: str, *, score: int, explanation: str, filename: str) -> None:
            row = clause_map.setdefault(
                clause,
                {
                    "clause": clause,
                    "score": 0,
                    "supporting_documents": [],
                    "reasons": [],
                },
            )
            row["score"] += score
            if filename and filename not in row["supporting_documents"]:
                row["supporting_documents"].append(filename)
            cleaned_reason = self._normalize_text(explanation)
            if cleaned_reason and cleaned_reason not in row["reasons"]:
                row["reasons"].append(cleaned_reason)

        for document in documents[:15]:
            filename = self._normalize_text(document.filename) or f"Document #{document.id}"
            insights = self._safe_load_insights(document)
            document_type = self._normalize_text(insights.get("document_type") or document.document_type).lower()
            general_summary = self._normalize_text(insights.get("general_summary") or document.summary_short or document.summary)
            key_points = " ".join(self._normalize_text(item) for item in insights.get("key_points") or [])
            payment_terms = " ".join(self._normalize_text(item) for item in insights.get("payment_terms") or [])
            termination_terms = " ".join(self._normalize_text(item) for item in insights.get("termination_terms") or [])
            legal_risks = " ".join(self._normalize_text(item) for item in insights.get("legal_risks") or [])
            combined_text = " ".join(
                [
                    filename,
                    document_type,
                    general_summary,
                    key_points,
                    payment_terms,
                    termination_terms,
                    legal_risks,
                ]
            ).lower()

            if any(token in combined_text for token in ["material breach", "cure period", "notice of breach", "breach notice", "terminate"]):
                add_clause(
                    "Notice, cure, and termination clause",
                    score=4 if document_type in {"master_service_agreement", "contract", "legal_letter"} else 3,
                    explanation="The record ties the dispute to notice, cure, and termination mechanics that usually control when breach becomes actionable.",
                    filename=filename,
                )

            if any(token in combined_text for token in ["sla", "service level", "kpi", "performance", "dashboard"]):
                add_clause(
                    "SLA / service-level obligations clause",
                    score=4 if document_type in {"master_service_agreement", "contract"} else 3,
                    explanation="The service-level and KPI materials show the contractual performance standard that the alleged breach is measured against.",
                    filename=filename,
                )

            if any(token in combined_text for token in ["invoice", "payment", "amount due", "reconciliation", "late payment", "net 30"]):
                add_clause(
                    "Payment obligation / invoice clause",
                    score=4 if document_type in {"invoice", "master_service_agreement", "contract"} else 3,
                    explanation="The payment and reconciliation materials show a concrete monetary obligation that can support breach and damages analysis.",
                    filename=filename,
                )

            if any(token in combined_text for token in ["response", "reservation of rights", "formal notice", "breach allegation"]):
                add_clause(
                    "Formal breach notice / response clause",
                    score=3,
                    explanation="The notice and response trail shows that the breach allegation was formally raised and contested.",
                    filename=filename,
                )

        ranked_rows = sorted(
            clause_map.values(),
            key=lambda row: (row["score"], len(row["supporting_documents"]), row["clause"].lower()),
            reverse=True,
        )

        formatted_rows: List[Dict[str, Any]] = []
        for row in ranked_rows[:4]:
            reasons = row.get("reasons") or []
            explanation = reasons[0] if reasons else "This clause is directly tied to the alleged breach theory."
            if len(reasons) > 1:
                explanation = f"{reasons[0]} {reasons[1]}"
            formatted_rows.append(
                {
                    "clause": row["clause"],
                    "explanation": explanation,
                    "supporting_documents": row.get("supporting_documents") or [],
                    "score": row.get("score", 0),
                }
            )

        return formatted_rows

    @staticmethod
    def _looks_like_prompt_template_noise(text: str) -> bool:
        candidate = str(text or "").strip().lower()
        if not candidate:
            return False

        noisy_fragments = (
            "<case_id>",
            "<document_id>",
            "optimize prompt:",
            "what success looks like",
            "email for case #<",
            "sources appea",
            "pdf_ready.md",
            "` - `",
        )
        if any(fragment in candidate for fragment in noisy_fragments):
            return True
        if "email for case #" in candidate and "optimize prompt" in candidate:
            return True
        return False

    @staticmethod
    def _looks_like_material_breach_clause_question(question: str) -> bool:
        lowered = str(question or "").lower()
        if not lowered:
            return False

        if any(keyword in lowered for keyword in CopilotService.MATERIAL_BREACH_QUERY_KEYWORDS):
            return True

        if "clause" in lowered and any(token in lowered for token in ["breach", "termination", "notice", "cure", "invoice", "sla"]):
            return True

        return False

    def _synthesize_answer_with_external_research(
        self,
        *,
        question: str,
        internal_answer: str,
        internal_sources: List[Dict[str, Any]],
        external_results: List[Dict[str, Any]],
        jurisdiction_prompt_block: str,
    ) -> str:
        if not self.client:
            return self._build_fallback_external_answer(
                internal_answer=internal_answer,
                external_results=external_results,
            )

        compact_internal_sources = internal_sources[:6]
        compact_external = external_results[:6]

        prompt = f"""
You are a legal AI copilot.
Synthesize one practical answer to the user's question using:
1) internal case/document evidence
2) external web research snippets

Rules:
- Prioritize internal evidence when there is conflict.
- Do not invent facts.
- Keep the answer concise and professional.
- End with a short "Web references" line listing up to 3 URLs.
- Respect the jurisdiction guardrails when applicable.

Jurisdiction context:
{jurisdiction_prompt_block or "No specific jurisdiction scope was provided."}

Question:
{question}

Internal grounded answer:
{internal_answer}

Internal sources (JSON):
{json.dumps(compact_internal_sources, ensure_ascii=False)}

External research snippets (JSON):
{json.dumps(compact_external, ensure_ascii=False)}
"""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            output = llm_gateway.extract_output_text(response).strip()
            if output:
                return output
        except Exception:
            pass

        return self._build_fallback_external_answer(
            internal_answer=internal_answer,
            external_results=external_results,
        )

    @staticmethod
    def _external_results_to_sources(external_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for item in external_results:
            title = str(item.get("title") or item.get("domain") or "Web Research").strip()
            url = str(item.get("url") or "").strip()
            snippet = str(item.get("snippet") or "").strip()

            source_text = snippet
            if url:
                source_text = f"{source_text} (source: {url})".strip()

            sources.append(
                {
                    "chunk_id": None,
                    "document_id": None,
                    "case_id": None,
                    "filename": title[:120] or "Web Research",
                    "chunk_index": None,
                    "score": 0.35,
                    "snippet": source_text[:300],
                }
            )
        return sources

    @staticmethod
    def _external_results_to_citations(external_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []
        for item in external_results[:6]:
            title = str(item.get("title") or item.get("domain") or "Web Research").strip()
            snippet = str(item.get("snippet") or "").strip()
            url = str(item.get("url") or "").strip()
            citations.append(
                {
                    "label": title[:120] or "Web Research",
                    "document_id": None,
                    "case_id": None,
                    "snippet": snippet[:280],
                    "url": url or None,
                }
            )
        return citations

    @staticmethod
    def _build_fallback_external_answer(*, internal_answer: str, external_results: List[Dict[str, Any]]) -> str:
        lines = [internal_answer.strip() or "No internal answer was generated."]
        lines.append("")
        lines.append("External web findings:")
        for item in external_results[:5]:
            title = str(item.get("title") or item.get("domain") or "Web Result").strip()
            snippet = str(item.get("snippet") or "").strip()
            url = str(item.get("url") or "").strip()
            combined = f"- {title}: {snippet}"
            if url:
                combined += f" ({url})"
            lines.append(combined[:360])
        return "\n".join(lines).strip()

    def _resolve_case_for_context(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> Optional[Case]:
        resolved_case_id = case_id
        if resolved_case_id is None and document_id is not None:
            document = (
                db.query(Document)
                .filter(
                    Document.id == document_id,
                    Document.tenant_id == tenant_id,
                )
                .first()
            )
            if document:
                resolved_case_id = document.case_id

        if resolved_case_id is None:
            return None

        return (
            db.query(Case)
            .filter(
                Case.id == resolved_case_id,
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None),
            )
            .first()
        )

    def _resolve_jurisdiction_context(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        case = self._resolve_case_for_context(
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
        )
        if not case:
            return None
        return jurisdiction_context_service.get_response_context(case.jurisdiction_country)

    def _build_artifact_context(
        self,
        *,
        db: Session,
        tenant_id: int,
        artifact_type: str,
        case_id: Optional[int] = None,
        document_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        rows = artifact_versioning_service.list_versions(
            db=db,
            tenant_id=tenant_id,
            artifact_type=artifact_type,  # type: ignore[arg-type]
            case_id=case_id,
            document_id=document_id,
        )
        version_payloads = [artifact_versioning_service.to_public_payload(row) for row in rows]
        selected = next((item for item in version_payloads if item.get("is_selected")), None)
        latest = selected or (version_payloads[-1] if version_payloads else None)

        return {
            "artifact_type": artifact_type,
            "case_id": latest.get("case_id") if latest else case_id,
            "document_id": latest.get("document_id") if latest else document_id,
            "selected_version_id": latest.get("id") if latest else None,
            "version_count": len(version_payloads),
            "latest_version": latest,
        }

    def _get_case_or_404(self, db: Session, tenant_id: int, case_id: Optional[int]) -> Case:
        if case_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Case id could not be detected from the message."
            )

        case = (
            db.query(Case)
            .filter(
                Case.id == case_id,
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None)
            )
            .first()
        )

        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found."
            )

        return case

    def _get_document_or_404(
        self,
        db: Session,
        tenant_id: int,
        document_id: Optional[int]
    ) -> Document:
        if document_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document id could not be detected from the message."
            )

        document = (
            db.query(Document)
            .filter(
                Document.id == document_id,
                Document.tenant_id == tenant_id
            )
            .first()
        )

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found."
            )

        return document

    def _get_case_documents(self, db: Session, tenant_id: int, case_id: int) -> List[Document]:
        return (
            db.query(Document)
            .filter(
                Document.case_id == case_id,
                Document.tenant_id == tenant_id
            )
            .order_by(Document.upload_timestamp.asc(), Document.id.asc())
            .all()
        )

    def _get_case_consultation_requests(
        self,
        db: Session,
        tenant_id: int,
        case_id: int
    ) -> List[ConsultationRequest]:
        return (
            db.query(ConsultationRequest)
            .filter(
                ConsultationRequest.case_id == case_id,
                ConsultationRequest.tenant_id == tenant_id
            )
            .order_by(ConsultationRequest.created_at.desc(), ConsultationRequest.id.desc())
            .all()
        )

    def _get_case_voice_recordings(
        self,
        db: Session,
        tenant_id: int,
        case_id: int
    ) -> List[VoiceRecording]:
        return (
            db.query(VoiceRecording)
            .filter(
                VoiceRecording.case_id == case_id,
                VoiceRecording.tenant_id == tenant_id
            )
            .order_by(VoiceRecording.created_at.desc(), VoiceRecording.id.desc())
            .all()
        )

    def _safe_load_insights(self, document: Document) -> Dict[str, Any]:
        insights_blob = self._text_or_empty(document.insights_json)
        if not insights_blob:
            return {}

        try:
            payload = json.loads(insights_blob)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _ensure_document_summary(self, db: Session, document: Document) -> Document:
        if self._text_or_empty(document.summary):
            return document

        if not (self._text_or_empty(document.redacted_text) or self._text_or_empty(document.extracted_text)):
            try:
                self.document_pipeline.process_document(document=document, db=db)
                db.refresh(document)
            except Exception:
                return document

        if not (self._text_or_empty(document.redacted_text) or self._text_or_empty(document.extracted_text)):
            return document

        try:
            return summarization_service.summarize_document(db=db, document=document)
        except Exception:
            return document

    def _document_summary_unavailable_reason(self, document: Document) -> str:
        processing_status = self._normalize_text(document.processing_status) or "unknown"
        summary_status = self._normalize_text(document.summary_status) or "not_started"
        processing_error = self._normalize_text(document.processing_error)
        summary_error = self._normalize_text(document.summary_error)

        notes: List[str] = []
        if processing_error:
            notes.append(f"processing error: {processing_error[:180]}")
        if summary_error:
            notes.append(f"summary error: {summary_error[:180]}")
        if not (self._text_or_empty(document.redacted_text) or self._text_or_empty(document.extracted_text)):
            notes.append("no extractable text detected")

        details = "; ".join(notes) if notes else "summary generation is pending"
        return (
            f"{document.filename} (processing={processing_status}, summary={summary_status}): {details}."
        )

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        return (value or "").strip()

    @staticmethod
    def _text_or_empty(value: Any) -> str:
        if value is None:
            return ""
        text = str(value)
        return "" if text.lower() == "none" else text.strip()

    @staticmethod
    def _coerce_optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_isoformat(value: Any) -> Optional[str]:
        if value is None:
            return None
        iso_method = getattr(value, "isoformat", None)
        if not callable(iso_method):
            return None
        try:
            return str(iso_method())
        except Exception:
            return None

    def _append_unique(self, items: List[str], value: Optional[str]) -> None:
        cleaned = self._normalize_text(value)
        if cleaned and cleaned not in items:
            items.append(cleaned)

    def _build_source(
        self,
        *,
        document: Document,
        snippet: str,
        score: float = 1.0
    ) -> Dict[str, Any]:
        return {
            "chunk_id": None,
            "document_id": document.id,
            "case_id": document.case_id,
            "filename": document.filename,
            "chunk_index": None,
            "score": score,
            "snippet": snippet[:300]
        }

    def _run_case_reasoning(
        self,
        *,
        db: Session,
        tenant_id: int,
        case: Case,
        documents: List[Document]
    ) -> Dict[str, Any]:
        agent_result = case_reasoning_agent.analyze_case(
            case=case,
            documents=documents,
            jurisdiction_country=case.jurisdiction_country,
            consultation_requests=self._get_case_consultation_requests(
                db=db,
                tenant_id=tenant_id,
                case_id=case.id
            ),
            voice_recordings=self._get_case_voice_recordings(
                db=db,
                tenant_id=tenant_id,
                case_id=case.id
            ),
        )

        if agent_result.success:
            return agent_result.payload

        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        return {
            "overview": f"Case {case.id} - {case.title}",
            "narrative_summary": f"Case {case.id} could not be fully synthesized by the case reasoning agent.",
            "main_issues": [],
            "key_dates": [],
            "legal_risks": [],
            "recommended_next_steps": [
                "Review the case documents manually.",
                "Regenerate case intelligence after more documents are processed.",
            ],
            "sources": [],
            "jurisdiction_country": jurisdiction_context.get("country_code"),
            "jurisdiction_display_name": jurisdiction_context.get("country_display_name"),
            "constitutional_references": jurisdiction_context.get("constitutional_references") or [],
            "used_llm": False,
        }

    @staticmethod
    def _format_case_reasoning_answer(reasoning_payload: Dict[str, Any]) -> str:
        sections: List[str] = []

        jurisdiction_name = (reasoning_payload.get("jurisdiction_display_name") or "").strip()
        constitutional_refs = reasoning_payload.get("constitutional_references") or []

        narrative_summary = (reasoning_payload.get("narrative_summary") or "").strip()
        if narrative_summary:
            sections.append(narrative_summary)
        else:
            overview = (reasoning_payload.get("overview") or "").strip()
            if overview:
                sections.append("Overview:")
                sections.append(overview)

        if jurisdiction_name:
            sections.append("")
            sections.append(f"Jurisdiction Lens: {jurisdiction_name}")
            if constitutional_refs:
                sections.append("Constitution references:")
                sections.extend(f"- {item}" for item in constitutional_refs[:2])

        sections.append("")
        sections.append("Main Issues:")
        main_issues = reasoning_payload.get("main_issues") or []
        if main_issues:
            sections.extend(f"- {item}" for item in main_issues[:8])
        else:
            sections.append("- No major issues were clearly extracted.")

        sections.append("")
        sections.append("Key Dates:")
        key_dates = reasoning_payload.get("key_dates") or []
        if key_dates:
            sections.extend(
                f"- {item['label']}: {item['value']}"
                for item in key_dates[:10]
                if item.get("label") and item.get("value")
            )
        else:
            sections.append("- No major dates were clearly detected.")

        sections.append("")
        sections.append("Legal Risks:")
        legal_risks = reasoning_payload.get("legal_risks") or []
        if legal_risks:
            sections.extend(f"- {item}" for item in legal_risks[:8])
        else:
            sections.append("- No major legal risks were clearly detected.")

        sections.append("")
        sections.append("Recommended Next Steps:")
        next_steps = reasoning_payload.get("recommended_next_steps") or []
        if next_steps:
            sections.extend(f"- {item}" for item in next_steps[:8])
        else:
            sections.append("- Review the case evidence manually.")

        return "\n".join(sections).strip()

    @staticmethod
    def _normalize_risk_items(items: List[str]) -> List[str]:
        normalized: List[str] = []
        for item in items:
            raw = str(item or "").strip()
            if not raw:
                continue
            if CopilotService._looks_like_prompt_template_noise(raw):
                continue

            split_candidate = re.sub(r"\s+(?=\d+[).]\s+)", "\n", raw)
            for fragment in split_candidate.splitlines():
                cleaned = fragment.strip().rstrip(".")
                if not cleaned:
                    continue
                cleaned = re.sub(r"^\d+[).]\s*", "", cleaned)
                if not cleaned:
                    continue
                if CopilotService._looks_like_prompt_template_noise(cleaned):
                    continue
                cleaned = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
                if cleaned not in normalized:
                    normalized.append(cleaned)
        return normalized

    @classmethod
    def _normalize_next_steps(cls, items: List[str]) -> List[str]:
        normalized: List[str] = []
        for item in items:
            cleaned = str(item or "").strip().rstrip(".")
            if not cleaned:
                continue
            if cls._looks_like_prompt_template_noise(cleaned):
                continue
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _normalize_contract_redline_objective(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return "Draft a practical contract redline with clause-level suggestions, fallback positions, and source documents."

        text = re.sub(r"^(draft|prepare|write|create)\s+(?:a\s+)?(?:contract\s+)?redline\s+(?:for|on|about)\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^(draft|prepare|write|create)\s+(?:a\s+)?(?:contract\s+)?redline\s*[:\-]?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^case\s*#?\s*\d+\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^for\s+case\s*#?\s*\d+\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^for\s+focused\s+on\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^focused\s+on\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+for\s+focused\s+on\s+", ", focused on ", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s+focused\s+on\s+", ", focused on ", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s+\s+", " ", text).strip(" ,.;:")

        if not text:
            return "Draft a practical contract redline with clause-level suggestions, fallback positions, and source documents."

        return text[0].upper() + text[1:] if text[0].islower() else text

    @staticmethod
    def _dedupe_ordered(items: List[str]) -> List[str]:
        deduped: List[str] = []
        seen: set[str] = set()
        for raw in items:
            value = str(raw or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(value)
        return deduped

    @classmethod
    def _extract_percentages(cls, text: str, *, max_items: int = 5) -> List[str]:
        matches = re.findall(r"\b\d{1,3}(?:\.\d+)?%", str(text or ""), flags=re.IGNORECASE)
        return cls._dedupe_ordered(matches)[:max_items]

    @classmethod
    def _extract_currency_amounts(cls, text: str, *, max_items: int = 5) -> List[str]:
        matches = re.findall(
            r"\b\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?\s*(?:tnd|usd|eur)\b",
            str(text or ""),
            flags=re.IGNORECASE,
        )
        return cls._dedupe_ordered(matches)[:max_items]

    @classmethod
    def _infer_document_kind(cls, *, filename: str, insights: Dict[str, Any]) -> str:
        lowered = filename.lower()
        if "master_service_agreement" in lowered or "msa" in lowered:
            return "Master Service Agreement"
        if "notice_of_breach" in lowered or "breach" in lowered:
            return "Notice of Breach"
        if "counterparty_response" in lowered or "response" in lowered:
            return "Counterparty Response"
        if "kpi" in lowered or "dashboard" in lowered:
            return "KPI Performance Extract"
        if "invoice" in lowered or "reconciliation" in lowered:
            return "Invoice Reconciliation"
        if "settlement" in lowered:
            return "Without-Prejudice Settlement Offer"
        if "memo" in lowered:
            return "Internal Legal Memo"
        if "transcript" in lowered or "call" in lowered:
            return "Call Transcript Summary"

        doc_type = cls._normalize_text(str(insights.get("document_type") or ""))
        if doc_type:
            normalized_doc_type = re.sub(r"[_\-]+", " ", doc_type).strip()
            if normalized_doc_type:
                styled_words: List[str] = []
                for word in normalized_doc_type.split():
                    lowered_word = word.lower()
                    if lowered_word in {"sla", "kpi", "msa"}:
                        styled_words.append(lowered_word.upper())
                    else:
                        styled_words.append(lowered_word.capitalize())
                return " ".join(styled_words)[:80]

        return "Case Document"

    @classmethod
    def _infer_document_impact_note(cls, *, filename: str, kind: str, text: str) -> str:
        lowered = (filename + " " + kind + " " + text).lower()
        if "agreement" in lowered or "msa" in lowered:
            return "Defines the contractual baseline: obligations, SLA thresholds, payment mechanics, and remedy triggers"
        if "notice" in lowered and "breach" in lowered:
            return "Frames breach allegations and triggers cure or escalation timelines"
        if "response" in lowered:
            return "Sets the counterparty defense and identifies contested allegations"
        if "kpi" in lowered or "performance" in lowered:
            return "Provides performance evidence used to support or challenge material-breach claims"
        if "invoice" in lowered or "reconciliation" in lowered:
            return "Quantifies disputed sums and supports damages or payment-position analysis"
        if "settlement" in lowered:
            return "Shows active negotiation posture while preserving formal legal rights"
        if "memo" in lowered:
            return "Captures internal risk framing and strategic legal posture"
        if "transcript" in lowered or "call" in lowered:
            return "Records statements and commitments that may affect liability or settlement leverage"
        return "Adds evidentiary context for disputed obligations, chronology, and party positions"

    def _build_case_document_resume_entry(self, *, position: int, document: Document, insights: Dict[str, Any]) -> str:
        filename = self._normalize_text(document.filename) or f"Document #{document.id}"
        kind = self._infer_document_kind(filename=filename, insights=insights)

        raw_summary = self._normalize_text(
            str(insights.get("general_summary") or "")
            or document.summary_short
            or document.summary
            or (document.redacted_text or document.extracted_text or "")[:700]
        )
        says = self._to_clean_summary_paragraph(
            raw_summary,
            fallback=f"{kind} captured in the case record.",
            max_sentences=1,
            max_chars=170,
        )
        says = re.sub(r"^\s*(this|the)\s+document\s+(?:is|contains|covers|presents)\s+", "", says, flags=re.IGNORECASE)
        says = says.rstrip(".")

        markers_source = " ".join(
            [
                raw_summary,
                self._normalize_text(document.summary),
                self._normalize_text(document.summary_short),
            ]
        )
        marker_parts: List[str] = []
        percentages = self._extract_percentages(markers_source, max_items=2)
        amounts = self._extract_currency_amounts(markers_source, max_items=2)
        if percentages:
            marker_parts.append("metrics " + ", ".join(percentages))
        if amounts:
            marker_parts.append("figures " + ", ".join(amounts))

        date_markers: List[str] = []
        for item in (insights.get("important_dates") or [])[:2]:
            label = self._normalize_text(str(item.get("label") or ""))
            value = self._normalize_text(str(item.get("value") or ""))
            if label and value:
                date_markers.append(f"{label} ({value})")
        if date_markers:
            marker_parts.append("dates " + "; ".join(date_markers[:2]))

        impact = self._infer_document_impact_note(
            filename=filename,
            kind=kind,
            text=" ".join([raw_summary, says]),
        )

        line = f"Document {position} ({filename}): {kind}. Says: {says}. Matters: {impact}."
        if marker_parts:
            line += " Key markers: " + "; ".join(marker_parts) + "."

        line = re.sub(r"\s+", " ", line).strip()
        if len(line) > 430:
            line = line[:430].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
        return line

    @staticmethod
    def _issue_signature_tokens(value: str) -> set[str]:
        tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "that",
            "this",
            "are",
            "was",
            "were",
            "into",
            "under",
            "case",
            "potential",
            "legal",
            "contractual",
            "service",
            "services",
        }
        return {token for token in tokens if len(token) > 2 and token not in stopwords}

    @classmethod
    def _is_redundant_issue_point(cls, candidate: str, existing_points: List[str]) -> bool:
        candidate_norm = str(candidate or "").strip().lower()
        if not candidate_norm:
            return False

        candidate_tokens = cls._issue_signature_tokens(candidate_norm)

        for existing in existing_points:
            existing_norm = str(existing or "").strip().lower()
            if not existing_norm:
                continue

            # Collapse near-duplicate breach labels (e.g., "SLA breaches" vs "material breaches of service levels").
            if (
                "breach" in candidate_norm
                and "breach" in existing_norm
                and any(token in candidate_norm for token in ["sla", "service level"])
                and any(token in existing_norm for token in ["sla", "service level"])
            ):
                return True

            if (
                candidate_norm == existing_norm
                or candidate_norm in existing_norm
                or existing_norm in candidate_norm
            ):
                return True

            existing_tokens = cls._issue_signature_tokens(existing_norm)
            if candidate_tokens and existing_tokens:
                overlap = len(candidate_tokens & existing_tokens)
                min_size = min(len(candidate_tokens), len(existing_tokens))
                if min_size > 0 and (overlap / min_size) >= 0.75:
                    return True

        return False

    @classmethod
    def _looks_contractual_signal(cls, value: str) -> bool:
        lowered = str(value or "").strip().lower()
        if not lowered:
            return False
        return any(token in lowered for token in cls.CONTRACTUAL_SIGNAL_KEYWORDS)

    @classmethod
    def _to_summary_bullet_sentence(cls, value: str, *, max_chars: int = 360) -> str:
        candidate = str(value or "").strip()
        if not candidate:
            return ""
        candidate = re.sub(r"^[-*\d\s\.)]+", "", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" .;:-")
        if not candidate:
            return ""
        candidate = candidate[0].upper() + candidate[1:] if candidate else candidate
        if len(candidate) > max_chars:
            candidate = candidate[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
        if candidate and candidate[-1] not in ".!?":
            candidate += "."
        return candidate

    def _append_case_summary_bullet(self, bullets: List[str], value: str) -> None:
        cleaned = self._to_summary_bullet_sentence(value)
        if not cleaned:
            return
        if self._looks_like_prompt_template_noise(cleaned):
            return
        if cleaned not in bullets:
            bullets.append(cleaned)

    def _build_contractual_context_bullets(
        self,
        *,
        summary_text: str,
        main_points: List[str],
        reasoning_sources: List[Dict[str, Any]],
    ) -> List[str]:
        snippets = [
            str(source.get("snippet") or "").strip().lower()
            for source in reasoning_sources
            if isinstance(source, dict)
        ]
        combined_text = " ".join(
            snippets
            + [str(summary_text or "").lower()]
            + [str(item or "").lower() for item in main_points]
        )

        bullets: List[str] = []
        if "sla" in combined_text or "service level" in combined_text:
            bullets.append("Contractual SLA obligations appear central to the dispute posture.")
        if any(token in combined_text for token in ["payment terms", "net 30", "late payment", "invoice"]):
            bullets.append("Payment obligations and invoice mechanics are explicitly contractual and actively disputed.")
        if any(token in combined_text for token in ["notice", "cure period", "formal notice"]):
            bullets.append("Notice and cure-period clauses likely govern whether escalation or termination rights are triggered.")
        if any(token in combined_text for token in ["liability cap", "liability"]):
            bullets.append("Liability exposure should be read through contractual cap language and any listed exceptions.")
        if any(token in combined_text for token in ["governing law", "dispute resolution", "arbitration", "mediation"]):
            bullets.append("Governing-law and dispute-resolution clauses shape the strongest forum and remedy options.")

        return bullets

    def _build_evidence_story_bullets(self, *, evidence_sources: List[str]) -> List[str]:
        lowered_sources = [str(name or "").strip().lower() for name in evidence_sources]
        bullets: List[str] = []

        if any("master_service_agreement" in name or "service_agreement" in name or "msa" in name for name in lowered_sources):
            bullets.append(
                "The Master Service Agreement sets the contractual baseline for service scope, SLA targets, payment mechanics, and cure or termination pathways."
            )
        if any("notice_of_breach" in name or "breach" in name for name in lowered_sources):
            bullets.append(
                "The breach notice formalizes underperformance allegations and opens a time-bound cure and escalation track."
            )
        if any("counterparty_response" in name or "response" in name for name in lowered_sources):
            bullets.append(
                "The counterparty response disputes breach framing and liability exposure, creating a contested fact record on performance and billing."
            )
        if any("kpi" in name or "dashboard" in name for name in lowered_sources):
            bullets.append(
                "KPI extracts provide trend evidence that can support or weaken material-breach arguments depending on methodology integrity."
            )
        if any("invoice" in name or "reconciliation" in name for name in lowered_sources):
            bullets.append(
                "Invoice reconciliation evidence is central for quantifying disputed sums, duplicate charges, and rate-cap compliance."
            )
        if any("settlement" in name for name in lowered_sources):
            bullets.append(
                "Without-prejudice settlement artifacts indicate active negotiation leverage while preserving litigation rights."
            )
        if any("transcript" in name or "call" in name for name in lowered_sources):
            bullets.append(
                "Call and meeting records add admissions, commitments, and unresolved points that shape negotiation credibility."
            )

        return bullets

    def _build_quantitative_anchor_bullet(
        self,
        *,
        summary_text: str,
        main_points: List[str],
        reasoning_sources: List[Dict[str, Any]],
    ) -> Optional[str]:
        snippets = [
            str(source.get("snippet") or "").strip()
            for source in reasoning_sources
            if isinstance(source, dict)
        ]
        combined_text = " ".join(
            [summary_text]
            + main_points
            + snippets
        )
        if not combined_text:
            return None

        percent_matches = re.findall(r"\b\d{1,3}(?:\.\d+)?%", combined_text, flags=re.IGNORECASE)

        amount_pattern = re.compile(
            r"\b\d{1,3}(?:[,\s]\d{3})*(?:\.\d+)?\s*(?:tnd|usd|eur)\b",
            re.IGNORECASE,
        )
        amount_candidates: List[tuple[str, int, int]] = []

        primary_finance_tokens = ["disputed", "claim", "claimed", "accepted", "invoice", "amount"]
        secondary_finance_tokens = ["payment", "fee", "charge", "surcharge", "credit", "rebate"]

        for match in amount_pattern.finditer(combined_text):
            value = match.group(0).strip()
            start, end = match.span()
            window = combined_text[max(0, start - 48) : min(len(combined_text), end + 48)].lower()
            score = 0
            if any(token in window for token in primary_finance_tokens):
                score += 2
            if any(token in window for token in secondary_finance_tokens):
                score += 1
            amount_candidates.append((value, score, start))

        default_currency = ""
        lowered_combined = combined_text.lower()
        for code in ["tnd", "usd", "eur"]:
            if code in lowered_combined:
                default_currency = code.upper()
                break

        bare_amount_pattern = re.compile(r"\b\d{1,3}(?:[,\s]\d{3})+(?:\.\d+)?\b")
        for match in bare_amount_pattern.finditer(combined_text):
            raw = match.group(0).strip()
            numeric = raw.replace(",", "").replace(" ", "")
            try:
                number_value = float(numeric)
            except ValueError:
                continue

            # Skip likely years and non-material low numbers.
            if 1900 <= number_value <= 2100 or number_value < 1000:
                continue

            start, end = match.span()
            left = combined_text[max(0, start - 1) : start]
            right = combined_text[end : min(len(combined_text), end + 3)]
            if "%" in left or "%" in right:
                continue

            window = combined_text[max(0, start - 48) : min(len(combined_text), end + 48)].lower()
            if not any(token in window for token in primary_finance_tokens + secondary_finance_tokens):
                continue

            normalized_value = raw + (f" {default_currency}" if default_currency else "")
            amount_candidates.append((normalized_value, 1, start))

        def _uniq(values: List[str]) -> List[str]:
            unique: List[str] = []
            seen: set[str] = set()
            for raw in values:
                item = str(raw or "").strip()
                if not item:
                    continue
                key = item.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(item)
            return unique

        def _ranked_unique_amounts(items: List[tuple[str, int, int]]) -> List[str]:
            unique: List[str] = []
            seen: set[str] = set()
            for value, _score, _index in sorted(items, key=lambda row: (-row[1], row[2])):
                cleaned = str(value or "").strip()
                if not cleaned:
                    continue
                key = cleaned.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(cleaned)
            return unique

        percentages = _uniq(percent_matches)[:4]
        amounts = _ranked_unique_amounts(amount_candidates)[:4]

        if not percentages and not amounts:
            return None

        if percentages and amounts:
            summary = (
                "Quantitative anchors include performance metrics "
                + ", ".join(percentages)
                + " and financial figures "
                + ", ".join(amounts)
            )
        elif percentages:
            summary = "Quantitative anchors include performance metrics " + ", ".join(percentages)
        else:
            summary = "Quantitative anchors include financial figures " + ", ".join(amounts)

        return summary + ", which should be tied to contractual thresholds and damages analysis."

    def _build_timeline_summary_bullet(self, *, key_dates: List[Dict[str, str]]) -> Optional[str]:
        anchors: List[str] = []
        for item in key_dates[:5]:
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if label and value:
                anchors.append(f"{label} ({value})")

        if len(anchors) < 2:
            return None

        return "Critical timeline markers are " + "; ".join(anchors) + "."

    def _build_issue_cluster_bullet(self, *, main_points: List[str]) -> Optional[str]:
        cleaned: List[str] = []
        for item in main_points:
            text = self._normalize_text(item).rstrip(".")
            if not text:
                continue
            if text not in cleaned:
                cleaned.append(text)
            if len(cleaned) >= 3:
                break

        if len(cleaned) < 2:
            return None

        return (
            "Core contested issues include "
            + "; ".join(cleaned)
            + ", and each should be mapped to specific clauses and source exhibits."
        )

    def _build_case_summary_bullets(
        self,
        *,
        summary_text: str,
        main_points: List[str],
        key_dates: List[Dict[str, str]],
        next_steps: List[str],
        evidence_sources: List[str],
        reasoning_sources: List[Dict[str, Any]],
        target_count: int,
        require_contractual_context: bool,
    ) -> List[str]:
        target = min(max(target_count or 8, 1), 12)
        bullets: List[str] = []

        self._append_case_summary_bullet(bullets, f"Case posture: {summary_text}")

        quantitative_bullet = self._build_quantitative_anchor_bullet(
            summary_text=summary_text,
            main_points=main_points,
            reasoning_sources=reasoning_sources,
        )
        if quantitative_bullet:
            self._append_case_summary_bullet(bullets, quantitative_bullet)

        timeline_summary = self._build_timeline_summary_bullet(key_dates=key_dates)
        if timeline_summary:
            self._append_case_summary_bullet(bullets, timeline_summary)

        issue_cluster_bullet = self._build_issue_cluster_bullet(main_points=main_points)
        if issue_cluster_bullet:
            self._append_case_summary_bullet(bullets, issue_cluster_bullet)

        if require_contractual_context:
            for item in self._build_contractual_context_bullets(
                summary_text=summary_text,
                main_points=main_points,
                reasoning_sources=reasoning_sources,
            ):
                self._append_case_summary_bullet(bullets, item)
                if len(bullets) >= target:
                    return bullets[:target]

        evidence_story_bullets = self._build_evidence_story_bullets(evidence_sources=evidence_sources)
        for item in evidence_story_bullets[:2]:
            self._append_case_summary_bullet(bullets, item)
            if len(bullets) >= target:
                return bullets[:target]

        for point in main_points:
            if len(bullets) >= target:
                break
            prefix = "Contractual issue" if require_contractual_context and self._looks_contractual_signal(point) else "Key issue"
            self._append_case_summary_bullet(
                bullets,
                f"{prefix}: {point}. This point should be backed by clause-level and exhibit-level references.",
            )

        for item in key_dates:
            if len(bullets) >= target:
                break
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if label and value:
                self._append_case_summary_bullet(
                    bullets,
                    f"Timeline anchor: {label} - {value}. This date should be linked to corresponding notice, cure, or invoice obligations.",
                )

        if len(bullets) < target and evidence_sources:
            self._append_case_summary_bullet(
                bullets,
                "Primary record set synthesized so far includes " + ", ".join(evidence_sources[:6]),
            )

        for step in next_steps:
            if len(bullets) >= target:
                break
            self._append_case_summary_bullet(
                bullets,
                f"Immediate legal step: {step}. Tie this action to specific deadlines and unresolved evidence points.",
            )

        if len(bullets) < target:
            self._append_case_summary_bullet(
                bullets,
                "Current summary confidence depends on processed evidence quality and will improve after full source verification and reconciliation.",
            )

        filler_index = 1
        while len(bullets) < target:
            self._append_case_summary_bullet(
                bullets,
                (
                    "Open validation track "
                    f"{filler_index}: reconcile KPI methodology, invoice support, and counterparty defenses against contractual thresholds"
                ),
            )
            filler_index += 1
            if filler_index > 20:
                break

        return bullets[:target]

    def _build_case_dispute_posture(
        self,
        *,
        evidence_sources: List[str],
        main_points: List[str],
        summary_text: str,
    ) -> List[str]:
        lowered_sources = [str(name or "").strip().lower() for name in evidence_sources]
        combined_points = " ".join([summary_text] + [str(item or "") for item in main_points]).lower()
        posture: List[str] = []

        if any("notice" in name for name in lowered_sources) and any("response" in name for name in lowered_sources):
            posture.append(
                "Both sides have exchanged formal position documents, indicating an active pre-escalation dispute record rather than an early-stage complaint."
            )
        if any("kpi" in name or "dashboard" in name for name in lowered_sources):
            posture.append(
                "Operational performance evidence appears central, so SLA methodology and source-log integrity will likely determine breach credibility."
            )
        if any("invoice" in name or "reconciliation" in name for name in lowered_sources):
            posture.append(
                "Financial exposure is tied to invoice line-item reconciliation, surcharge cap compliance, and proof for challenged charges."
            )
        if any("settlement" in name for name in lowered_sources):
            posture.append(
                "A settlement channel is already active, suggesting a dual-track strategy can preserve leverage while avoiding premature hard escalation."
            )
        if any("transcript" in name or "call" in name for name in lowered_sources):
            posture.append(
                "Call records may contain admissions or commitments that can materially affect negotiation narrative and evidentiary posture."
            )

        if not posture and any(token in combined_points for token in ["breach", "dispute", "invoice", "sla"]):
            posture.append(
                "The matter appears to combine operational-performance allegations with monetary disputes, requiring synchronized legal and quantitative analysis."
            )

        return posture[:4]

    def _build_case_overall_overview(
        self,
        *,
        summary_text: str,
        parties: List[str],
        evidence_sources: List[str],
        main_points: List[str],
    ) -> str:
        sentences: List[str] = []

        normalized_summary = self._normalize_text(summary_text).rstrip(".")
        if normalized_summary:
            sentences.append(normalized_summary)

        if len(parties) >= 2:
            sentences.append(f"Primary counterparties are {parties[0]} and {parties[1]}")

        core_points = [self._normalize_text(item).rstrip(".") for item in main_points[:2] if self._normalize_text(item)]
        if core_points:
            sentences.append("Core dispute focus: " + "; ".join(core_points))

        lowered_sources = [str(name or "").strip().lower() for name in evidence_sources]
        if any("notice" in name for name in lowered_sources) and any("response" in name for name in lowered_sources):
            sentences.append("The record includes both a formal breach notice and a counterparty response.")

        paragraph = ". ".join(item.strip(" .") for item in sentences if item.strip())
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if paragraph and paragraph[-1] not in ".!?":
            paragraph += "."
        if len(paragraph) > 460:
            paragraph = paragraph[:460].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."

        return paragraph or "Case evidence is available, but a concise overview could not be synthesized yet."

    def _build_case_key_takeaways(
        self,
        *,
        documents: List[Document],
        main_points: List[str],
        legal_risks: List[str],
        quantitative_anchor: Optional[str],
    ) -> List[str]:
        takeaways: List[str] = []

        if main_points:
            primary_points = [self._normalize_text(item).rstrip(".") for item in main_points[:2] if self._normalize_text(item)]
            if primary_points:
                takeaways.append("Dispute core: " + "; ".join(primary_points) + ".")

        notice_file = ""
        response_file = ""
        notice_perc: List[str] = []
        response_perc: List[str] = []
        amount_markers: List[str] = []
        amount_sources: List[str] = []

        for document in documents:
            filename = self._normalize_text(document.filename)
            lowered_name = filename.lower()
            text_blob = " ".join(
                [
                    self._normalize_text(document.summary),
                    self._normalize_text(document.summary_short),
                    self._normalize_text((document.redacted_text or "")[:2200]),
                    self._normalize_text((document.extracted_text or "")[:2200]),
                ]
            )
            percentages = self._extract_percentages(text_blob, max_items=6)
            amounts = self._extract_currency_amounts(text_blob, max_items=6)

            if "notice" in lowered_name and "breach" in lowered_name:
                notice_file = filename or notice_file
                notice_perc = self._dedupe_ordered(notice_perc + percentages)
            if "response" in lowered_name:
                response_file = filename or response_file
                response_perc = self._dedupe_ordered(response_perc + percentages)

            if any(token in lowered_name for token in ["invoice", "reconciliation", "notice", "response"]):
                if amounts:
                    amount_markers = self._dedupe_ordered(amount_markers + amounts)
                    if filename and filename not in amount_sources:
                        amount_sources.append(filename)

        if notice_file and response_file and notice_perc and response_perc:
            notice_sample = ", ".join(notice_perc[:2])
            response_sample = ", ".join(response_perc[:2])
            if notice_sample.lower() != response_sample.lower():
                takeaways.append(
                    f"KPI figures diverge between party submissions ({notice_file}: {notice_sample}; {response_file}: {response_sample})."
                )

        if amount_markers:
            refs = ", ".join(amount_sources[:2]) if amount_sources else "invoice-related evidence"
            takeaways.append(
                "Invoice quantum is contested around "
                + ", ".join(amount_markers[:3])
                + f" ({refs})."
            )

        if notice_file and response_file:
            takeaways.append(
                f"Legal position mismatch: breach allegations are asserted in {notice_file} and challenged in {response_file}."
            )

        if legal_risks:
            lead_risk = self._normalize_text(legal_risks[0]).rstrip(".")
            if lead_risk:
                takeaways.append(f"Top legal risk signal: {lead_risk}.")

        if quantitative_anchor:
            compact_quant = self._normalize_text(quantitative_anchor)
            if compact_quant:
                compact_quant = compact_quant.rstrip(".")
                takeaways.append(compact_quant + ".")

        if not takeaways:
            takeaways.append("Key disputes and risk signals are present but require additional processed evidence for sharper extraction.")

        return self._dedupe_ordered(takeaways)[:6]

    def _build_case_executive_summary(
        self,
        *,
        summary_text: str,
        parties: List[str],
        evidence_sources: List[str],
        key_dates: List[Dict[str, str]],
    ) -> str:
        sentences: List[str] = []

        base = self._normalize_text(summary_text).rstrip(".")
        if base:
            sentences.append(base)

        normalized_parties = [self._normalize_text(item) for item in parties if self._normalize_text(item)]
        if len(normalized_parties) >= 2:
            sentences.append(
                f"Primary counterparties are {normalized_parties[0]} and {normalized_parties[1]}, with obligations anchored in the service agreement framework"
            )

        lowered_sources = [str(name or "").strip().lower() for name in evidence_sources]
        if any("master_service_agreement" in name or "service_agreement" in name or "msa" in name for name in lowered_sources):
            if any("notice" in name for name in lowered_sources) and any("response" in name for name in lowered_sources):
                sentences.append(
                    "The record includes the contract baseline, formal breach notice, and counterparty response, creating a mature dispute file for strategy decisions"
                )

        actionable_date_bits: List[str] = []
        fallback_date_bits: List[str] = []
        for item in key_dates[:6]:
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if not label or not value:
                continue
            entry = f"{label} ({value})"
            lowered_label = label.lower()
            if "effective date" in lowered_label:
                fallback_date_bits.append(entry)
                continue
            if any(token in lowered_label for token in ["notice", "due", "deadline", "cure", "response", "hearing"]):
                actionable_date_bits.append(entry)
            else:
                fallback_date_bits.append(entry)

        date_bits = (actionable_date_bits + fallback_date_bits)[:4]
        if date_bits:
            sentences.append("Immediate timeline anchors include " + "; ".join(date_bits))

        paragraph = ". ".join(item.strip(" .") for item in sentences if item.strip())
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if paragraph and paragraph[-1] not in ".!?":
            paragraph += "."
        if len(paragraph) > 920:
            paragraph = paragraph[:920].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
        return paragraph or summary_text

    def _build_contextual_case_next_steps(
        self,
        *,
        current_steps: List[str],
        key_dates: List[Dict[str, str]],
        evidence_sources: List[str],
        quantitative_anchor: Optional[str],
    ) -> List[str]:
        planned: List[str] = []

        generic_fragments = (
            "review the agreement carefully",
            "verify the completeness and accuracy",
            "cross-check this document",
            "cross-check documents",
            "review the clauses governing",
        )

        lowered_sources = [str(name or "").strip().lower() for name in evidence_sources]

        def _append(step: str) -> None:
            cleaned = self._normalize_text(step).rstrip(".")
            if cleaned and cleaned not in planned:
                planned.append(cleaned)

        if any("kpi" in name or "dashboard" in name for name in lowered_sources):
            _append("Validate SLA and KPI computation methodology against raw route logs, exclusions, and contract-defined measurement rules")

        if any("invoice" in name or "reconciliation" in name for name in lowered_sources):
            _append("Finalize a line-item reconciliation schedule that maps each disputed charge to support evidence, rate-card terms, and cap limits")

        if any("notice" in name for name in lowered_sources):
            date_anchors: List[str] = []
            for item in key_dates[:6]:
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                if not label or not value:
                    continue
                lowered_label = label.lower()
                if "effective date" in lowered_label:
                    continue
                if any(token in lowered_label for token in ["due", "deadline", "notice", "cure", "response", "hearing"]):
                    date_anchors.append(f"{label} ({value})")
            if date_anchors:
                _append(
                    "Build a deadline execution matrix for "
                    + "; ".join(date_anchors)
                    + " with owners and evidence deliverables"
                )

        if quantitative_anchor:
            _append("Tie every quantitative anchor to the governing clause and damages narrative before partner review")

        if any("settlement" in name for name in lowered_sources):
            _append("Prepare dual-track negotiation material: without-prejudice terms for settlement and an escalation-ready fallback brief")

        has_contextual_steps = bool(planned)

        for step in current_steps:
            cleaned = self._normalize_text(step).rstrip(".")
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if has_contextual_steps and any(fragment in lowered for fragment in generic_fragments):
                continue
            _append(cleaned)

        return planned[:6]

    @classmethod
    def _extract_concise_summary_text(
        cls,
        *,
        narrative_summary: str,
        overview: str,
        main_issues: List[str],
    ) -> str:
        candidate = (narrative_summary or "").strip()
        if not candidate:
            candidate = (overview or "").strip()

        if candidate:
            lines: List[str] = []
            stop_headers = {
                "main issues:",
                "key dates:",
                "legal risks:",
                "recommended next steps:",
                "risk assessment:",
                "practical next steps:",
            }
            for raw_line in candidate.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                lowered = line.lower()
                if lowered in stop_headers:
                    break
                if line.startswith("-"):
                    continue
                if cls._looks_like_prompt_template_noise(line):
                    continue
                lines.append(line)
                if len(lines) >= 4:
                    break

            concise = " ".join(lines).strip()
            concise = re.sub(r"\s+", " ", concise)
            if concise:
                return concise[:720]

        cleaned_issues = [
            str(item or "").strip().rstrip(".")
            for item in (main_issues or [])
            if str(item or "").strip() and not cls._looks_like_prompt_template_noise(str(item or ""))
        ]
        if cleaned_issues:
            return f"{cleaned_issues[0]}."

        return "A concise case summary could not be synthesized from current evidence."

    @classmethod
    def _to_clean_summary_paragraph(
        cls,
        text: str,
        *,
        fallback: str,
        max_sentences: int = 3,
        max_chars: int = 560,
    ) -> str:
        candidate = str(text or "").strip()
        if not candidate:
            return fallback

        lowered = candidate.lower()
        cut_indexes = [lowered.find(marker) for marker in cls.SUMMARY_STOP_HEADERS if lowered.find(marker) >= 0]
        if cut_indexes:
            candidate = candidate[: min(cut_indexes)].strip()

        candidate = re.sub(r"^\s*(summary|overview)\s*:\s*", "", candidate, flags=re.IGNORECASE)
        candidate = candidate.replace("\r", "\n")
        candidate = re.sub(r"\n+", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" -:;,.")

        if not candidate or cls._looks_like_prompt_template_noise(candidate):
            return fallback

        sentence_chunks = [part.strip() for part in re.split(r"(?<=[.!?])\s+", candidate) if part.strip()]
        if sentence_chunks:
            paragraph = " ".join(sentence_chunks[:max_sentences]).strip()
        else:
            paragraph = candidate

        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if len(paragraph) > max_chars:
            paragraph = paragraph[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."

        return paragraph or fallback

    def _is_reasonable_party(self, value: str) -> bool:
        lowered = value.lower().strip()
        if not lowered:
            return False

        blocked_fragments = [
            "invoice records",
            "warehouse logs",
            "document overview",
            "this document",
            "question answering",
            "sample document",
            "used to test",
            "key dates"
        ]

        if any(fragment in lowered for fragment in blocked_fragments):
            return False

        return len(value) <= 60

    def _summarize_document(
        self,
        db: Session,
        tenant_id: int,
        document_id: Optional[int]
    ) -> Dict[str, Any]:
        document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
        document = self._ensure_document_summary(db=db, document=document)
        jurisdiction_context = self._resolve_jurisdiction_context(
            db=db,
            tenant_id=tenant_id,
            document_id=document.id,
        )

        try:
            artifact_versioning_service.ensure_seed_version_for_document_summary(
                db=db,
                tenant_id=tenant_id,
                document=document,
            )
        except Exception:
            pass

        artifact_context = self._build_artifact_context(
            db=db,
            tenant_id=tenant_id,
            artifact_type="document_summary",
            case_id=document.case_id,
            document_id=document.id,
        )

        summary_text = (
            document.summary
            or document.summary_short
            or (document.redacted_text or document.extracted_text or "")[:1200]
        ).strip()

        if not summary_text:
            status_note = self._document_summary_unavailable_reason(document)
            return {
                "answer": (
                    "I could not summarize this document because no processed text is available yet. "
                    f"{status_note}"
                ),
                "used_fallback": True,
                "fallback_reason": "Document has no processed text",
                "confidence": "low",
                "scope": "document",
                "sources": [],
                "artifact": artifact_context,
                "jurisdiction": jurisdiction_context,
            }

        return {
            "answer": self._to_clean_summary_paragraph(
                summary_text,
                fallback=f"A concise summary is not available yet for {document.filename}.",
            ),
            "used_fallback": False,
            "fallback_reason": None,
            "confidence": "high" if self._text_or_empty(document.summary) else "medium",
            "scope": "document",
            "sources": [
                self._build_source(
                    document=document,
                    snippet=document.summary_short or summary_text
                )
            ],
            "artifact": artifact_context,
            "jurisdiction": jurisdiction_context,
        }

    def _summarize_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
        requested_contractual_context: bool = False,
        summary_request_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet.",
                "used_fallback": True,
                "fallback_reason": "No documents found in case",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        documents = [self._ensure_document_summary(db=db, document=document) for document in documents]

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        summary_text = self._extract_concise_summary_text(
            narrative_summary=str(reasoning_payload.get("narrative_summary") or ""),
            overview=str(reasoning_payload.get("overview") or ""),
            main_issues=reasoning_payload.get("main_issues") or [],
        )

        main_points: List[str] = []
        for issue in reasoning_payload.get("main_issues") or []:
            cleaned = str(issue or "").strip().rstrip(".")
            if not cleaned:
                continue
            if self._looks_like_prompt_template_noise(cleaned):
                continue
            normalized = cleaned[0].upper() + cleaned[1:] if cleaned else cleaned
            if not self._is_redundant_issue_point(normalized, main_points):
                main_points.append(normalized)

        legal_risks = self._normalize_risk_items(reasoning_payload.get("legal_risks") or [])

        key_dates: List[Dict[str, str]] = []
        for item in reasoning_payload.get("key_dates") or []:
            label = self._normalize_text(item.get("label"))
            value = self._normalize_text(item.get("value"))
            if not label or not value:
                continue
            normalized_item = {"label": label, "value": value}
            if normalized_item not in key_dates:
                key_dates.append(normalized_item)

        next_steps = self._normalize_next_steps(reasoning_payload.get("recommended_next_steps") or [])

        evidence_sources: List[str] = []
        for source in reasoning_payload.get("sources") or []:
            filename = str(source.get("filename") or "").strip()
            if not filename or filename in evidence_sources:
                continue
            evidence_sources.append(filename)

        for document in documents:
            filename = self._normalize_text(document.filename)
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)

        unavailable_documents: List[str] = []
        fallback_sources: List[Dict[str, Any]] = []

        for document in documents:
            source_text = self._text_or_empty(document.summary) or self._text_or_empty(document.summary_short)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))
            else:
                unavailable_documents.append(self._document_summary_unavailable_reason(document))

        reasoning_sources_for_quant = list(reasoning_payload.get("sources") or [])
        for source in fallback_sources:
            if source not in reasoning_sources_for_quant:
                reasoning_sources_for_quant.append(source)

        for document in documents:
            numeric_source_text = self._normalize_text(document.redacted_text or document.extracted_text)
            if not numeric_source_text:
                continue
            candidate_source = {
                "filename": document.filename,
                "snippet": numeric_source_text[:1800],
            }
            if candidate_source not in reasoning_sources_for_quant:
                reasoning_sources_for_quant.append(candidate_source)

        requested_count_value = int(requested_count or 0) if requested_count else 0
        requested_count_value = min(max(requested_count_value, 0), 12)
        lowered_request = (summary_request_text or "").strip().lower()
        wants_bullets = requested_count_value > 0 or "bullet" in lowered_request
        bullet_target = requested_count_value or (8 if wants_bullets else 0)
        wants_contractual_context = bool(requested_contractual_context) or "contractual context" in lowered_request
        quantitative_anchor = self._build_quantitative_anchor_bullet(
            summary_text=summary_text,
            main_points=main_points,
            reasoning_sources=reasoning_sources_for_quant,
        )

        parties: List[str] = []
        for item in reasoning_payload.get("parties") or []:
            cleaned = self._normalize_text(str(item or ""))
            if cleaned and cleaned not in parties:
                parties.append(cleaned)

        overall_overview = self._build_case_overall_overview(
            summary_text=summary_text,
            parties=parties,
            evidence_sources=evidence_sources,
            main_points=main_points,
        )

        document_resume_lines: List[str] = []
        for index, document in enumerate(documents, start=1):
            insights = self._safe_load_insights(document)
            document_resume_lines.append(
                self._build_case_document_resume_entry(position=index, document=document, insights=insights)
            )

        key_takeaways = self._build_case_key_takeaways(
            documents=documents,
            main_points=main_points,
            legal_risks=legal_risks,
            quantitative_anchor=quantitative_anchor,
        )

        recommended_steps = self._build_contextual_case_next_steps(
            current_steps=next_steps,
            key_dates=key_dates,
            evidence_sources=evidence_sources,
            quantitative_anchor=quantitative_anchor,
        )
        wants_next_steps = any(
            token in lowered_request
            for token in [
                "next step",
                "next steps",
                "action plan",
                "recommendation",
                "recommended next steps",
            ]
        )

        if wants_bullets:
            bullets = self._build_case_summary_bullets(
                summary_text=summary_text,
                main_points=main_points,
                key_dates=key_dates,
                next_steps=next_steps,
                evidence_sources=evidence_sources,
                reasoning_sources=reasoning_sources_for_quant,
                target_count=bullet_target,
                require_contractual_context=wants_contractual_context,
            )
            lines: List[str] = [f"Case #{case.id} summary:", ""]
            lines.extend(f"- {item}" for item in bullets)
        else:
            lines = [f"Case #{case.id} resume:"]

            lines.append("")
            lines.append("Overall Case Overview:")
            lines.append(overall_overview)

            lines.append("")
            lines.append("Documents Summary:")
            if document_resume_lines:
                lines.extend(document_resume_lines)
            else:
                lines.append("- No document-level summary could be generated yet.")

            lines.append("")
            lines.append("Key Takeaways:")
            if key_takeaways:
                for point in key_takeaways[:5]:
                    lines.append(f"- {point}")
            else:
                lines.append("- No critical conflict signals were confidently extracted yet.")

            lines.append("")
            lines.append("Important Dates:")
            if key_dates:
                for item in key_dates[:6]:
                    lines.append(f"- {item['label']}: {item['value']}")
            else:
                lines.append("- No critical dates were confidently extracted yet.")

            if wants_next_steps:
                lines.append("")
                lines.append("Recommended Next Steps:")
                if recommended_steps:
                    for step in recommended_steps[:4]:
                        lines.append(f"- {step}")
                else:
                    lines.append("- Validate chronology, disputed amounts, and contractual triggers against source documents.")

        answer = "\n".join(lines).strip()
        if unavailable_documents:
            answer = (
                f"{answer}\n\n"
                "Document processing status:\n"
                + "\n".join(f"- {item}" for item in unavailable_documents[:10])
            ).strip()

        complete_document_count = sum(1 for doc in documents if (doc.summary or "").strip())
        used_llm = bool(reasoning_payload.get("used_llm"))
        if used_llm and complete_document_count > 0:
            confidence = "high"
        elif complete_document_count == 0:
            confidence = "low"
        else:
            confidence = "medium"

        if not used_llm and unavailable_documents:
            fallback_reason = "documents_missing_processed_text_and_reasoning_llm_unavailable"
        elif not used_llm:
            fallback_reason = "Used case reasoning heuristic synthesis"
        elif unavailable_documents:
            fallback_reason = "documents_missing_processed_text"
        else:
            fallback_reason = None

        sources = (reasoning_payload.get("sources") or fallback_sources)[:10]

        return {
            "answer": answer,
            "used_fallback": bool(unavailable_documents) or not used_llm,
            "fallback_reason": fallback_reason,
            "confidence": confidence,
            "scope": "case",
            "sources": sources,
            "jurisdiction": jurisdiction_context,
        }

    def _summarize_and_analyze_case_risks(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet.",
                "used_fallback": True,
                "fallback_reason": "No documents found in case",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        narrative_summary = self._extract_concise_summary_text(
            narrative_summary=str(reasoning_payload.get("narrative_summary") or ""),
            overview=str(reasoning_payload.get("overview") or ""),
            main_issues=reasoning_payload.get("main_issues") or [],
        )
        key_dates = reasoning_payload.get("key_dates") or []
        legal_risks = self._normalize_risk_items(reasoning_payload.get("legal_risks") or [])
        next_steps = self._normalize_next_steps(reasoning_payload.get("recommended_next_steps") or [])
        evidence_sources = []
        for source in reasoning_payload.get("sources") or []:
            filename = str(source.get("filename") or "").strip()
            if not filename:
                continue
            if filename in evidence_sources:
                continue
            evidence_sources.append(filename)
            if len(evidence_sources) >= 3:
                break

        risk_count = min(max(requested_count or 5, 1), 10)
        lines: List[str] = [f"Case #{case.id} summary and risk assessment:"]

        lines.append("")
        lines.append("Summary:")
        lines.append(narrative_summary)

        if evidence_sources:
            lines.append("")
            lines.append("Evidence basis:")
            for filename in evidence_sources:
                lines.append(f"- {filename}")

        if key_dates:
            lines.append("")
            lines.append("Key Dates:")
            for item in key_dates[:5]:
                label = str(item.get("label") or "").strip()
                value = str(item.get("value") or "").strip()
                if label and value:
                    lines.append(f"- {label}: {value}")

        lines.append("")
        lines.append("Risk Assessment:")
        if legal_risks:
            for risk in legal_risks[:risk_count]:
                lines.append(f"- {risk}")
        else:
            lines.append("- No major legal risks were clearly detected from current evidence.")

        lines.append("")
        lines.append("Practical Next Steps:")
        if next_steps:
            for step in next_steps[:5]:
                lines.append(f"- {step}")
        else:
            lines.append("- Review obligations, dates, and dispute mechanics manually against the uploaded documents.")

        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not bool(reasoning_payload.get("used_llm")),
            "fallback_reason": None if reasoning_payload.get("used_llm") else "Used case reasoning agent heuristic synthesis",
            "confidence": "high" if reasoning_payload.get("used_llm") else "medium",
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or [])[:10],
            "jurisdiction": jurisdiction_context,
        }

    def _list_case_deadlines(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        deadline_items: List[Dict[str, str]] = []
        sources: List[Dict[str, Any]] = []

        for document in documents:
            insights = self._safe_load_insights(document)

            for item in insights.get("important_dates", []):
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))

                if not label or not value:
                    continue

                normalized_item = {
                    "label": label,
                    "value": value,
                    "filename": document.filename,
                    "document_id": document.id,
                    "case_id": document.case_id
                }

                if normalized_item not in deadline_items:
                    deadline_items.append(normalized_item)

        if deadline_items:
            target_count = min(max(requested_count or 10, 1), 12)
            ordered_deadlines = deadline_items[:25]
            grouped: Dict[str, List[Dict[str, str]]] = {
                "Deadlines / Due Dates": [],
                "Notice Periods": [],
                "Recurring Dates": [],
                "Other Time References": []
            }

            for item in ordered_deadlines:
                label = item["label"].lower()

                if "notice" in label:
                    grouped["Notice Periods"].append(item)
                elif "recurring" in label:
                    grouped["Recurring Dates"].append(item)
                elif "deadline" in label or "due" in label or "hearing" in label:
                    grouped["Deadlines / Due Dates"].append(item)
                else:
                    grouped["Other Time References"].append(item)

                sources.append({
                    "chunk_id": None,
                    "document_id": item["document_id"],
                    "case_id": item["case_id"],
                    "filename": item["filename"],
                    "chunk_index": None,
                    "score": 1.0,
                    "snippet": f"{item['label']}: {item['value']}"
                })

            if requested_count:
                lines = [f"Detected key deadlines for case {case.id}:"]
                for item in ordered_deadlines[:target_count]:
                    lines.append(f"- {item['value']} ({item['label']}) - {item['filename']}")
                return {
                    "answer": "\n".join(lines),
                    "used_fallback": False,
                    "fallback_reason": None,
                    "confidence": "high",
                    "scope": "case",
                    "sources": sources[:10],
                    "jurisdiction": jurisdiction_context,
                }

            lines = [f"Detected deadlines and time-related obligations for case {case.id}:"]

            for section, items in grouped.items():
                if not items:
                    continue
                lines.append("")
                lines.append(f"{section}:")
                for item in items[:10]:
                    lines.append(f"- {item['value']} ({item['label']}) - {item['filename']}")

            return {
                "answer": "\n".join(lines),
                "used_fallback": False,
                "fallback_reason": None,
                "confidence": "high",
                "scope": "case",
                "sources": sources[:10],
                "jurisdiction": jurisdiction_context,
            }

        rag_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            question="What deadlines, notice periods, due dates, or hearing dates are mentioned in this case?",
            top_k=5,
            case_id=case.id,
            document_id=None
        )
        rag_result["scope"] = "case"
        rag_result["jurisdiction"] = jurisdiction_context
        return rag_result

    @staticmethod
    def _parse_timeline_date_value(value: str, *, default_year: Optional[int] = None) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None

        patterns = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y-%m-%d %H:%M:%S",
            "%B %d, %Y",
            "%b %d, %Y",
            "%B %d %Y",
            "%b %d %Y",
            "%B %d, %Y %I:%M %p",
            "%b %d, %Y %I:%M %p",
            "%d/%m/%Y",
            "%m/%d/%Y",
        ]
        for fmt in patterns:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue

        if default_year is not None:
            inferred_patterns = [
                "%B %d",
                "%b %d",
                "%B %d, %I:%M %p",
                "%b %d, %I:%M %p",
                "%B %d %I:%M %p",
                "%b %d %I:%M %p",
            ]
            for fmt in inferred_patterns:
                try:
                    parsed = datetime.strptime(normalized, fmt)
                    return parsed.replace(year=int(default_year))
                except ValueError:
                    continue

        inline_iso = re.search(r"\d{4}-\d{2}-\d{2}", normalized)
        if inline_iso:
            try:
                return datetime.strptime(inline_iso.group(0), "%Y-%m-%d")
            except ValueError:
                return None

        return None

    @classmethod
    def _normalize_timeline_label(cls, value: str) -> str:
        cleaned = re.sub(r"[_\-]+", " ", str(value or "")).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if not cleaned:
            return "Event"

        acronyms = {"sla", "kpi", "msa", "api", "pdf"}
        lower_words = {"of", "and", "for", "the", "to", "in", "on", "at", "by", "or", "a", "an", "from", "with"}
        words: List[str] = []
        for index, token in enumerate(cleaned.split()):
            lowered = token.lower()
            if lowered in acronyms:
                words.append(lowered.upper())
            elif index > 0 and lowered in lower_words:
                words.append(lowered)
            else:
                words.append(lowered.capitalize())

        return " ".join(words)

    @classmethod
    def _canonicalize_timeline_label(cls, value: str) -> str:
        cleaned = cls._normalize_timeline_label(value)
        lowered = cleaned.lower()

        if "revised invoice" in lowered and ("due" in lowered or "deadline" in lowered):
            return "Revised Invoice Due"
        if "notice" in lowered and "breach" in lowered:
            return "Notice of Breach"
        if "root cause report" in lowered and "due" in lowered:
            return "Root Cause Report Due"
        if "corrective operations plan" in lowered and "due" in lowered:
            return "Corrective Operations Plan Due"
        if "counterparty" in lowered and "response" in lowered:
            return "Counterparty Response"
        if lowered in {"response date", "response"}:
            return "Counterparty Response"
        if lowered in {"invoice date"}:
            return "Invoice Date"

        return cleaned

    @classmethod
    def _build_strict_case_timeline_text(
        cls,
        *,
        case_id: int,
        case_title: str,
        events: List[Dict[str, Any]],
    ) -> tuple[str, List[Dict[str, Any]]]:
        raw_rows: List[Dict[str, Any]] = []
        known_years: List[int] = []

        for item in events:
            raw_date = cls._normalize_text(str(item.get("date") or ""))
            raw_label = cls._normalize_text(str(item.get("label") or item.get("event") or ""))
            source = cls._normalize_text(str(item.get("source") or item.get("filename") or "Unknown source"))
            if not raw_date or not raw_label:
                continue

            parsed = cls._parse_timeline_date_value(raw_date)
            if parsed is not None:
                known_years.append(parsed.year)

            raw_rows.append(
                {
                    "raw_date": raw_date,
                    "label": cls._canonicalize_timeline_label(raw_label),
                    "source": source,
                    "parsed_date": parsed,
                }
            )

        inferred_year: Optional[int] = None
        if known_years:
            year_counts: Dict[int, int] = {}
            for year in known_years:
                year_counts[year] = year_counts.get(year, 0) + 1
            inferred_year = sorted(year_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

        absolute_events_map: Dict[tuple[str, str], Dict[str, Any]] = {}
        relative_events: List[Dict[str, Any]] = []

        for row in raw_rows:
            parsed = row.get("parsed_date") or cls._parse_timeline_date_value(
                row.get("raw_date") or "",
                default_year=inferred_year,
            )

            if parsed is None:
                relative_events.append(
                    {
                        "raw_date": row.get("raw_date"),
                        "label": row.get("label"),
                        "source": row.get("source"),
                    }
                )
                continue

            date_display = parsed.strftime("%Y-%m-%d")
            key = (date_display.lower(), str(row.get("label") or "").lower())
            existing = absolute_events_map.get(key)
            source = cls._normalize_text(str(row.get("source") or "Unknown source"))

            if existing is None:
                absolute_events_map[key] = {
                    "date_display": date_display,
                    "raw_date": row.get("raw_date"),
                    "label": row.get("label"),
                    "source": source,
                    "sources": [source] if source else ["Unknown source"],
                    "parsed_date": parsed,
                }
            else:
                if source and source not in existing["sources"]:
                    existing["sources"].append(source)

        normalized_events = sorted(
            absolute_events_map.values(),
            key=lambda event: (
                event.get("parsed_date") or datetime.max,
                str(event.get("label") or "").lower(),
            ),
        )

        relative_events = sorted(
            relative_events,
            key=lambda event: (
                str(event.get("raw_date") or "").lower(),
                str(event.get("label") or "").lower(),
            ),
        )

        lines: List[str] = [f"Case #{case_id} strict chronology ({case_title}):"]
        lines.append("")
        lines.append("Dated Events:")

        if not normalized_events:
            lines.append("None")
        else:
            for event in normalized_events[:35]:
                source_values = [cls._normalize_text(str(item or "")) for item in (event.get("sources") or [])]
                source_values = [item for item in source_values if item]
                source_values = cls._dedupe_ordered(source_values)
                if not source_values:
                    source_values = [cls._normalize_text(str(event.get("source") or "Unknown source")) or "Unknown source"]

                if len(source_values) > 3:
                    source_display = ", ".join(source_values[:3]) + f" +{len(source_values) - 3} more"
                else:
                    source_display = ", ".join(source_values)

                lines.append(
                    f"{event['date_display']} | {event['label']} | Source: {source_display}"
                )

            if len(normalized_events) > 35:
                lines.append("")
                lines.append(f"Showing first 35 events out of {len(normalized_events)} extracted dated events.")

        if relative_events:
            lines.append("")
            lines.append("Undated/Relative Time References:")
            for event in relative_events[:8]:
                lines.append(
                    f"{event.get('raw_date')} | {event.get('label')} | Source: {event.get('source')}"
                )

        return "\n".join(lines), normalized_events

    def _build_case_timeline(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)

        timeline_result = timeline_agent.build_case_timeline(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            consultations=consultations,
        )

        if timeline_result.success:
            timeline_text, normalized_events = self._build_strict_case_timeline_text(
                case_id=case.id,
                case_title=case.title,
                events=timeline_result.payload.get("events") or [],
            )

            document_by_filename = {
                self._normalize_text(document.filename): document
                for document in documents
                if self._normalize_text(document.filename)
            }

            sources: List[Dict[str, Any]] = []
            seen_sources: set[tuple[str, str]] = set()
            for event in normalized_events:
                snippet = f"{event.get('date_display')}: {event.get('label')}"
                source_names = [
                    self._normalize_text(str(item or ""))
                    for item in (event.get("sources") or [event.get("source")])
                ]
                source_names = [item for item in source_names if item]
                if not source_names:
                    source_names = ["Unknown source"]

                for source_name in self._dedupe_ordered(source_names)[:4]:
                    source_signature = (source_name.lower(), snippet.lower())
                    if source_signature in seen_sources:
                        continue
                    seen_sources.add(source_signature)

                    document = document_by_filename.get(source_name)
                    if document is not None:
                        sources.append(self._build_source(document=document, snippet=snippet))
                    else:
                        sources.append(
                            {
                                "chunk_id": None,
                                "document_id": None,
                                "case_id": case.id,
                                "filename": source_name,
                                "chunk_index": None,
                                "score": 1.0,
                                "snippet": snippet[:300],
                            }
                        )

            return {
                "answer": timeline_text,
                "used_fallback": not bool(timeline_result.payload.get("used_llm")),
                "fallback_reason": None if timeline_result.payload.get("used_llm") else "Used timeline agent heuristic synthesis",
                "confidence": "high" if normalized_events else "medium",
                "scope": "case",
                "sources": sources[:10],
                "jurisdiction": jurisdiction_context,
            }

        return {
            "answer": "I could not build a timeline for this case yet.",
            "used_fallback": True,
            "fallback_reason": timeline_result.error or "Timeline agent failed",
            "confidence": "low",
            "scope": "case",
            "sources": [],
            "jurisdiction": jurisdiction_context,
        }

    def _generate_case_insights(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)
        recordings = self._get_case_voice_recordings(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents and not consultations and not recordings:
            return {
                "answer": f"Case {case.id} has no evidence yet, so insights cannot be generated.",
                "used_fallback": True,
                "fallback_reason": "No case evidence found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        insight_result = insight_agent.generate_case_insights(
            case_id=case.id,
            case_title=case.title,
            jurisdiction_country=case.jurisdiction_country,
            reasoning_payload=reasoning_payload,
            documents=documents,
            consultation_count=len(consultations),
            voice_recording_count=len(recordings),
        )

        if not insight_result.success:
            return {
                "answer": "I could not generate insights for this case yet.",
                "used_fallback": True,
                "fallback_reason": insight_result.error or "Insight agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = insight_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("insight_summary") or ""),
            fallback=f"Case #{case.id} insight snapshot is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        key_insights = self._normalize_next_steps(payload.get("key_insights") or [])
        priority_actions = self._normalize_next_steps(payload.get("priority_actions") or [])
        evidence_gaps = self._normalize_next_steps(payload.get("evidence_gaps") or [])

        evidence_sources: List[str] = []
        for item in payload.get("evidence_sources") or []:
            filename = str(item or "").strip()
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)
            if len(evidence_sources) >= 10:
                break

        lines: List[str] = [f"Case #{case.id} insight brief:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        lines.append("")
        lines.append("Strategic insights:")
        if key_insights:
            for item in key_insights[:6]:
                lines.append(f"- {item}")
        else:
            lines.append("- No high-confidence insight was extracted from current evidence.")

        if priority_actions:
            lines.append("")
            lines.append("Partner review action plan:")
            for item in priority_actions[:5]:
                lines.append(f"- {item}")

        if evidence_gaps:
            lines.append("")
            lines.append("Open proof gaps to close:")
            for item in evidence_gaps[:5]:
                lines.append(f"- {item}")

        if evidence_sources:
            lines.append("")
            lines.append("Evidence reviewed:")
            for item in evidence_sources:
                lines.append(f"- {item}")

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm or not key_insights,
            "fallback_reason": None if used_llm else "Used insight agent heuristic synthesis",
            "confidence": "high" if used_llm and key_insights else "medium" if key_insights else "low",
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
        }

    def _generate_case_memory(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        if case_id is None:
            return {
                "answer": "Please open a case first so I can build a case memory snapshot.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)
        recordings = self._get_case_voice_recordings(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents and not consultations and not recordings:
            return {
                "answer": f"Case {case.id} has no evidence yet, so a memory snapshot cannot be generated.",
                "used_fallback": True,
                "fallback_reason": "No case evidence found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        memory_result = case_memory_agent.build_case_memory(
            case_id=case.id,
            case_title=case.title,
            jurisdiction_country=case.jurisdiction_country,
            documents=documents,
            consultations=consultations,
            voice_recordings=recordings,
            reasoning_payload=reasoning_payload,
            objective=objective or "Build a case memory snapshot that highlights missing proof and evidence trace.",
        )

        if not memory_result.success:
            return {
                "answer": "I could not build a case memory snapshot yet.",
                "used_fallback": True,
                "fallback_reason": memory_result.error or "Case memory agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = memory_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("memory_summary") or ""),
            fallback=f"Case #{case.id} memory snapshot is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        document_inventory = payload.get("document_inventory") or []
        claim_trace = payload.get("claim_trace") or []
        contradictions = self._normalize_next_steps(payload.get("contradictions") or [])
        open_gaps = self._normalize_next_steps(payload.get("open_proof_gaps") or [])
        deadline_signals = payload.get("deadline_signals") or []
        next_steps = self._normalize_next_steps(payload.get("recommended_next_steps") or [])

        evidence_sources: List[str] = []
        for item in payload.get("evidence_sources") or []:
            filename = str(item or "").strip()
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)
            if len(evidence_sources) >= 10:
                break

        lines: List[str] = [f"Case #{case.id} memory snapshot:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        lines.append("")
        lines.append("Document inventory:")
        if document_inventory:
            for item in document_inventory[:8]:
                filename = self._normalize_text(item.get("filename"))
                role = self._normalize_text(item.get("role")) or "case evidence"
                summary = self._normalize_text(item.get("summary"))
                descriptor = f"{filename} — {role}"
                if summary:
                    descriptor += f": {summary}"
                lines.append(f"- {descriptor}")
        else:
            lines.append("- No document inventory was extracted yet.")

        lines.append("")
        lines.append("Claim trace:")
        if claim_trace:
            for item in claim_trace[:6]:
                claim = self._normalize_text(item.get("claim"))
                support = item.get("supporting_documents") or []
                status = self._normalize_text(item.get("status")) or "unknown"
                note = self._normalize_text(item.get("note"))
                support_text = ", ".join(str(doc).strip() for doc in support if str(doc).strip()) or "no direct support yet"
                line = f"- {claim} [{status}]: {support_text}"
                if note:
                    line += f" ({note})"
                lines.append(line)
        else:
            lines.append("- No claim trace was extracted yet.")

        if contradictions:
            lines.append("")
            lines.append("Contradictions to resolve:")
            lines.extend(f"- {item}" for item in contradictions[:5])

        if deadline_signals:
            lines.append("")
            lines.append("Live deadlines and date signals:")
            for item in deadline_signals[:6]:
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                source = self._normalize_text(item.get("source"))
                if label and value:
                    line = f"- {label}: {value}"
                    if source:
                        line += f" (source: {source})"
                    lines.append(line)

        if open_gaps:
            lines.append("")
            lines.append("Open proof gaps:")
            lines.extend(f"- {item}" for item in open_gaps[:6])

        if next_steps:
            lines.append("")
            lines.append("Recommended next steps:")
            lines.extend(f"- {item}" for item in next_steps[:6])

        if evidence_sources:
            lines.append("")
            lines.append("Evidence reviewed:")
            lines.extend(f"- {item}" for item in evidence_sources[:8])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used case memory heuristic synthesis",
            "confidence": str(payload.get("confidence") or ("high" if claim_trace else "medium")),
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }

    def _trace_case_evidence(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        if case_id is None:
            return {
                "answer": "Please open a case first so I can trace evidence to the record.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)
        recordings = self._get_case_voice_recordings(db=db, tenant_id=tenant_id, case_id=case.id)

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet, so evidence tracing cannot run.",
                "used_fallback": True,
                "fallback_reason": "No case documents found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        trace_result = evidence_trace_agent.build_claim_trace(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            reasoning_payload=reasoning_payload,
            objective=objective or "Trace claims to supporting case evidence.",
        )

        if not trace_result.success:
            return {
                "answer": "I could not build an evidence trace yet.",
                "used_fallback": True,
                "fallback_reason": trace_result.error or "Evidence trace agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = trace_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("trace_summary") or ""),
            fallback=f"Case #{case.id} evidence trace is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        claim_trace = payload.get("claim_trace") or []
        unsupported_claims = self._normalize_next_steps(payload.get("unsupported_claims") or [])
        next_steps = self._normalize_next_steps(payload.get("recommended_follow_up") or [])

        evidence_sources: List[str] = []
        for item in payload.get("evidence_sources") or []:
            filename = str(item or "").strip()
            if filename and filename not in evidence_sources:
                evidence_sources.append(filename)
            if len(evidence_sources) >= 10:
                break

        lines: List[str] = [f"Case #{case.id} evidence trace:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        lines.append("")
        lines.append("Claim trace:")
        if claim_trace:
            for item in claim_trace[:8]:
                claim = self._normalize_text(item.get("claim"))
                support = item.get("supporting_documents") or []
                status = self._normalize_text(item.get("status")) or "unknown"
                note = self._normalize_text(item.get("note"))
                support_text = ", ".join(str(doc).strip() for doc in support if str(doc).strip()) or "no direct support yet"
                line = f"- {claim} [{status}]: {support_text}"
                if note:
                    line += f" ({note})"
                lines.append(line)
        else:
            lines.append("- No claim trace was extracted yet.")

        if unsupported_claims:
            lines.append("")
            lines.append("Unsupported claims:")
            lines.extend(f"- {item}" for item in unsupported_claims[:5])

        if next_steps:
            lines.append("")
            lines.append("Recommended follow-up:")
            lines.extend(f"- {item}" for item in next_steps[:6])

        if evidence_sources:
            lines.append("")
            lines.append("Evidence reviewed:")
            lines.extend(f"- {item}" for item in evidence_sources[:8])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used evidence trace heuristic synthesis",
            "confidence": str(payload.get("confidence") or ("high" if claim_trace else "medium")),
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }

    def _monitor_deadlines_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        document_id: Optional[int] = None,
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        focus_document_name = None
        if case_id is None and document_id is not None:
            focus_document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
            case_id = focus_document.case_id
            focus_document_name = focus_document.filename

        if case_id is None:
            return {
                "answer": "Please open a case first so I can monitor deadlines and obligations.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)

        if document_id is not None and focus_document_name is None:
            focus_document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
            focus_document_case_id = self._coerce_optional_int(focus_document.case_id)
            case_identity = self._coerce_optional_int(case.id)
            if focus_document_case_id != case_identity:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found in the selected case.",
                )
            focus_document_name = self._text_or_empty(focus_document.filename) or None

        if not documents and not consultations:
            return {
                "answer": f"Case {case.id} has no documents or consultations yet, so deadline monitoring cannot run.",
                "used_fallback": True,
                "fallback_reason": "No case evidence found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents,
        )

        monitor_result = deadline_obligation_agent.monitor_deadlines(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            consultations=consultations,
            reasoning_payload=reasoning_payload,
            objective=(objective or "Monitor deadlines, notice windows, cure periods, and live obligations.")
            + (f" Focus on document: {focus_document_name}." if str(focus_document_name or "").strip() else ""),
        )

        if not monitor_result.success:
            return {
                "answer": "I could not build a deadline monitor yet.",
                "used_fallback": True,
                "fallback_reason": monitor_result.error or "Deadline monitor agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        payload = monitor_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("deadline_summary") or ""),
            fallback=f"Case #{case.id} deadline monitoring is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        deadline_items = payload.get("deadline_items") or []
        obligation_items = payload.get("obligation_items") or []
        next_actions = self._normalize_next_steps(payload.get("next_actions") or [])

        lines: List[str] = [f"Case #{case.id} deadline monitor:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        if deadline_items:
            lines.append("")
            lines.append("Deadline signals:")
            for item in deadline_items[:8]:
                label = self._normalize_text(item.get("label"))
                value = self._normalize_text(item.get("value"))
                source = self._normalize_text(item.get("source"))
                urgency = self._normalize_text(item.get("urgency")) or "medium"
                if label and value:
                    line = f"- {label}: {value} [{urgency}]"
                    if source:
                        line += f" (source: {source})"
                    lines.append(line)

        if obligation_items:
            lines.append("")
            lines.append("Live obligations:")
            for item in obligation_items[:8]:
                obligation = self._normalize_text(item.get("obligation"))
                due_date = self._normalize_text(item.get("due_date"))
                source = self._normalize_text(item.get("source"))
                priority = self._normalize_text(item.get("priority")) or "medium"
                note = self._normalize_text(item.get("note"))
                if obligation:
                    line = f"- {obligation} [{priority}]"
                    if due_date:
                        line += f" due: {due_date}"
                    if note:
                        line += f" ({note})"
                    if source:
                        line += f" (source: {source})"
                    lines.append(line)

        if next_actions:
            lines.append("")
            lines.append("Recommended next steps:")
            lines.extend(f"- {item}" for item in next_actions[:6])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used deadline monitor heuristic synthesis",
            "confidence": str(payload.get("confidence") or ("high" if deadline_items or obligation_items else "medium")),
            "scope": "case",
            "sources": (reasoning_payload.get("sources") or fallback_sources)[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }

    def _draft_contract_redline_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        document_id: Optional[int] = None,
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        if case_id is None and document_id is not None:
            focused_document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
            case_id = focused_document.case_id

        if case_id is None:
            return {
                "answer": "Please open a case first so I can draft a contract redline.",
                "used_fallback": True,
                "fallback_reason": "No case context provided",
                "confidence": "low",
                "scope": "global",
                "sources": [],
            }

        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        case_documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if document_id is not None:
            focused_document = self._get_document_or_404(db=db, tenant_id=tenant_id, document_id=document_id)
            focused_document_case_id = self._coerce_optional_int(focused_document.case_id)
            case_identity = self._coerce_optional_int(case.id)
            if focused_document_case_id != case_identity:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found in the selected case.",
                )
            focused_document_id = self._coerce_optional_int(focused_document.id)
            documents = [focused_document] + [
                document
                for document in case_documents
                if self._coerce_optional_int(document.id) != focused_document_id
            ]
            focus_document_name = self._text_or_empty(focused_document.filename) or None
        else:
            documents = case_documents
            focus_document_name = None

        if not documents:
            return {
                "answer": f"Case {case.id} has no documents yet, so contract redlining cannot run.",
                "used_fallback": True,
                "fallback_reason": "No case documents found",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        redline_result = contract_redline_agent.draft_redline(
            case_id=case.id,
            case_title=case.title,
            documents=documents,
            objective=self._normalize_contract_redline_objective(
                objective or "Draft a practical contract redline with clause-level suggestions, fallback positions, and source documents."
            ),
            focus_document_name=focus_document_name,
        )

        if not redline_result.success:
            return {
                "answer": "I could not draft a contract redline yet.",
                "used_fallback": True,
                "fallback_reason": redline_result.error or "Contract redline agent failed",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        payload = redline_result.payload
        summary_text = self._to_clean_summary_paragraph(
            str(payload.get("redline_summary") or ""),
            fallback=f"Case #{case.id} contract redline guidance is available but no concise summary was produced.",
            max_sentences=2,
            max_chars=420,
        )
        clause_rows = payload.get("clause_rows") or []
        priority_changes = self._normalize_next_steps(payload.get("priority_changes") or [])
        fallback_positions = self._normalize_next_steps(payload.get("fallback_positions") or [])
        risk_notes = self._normalize_next_steps(payload.get("risk_notes") or [])
        target_document = self._normalize_text(payload.get("target_document"))

        lines: List[str] = [f"Case #{case.id} contract redline:"]
        lines.append("")
        lines.append("Summary:")
        lines.append(summary_text)

        if target_document:
            lines.extend(["", "Target document:", f"- {target_document}"])

        if clause_rows:
            lines.append("")
            lines.append("Clause-level edits:")
            for item in clause_rows[:8]:
                clause = self._normalize_text(item.get("clause"))
                issue = self._normalize_text(item.get("issue"))
                suggestion = self._normalize_text(item.get("suggestion"))
                fallback_position_text = self._normalize_text(item.get("fallback_position"))
                source_documents = item.get("source_documents") or []
                source_text = ", ".join(self._normalize_text(doc) for doc in source_documents if self._normalize_text(doc))
                if clause:
                    line = f"- {clause}: {issue or 'Review required.'}"
                    if suggestion:
                        line += f" Suggested change: {suggestion}."
                    if fallback_position_text:
                        line += f" Fallback: {fallback_position_text}."
                    if source_text:
                        line += f" Sources: {source_text}."
                    lines.append(line)

        if priority_changes:
            lines.append("")
            lines.append("Priority changes:")
            lines.extend(f"- {item}" for item in priority_changes[:6])

        if risk_notes:
            lines.append("")
            lines.append("Risk notes:")
            lines.extend(f"- {item}" for item in risk_notes[:6])

        if fallback_positions:
            lines.append("")
            lines.append("Fallback positions:")
            lines.extend(f"- {item}" for item in fallback_positions[:5])

        fallback_sources: List[Dict[str, Any]] = []
        for document in documents:
            source_text = self._text_or_empty(document.summary_short) or self._text_or_empty(document.summary)
            if source_text:
                fallback_sources.append(self._build_source(document=document, snippet=source_text))

        used_llm = bool(payload.get("used_llm"))
        return {
            "answer": "\n".join(lines).strip(),
            "used_fallback": not used_llm,
            "fallback_reason": None if used_llm else "Used contract redline heuristic synthesis",
            "confidence": str(payload.get("confidence") or ("high" if clause_rows else "medium")),
            "scope": "case",
            "sources": fallback_sources[:10],
            "jurisdiction": jurisdiction_context,
            "structured_result": payload,
        }

    def _analyze_case_risks(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
        risk_request_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        for document in documents:
            self._ensure_document_summary(db=db, document=document)

        reasoning_payload = self._run_case_reasoning(
            db=db,
            tenant_id=tenant_id,
            case=case,
            documents=documents
        )
        lowered_request = self._normalize_text(risk_request_text).lower()
        wants_operational = (
            "operational" in lowered_request
            or "business risk" in lowered_request
            or "operations risk" in lowered_request
        )
        wants_legal = "legal" in lowered_request or not wants_operational

        target_default = 6 if wants_legal and wants_operational else 5
        target_count = min(max(requested_count or target_default, 1), 12)

        ranked_entries = self._build_ranked_case_risks(
            reasoning_payload=reasoning_payload,
            wants_legal=wants_legal,
            wants_operational=wants_operational,
        )

        if ranked_entries:
            return {
                "answer": self._format_ranked_case_risks_answer(
                    case_id=case.id,
                    ranked_entries=ranked_entries,
                    target_count=target_count,
                    wants_legal=wants_legal,
                    wants_operational=wants_operational,
                ),
                "used_fallback": not bool(reasoning_payload.get("used_llm")),
                "fallback_reason": None if reasoning_payload.get("used_llm") else "Used case reasoning agent heuristic synthesis",
                "confidence": "high" if reasoning_payload.get("used_llm") else "medium",
                "scope": "case",
                "sources": (reasoning_payload.get("sources") or [])[:10],
                "jurisdiction": jurisdiction_context,
            }

        rag_result = self.rag_service.answer_question(
            db=db,
            tenant_id=tenant_id,
            question="What legal risks, missing clauses, missing evidence, or timeline issues are mentioned in this case?",
            top_k=5,
            case_id=case.id,
            document_id=None
        )
        rag_result["scope"] = "case"
        rag_result["jurisdiction"] = jurisdiction_context
        return rag_result

    def _draft_client_email_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case_summary = self._summarize_case(db=db, tenant_id=tenant_id, case_id=case_id)
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)

        draft_result = drafting_agent.draft_client_update_email(
            case_id=case.id,
            case_title=case.title,
            case_summary=case_summary["answer"],
            jurisdiction_country=case.jurisdiction_country,
        )
        draft_text = (draft_result.payload.get("email_body") or "").strip()

        if draft_text:
            try:
                artifact_versioning_service.create_version(
                    db=db,
                    tenant_id=tenant_id,
                    artifact_type="case_email",
                    content=draft_text,
                    case_id=case.id,
                    source_kind="agent_generation",
                    metadata={
                        "case_title": case.title,
                        "used_llm": bool(draft_result.payload.get("used_llm")),
                    },
                    auto_select=True,
                )
            except Exception:
                pass

        artifact_context = self._build_artifact_context(
            db=db,
            tenant_id=tenant_id,
            artifact_type="case_email",
            case_id=case.id,
        )

        return {
            "answer": draft_text,
            "used_fallback": not bool(draft_result.payload.get("used_llm")),
            "fallback_reason": None if draft_result.payload.get("used_llm") else "Used drafting agent template fallback",
            "confidence": "high" if draft_result.payload.get("used_llm") else "medium",
            "scope": "case",
            "sources": case_summary["sources"],
            "artifact": artifact_context,
            "jurisdiction": jurisdiction_context,
        }

    def _draft_internal_email_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case_summary = self._summarize_case(db=db, tenant_id=tenant_id, case_id=case_id)
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        sources = case_summary.get("sources") or []
        document_names: list[str] = []
        for source in sources:
            filename = self._normalize_text(source.get("filename") if isinstance(source, dict) else "")
            if filename and filename not in document_names:
                document_names.append(filename)
        documents_text = ", ".join(document_names[:8]) if document_names else "the current case record"

        summary_text = str(case_summary.get("answer") or "").strip()
        concise_overview = self._extract_internal_overview_sentence(summary_text, case.title)

        internal_email_lines = [
            f"Subject: Internal update - case #{case.id} ({case.title})",
            "",
            "Dear Supervising Lawyer,",
            "",
            (
                f"Case #{case.id} is currently centered on {concise_overview}. Reviewed documents: {documents_text}. "
                "Recommended next step: keep a short response window, preserve the factual record, and decide whether a narrower without-prejudice proposal should follow."
            ),
            "",
            "Best regards,",
            "Legal AI Platform",
        ]

        artifact_context = self._build_artifact_context(
            db=db,
            tenant_id=tenant_id,
            artifact_type="case_email",
            case_id=case.id,
        )

        return {
            "answer": "\n".join(internal_email_lines).strip(),
            "used_fallback": True,
            "fallback_reason": "Used deterministic internal update template",
            "confidence": "high",
            "scope": "case",
            "sources": case_summary["sources"],
            "artifact": artifact_context,
            "jurisdiction": jurisdiction_context,
        }

    def _draft_partner_strategy_note_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case_summary = self._summarize_case(db=db, tenant_id=tenant_id, case_id=case_id)
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        sources = case_summary.get("sources") or []

        document_names: list[str] = []
        for source in sources:
            filename = self._normalize_text(source.get("filename") if isinstance(source, dict) else "")
            if filename and filename not in document_names:
                document_names.append(filename)

        documents_text = ", ".join(document_names[:8]) if document_names else "the current case record"
        summary_text = str(case_summary.get("answer") or "").strip()
        concise_overview = self._extract_internal_overview_sentence(summary_text, case.title)

        note_lines = [
            f"Partner-ready strategy note - case #{case.id} ({case.title})",
            "",
            (
                f"Case #{case.id} is best framed as {concise_overview}. Reviewed documents: {documents_text}. "
                "The current leverage sits in the facts, dates, and any unresolved documentary gaps, so the clean next move is to keep the ask narrow, preserve concessions, and hold a short without-prejudice fallback in reserve if the other side does not move."
            ),
        ]

        artifact_context = self._build_artifact_context(
            db=db,
            tenant_id=tenant_id,
            artifact_type="case_email",
            case_id=case.id,
        )

        return {
            "answer": "\n".join(note_lines).strip(),
            "used_fallback": True,
            "fallback_reason": "Used deterministic partner strategy note template",
            "confidence": "high",
            "scope": "case",
            "sources": case_summary["sources"],
            "artifact": artifact_context,
            "jurisdiction": jurisdiction_context,
        }

    @staticmethod
    def _extract_internal_overview_sentence(summary_text: str, case_title: str) -> str:
        cleaned_lines = [
            line.strip()
            for line in str(summary_text or "").splitlines()
            if line.strip()
            and not line.startswith("Case #")
            and not line.startswith("Overall Case Overview:")
            and not line.startswith("Documents Summary:")
            and not line.startswith("Key Takeaways:")
            and not line.startswith("Important Dates:")
            and not line.startswith("Recommended Next Steps:")
        ]
        if cleaned_lines:
            return CopilotService._trim_internal_sentence(cleaned_lines[0], 220)

        return CopilotService._trim_internal_sentence(case_title or "the current case record", 220)

    @staticmethod
    def _trim_internal_sentence(text: str, limit: int) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "").strip())
        if len(cleaned) <= limit:
            return cleaned.rstrip(". ")
        return cleaned[: limit - 1].rstrip(" ,;:-") + "..."

    def _draft_negotiation_strategy(
        self,
        *,
        objective: str,
        horizon_days: int,
        use_external_research: bool,
        case_context: Dict[str, Any] | None = None,
        case_snapshot: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        strategy_result = negotiation_strategy_agent.draft_strategy(
            objective=objective,
            horizon_days=horizon_days,
            case_context=case_context,
            case_snapshot=case_snapshot,
            use_external_research=use_external_research,
        )

        payload = strategy_result.payload
        lines = ["Negotiation strategy:"]

        summary = self._normalize_text(payload.get("strategy_summary"))
        if summary:
            lines.append(summary)

        case_basis = payload.get("case_basis") or []
        if case_basis:
            lines.extend(["", "Case basis:"])
            lines.extend(f"- {item}" for item in case_basis[:5])

        opening_position = self._normalize_text(payload.get("opening_position"))
        if opening_position:
            lines.extend(["", "Opening position:", f"- {opening_position}"])

        target_outcome = self._normalize_text(payload.get("target_outcome"))
        if target_outcome:
            lines.extend(["", "Target outcome:", f"- {target_outcome}"])

        red_lines = payload.get("red_lines") or []
        if red_lines:
            lines.extend(["", "Red lines:"])
            lines.extend(f"- {item}" for item in red_lines[:5])

        concessions = payload.get("concessions") or []
        if concessions:
            lines.extend(["", "Concession ladder:"])
            lines.extend(f"- {item}" for item in concessions[:5])

        day_by_day_plan = payload.get("day_by_day_plan") or []
        if day_by_day_plan:
            lines.extend(["", f"{min(max(int(horizon_days or 15), 1), 30)}-day plan:"])
            lines.extend(f"- {item}" for item in day_by_day_plan[:10])

        fallback_options = payload.get("fallback_options") or []
        if fallback_options:
            lines.extend(["", "Fallback options:"])
            lines.extend(f"- {item}" for item in fallback_options[:5])

        web_references = payload.get("web_references") or []
        if web_references:
            lines.extend(["", "Web references:"])
            lines.extend(f"- {item}" for item in web_references[:3])

        closing_position = self._normalize_text(payload.get("closing_position"))
        if closing_position:
            lines.extend(["", "Close:", f"- {closing_position}"])

        answer_text = "\n".join(lines).strip()

        return {
            "answer": answer_text,
            "used_fallback": not bool(payload.get("used_llm")),
            "fallback_reason": None if payload.get("used_llm") else "Used negotiation strategy agent template fallback",
            "confidence": "high" if payload.get("used_llm") else "medium",
            "scope": "global",
            "sources": [],
            "structured_result": payload,
        }

    def _review_case_booking(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        consultations = self._get_case_consultation_requests(db=db, tenant_id=tenant_id, case_id=case.id)

        booking_result = booking_agent.analyze_consultations(
            case_id=case.id,
            case_title=case.title,
            consultations=consultations,
        )

        if booking_result.success:
            payload = booking_result.payload
            answer_lines = [
                payload.get("narrative_summary") or f"Booking overview for case {case.id}.",
                "",
                f"Booking intent: {payload.get('booking_intent') or 'not_detected'}",
                f"Urgency: {payload.get('urgency_level') or 'normal'}",
                f"Preferred schedule: {payload.get('preferred_schedule') or 'Not provided'}",
                f"Recommended action: {payload.get('recommended_action') or 'Follow up with the client to confirm scheduling.'}",
            ]
            return {
                "answer": "\n".join(answer_lines).strip(),
                "used_fallback": not bool(payload.get("used_llm")),
                "fallback_reason": None if payload.get("used_llm") else "Used booking agent heuristic synthesis",
                "confidence": "high" if payload.get("booking_intent") == "requested" else "medium",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        return {
            "answer": "No consultation booking details are available for this case yet.",
            "used_fallback": True,
            "fallback_reason": booking_result.error or "Booking agent failed",
            "confidence": "low",
            "scope": "case",
            "sources": [],
            "jurisdiction": jurisdiction_context,
        }

    def _compare_case_documents(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        case = self._get_case_or_404(db=db, tenant_id=tenant_id, case_id=case_id)
        jurisdiction_context = jurisdiction_context_service.get_response_context(case.jurisdiction_country)
        documents = self._get_case_documents(db=db, tenant_id=tenant_id, case_id=case.id)

        if len(documents) < 2:
            return {
                "answer": f"Case {case.id} does not contain enough documents to compare.",
                "used_fallback": True,
                "fallback_reason": "Need at least two documents",
                "confidence": "low",
                "scope": "case",
                "sources": [],
                "jurisdiction": jurisdiction_context,
            }

        sources: List[Dict[str, Any]] = []

        for document in documents[:10]:
            document = self._ensure_document_summary(db=db, document=document)
            summary = self._normalize_text(
                document.summary_short
                or document.summary
                or (document.redacted_text or document.extracted_text or "")[:250]
            )
            if summary:
                sources.append(self._build_source(document=document, snippet=summary))

        comparison_result = document_comparison_agent.compare_case_documents(
            case_id=case.id,
            documents=documents,
        )

        return {
            "answer": comparison_result.payload.get("comparison_text") or f"Comparison overview for case {case.id} is not available.",
            "used_fallback": not bool(comparison_result.payload.get("used_llm")),
            "fallback_reason": None if comparison_result.payload.get("used_llm") else "Used document comparison agent heuristic synthesis",
            "confidence": "high" if comparison_result.success else "low",
            "scope": "case",
            "sources": sources[:10],
            "jurisdiction": jurisdiction_context,
        }
