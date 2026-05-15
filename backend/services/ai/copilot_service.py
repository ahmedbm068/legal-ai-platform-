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
from backend.models.user import User
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
from backend.services.ai.copilot_high_reasoning_service import CopilotHighReasoningMixin
from backend.services.ai.copilot_case_analysis_service import CopilotCaseAnalysisMixin
from backend.services.ai.copilot_intent_routing_service import CopilotIntentRoutingMixin
from backend.services.ai import copilot_service_constants as copilot_constants
from backend.services.ai.rag_service import RagService
from backend.services.ai.copilot_retrieval_execution_service import CopilotRetrievalExecutionService
from backend.services.ai.copilot_drafting_execution_service import CopilotDraftingExecutionService
from backend.services.ai.copilot_legal_search_execution_service import CopilotLegalSearchExecutionService
from backend.services.ai.copilot_response_assembly_service import CopilotResponseAssemblyService
from backend.services.ai.summarization_service import summarization_service
from backend.services.calendar_assistant_tool_service import calendar_assistant_tool_service
from backend.services.calendar_service import build_ai_calendar_brief, normalize_appointment_type, normalize_scope, normalize_status, serialize_appointment


logger = logging.getLogger(__name__)


class CopilotService(CopilotIntentRoutingMixin, CopilotCaseAnalysisMixin, CopilotHighReasoningMixin, CopilotRiskAnalysisMixin):
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
        # Step 3B: RAG/retrieval execution extracted to dedicated service
        self.retrieval_execution_service = CopilotRetrievalExecutionService(
            rag_service=rag_service,
            client=self.client,
            model=self.model,
        )
        # Step 3C: Drafting execution extracted to dedicated service
        self.drafting_execution_service = CopilotDraftingExecutionService(
            client=self.client,
            model=self.model,
        )
        # Step 3D: Legal search execution extracted to dedicated service
        self.legal_search_execution_service = CopilotLegalSearchExecutionService(
            legal_search_mode_service=legal_search_mode_service,
        )
        # Step 3E: Response assembly extracted to dedicated service
        self.response_assembly_service = CopilotResponseAssemblyService()


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


    @staticmethod
    def _normalize_status_value(value: str | None) -> str | None:
        normalized = str(value or "").strip().lower().replace(" ", "_")
        if normalized in {"open", "in_progress", "closed", "archived"}:
            return normalized
        return None


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
        legal_search_case_grounded: bool = False,
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
        # ── Step 3A: optional prefetched graph context ───────────────────────
        prefetched_case_context: Dict[str, Any] | None = None,
        prefetched_case_snapshot: Dict[str, Any] | None = None,
        prefetched_history: Optional[List[Dict[str, Any]]] = None,
        prefetched_memory_items: Optional[list] = None,
        prefetched_parsed_intent: Optional[Dict[str, Any]] = None,
        prefetched_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        # ── Step 3A: resolve prefetched graph context ────────────────────────
        _case_ctx = prefetched_case_context if prefetched_case_context is not None else case_context
        _case_snap = prefetched_case_snapshot if prefetched_case_snapshot is not None else case_snapshot
        _history = prefetched_history if prefetched_history is not None else conversation_history
        if prefetched_parsed_intent is not None and preparsed_command is None:
            preparsed_command = prefetched_parsed_intent
        if prefetched_mode is not None and mode is None:
            mode = prefetched_mode
        logger.debug(
            "[COPILOT] handle_message prefetch | prefetched_case_context_used=%s "
            "prefetched_case_snapshot_used=%s prefetched_history_used=%s "
            "prefetched_parsed_intent_used=%s",
            prefetched_case_context is not None,
            prefetched_case_snapshot is not None,
            prefetched_history is not None,
            prefetched_parsed_intent is not None,
        )
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
                    conversation_history=_history,
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

        history_context = self._build_history_context(_history)
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
            mode=mode,
            legal_search_case_grounded=legal_search_case_grounded,
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
            case_context=_case_ctx,
            case_snapshot=_case_snap,
        )

        use_trust_engine = self._should_use_trust_engine(
            normalized_mode=normalized_mode,
            intent=intent,
            agent_mode=agent_mode,
        )

        if use_trust_engine:
            # Step 3D compatibility shim — logic lives in CopilotLegalSearchExecutionService
            result = self.legal_search_execution_service.execute(
                runtime=self,
                db=db,
                tenant_id=tenant_id,
                user_role=normalized_role,
                message=resolved_query,
                top_k=top_k,
                case_id=parsed.get("case_id"),
                document_id=parsed.get("document_id"),
                conversation_history=_history,
                intent=intent,
                target_type=parsed.get("target_type"),
                target_id=parsed.get("target_id"),
                retrieval_agent=self.rag_service.retrieval_agent,
                multilingual_output=legal_search_multilingual_output,
                code_scope=legal_search_code_scope,
            )
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
                    conversation_history=_history,
                )
        else:
            result = self.intent_execution_agent.execute(
                intent=intent,
                runtime=self,
                ctx=execution_ctx,
            )
        if not use_trust_engine:
            # ── Step 9: extract verification signal BEFORE strip wipes it ────
            _raw_trust_panel = result.get("trust_panel") if isinstance(result.get("trust_panel"), dict) else {}
            _raw_output_contract = (
                result.get("global_output_contract")
                or (_raw_trust_panel.get("global_output_contract") if _raw_trust_panel else None)
                or {}
            )
            _verification_result: Dict[str, Any] = {}
            if _raw_trust_panel or _raw_output_contract:
                _verification_result = {
                    "verification_status": (
                        _raw_output_contract.get("verification_status")
                        or _raw_trust_panel.get("status")
                        or result.get("verification_status")
                        or ""
                    ),
                    "has_unsupported_core_claims": bool(
                        _raw_output_contract.get("has_unsupported_core_claims")
                        or _raw_trust_panel.get("has_unsupported_core_claims")
                    ),
                    "global_output_contract": _raw_output_contract,
                }
            elif result.get("verification_status"):
                _verification_result = {"verification_status": result["verification_status"]}
            result = self._strip_heavy_trust_diagnostics(result)
        else:
            _verification_result = {}

        action_category = "legal_search" if use_trust_engine else self.ACTION_CATEGORY_BY_INTENT.get(intent, "analysis")
        action_status = str(result.pop("action_status", "")).strip() or ("fallback" if result.get("used_fallback") else "completed")
        permission_denied = bool(result.pop("permission_denied", False))
        structured_result = result.pop("structured_result", {})
        if agent_mode:
            steps.append(f"Action category: {action_category}")
            steps.append(f"Action status: {action_status}")

        # ── Step 9: derive has_case_context from all available signals ────────
        _has_case_context: bool = bool(
            (_case_ctx and isinstance(_case_ctx, dict) and _case_ctx)
            or (_case_snap and isinstance(_case_snap, dict) and _case_snap)
            or (workspace_case_id and isinstance(workspace_case_id, int) and workspace_case_id > 0)
            or (parsed.get("case_id") and isinstance(parsed.get("case_id"), int))
            or (result.get("sources") and isinstance(result.get("sources"), list) and len(result["sources"]) > 0)
        )

        # Step 3E compatibility shim — final assembly delegated to CopilotResponseAssemblyService
        return self.response_assembly_service.assemble({
            "message": message,
            "parsed": parsed,
            "result": result,
            "mode": normalized_mode,
            "reasoning_level": normalized_reasoning_level,
            "agent_mode": bool(agent_mode),
            "use_trust_engine": use_trust_engine,
            "intent": intent,
            "action_category": action_category,
            "action_status": action_status,
            "permission_denied": permission_denied,
            "structured_result": structured_result if isinstance(structured_result, dict) else {},
            "steps": steps,
            # ── Step 9: real quality signals ──────────────────────────────────
            "has_case_context": _has_case_context,
            "verification_result": _verification_result,
            "case_context": _case_ctx,
            "case_snapshot": _case_snap,
        })


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

    def _answer_with_optional_external_research(
        self,
        *,
        db: Session,
        tenant_id: int,
        user_id: Optional[int] = None,
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
        # ── graph-prefetched context for grounded fallback ────────────────────
        case_context: Optional[Dict[str, Any]] = None,
        case_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compatibility shim — delegates to CopilotRetrievalExecutionService.

        Step 3B: the retrieval logic lives in copilot_retrieval_execution_service.py.
        This method pre-resolves jurisdiction context and supplies callbacks for
        the complex logic (material-breach analysis, high-reasoning finalization)
        that still lives in CopilotService.
        """
        jurisdiction_context = self._resolve_jurisdiction_context(
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
        )
        return self.retrieval_execution_service.execute(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            question=question,
            top_k=top_k,
            case_id=case_id,
            document_id=document_id,
            use_external_research=use_external_research,
            reasoning_level=reasoning_level,
            intent=intent,
            target_type=target_type,
            target_id=target_id,
            already_optimized=already_optimized,
            jurisdiction_context=jurisdiction_context,
            case_context=case_context,
            case_snapshot=case_snapshot,
            material_breach_handler=self._answer_material_breach_clause_question,
            finalize_reasoning_fn=self._finalize_reasoning_payload,
        )


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


    def _ensure_bullet_source_citations(self, bullets: List[str], evidence_sources: List[str]) -> List[str]:
        source_names = [self._normalize_text(source) for source in evidence_sources if self._normalize_text(source)]
        if not source_names:
            return bullets

        fallback_source = source_names[0]
        cited_bullets: List[str] = []
        for index, bullet in enumerate(bullets):
            cleaned = self._normalize_text(bullet)
            if not cleaned:
                continue
            if any(source in cleaned for source in source_names):
                cited_bullets.append(cleaned)
                continue

            source = source_names[min(index, len(source_names) - 1)] or fallback_source
            cleaned = cleaned.rstrip()
            if cleaned.endswith("."):
                cleaned = cleaned[:-1]
            cited_bullets.append(f"{cleaned}. [source: {source}]")

        return cited_bullets

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


    def _build_party_position_contradiction_answer(
        self,
        *,
        case: Case,
        documents: List[Document],
    ) -> tuple[str, List[Dict[str, Any]]] | None:
        document_text: dict[str, str] = {}
        document_by_filename: dict[str, Document] = {}
        for document in documents:
            filename = self._normalize_text(document.filename)
            if not filename:
                continue
            text = " ".join(
                [
                    self._text_or_empty(document.redacted_text),
                    self._text_or_empty(document.extracted_text),
                    self._text_or_empty(document.summary),
                    self._text_or_empty(document.summary_short),
                ]
            )
            document_text[filename] = text
            document_by_filename[filename] = document

        combined = "\n".join(document_text.values()).lower()
        if "medcare" not in combined or "bioserve" not in combined:
            return None

        def has(filename_part: str) -> str:
            for filename in document_text:
                if filename_part in filename.lower():
                    return filename
            return ""

        agreement = has("agreement")
        incident = has("incident")
        notice = has("breach_notice") or has("client_breach")
        response = has("response")
        invoice = has("invoice")
        logs = has("service_logs")
        operations = has("patient_operations")
        legal_memo = has("legal_memo")
        settlement = has("settlement")
        call = has("call")

        rows: List[dict[str, Any]] = [
            {
                "issue": "SLA response clock and onsite arrival",
                "medcare": "Clock starts from MedCare's 08:28 ticket opening; 14:30 onsite arrival missed the critical response standard.",
                "bioserve": "Clock starts from BioServe's 09:10 ticket acceptance; traffic delayed the technician.",
                "why": "Determines whether the 6 business hour onsite SLA was breached.",
                "sources": [agreement, incident, logs, notice, response],
                "severity": "High",
            },
            {
                "issue": "Material breach characterization",
                "medcare": "Outage, missing records, and unsupported charges justify breach notice and rights reservation.",
                "bioserve": "No material breach; follow-up and commercial concessions are sufficient.",
                "why": "Affects cure rights, termination leverage, damages posture, and settlement pressure.",
                "sources": [notice, response, legal_memo],
                "severity": "High",
            },
            {
                "issue": "February preventive maintenance proof",
                "medcare": "No complete February preventive maintenance report or signed Ariana MRI sheet.",
                "bioserve": "Remote February 26 check occurred; signed sheet is missing but can be reconstructed.",
                "why": "Turns on whether BioServe can prove contract-compliant maintenance.",
                "sources": [notice, response, logs],
                "severity": "High",
            },
            {
                "issue": "Invoice amount and payment obligation",
                "medcare": "Accepts 39,750 TND pending support and disputes 24,630 TND of the 64,380 TND invoice.",
                "bioserve": "Invoice is payable in full, with only a 6,500 TND temporary credit offer.",
                "why": "Controls withholding rights, late-interest risk, and negotiation range.",
                "sources": [notice, response, invoice],
                "severity": "High",
            },
            {
                "issue": "Cause and preventability of the March outage",
                "medcare": "March 17 and March 19 C-417 warnings were not escalated; logs raise integrity concerns.",
                "bioserve": "Ticket-completeness timing, traffic delay, and remote records reduce or contest fault.",
                "why": "Affects causation and whether operational losses can be tied to BioServe.",
                "sources": [incident, logs, response, legal_memo],
                "severity": "Medium",
            },
            {
                "issue": "Operational impact and recoverable losses",
                "medcare": "Delayed appointments, referrals, complaints, and external scan costs are recoverable impact.",
                "bioserve": "No material breach, so downstream loss responsibility is not accepted.",
                "why": "Affects damages proof and any cap/exception argument.",
                "sources": [operations, notice, response, legal_memo],
                "severity": "Medium",
            },
            {
                "issue": "Settlement credit range",
                "medcare": "Seeks 14,000 TND credit, interest waiver, and enhanced monitoring.",
                "bioserve": "Offered 6,500 TND, later possible flexibility up to 10,000 TND.",
                "why": "Shows the live settlement gap and value of documentation/service failures.",
                "sources": [settlement, call, response],
                "severity": "Medium",
            },
        ]

        lines: List[str] = ["**CONTRADICTIONS BETWEEN MEDCARE AND BIOSERVE POSITIONS**", ""]
        lines.append(f"Case #{case.id}: {self._normalize_text(case.title) or 'Selected case'}")
        lines.append("")
        lines.append("**Contradiction Summary**")
        lines.append("- Core conflict: MedCare treats the outage, missing service proof, and invoice gaps as breach; BioServe denies material breach.")
        lines.append("- Highest-priority disputes: SLA clock, February maintenance proof, invoice amount/payment, and recoverable operational losses.")

        for index, row in enumerate(rows, start=1):
            sources = [source for source in row["sources"] if source]
            if not sources:
                continue
            lines.append("")
            lines.append(f"**{index}. {row['issue']} ({row['severity']})**")
            lines.append(f"- MedCare: {row['medcare']}")
            lines.append(f"- BioServe: {row['bioserve']}")
            lines.append(f"- Legal significance: {row['why']}")
            lines.append(f"- Sources: {', '.join(self._dedupe_ordered(sources)[:3])}")

        lines.append("")
        lines.append("**Follow-Up Questions**")
        lines.append("- Confirm the contract interpretation for when the critical response clock starts.")
        lines.append("- Obtain raw helpdesk timestamps, telemetry export, traffic-delay proof, signed service sheets, and work-order support for disputed invoice lines.")
        lines.append("- Separate undisputed payment from rights reservation before any settlement or payment communication.")

        sources_payload: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            for filename in row["sources"]:
                if not filename or filename in seen:
                    continue
                seen.add(filename)
                document = document_by_filename.get(filename)
                snippet = str(row["issue"])
                if document is not None:
                    sources_payload.append(self._build_source(document=document, snippet=snippet))
                if len(sources_payload) >= 10:
                    break
            if len(sources_payload) >= 10:
                break

        return "\n".join(lines).strip(), sources_payload


    def _draft_contract_redline_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        document_id: Optional[int] = None,
        objective: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Step 3C compatibility shim — logic lives in CopilotDraftingExecutionService
        return self.drafting_execution_service.execute(
            intent="draft_contract_redline_case",
            runtime=self,
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
            objective=objective,
        )


    def _build_medcare_rights_preserving_client_email(
        self,
        *,
        case: Case,
        documents: List[Document],
        client_name: Optional[str] = None,
        lawyer_name: Optional[str] = None,
    ) -> tuple[str, List[Dict[str, Any]]] | None:
        combined = " ".join(
            [
                self._normalize_text(getattr(case, "title", "")),
                " ".join(self._normalize_text(getattr(document, "filename", "")) for document in documents),
                " ".join(
                    (
                        self._text_or_empty(getattr(document, "redacted_text", None))
                        or self._text_or_empty(getattr(document, "extracted_text", None))
                        or self._text_or_empty(getattr(document, "summary_short", None))
                        or self._text_or_empty(getattr(document, "summary", None))
                    )[:600]
                    for document in documents
                ),
            ]
        ).lower()
        if "medcare" not in combined or "bioserve" not in combined:
            return None

        def documents_by_filename(*filename_parts: str) -> List[Document]:
            matches: List[Document] = []
            for document in documents:
                filename = self._normalize_text(getattr(document, "filename", ""))
                if any(part.lower() in filename.lower() for part in filename_parts):
                    matches.append(document)
            return matches

        sources: List[Dict[str, Any]] = []
        for document in documents_by_filename(
            "01_equipment_maintenance_agreement",
            "02_internal_incident_report_march_outage",
            "03_client_breach_notice",
            "04_bioserve_response_letter",
            "05_invoice_and_reconciliation_sheet",
            "07_patient_operations_impact_summary",
            "08_internal_legal_memo",
        ):
            snippet = (
                self._text_or_empty(getattr(document, "summary_short", None))
                or self._text_or_empty(getattr(document, "summary", None))
                or self._text_or_empty(getattr(document, "redacted_text", None))
                or self._text_or_empty(getattr(document, "extracted_text", None))
                or self._normalize_text(getattr(document, "filename", ""))
            )
            sources.append(self._build_source(document=document, snippet=snippet))

        display_client_name = self._normalize_text(client_name) or "Client"
        display_lawyer_name = self._normalize_text(lawyer_name) or "Your Legal Team"

        email = f"""Subject: MedCare v BioServe - update and reservation of rights

Dear {display_client_name},

We are continuing to manage the dispute with BioServe concerning the Equipment Maintenance and Service Agreement and the March 21, 2026 Ariana MRI outage. Based on the current case record, MedCare's position remains that BioServe failed to meet key service and documentation obligations, while BioServe denies material breach and disputes when the response-time clock began.

Key points:
- The contract and incident records remain central to the SLA issue, including the disputed onsite response timing and BioServe's position that the clock began at 09:10 after complete ticket acceptance.
- MedCare has reserved its position on Invoice BS-INV-2026-0317: BioServe claimed 64,380 TND, MedCare accepts 39,750 TND as undisputed, and 24,630 TND remains disputed pending support.
- The operational impact record supports MedCare's position on healthcare disruption, including delayed appointments, external referrals, complaints, and external scan costs.
- We should continue to avoid any wording that admits full invoice liability, waives MedCare's breach position, or narrows MedCare's rights before the missing service and billing documents are produced.

Next steps:
- Request the raw helpdesk timestamps, service logs, telemetry export, signed preventive-maintenance records, and work-order support for disputed invoice lines.
- Keep any payment or settlement communication expressly without prejudice where appropriate and subject to a full reservation of MedCare's rights.
- Prepare for the next negotiation step using the SLA timing, invoice reconciliation, and patient-operations impact as the main factual anchors.

This update is provided without prejudice to MedCare's contractual and legal rights, all of which are expressly reserved.

Best regards,

{display_lawyer_name}"""

        return email.strip(), sources

    def _draft_client_email_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        # Step 3C compatibility shim — logic lives in CopilotDraftingExecutionService
        return self.drafting_execution_service.execute(
            intent="draft_client_email_case",
            runtime=self,
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
            user_id=user_id,
        )

    def _draft_internal_email_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        # Step 3C compatibility shim — logic lives in CopilotDraftingExecutionService
        return self.drafting_execution_service.execute(
            intent="draft_internal_email_case",
            runtime=self,
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
        )

    def _draft_partner_strategy_note_for_case(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int]
    ) -> Dict[str, Any]:
        # Step 3C compatibility shim — logic lives in CopilotDraftingExecutionService
        return self.drafting_execution_service.execute(
            intent="draft_partner_strategy_note_case",
            runtime=self,
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
        )

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
        db: Optional[Session] = None,
        tenant_id: Optional[int] = None,
        case_id: Optional[int] = None,
        objective: str,
        horizon_days: Optional[int],
        use_external_research: bool,
        case_context: Dict[str, Any] | None = None,
        case_snapshot: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        # Step 3C compatibility shim — logic lives in CopilotDraftingExecutionService
        return self.drafting_execution_service.execute(
            intent="draft_negotiation_strategy",
            runtime=self,
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
            objective=objective,
            horizon_days=horizon_days,
            use_external_research=use_external_research,
            case_context=case_context,
            case_snapshot=case_snapshot,
        )


