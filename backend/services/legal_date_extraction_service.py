from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from backend.api.calendar_schema import CalendarEventCreate
from backend.models.case import Case
from backend.models.document import Document
from backend.models.document_chunk import DocumentChunk
from backend.services.calendar_automation_hook_service import calendar_automation_hook_service
from backend.services.calendar_service import calendar_event_service


@dataclass(frozen=True)
class DateCandidate:
    title: str
    event_type: str
    priority: str
    start_datetime: datetime
    source_quote: str
    source_chunk_id: int | None
    confidence: float
    all_day: bool = True


class LegalDateExtractionService:
    MAX_EVENTS_PER_DOCUMENT = 20
    MONTH_NAMES = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    MONTH_PATTERN = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
    ISO_PATTERN = re.compile(r"\b(20\d{2}|19\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b")
    DMY_PATTERN = re.compile(r"\b(0?[1-9]|[12]\d|3[01])[-/.](0?[1-9]|1[0-2])[-/.]((?:20|19)?\d{2})\b")
    TEXTUAL_DMY_PATTERN = re.compile(
        rf"\b(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s+({MONTH_PATTERN})\s+((?:20|19)\d{{2}})\b",
        re.IGNORECASE,
    )
    TEXTUAL_MDY_PATTERN = re.compile(
        rf"\b({MONTH_PATTERN})\s+(0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?\s*,?\s+((?:20|19)\d{{2}})\b",
        re.IGNORECASE,
    )
    RELATIVE_PATTERN = re.compile(
        r"\b(?:within|no later than|not later than)\s+(\d{1,3})\s+(day|days|week|weeks|month|months)\b",
        re.IGNORECASE,
    )

    LEGAL_HINTS = {
        "hearing": ("hearing", "court", "tribunal", "session", "audience"),
        "filing_deadline": ("filing", "file", "submit", "submission", "response", "appeal"),
        "payment_due": ("payment", "invoice", "due", "installment", "amount", "fee"),
        "limitation_period": ("limitation", "prescription", "statute", "time-bar", "time barred"),
        "contract_date": ("contract", "effective", "expiry", "expiration", "renewal", "signature"),
        "deadline": ("deadline", "notice period", "within", "before", "after notification"),
        "meeting": ("meeting", "appointment", "call", "consultation"),
    }

    def extract_events_from_document(self, *, db: Session, document: Document) -> dict:
        if not document.case_id or not document.tenant_id:
            return self._empty(document, "missing_case_or_tenant")

        case = (
            db.query(Case)
            .filter(Case.id == document.case_id, Case.tenant_id == document.tenant_id, Case.deleted_at.is_(None))
            .first()
        )
        if not case:
            return self._empty(document, "case_not_found")

        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(200)
            .all()
        )
        if chunks:
            pieces: Iterable[tuple[str, int | None]] = ((chunk.content, chunk.id) for chunk in chunks)
        else:
            pieces = ((document.extracted_text or document.redacted_text or "", None),)

        created_ids: list[int] = []
        updated_ids: list[int] = []
        skipped_count = 0
        seen_keys: set[tuple[str, str]] = set()

        for text, chunk_id in pieces:
            for candidate in self._extract_candidates(text=text, chunk_id=chunk_id, anchor=document.upload_timestamp):
                key = (candidate.start_datetime.date().isoformat(), self._compact(candidate.title))
                if key in seen_keys:
                    skipped_count += 1
                    continue
                seen_keys.add(key)

                payload = CalendarEventCreate(
                    case_id=case.id,
                    client_id=case.client_id,
                    lawyer_id=case.lawyer_id,
                    title=candidate.title[:240],
                    description=self._build_description(document=document, candidate=candidate),
                    event_type=candidate.event_type,
                    status="tentative",
                    priority=candidate.priority,
                    start_datetime=candidate.start_datetime,
                    end_datetime=None,
                    all_day=candidate.all_day,
                    timezone="UTC",
                    location="Extracted from legal document",
                    source_type="document_extraction",
                    source_document_id=document.id,
                    source_chunk_id=candidate.source_chunk_id,
                    source_quote=candidate.source_quote[:5000],
                    extraction_confidence=candidate.confidence,
                    requires_review=True,
                )
                event, created = calendar_event_service.create_event(
                    db=db,
                    tenant_id=document.tenant_id,
                    created_by=None,
                    payload=payload,
                    case=case,
                    dedupe=True,
                    commit=False,
                )
                if created:
                    created_ids.append(event.id)
                else:
                    updated_ids.append(event.id)

                if len(created_ids) + len(updated_ids) >= self.MAX_EVENTS_PER_DOCUMENT:
                    break
            if len(created_ids) + len(updated_ids) >= self.MAX_EVENTS_PER_DOCUMENT:
                break

        db.commit()
        calendar_automation_hook_service.emit(
            "document.dates.extracted",
            {
                "document_id": document.id,
                "case_id": document.case_id,
                "created_count": len(created_ids),
                "updated_count": len(updated_ids),
            },
        )
        return {
            "document_id": document.id,
            "created_count": len(created_ids),
            "updated_count": len(set(updated_ids)),
            "skipped_count": skipped_count,
            "created_ids": created_ids,
            "updated_ids": sorted(set(updated_ids)),
        }

    def _extract_candidates(self, *, text: str, chunk_id: int | None, anchor: datetime | None) -> list[DateCandidate]:
        candidates: list[DateCandidate] = []
        for match in self.ISO_PATTERN.finditer(text or ""):
            parsed = self._date_or_none(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            if parsed:
                candidates.append(self._candidate(text=text, match=match, parsed=parsed, chunk_id=chunk_id, base_confidence=0.7))

        for match in self.DMY_PATTERN.finditer(text or ""):
            year = int(match.group(3))
            if year < 100:
                year += 2000
            parsed = self._date_or_none(year, int(match.group(2)), int(match.group(1)))
            if parsed:
                candidates.append(self._candidate(text=text, match=match, parsed=parsed, chunk_id=chunk_id, base_confidence=0.64))

        for match in self.TEXTUAL_DMY_PATTERN.finditer(text or ""):
            month = self.MONTH_NAMES[match.group(2).lower()]
            parsed = self._date_or_none(int(match.group(3)), month, int(match.group(1)))
            if parsed:
                candidates.append(self._candidate(text=text, match=match, parsed=parsed, chunk_id=chunk_id, base_confidence=0.74))

        for match in self.TEXTUAL_MDY_PATTERN.finditer(text or ""):
            month = self.MONTH_NAMES[match.group(1).lower()]
            parsed = self._date_or_none(int(match.group(3)), month, int(match.group(2)))
            if parsed:
                candidates.append(self._candidate(text=text, match=match, parsed=parsed, chunk_id=chunk_id, base_confidence=0.7))

        anchor_dt = anchor or datetime.now(timezone.utc)
        for match in self.RELATIVE_PATTERN.finditer(text or ""):
            quote = self._sentence_around(text, match.start(), match.end())
            days = self._relative_days(int(match.group(1)), match.group(2))
            parsed = anchor_dt + timedelta(days=days)
            event_type, priority = self._classify(quote)
            candidates.append(
                DateCandidate(
                    title=self._title_for(event_type, quote, relative=True),
                    event_type=event_type,
                    priority=priority,
                    start_datetime=parsed.replace(hour=9, minute=0, second=0, microsecond=0),
                    source_quote=quote,
                    source_chunk_id=chunk_id,
                    confidence=0.42,
                )
            )

        return candidates

    def _candidate(self, *, text: str, match: re.Match, parsed: datetime, chunk_id: int | None, base_confidence: float) -> DateCandidate:
        quote = self._sentence_around(text, match.start(), match.end())
        event_type, priority = self._classify(quote)
        legal_boost = 0.16 if event_type != "document_date" else 0
        return DateCandidate(
            title=self._title_for(event_type, quote),
            event_type=event_type,
            priority=priority,
            start_datetime=parsed,
            source_quote=quote,
            source_chunk_id=chunk_id,
            confidence=min(0.92, base_confidence + legal_boost),
        )

    def _classify(self, quote: str) -> tuple[str, str]:
        lowered = quote.lower()
        for event_type, hints in self.LEGAL_HINTS.items():
            if any(hint in lowered for hint in hints):
                if event_type in {"hearing", "filing_deadline", "limitation_period"}:
                    return event_type, "critical"
                if event_type in {"deadline", "payment_due"}:
                    return event_type, "high"
                return event_type, "medium"
        return "document_date", "medium"

    @staticmethod
    def _title_for(event_type: str, quote: str, relative: bool = False) -> str:
        label = {
            "hearing": "Hearing date",
            "filing_deadline": "Filing or response deadline",
            "payment_due": "Payment due date",
            "limitation_period": "Limitation period",
            "contract_date": "Contract date",
            "deadline": "Legal deadline",
            "meeting": "Legal meeting",
            "document_date": "Document date",
        }.get(event_type, "Legal calendar date")
        if relative:
            label = f"Review relative {label.lower()}"
        hint = re.sub(r"\s+", " ", quote).strip()
        return f"{label}: {hint[:80]}" if hint else label

    @staticmethod
    def _sentence_around(text: str, start: int, end: int) -> str:
        left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start))
        right_candidates = [idx for idx in [text.find(".", end), text.find("\n", end)] if idx != -1]
        right = min(right_candidates) if right_candidates else min(len(text), end + 180)
        quote = text[max(0, left + 1): right + 1]
        return re.sub(r"\s+", " ", quote).strip()[:800]

    @staticmethod
    def _date_or_none(year: int, month: int, day: int) -> datetime | None:
        try:
            return datetime(year, month, day, 9, 0, tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _relative_days(amount: int, unit: str) -> int:
        unit = unit.lower()
        if unit.startswith("week"):
            return amount * 7
        if unit.startswith("month"):
            return amount * 30
        return amount

    @staticmethod
    def _build_description(*, document: Document, candidate: DateCandidate) -> str:
        return (
            f"AI-detected legal date from '{document.filename}'. "
            "This is a candidate only and must be reviewed by a lawyer before reliance. "
            f"Source quote: {candidate.source_quote}"
        )[:5000]

    @staticmethod
    def _compact(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()[:80]

    @staticmethod
    def _empty(document: Document, reason: str) -> dict:
        return {
            "document_id": document.id,
            "created_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "created_ids": [],
            "updated_ids": [],
            "reason": reason,
        }


legal_date_extraction_service = LegalDateExtractionService()
