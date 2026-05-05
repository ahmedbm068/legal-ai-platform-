# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from backend.services.ai import copilot_service_constants as copilot_constants
from backend.services.ai.agents.prompt_correction_agent import prompt_correction_agent
from backend.services.ai.llm_gateway import llm_gateway

logger = logging.getLogger(__name__)


class CopilotIntentRoutingMixin:
    """Intent classification and routing logic extracted from CopilotService.

    Provides:
      - input normalization (_normalize_role, _normalize_mode, _normalize_reasoning_level)
      - mode-routing decisions (_should_use_trust_engine, _chat_mode_needs_rag)
      - scope/permission gating (_apply_workspace_scope, _validate_scope_permissions)
      - conversation-memory routing (_apply_conversation_memory, _build_history_context)
      - chat-mode responses (_respond_in_chat_mode, _build_chat_greeting_answer, ...)
      - guard responses (_permission_denied_response, _agent_mode_required_response, ...)
    """

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
        if CopilotIntentRoutingMixin._looks_like_conversational_opening(lowered):
            return False
        if copilot_constants.CHAT_THANKS_PATTERN.search(lowered):
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
            "evaluate_case_evidence",
            "trace_case_evidence",
            "compare_case_documents",
            "monitor_deadlines_case",
        }
        if intent in document_action_intents and (case_id is not None or document_id is not None):
            return True
        # Drafting intents always need the execution agent (not chat LLM) when a case
        # is in scope, regardless of whether the clean_query retains "case #".
        drafting_intents = {
            "draft_client_email_case",
            "draft_internal_email_case",
            "draft_partner_strategy_note_case",
            "draft_contract_redline_case",
        }
        if intent in drafting_intents and case_id is not None:
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
        if copilot_constants.CHAT_GREETING_PATTERN.search(compact):
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
            return CopilotIntentRoutingMixin._build_chat_greeting_answer(user_role="assistant")
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
                for token in ["draft", "write", "prepare", "send email", "email to client", "client update email", "mail to"]
            ):
                next_parsed["intent"] = "draft_client_email_case"
                next_parsed["case_id"] = workspace_case_id
                next_parsed["target_type"] = "case"
                next_parsed["target_id"] = workspace_case_id
            else:
                # Generic analysis question in a case workspace — route to ask_case
                next_parsed["intent"] = "ask_case"
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


