from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models.case import Case
from backend.models.client import Client
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.booking_agent import booking_agent
from backend.services.ai.agents.case_reasoning_agent import case_reasoning_agent
from backend.services.ai.agents.drafting_agent import drafting_agent
from backend.services.ai.agents.document_comparison_agent import document_comparison_agent
from backend.services.ai.agents.prompt_optimizer_agent import prompt_optimizer_agent
from backend.services.ai.agents.prompt_correction_agent import prompt_correction_agent
from backend.services.ai.agents.timeline_agent import timeline_agent
from backend.services.ai.artifact_versioning_service import artifact_versioning_service
from backend.services.ai.command_parsing_service import command_parsing_service
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.external_research_service import external_research_service
from backend.services.ai.jurisdiction_context_service import jurisdiction_context_service
from backend.services.ai.legal_search_mode_service import legal_search_mode_service
from backend.services.ai.llm_gateway import llm_gateway
from backend.services.ai.rag_service import RagService
from backend.services.ai.summarization_service import summarization_service


class CopilotService:
    READ_ONLY_ROLES = {"admin", "lawyer", "assistant", "client"}
    CASE_WRITE_ROLES = {"admin", "lawyer"}
    CLIENT_ALLOWED_INTENTS = {
        "list_cases",
        "list_case_documents",
        "list_case_appointments",
        "summarize_case",
        "summarize_document",
        "summarize_and_analyze_risks_case",
        "analyze_risks_case",
        "list_deadlines_case",
        "build_timeline_case",
        "compare_case_documents",
        "review_booking_case",
        "ask_case",
        "ask_document",
        "ask_global",
        "summarize_global",
    }
    CRUD_INTENTS = {
        "create_case",
        "create_client",
        "create_case_appointment",
        "update_case_status",
        "request_document_upload",
        "request_audio_upload",
    }
    ACTION_CATEGORY_BY_INTENT = {
        "create_case": "crud",
        "create_client": "crud",
        "list_cases": "query",
        "list_clients": "query",
        "list_case_documents": "query",
        "list_case_appointments": "query",
        "request_document_upload": "crud",
        "request_audio_upload": "crud",
        "create_case_appointment": "crud",
        "update_case_status": "crud",
        "optimize_prompt": "analysis",
        "summarize_case": "analysis",
        "summarize_document": "analysis",
        "summarize_and_analyze_risks_case": "analysis",
        "analyze_risks_case": "analysis",
        "list_deadlines_case": "analysis",
        "build_timeline_case": "analysis",
        "compare_case_documents": "analysis",
        "review_booking_case": "analysis",
        "draft_client_email_case": "analysis",
        "ask_case": "query",
        "ask_document": "query",
        "ask_global": "query",
        "summarize_global": "analysis",
    }
    LEGAL_SEARCH_ELIGIBLE_INTENTS = {
        "ask_document",
        "ask_case",
        "ask_global",
        "summarize_global",
        "summarize_case",
        "summarize_document",
        "summarize_and_analyze_risks_case",
        "analyze_risks_case",
        "list_deadlines_case",
        "build_timeline_case",
        "compare_case_documents",
    }
    NUMBER_WORDS = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }
    FOLLOW_UP_COUNT_PATTERN = re.compile(
        r"\b(?:just|only|exactly|give\s+me|show\s+me|list)?\s*(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
        re.IGNORECASE,
    )
    FOLLOW_UP_HINT_PATTERN = re.compile(
        r"\b(just|only|same|again|i meant|shorter|one)\b",
        re.IGNORECASE,
    )
    SUMMARY_STOP_HEADERS = (
        "main issues:",
        "key dates:",
        "legal risks:",
        "recommended next steps:",
        "risk assessment:",
        "practical next steps:",
        "deadlines:",
        "notice periods:",
        "other time references:",
        "evidence basis:",
    )

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

    @staticmethod
    def _normalize_role(value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {"admin", "lawyer", "assistant", "client"} else "assistant"

    @staticmethod
    def _normalize_mode(value: str | None) -> str:
        normalized = str(value or "default").strip().lower()
        return normalized or "default"

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
        match = self.FOLLOW_UP_COUNT_PATTERN.search(lowered)
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
                "analyze_risks_case",
                "review_booking_case",
                "draft_client_email_case",
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
        agent_mode: bool = False,
        workspace_case_id: Optional[int] = None,
        workspace_document_id: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        preparsed_command: Optional[Dict[str, Any]] = None,
        skip_autocorrect: bool = False,
        preoptimized_query: Optional[str] = None,
        allowed_case_ids: Optional[List[int]] = None,
        allowed_document_ids: Optional[List[int]] = None,
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
                    "summarize_and_analyze_risks_case",
                    "summarize_case",
                    "analyze_risks_case",
                    "list_deadlines_case",
                    "build_timeline_case",
                    "review_booking_case",
                    "draft_client_email_case",
                    "compare_case_documents",
                    "list_case_documents",
                    "list_case_appointments",
                    "request_document_upload",
                    "request_audio_upload",
                    "create_case_appointment",
                    "update_case_status",
                    "list_cases",
                    "list_clients",
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

        handlers = {
            "create_case": lambda: self._create_case_action(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=normalized_role,
                requested_case_title=parsed.get("requested_case_title"),
                requested_case_description=parsed.get("requested_case_description"),
                requested_client_id=parsed.get("requested_client_id"),
                requested_client_name=parsed.get("requested_client_name"),
                requested_jurisdiction_country=parsed.get("requested_jurisdiction_country"),
                workspace_case_id=workspace_case_id,
                raw_message=parsed.get("raw_message") or message,
            ),
            "create_client": lambda: self._create_client_action(
                db=db,
                tenant_id=tenant_id,
                user_role=normalized_role,
                requested_client_name=parsed.get("requested_client_name"),
                raw_message=parsed.get("raw_message") or message,
            ),
            "list_cases": lambda: self._list_cases(
                db=db,
                tenant_id=tenant_id,
                allowed_case_ids=normalized_allowed_case_ids,
            ),
            "list_clients": lambda: self._list_clients(
                db=db,
                tenant_id=tenant_id,
            ),
            "list_case_documents": lambda: self._list_case_documents(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"],
            ),
            "list_case_appointments": lambda: self._list_case_appointments(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"],
            ),
            "request_document_upload": lambda: self._request_document_upload_action(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed.get("case_id"),
            ),
            "request_audio_upload": lambda: self._request_audio_upload_action(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed.get("case_id"),
            ),
            "create_case_appointment": lambda: self._create_case_appointment(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"],
                user_role=normalized_role,
                message=parsed.get("clean_query") or parsed.get("raw_message") or message,
            ),
            "update_case_status": lambda: self._update_case_status(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"],
                user_role=normalized_role,
                user_id=user_id,
                requested_status=parsed.get("requested_case_status"),
            ),
            "optimize_prompt": lambda: self._optimize_prompt_intent(
                raw_prompt=parsed["clean_query"] or parsed["raw_message"],
                intent=parsed["intent"],
                target_type=parsed["target_type"],
                target_id=parsed["target_id"],
            ),
            "summarize_case": lambda: self._summarize_case(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "summarize_and_analyze_risks_case": lambda: self._summarize_and_analyze_case_risks(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"],
                requested_count=parsed.get("requested_count"),
            ),
            "summarize_document": lambda: self._summarize_document(
                db=db,
                tenant_id=tenant_id,
                document_id=parsed["document_id"]
            ),
            "list_deadlines_case": lambda: self._list_case_deadlines(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"],
                requested_count=parsed.get("requested_count"),
            ),
            "build_timeline_case": lambda: self._build_case_timeline(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "analyze_risks_case": lambda: self._analyze_case_risks(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"],
                requested_count=parsed.get("requested_count"),
            ),
            "review_booking_case": lambda: self._review_case_booking(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "draft_client_email_case": lambda: self._draft_client_email_for_case(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "compare_case_documents": lambda: self._compare_case_documents(
                db=db,
                tenant_id=tenant_id,
                case_id=parsed["case_id"]
            ),
            "ask_document": lambda: self._answer_with_optional_external_research(
                db=db,
                tenant_id=tenant_id,
                question=resolved_query,
                top_k=top_k,
                case_id=None,
                document_id=parsed["document_id"],
                use_external_research=use_external_research,
                intent="ask_document",
                target_type="document",
                target_id=parsed["document_id"],
                already_optimized=bool(preoptimized_query),
            ),
            "ask_case": lambda: self._answer_with_optional_external_research(
                db=db,
                tenant_id=tenant_id,
                question=resolved_query,
                top_k=top_k,
                case_id=parsed["case_id"],
                document_id=None,
                use_external_research=use_external_research,
                intent="ask_case",
                target_type="case",
                target_id=parsed["case_id"],
                already_optimized=bool(preoptimized_query),
            ),
            "ask_global": lambda: self._answer_with_optional_external_research(
                db=db,
                tenant_id=tenant_id,
                question=resolved_query,
                top_k=top_k,
                case_id=None,
                document_id=None,
                use_external_research=use_external_research,
                intent="ask_global",
                target_type="global",
                target_id=None,
                already_optimized=bool(preoptimized_query),
            ),
            "summarize_global": lambda: self._answer_with_optional_external_research(
                db=db,
                tenant_id=tenant_id,
                question=resolved_query,
                top_k=top_k,
                case_id=None,
                document_id=None,
                use_external_research=use_external_research,
                intent="summarize_global",
                target_type="global",
                target_id=None,
                already_optimized=bool(preoptimized_query),
            ),
        }

        is_legal_search_mode = normalized_mode == "legal_search" and intent in self.LEGAL_SEARCH_ELIGIBLE_INTENTS

        if is_legal_search_mode:
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
            )
        elif intent in self.CRUD_INTENTS and not agent_mode:
            result = self._agent_mode_required_response(action=intent)
        else:
            result = handlers.get(intent, self._unsupported_intent_response)()
        action_category = "legal_search" if is_legal_search_mode else self.ACTION_CATEGORY_BY_INTENT.get(intent, "analysis")
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
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
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
                        "upload_timestamp": row.upload_timestamp.isoformat() if row.upload_timestamp else None,
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
        if user_role == "lawyer" and user_id and case.lawyer_id != user_id:
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
            return {
                **base_result,
                "jurisdiction": jurisdiction_context,
            }

        research = external_research_service.search(
            query=optimized_question,
            max_results=max(3, min(top_k, 8)),
        )
        if not research.get("used_external"):
            return {
                **base_result,
                "jurisdiction": jurisdiction_context,
            }

        external_results = research.get("results") or []
        if not external_results:
            return {
                **base_result,
                "jurisdiction": jurisdiction_context,
            }

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

        return {
            "answer": synthesized_answer or base_result.get("answer", ""),
            "used_fallback": bool(base_result.get("used_fallback")),
            "fallback_reason": base_result.get("fallback_reason"),
            "confidence": base_result.get("confidence", "medium"),
            "scope": base_result.get("scope", "global"),
            "sources": merged_sources[:20],
            "citations": merged_citations[:12],
            "cache": base_result.get("cache", {"hit": False, "backend": "none"}),
            "jurisdiction": jurisdiction_context,
        }

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
            if url:
                snippet = f"{snippet} ({url})".strip()
            citations.append(
                {
                    "label": title[:120] or "Web Research",
                    "document_id": None,
                    "case_id": None,
                    "snippet": snippet[:280],
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
        if not document.insights_json:
            return {}

        try:
            payload = json.loads(document.insights_json)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _ensure_document_summary(self, db: Session, document: Document) -> Document:
        if document.summary and document.summary.strip():
            return document

        if not (document.redacted_text or document.extracted_text):
            try:
                self.document_pipeline.process_document(document=document, db=db)
                db.refresh(document)
            except Exception:
                return document

        if not (document.redacted_text or document.extracted_text):
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
        if not (document.redacted_text or document.extracted_text):
            notes.append("no extractable text detected")

        details = "; ".join(notes) if notes else "summary generation is pending"
        return (
            f"{document.filename} (processing={processing_status}, summary={summary_status}): {details}."
        )

    @staticmethod
    def _normalize_text(value: Optional[str]) -> str:
        return (value or "").strip()

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
            cleaned = str(item or "").strip().rstrip(".")
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
                    if lines:
                        break
                    continue
                lowered = line.lower()
                if lowered in stop_headers:
                    break
                if line.startswith("-"):
                    continue
                if cls._looks_like_prompt_template_noise(line):
                    continue
                lines.append(line)
                if len(lines) >= 2:
                    break

            concise = " ".join(lines).strip()
            concise = re.sub(r"\s+", " ", concise)
            if concise:
                return concise[:420]

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

    @classmethod
    def _expand_risks_from_reasoning(cls, reasoning_payload: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        for issue in reasoning_payload.get("main_issues") or []:
            text = str(issue or "").strip()
            lowered = text.lower()
            if not text:
                continue
            if any(token in lowered for token in ["breach", "termination", "dispute", "deadline", "notice", "liability"]):
                candidates.append(text)
        return cls._normalize_risk_items(candidates)

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
            "confidence": "high" if document.summary else "medium",
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
        case_id: Optional[int]
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
        document_types: List[str] = []
        parties: List[str] = []
        paragraphs: List[str] = []
        sources: List[Dict[str, Any]] = []
        unavailable_documents: List[str] = []

        for document in documents:
            insights = self._safe_load_insights(document)

            document_type = self._normalize_text(insights.get("document_type") or document.document_type)
            if document_type and document_type not in document_types:
                document_types.append(document_type)

            for party in insights.get("parties_detected", []):
                party_text = self._normalize_text(party)
                if party_text and party_text not in parties and self._is_reasonable_party(party_text):
                    parties.append(party_text)

            source_text = (
                document.summary
                or document.summary_short
                or self._normalize_text(insights.get("general_summary"))
                or (document.redacted_text or document.extracted_text or "")[:1200]
            )
            if source_text:
                doc_paragraph = self._to_clean_summary_paragraph(
                    source_text,
                    fallback=f"A concise summary is not available yet for {document.filename}.",
                )
            else:
                doc_paragraph = "Summary unavailable until document processing completes."
                unavailable_documents.append(self._document_summary_unavailable_reason(document))
            paragraphs.append(f"Document {len(paragraphs) + 1} ({document.filename}): {doc_paragraph}")
            sources.append(self._build_source(document=document, snippet=doc_paragraph))

        overview_parts: List[str] = [f"Case {case.id} ({case.title}) currently includes {len(documents)} document(s)."]
        if document_types:
            overview_parts.append(f"The file set mainly includes {', '.join(document_types[:4])}.")
        if parties:
            overview_parts.append(f"The main parties across these documents are {', '.join(parties[:5])}.")

        case_overview_paragraph = self._to_clean_summary_paragraph(
            " ".join(overview_parts),
            fallback=f"Case {case.id} ({case.title}) currently includes {len(documents)} document(s).",
            max_sentences=4,
            max_chars=640,
        )

        answer = "\n\n".join([case_overview_paragraph, *paragraphs]).strip()
        if unavailable_documents:
            answer = (
                f"{answer}\n\n"
                "Document processing status:\n"
                + "\n".join(f"- {item}" for item in unavailable_documents[:10])
            ).strip()

        complete_document_count = sum(1 for doc in documents if (doc.summary or "").strip())
        if complete_document_count == len(documents):
            confidence = "high"
        elif complete_document_count == 0:
            confidence = "low"
        else:
            confidence = "medium"

        return {
            "answer": answer,
            "used_fallback": bool(unavailable_documents),
            "fallback_reason": "documents_missing_processed_text" if unavailable_documents else None,
            "confidence": confidence,
            "scope": "case",
            "sources": sources[:10],
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
            sources: List[Dict[str, Any]] = []
            for document in documents:
                insights = self._safe_load_insights(document)
                for item in insights.get("important_dates", []):
                    label = self._normalize_text(item.get("label"))
                    value = self._normalize_text(item.get("value"))
                    if label and value:
                        sources.append(self._build_source(document=document, snippet=f"{label}: {value}"))

            return {
                "answer": timeline_result.payload.get("timeline_text") or "No timeline could be generated.",
                "used_fallback": not bool(timeline_result.payload.get("used_llm")),
                "fallback_reason": None if timeline_result.payload.get("used_llm") else "Used timeline agent heuristic synthesis",
                "confidence": "high" if timeline_result.payload.get("events") else "medium",
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

    def _analyze_case_risks(
        self,
        db: Session,
        tenant_id: int,
        case_id: Optional[int],
        requested_count: Optional[int] = None,
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
        collected_risks = self._normalize_risk_items(reasoning_payload.get("legal_risks") or [])
        if requested_count:
            expanded = self._expand_risks_from_reasoning(reasoning_payload)
            for item in expanded:
                if item not in collected_risks:
                    collected_risks.append(item)
                if len(collected_risks) >= requested_count:
                    break

        target_count = min(max(requested_count or 6, 1), 12)

        if collected_risks:
            return {
                "answer": (
                    f"Detected legal risks for case {case.id}:\n\n"
                    + "\n".join(f"- {risk}" for risk in collected_risks[:target_count])
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
