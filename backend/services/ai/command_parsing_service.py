from __future__ import annotations

import re
from typing import Any, Dict, Optional


class CommandParsingService:
    CASE_PATTERN = re.compile(r"\bcase\s*#?\s*(\d+)\b", re.IGNORECASE)
    DOCUMENT_PATTERN = re.compile(r"\bdocument\s*#?\s*(\d+)\b", re.IGNORECASE)
    RISK_COUNT_PATTERN = re.compile(r"\b(?:top\s+)?(\d{1,2})\s+risks?\b", re.IGNORECASE)
    DEADLINE_COUNT_PATTERN = re.compile(r"\b(?:top\s+)?(\d{1,2})\s+deadlines?\b", re.IGNORECASE)

    def parse(self, message: str) -> Dict[str, Any]:
        original_message = (message or "").strip()
        lowered = original_message.lower()

        case_match = self.CASE_PATTERN.search(original_message)
        document_match = self.DOCUMENT_PATTERN.search(original_message)

        case_id = int(case_match.group(1)) if case_match else None
        document_id = int(document_match.group(1)) if document_match else None

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
        requested_count = self._extract_requested_count(
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
            "requested_count": requested_count,
            "confidence": confidence
        }

    def _detect_intent(self, lowered: str, target_type: Optional[str]) -> tuple[str, str]:
        if self._contains_any(lowered, ["optimize prompt", "improve prompt", "rewrite prompt", "better prompt", "prompt optimizer"]):
            return "optimize_prompt", "high"

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

        if self._contains_any(lowered, ["booking", "book", "consultation", "appointment", "session request", "schedule session"]):
            if target_type == "case":
                return "review_booking_case", "high"
            return "ask_global", "medium"

        if self._contains_any(lowered, ["risk", "risks", "missing evidence", "unresolved", "weakness", "exposure", "issue", "issues"]):
            if target_type == "case":
                return "analyze_risks_case", "high"
            if target_type == "document":
                return "ask_document", "medium"
            return "ask_global", "medium"

        if self._contains_any(lowered, ["summarize", "summary", "recap", "overview", "brief"]):
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

    def _extract_requested_count(
        self,
        *,
        lowered: str,
        intent: str,
    ) -> Optional[int]:
        if intent not in {"analyze_risks_case", "list_deadlines_case"}:
            return None

        if intent == "analyze_risks_case" and "risk" not in lowered:
            return None
        if intent == "list_deadlines_case" and not self._contains_any(lowered, ["deadline", "due date", "notice"]):
            return None

        if intent == "analyze_risks_case":
            match = self.RISK_COUNT_PATTERN.search(lowered)
        elif intent == "list_deadlines_case":
            match = self.DEADLINE_COUNT_PATTERN.search(lowered)
        else:
            match = None

        if not match:
            return None

        count = int(match.group(1))
        if count <= 0:
            return None

        return min(count, 12)


command_parsing_service = CommandParsingService()
