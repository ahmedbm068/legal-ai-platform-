from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models.calendar_event import CalendarEvent


class CalendarAssistantToolService:
    def summarize_deadlines(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int | None = None,
        limit: int = 8,
    ) -> str:
        query = db.query(CalendarEvent).filter(
            CalendarEvent.tenant_id == tenant_id,
            CalendarEvent.deleted_at.is_(None),
            CalendarEvent.status.in_(["scheduled", "tentative"]),
            CalendarEvent.start_datetime >= datetime.now(timezone.utc),
        )
        if case_id:
            query = query.filter(CalendarEvent.case_id == case_id)

        rows = query.order_by(CalendarEvent.start_datetime.asc()).limit(limit).all()
        if not rows:
            return "No upcoming legal calendar deadlines were found."

        lines = []
        for row in rows:
            review_note = " pending lawyer review" if row.requires_review else ""
            lines.append(
                f"- {row.start_datetime:%Y-%m-%d}: {row.title} "
                f"({row.event_type}, {row.priority}{review_note})"
            )
        return "\n".join(lines)


calendar_assistant_tool_service = CalendarAssistantToolService()
