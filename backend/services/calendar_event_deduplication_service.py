from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.calendar_event import CalendarEvent


class CalendarEventDeduplicationService:
    def find_duplicate(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int | None,
        start_datetime: datetime,
        title: str,
        source_document_id: int | None = None,
        source_quote: str | None = None,
    ) -> CalendarEvent | None:
        query = db.query(CalendarEvent).filter(
            CalendarEvent.tenant_id == tenant_id,
            CalendarEvent.deleted_at.is_(None),
            func.date(CalendarEvent.start_datetime) == start_datetime.date(),
        )
        if case_id is None:
            query = query.filter(CalendarEvent.case_id.is_(None))
        else:
            query = query.filter(CalendarEvent.case_id == case_id)

        candidates = query.limit(50).all()
        wanted_title = self._fingerprint(title)
        wanted_quote = self._fingerprint(source_quote or "")

        for event in candidates:
            if source_document_id and event.source_document_id == source_document_id:
                event_quote = self._fingerprint(event.source_quote or "")
                if wanted_quote and (wanted_quote in event_quote or event_quote in wanted_quote):
                    return event

            event_title = self._fingerprint(event.title)
            if wanted_title and (wanted_title in event_title or event_title in wanted_title):
                return event

        return None

    @staticmethod
    def _fingerprint(value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
        tokens = [token for token in cleaned.split() if len(token) > 2]
        return " ".join(tokens[:12])


calendar_event_deduplication_service = CalendarEventDeduplicationService()
