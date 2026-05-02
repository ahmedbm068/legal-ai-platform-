from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.models.calendar_event import CalendarEvent
from backend.models.calendar_reminder import CalendarReminder
from backend.services.calendar_automation_hook_service import calendar_automation_hook_service


class CalendarReminderService:
    CRITICAL_OFFSETS_DAYS = (30, 14, 7, 3, 1)

    def create_reminder(
        self,
        *,
        db: Session,
        event: CalendarEvent,
        remind_at: datetime,
        method: str = "in_app",
    ) -> CalendarReminder:
        reminder = CalendarReminder(
            tenant_id=event.tenant_id,
            event_id=event.id,
            remind_at=remind_at,
            method=self.normalize_method(method),
            status="pending",
        )
        db.add(reminder)
        db.flush()
        calendar_automation_hook_service.emit(
            "calendar.reminder.due",
            {"event_id": event.id, "remind_at": remind_at.isoformat(), "method": reminder.method},
        )
        return reminder

    def ensure_default_critical_reminders(self, *, db: Session, event: CalendarEvent) -> list[CalendarReminder]:
        if event.priority != "critical" or event.requires_review:
            return []

        created: list[CalendarReminder] = []
        now = datetime.now(timezone.utc)
        existing = {
            row.remind_at.replace(microsecond=0)
            for row in db.query(CalendarReminder)
            .filter(CalendarReminder.event_id == event.id, CalendarReminder.status == "pending")
            .all()
        }

        for days in self.CRITICAL_OFFSETS_DAYS:
            remind_at = (event.start_datetime - timedelta(days=days)).replace(microsecond=0)
            if remind_at <= now or remind_at in existing:
                continue
            created.append(self.create_reminder(db=db, event=event, remind_at=remind_at, method="in_app"))

        return created

    @staticmethod
    def normalize_method(value: str | None) -> str:
        cleaned = (value or "in_app").strip().lower()
        return cleaned if cleaned in {"in_app", "email", "future_webhook"} else "in_app"


calendar_reminder_service = CalendarReminderService()
