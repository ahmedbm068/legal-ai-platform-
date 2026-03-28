from __future__ import annotations

import re
from typing import Any

from backend.services.ai.legal_text_formatter import LegalTextFormatter


class TranscriptIntakeService:
    EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    PHONE_PATTERN = re.compile(r"(?:(?:\+|00)\d{1,3}[\s\-]?)?(?:\d[\s\-]?){8,14}\d")
    DATE_PATTERN = re.compile(
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|next week|this week|"
        r"\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|"
        r"\d{1,2}\s+(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4})\b",
        re.IGNORECASE,
    )
    TIME_PATTERN = re.compile(r"\b(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", re.IGNORECASE)

    BOOKING_KEYWORDS = [
        "book", "booking", "schedule", "appointment", "consultation", "session", "meet", "meeting", "call back"
    ]
    URGENT_KEYWORDS = ["urgent", "asap", "immediately", "emergency", "deadline", "tomorrow", "today"]
    HIGH_PRIORITY_KEYWORDS = ["soon", "quickly", "this week", "next week"]

    LEGAL_AREA_KEYWORDS = {
        "employment": ["employment", "salary", "dismissal", "termination", "workplace", "employer", "employee"],
        "contract": ["contract", "agreement", "invoice", "payment", "supplier", "buyer", "breach"],
        "family": ["family", "divorce", "custody", "marriage", "child support"],
        "property": ["property", "landlord", "tenant", "lease", "rent", "real estate"],
        "litigation": ["court", "judge", "complaint", "lawsuit", "hearing", "appeal", "evidence"],
        "commercial": ["company", "commercial", "shareholder", "business", "corporate"],
    }

    def build_intake(self, transcript_text: str) -> dict[str, Any]:
        cleaned = LegalTextFormatter.prepare_for_summary(transcript_text, max_chars=12000)
        lowered = cleaned.lower()

        client_name = self._extract_name(cleaned)
        client_email = self._extract_email(cleaned)
        client_phone = self._extract_phone(cleaned)
        booking_intent = "requested" if any(keyword in lowered for keyword in self.BOOKING_KEYWORDS) else "not_detected"
        urgency_level = self._detect_urgency(lowered)
        legal_area = self._detect_legal_area(lowered)
        preferred_schedule = self._extract_schedule(cleaned)
        issue_summary = self._build_issue_summary(cleaned)
        case_description = self._build_case_description(cleaned)
        intake_notes = self._build_intake_notes(cleaned, booking_intent, urgency_level, preferred_schedule)

        return {
            "client_name": client_name,
            "client_email": client_email,
            "client_phone": client_phone,
            "booking_intent": booking_intent,
            "urgency_level": urgency_level,
            "legal_area": legal_area,
            "preferred_schedule": preferred_schedule,
            "issue_summary": issue_summary,
            "extracted_case_description": case_description,
            "intake_notes": intake_notes,
            "extraction_source": "transcript_intake_heuristic_v1",
        }

    def _extract_name(self, text: str) -> str | None:
        patterns = [
            r"\bmy name is\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b",
            r"\bi am\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b",
            r"\bthis is\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_email(self, text: str) -> str | None:
        match = self.EMAIL_PATTERN.search(text)
        return match.group(0) if match else None

    def _extract_phone(self, text: str) -> str | None:
        match = self.PHONE_PATTERN.search(text)
        if not match:
            return None

        phone = re.sub(r"\s+", " ", match.group(0)).strip()
        digits = re.sub(r"\D", "", phone)
        return phone if len(digits) >= 8 else None

    def _detect_urgency(self, lowered: str) -> str:
        if any(keyword in lowered for keyword in self.URGENT_KEYWORDS):
            return "urgent"
        if any(keyword in lowered for keyword in self.HIGH_PRIORITY_KEYWORDS):
            return "high"
        return "normal"

    def _detect_legal_area(self, lowered: str) -> str | None:
        best_area = None
        best_score = 0

        for area, keywords in self.LEGAL_AREA_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in lowered)
            if score > best_score:
                best_area = area
                best_score = score

        return best_area

    def _extract_schedule(self, text: str) -> str | None:
        date_match = self.DATE_PATTERN.search(text)
        time_match = self.TIME_PATTERN.search(text)

        if date_match and time_match:
            return f"{date_match.group(0)} {time_match.group(0)}"
        if date_match:
            return date_match.group(0)
        if time_match:
            return time_match.group(0)
        return None

    def _build_issue_summary(self, text: str) -> str:
        sentences = self._extract_relevant_sentences(text)
        if not sentences:
            return "Client described a legal issue during the voice intake, but the summary needs manual review."
        return " ".join(sentences[:2])

    def _build_case_description(self, text: str) -> str | None:
        sentences = self._extract_relevant_sentences(text)
        if not sentences:
            return None
        return " ".join(sentences[:4])

    def _build_intake_notes(
        self,
        text: str,
        booking_intent: str,
        urgency_level: str,
        preferred_schedule: str | None
    ) -> str:
        notes: list[str] = []

        if booking_intent == "requested":
            notes.append("Client appears to be requesting a consultation or scheduling action.")
        if urgency_level != "normal":
            notes.append(f"Urgency level detected: {urgency_level}.")
        if preferred_schedule:
            notes.append(f"Preferred schedule reference detected: {preferred_schedule}.")

        if not notes:
            notes.append("Transcript was converted into an intake summary, but no strong booking signal was detected.")

        return " ".join(notes)

    def _extract_relevant_sentences(self, text: str) -> list[str]:
        normalized = text.replace("\n", " ")
        sentences = re.split(r"(?<=[.!?])\s+", normalized)

        scored: list[tuple[int, str]] = []
        for sentence in sentences:
            cleaned = self._clean_sentence(sentence)
            if len(cleaned) < 25:
                continue

            lowered = cleaned.lower()
            score = 0
            if any(keyword in lowered for keyword in self.BOOKING_KEYWORDS):
                score += 1
            if any(keyword in lowered for keyword in self.URGENT_KEYWORDS + self.HIGH_PRIORITY_KEYWORDS):
                score += 1
            if any(keyword in lowered for keywords in self.LEGAL_AREA_KEYWORDS.values() for keyword in keywords):
                score += 3
            if "my name is" in lowered or "this is" in lowered:
                score -= 2
            if self.EMAIL_PATTERN.search(cleaned) or self.PHONE_PATTERN.search(cleaned):
                score -= 1

            scored.append((score, cleaned))

        scored.sort(key=lambda item: item[0], reverse=True)

        results: list[str] = []
        for _, sentence in scored:
            if sentence not in results:
                results.append(sentence)
            if len(results) >= 4:
                break

        return results

    @staticmethod
    def _clean_sentence(value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip(" ,;:-")
        return value


transcript_intake_service = TranscriptIntakeService()
