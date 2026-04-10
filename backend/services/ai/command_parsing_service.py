from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Optional


class CommandParsingService:
    CASE_PATTERN = re.compile(r"\bcase\s*#?\s*(\d+)\b", re.IGNORECASE)
    DOCUMENT_PATTERN = re.compile(r"\bdocument\s*#?\s*(\d+)\b", re.IGNORECASE)
    CLIENT_ID_PATTERN = re.compile(r"\bclient\s*#?\s*(\d+)\b", re.IGNORECASE)
    RISK_COUNT_PATTERN = re.compile(
        r"\b(?:top\s+|only\s+|just\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+risks?\b",
        re.IGNORECASE,
    )
    DEADLINE_COUNT_PATTERN = re.compile(
        r"\b(?:top\s+|only\s+|just\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+deadlines?\b",
        re.IGNORECASE,
    )
    SUMMARY_BULLET_COUNT_PATTERN = re.compile(
        r"\b(?:in|with|as)?\s*(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(?:bullet\s*points?|bullets?)\b",
        re.IGNORECASE,
    )
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
    SUMMARY_KEYWORDS = ["summarize", "summary", "recap", "overview", "brief", "synopsis", "tldr", "tl;dr"]
    SUMMARY_ONLY_HINTS = [
        "summary only",
        "only summary",
        "paragraph only",
        "no risks",
        "without risks",
        "no dates",
        "without dates",
        "no bullets",
        "just summary",
        "only a summary",
    ]
    RISK_KEYWORDS = [
        "risk",
        "risks",
        "danger",
        "dangers",
        "exposure",
        "exposures",
        "weakness",
        "weaknesses",
        "issue",
        "issues",
        "missing evidence",
        "unresolved",
        "liability",
        "liabilities",
    ]
    INSIGHT_KEYWORDS = [
        "insight",
        "insights",
        "key insight",
        "case insight",
        "strategic insight",
        "critical insight",
        "what stands out",
    ]
    CASE_MEMORY_KEYWORDS = [
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
    EVIDENCE_TRACE_KEYWORDS = [
        "trace evidence",
        "evidence trace",
        "claim trace",
        "claim to evidence",
        "claim-to-evidence",
        "evidence map",
        "source map",
        "support this claim",
        "supporting evidence",
        "back this up",
    ]
    DEADLINE_MONITOR_KEYWORDS = [
        "monitor deadlines",
        "deadline monitor",
        "deadline tracker",
        "track deadlines",
        "track obligations",
        "obligation monitor",
        "monitor obligations",
        "cure period",
        "notice window",
        "renewal deadline",
        "deadline register",
    ]
    CONTRACT_REDLINE_KEYWORDS = [
        "redline",
        "contract redline",
        "markup",
        "mark up",
        "revise the contract",
        "revise the agreement",
        "contract markup",
        "line by line",
        "clause changes",
        "annotate contract",
        "edit the contract",
    ]
    NEGOTIATION_KEYWORDS = [
        "negotiation",
        "negotiating",
        "settlement",
        "without prejudice",
        "counteroffer",
        "concession",
        "walk away",
        "walkaway",
        "deal",
        "offer",
        "compromise",
    ]
    NEGOTIATION_STRATEGY_KEYWORDS = [
        "strategy",
        "plan",
        "playbook",
        "approach",
        "tactics",
        "structure",
        "fallback",
        "fallback options",
        "proposal",
        "propose",
        "terms",
        "term sheet",
        "package",
        "settlement structure",
    ]
    CASE_STATUS_PATTERN = re.compile(
        r"\b(open|in\s+progress|in_progress|closed|archived)\b",
        re.IGNORECASE,
    )
    CASE_TITLE_PATTERN = re.compile(
        r"\b(?:case\s+(?:called|named)|(?:create|add)\s+(?:a\s+)?(?:new\s+)?case(?:\s+(?:called|named|titled))?)\s*[:\-]?\s*['\"]?([^\"'\n,]{2,180})",
        re.IGNORECASE,
    )
    CLIENT_NAME_PATTERN = re.compile(
        r"\bclient\b(?:\s*(?:is|=|named|called))?\s*[:\-]?\s*['\"]?([^\"'\n,]{2,160})",
        re.IGNORECASE,
    )
    CASE_DESCRIPTION_PATTERN = re.compile(
        r"\b(?:description|desc)\b(?:\s*(?:is|=|:))?\s*['\"]?([^\"'\n]{4,1200})",
        re.IGNORECASE,
    )
    LIST_CASE_KEYWORDS = [
        "list cases",
        "show cases",
        "my cases",
        "active cases",
        "all cases",
    ]
    LIST_CLIENT_KEYWORDS = [
        "list clients",
        "show clients",
        "my clients",
        "all clients",
        "client list",
    ]
    LIST_CASE_DOCUMENT_KEYWORDS = [
        "list documents",
        "show documents",
        "case documents",
        "documents in this case",
        "files in this case",
        "list files",
    ]
    LIST_APPOINTMENT_KEYWORDS = [
        "appointments",
        "consultations",
        "consultation requests",
        "booking requests",
        "meeting requests",
    ]
    CREATE_CASE_KEYWORDS = [
        "create case",
        "create a case",
        "create new case",
        "create a new case",
        "add case",
        "add a case",
        "add new case",
        "add a new case",
        "open new case",
        "open a new case",
    ]
    CREATE_CLIENT_KEYWORDS = [
        "create client",
        "create a client",
        "add client",
        "add a client",
        "new client",
        "register client",
    ]
    DOCUMENT_UPLOAD_KEYWORDS = [
        "upload document",
        "add document",
        "attach document",
        "upload file",
        "attach file",
        "upload pdf",
    ]
    AUDIO_UPLOAD_KEYWORDS = [
        "upload audio",
        "add audio",
        "upload voice",
        "upload voice note",
        "record voice",
        "record audio",
        "add voice note",
    ]
    CREATE_APPOINTMENT_KEYWORDS = [
        "create appointment",
        "schedule appointment",
        "book appointment",
        "new appointment",
        "create consultation",
        "schedule consultation",
        "book consultation",
    ]
    UPDATE_STATUS_KEYWORDS = [
        "update status",
        "set status",
        "change status",
        "mark case",
        "close case",
        "archive case",
        "reopen case",
    ]

    def parse(self, message: str) -> Dict[str, Any]:
        original_message = (message or "").strip()
        lowered = self._normalize_for_intent(original_message)

        case_match = self.CASE_PATTERN.search(original_message)
        document_match = self.DOCUMENT_PATTERN.search(original_message)
        client_id_match = self.CLIENT_ID_PATTERN.search(original_message)

        case_id = int(case_match.group(1)) if case_match else None
        document_id = int(document_match.group(1)) if document_match else None
        requested_client_id = int(client_id_match.group(1)) if client_id_match else None

        target_type: Optional[str] = None
        target_id: Optional[int] = None

        if document_id is not None:
            target_type = "document"
            target_id = document_id
        elif case_id is not None:
            target_type = "case"
            target_id = case_id

        intent, confidence = self._detect_intent(lowered=lowered, target_type=target_type)
        clean_query = self._clean_query(original_message)
        requested_case_status = self._extract_case_status(lowered=lowered, intent=intent)
        requested_case_title = self._extract_case_title(original_message=original_message, lowered=lowered, intent=intent)
        requested_client_name = self._extract_client_name(original_message=original_message, lowered=lowered, intent=intent)
        requested_case_description = self._extract_case_description(original_message=original_message, lowered=lowered, intent=intent)
        requested_jurisdiction_country = self._extract_jurisdiction_country(lowered=lowered, intent=intent)
        requested_count = self._extract_requested_count(
            lowered=lowered,
            intent=intent,
        )
        requested_horizon_days = self._extract_negotiation_horizon_days(lowered=lowered, intent=intent)
        requested_contractual_context = self._extract_summary_contractual_context(
            lowered=lowered,
            intent=intent,
        )

        return {
            "raw_message": original_message,
            "intent": intent,
            "target_type": target_type,
            "target_id": target_id,
            "case_id": case_id,
            "document_id": document_id,
            "clean_query": clean_query,
            "requested_case_status": requested_case_status,
            "requested_case_title": requested_case_title,
            "requested_case_description": requested_case_description,
            "requested_client_id": requested_client_id,
            "requested_client_name": requested_client_name,
            "requested_jurisdiction_country": requested_jurisdiction_country,
            "requested_count": requested_count,
            "requested_horizon_days": requested_horizon_days,
            "requested_contractual_context": requested_contractual_context,
            "confidence": confidence
        }

    def _detect_intent(self, lowered: str, target_type: Optional[str]) -> tuple[str, str]:
        if self._contains_any(lowered, self.CREATE_CASE_KEYWORDS):
            return "create_case", "high"

        if self._contains_any(lowered, self.CREATE_CLIENT_KEYWORDS):
            return "create_client", "high"

        if self._contains_any(lowered, self.DOCUMENT_UPLOAD_KEYWORDS):
            return "request_document_upload", "high"

        if self._contains_any(lowered, self.AUDIO_UPLOAD_KEYWORDS):
            return "request_audio_upload", "high"

        if self._contains_any(lowered, self.LIST_CLIENT_KEYWORDS):
            return "list_clients", "high"

        if self._contains_any(lowered, self.LIST_CASE_KEYWORDS):
            return "list_cases", "high"

        if target_type == "case" and self._contains_any(lowered, self.UPDATE_STATUS_KEYWORDS):
            return "update_case_status", "high"

        if target_type == "case" and self._contains_any(lowered, self.CREATE_APPOINTMENT_KEYWORDS):
            return "create_case_appointment", "medium"

        if target_type == "case" and self._contains_any(lowered, self.LIST_APPOINTMENT_KEYWORDS):
            return "list_case_appointments", "high"

        if target_type == "case" and self._contains_any(lowered, self.LIST_CASE_DOCUMENT_KEYWORDS):
            return "list_case_documents", "high"

        if self._contains_any(lowered, ["optimize prompt", "improve prompt", "rewrite prompt", "better prompt", "prompt optimizer"]):
            return "optimize_prompt", "high"

        if self._contains_any(lowered, self.EVIDENCE_TRACE_KEYWORDS):
            if target_type == "case" or self._contains_any(lowered, ["case", "matter", "workspace"]):
                return "trace_case_evidence", "high"
            return "trace_case_evidence", "medium"

        if self._contains_any(lowered, self.CASE_MEMORY_KEYWORDS):
            if target_type == "case" or self._contains_any(lowered, ["case", "matter", "workspace"]):
                return "generate_case_memory", "high"
            return "generate_case_memory", "medium"

        if self._contains_any(lowered, self.DEADLINE_MONITOR_KEYWORDS) or (
            "monitor" in lowered and self._contains_any(lowered, ["deadline", "obligation", "cure", "renewal", "notice"])
        ):
            if target_type == "case" or self._contains_any(lowered, ["case", "matter", "workspace"]):
                return "monitor_deadlines_case", "high"
            return "monitor_deadlines_case", "medium"

        if self._contains_any(lowered, self.CONTRACT_REDLINE_KEYWORDS):
            if target_type in {"case", "document"} or self._contains_any(lowered, ["case", "document", "file", "workspace", "agreement", "contract"]):
                return "draft_contract_redline_case", "high"
            return "draft_contract_redline_case", "medium"

        if self._contains_any(lowered, self.NEGOTIATION_KEYWORDS) and self._contains_any(lowered, self.NEGOTIATION_STRATEGY_KEYWORDS):
            return "draft_negotiation_strategy", "high"

        # Handle compound requests first: "summarize ... and analyze risks ..."
        if target_type == "case":
            wants_summary = self._looks_like_summary_request(lowered=lowered, target_type=target_type)
            wants_risks = self._contains_any(lowered, self.RISK_KEYWORDS)
            if wants_summary and self._contains_any(lowered, self.SUMMARY_ONLY_HINTS):
                return "summarize_case", "high"
            if wants_summary and wants_risks:
                return "summarize_and_analyze_risks_case", "high"

        if target_type == "document":
            wants_summary = self._looks_like_summary_request(lowered=lowered, target_type=target_type)
            if wants_summary and self._contains_any(lowered, self.SUMMARY_ONLY_HINTS):
                return "summarize_document", "high"

        if self._contains_any(lowered, ["draft", "write", "prepare"]) and self._contains_any(lowered, ["email", "mail", "client update"]):
            if target_type == "case":
                return "draft_client_email_case", "high"
            return "ask_global", "medium"

        if self._contains_any(lowered, ["deadline", "deadlines", "due date", "due dates", "notice period", "hearing date", "hearing dates", "time limit"]):
            if target_type == "case":
                return "list_deadlines_case", "high"
            if target_type == "document":
                return "ask_document", "medium"
            return "ask_global", "medium"

        if self._contains_any(lowered, ["timeline", "chronology", "chronological", "sequence of events", "case events"]):
            if target_type == "case":
                return "build_timeline_case", "high"
            return "ask_global", "medium"

        if self._contains_any(lowered, self.INSIGHT_KEYWORDS):
            if target_type == "case" or self._contains_any(lowered, ["case", "matter", "workspace"]):
                return "generate_case_insights", "high" if target_type == "case" else "medium"
            if target_type == "document":
                return "ask_document", "medium"
            return "generate_case_insights", "medium"

        if self._contains_any(lowered, ["booking", "book", "consultation", "appointment", "session request", "schedule session"]):
            if target_type == "case":
                return "review_booking_case", "high"
            return "ask_global", "medium"

        if self._contains_any(lowered, self.RISK_KEYWORDS):
            if target_type == "case":
                return "analyze_risks_case", "high"
            if target_type == "document":
                return "ask_document", "medium"
            return "ask_global", "medium"

        if self._looks_like_summary_request(lowered=lowered, target_type=target_type):
            if target_type == "case":
                return "summarize_case", "high"
            if target_type == "document":
                return "summarize_document", "high"
            return "summarize_global", "medium"

        if self._contains_any(lowered, ["compare", "comparison", "contradiction", "contradictions", "conflict", "conflicts", "inconsisten", "mismatch"]):
            if target_type == "case":
                return "compare_case_documents", "high"
            return "ask_global", "medium"

        if target_type == "case":
            return "ask_case", "medium"

        if target_type == "document":
            return "ask_document", "medium"

        return "ask_global", "low"

    def _clean_query(self, message: str) -> str:
        cleaned = self.CASE_PATTERN.sub("", message)
        cleaned = self.DOCUMENT_PATTERN.sub("", cleaned)

        cleaned = re.sub(
            r"^\s*(?:optimi[sz]e\s+prompt|improve\s+prompt|rewrite\s+prompt|better\s+prompt)\s*[:\-]\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\b(?:please|can you|could you|would you|for me|about|regarding)\b",
            "",
            cleaned,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r"\b(?:yo|hey|pls|plz|make me|gimme|give me)\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;!?-")
        cleaned = re.sub(
            r"\b(?:for|to|in|on|at|with|of|from|about|regarding)\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" .,:;!?-")
        return cleaned or message.strip()

    @staticmethod
    def _contains_any(text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _normalize_for_intent(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        normalized = normalized.lower()
        normalized = normalized.replace("/", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _looks_like_summary_request(self, *, lowered: str, target_type: Optional[str]) -> bool:
        if self._contains_any(lowered, self.SUMMARY_KEYWORDS):
            return True

        # In this product context, users often say "resume" meaning "summary/resume of the case".
        if "resume" not in lowered:
            return False

        if target_type in {"case", "document"}:
            return True

        return self._contains_any(lowered, ["case", "document", "file", "matter"])

    def _extract_requested_count(
        self,
        *,
        lowered: str,
        intent: str,
    ) -> Optional[int]:
        if intent not in {"analyze_risks_case", "list_deadlines_case", "summarize_case", "summarize_global", "draft_negotiation_strategy"}:
            return None

        if intent == "analyze_risks_case" and "risk" not in lowered:
            return None
        if intent == "list_deadlines_case" and not self._contains_any(lowered, ["deadline", "due date", "notice"]):
            return None
        if intent in {"summarize_case", "summarize_global"} and not self._contains_any(lowered, ["bullet", "bullet point", "bullets"]):
            return None
        if intent == "draft_negotiation_strategy" and not self._contains_any(lowered, ["day", "days", "week", "weeks", "timeline", "plan", "strategy"]):
            return None

        if intent == "analyze_risks_case":
            match = self.RISK_COUNT_PATTERN.search(lowered)
        elif intent == "list_deadlines_case":
            match = self.DEADLINE_COUNT_PATTERN.search(lowered)
        elif intent in {"summarize_case", "summarize_global"}:
            match = self.SUMMARY_BULLET_COUNT_PATTERN.search(lowered)
        elif intent == "draft_negotiation_strategy":
            match = re.search(r"\b(?:next\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(?:day|days|week|weeks)\b", lowered, re.IGNORECASE)
        else:
            match = None

        if not match:
            return None

        raw_count = match.group(1).lower()
        if raw_count.isdigit():
            count = int(raw_count)
        else:
            count = self.NUMBER_WORDS.get(raw_count, 0)
        if count <= 0:
            return None

        if intent == "draft_negotiation_strategy" and "week" in (match.group(0).lower() if match else ""):
            count *= 7

        return min(count, 12)

    def _extract_negotiation_horizon_days(self, *, lowered: str, intent: str) -> Optional[int]:
        if intent != "draft_negotiation_strategy":
            return None

        match = re.search(
            r"\b(?:next\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+(?:day|days|week|weeks)\b",
            lowered,
            re.IGNORECASE,
        )
        if not match:
            return None

        raw_count = match.group(1).lower()
        if raw_count.isdigit():
            count = int(raw_count)
        else:
            count = self.NUMBER_WORDS.get(raw_count, 0)
        if count <= 0:
            return None

        if "week" in match.group(0).lower():
            count *= 7
        return min(count, 30)

    def _extract_summary_contractual_context(self, *, lowered: str, intent: str) -> bool:
        if intent not in {"summarize_case", "summarize_global"}:
            return False

        return self._contains_any(
            lowered,
            [
                "contractual context",
                "contract context",
                "contractual",
                "contract terms",
                "agreement terms",
                "clause",
                "obligation",
                "obligations",
                "sla",
            ],
        )

    def _extract_case_status(self, *, lowered: str, intent: str) -> Optional[str]:
        if intent != "update_case_status":
            return None

        if "reopen" in lowered:
            return "open"
        if "close" in lowered:
            return "closed"
        if "archive" in lowered:
            return "archived"

        match = self.CASE_STATUS_PATTERN.search(lowered)
        if not match:
            return None

        normalized = match.group(1).strip().lower().replace(" ", "_")
        if normalized in {"open", "in_progress", "closed", "archived"}:
            return normalized
        return None

    def _extract_case_title(
        self,
        *,
        original_message: str,
        lowered: str,
        intent: str,
    ) -> Optional[str]:
        if intent != "create_case":
            return None

        match = self.CASE_TITLE_PATTERN.search(original_message)
        if match:
            candidate = match.group(1).strip()
            candidate = re.split(
                r"\s+\b(?:for|with|and|description|client|in|status)\b",
                candidate,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" .,:;!?-\"'")
            if len(candidate) >= 2:
                return candidate[:180]

        fallback = original_message
        fallback = re.sub(
            r"\b(?:yo|hey|pls|plz|please|can you|could you|would you)\b",
            "",
            fallback,
            flags=re.IGNORECASE,
        )
        fallback = re.sub(
            r"\b(?:create|add|open)\s+(?:a\s+)?(?:new\s+)?case\b",
            "",
            fallback,
            flags=re.IGNORECASE,
        )
        fallback = re.sub(
            r"\b(?:for|with)\s+client\b.*$",
            "",
            fallback,
            flags=re.IGNORECASE,
        )
        fallback = re.sub(r"\s+", " ", fallback).strip(" .,:;!?-\"'")
        if len(fallback) >= 2:
            return fallback[:180]
        return None

    def _extract_client_name(
        self,
        *,
        original_message: str,
        lowered: str,
        intent: str,
    ) -> Optional[str]:
        if intent not in {"create_case", "create_client"}:
            return None

        match = self.CLIENT_NAME_PATTERN.search(original_message)
        if match:
            candidate = match.group(1).strip()
            candidate = re.split(
                r"\s+\b(?:and|with|for|description|email|phone|address|status)\b",
                candidate,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" .,:;!?-\"'")
            if len(candidate) >= 2:
                return candidate[:160]
        return None

    def _extract_case_description(
        self,
        *,
        original_message: str,
        lowered: str,
        intent: str,
    ) -> Optional[str]:
        if intent != "create_case":
            return None

        match = self.CASE_DESCRIPTION_PATTERN.search(original_message)
        if match:
            candidate = match.group(1).strip().strip(" .,:;!?-\"'")
            if len(candidate) >= 4:
                return candidate[:1200]

        if "random description" in lowered or "any description" in lowered:
            return "__AUTO_DESCRIPTION__"

        return None

    def _extract_jurisdiction_country(self, *, lowered: str, intent: str) -> Optional[str]:
        if intent not in {"create_case", "update_case_status", "ask_case", "analyze_risks_case", "summarize_case", "generate_case_insights"}:
            return None

        if any(keyword in lowered for keyword in ["germany", "deutschland", "german", "deutsch"]):
            return "germany"
        if any(keyword in lowered for keyword in ["tunisia", "tunisian", "tunisie", "tunis"]):
            return "tunisia"
        return None


command_parsing_service = CommandParsingService()
