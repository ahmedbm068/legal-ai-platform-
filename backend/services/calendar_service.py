from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.api.calendar_schema import (
    EVENT_PRIORITIES,
    EVENT_STATUSES,
    EVENT_TYPES,
    SOURCE_TYPES,
    CalendarEventCreate,
    CalendarEventUpdate,
    normalize_choice,
)
from backend.core.enums import UserRole
from backend.models.appointment import Appointment
from backend.models.calendar_event import CalendarEvent
from backend.models.calendar_event_source import CalendarEventSource
from backend.models.case import Case
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.services.calendar_automation_hook_service import calendar_automation_hook_service
from backend.services.calendar_event_deduplication_service import calendar_event_deduplication_service
from backend.services.calendar_reminder_service import calendar_reminder_service
from backend.services.ai.agents.agent_output_formatter import AgentOutputFormatter
from backend.services.ai.agents.booking_agent import booking_agent


ALLOWED_VISIBILITY_SCOPES = {"shared", "client", "lawyer", "assistant", "internal"}
ALLOWED_APPOINTMENT_TYPES = {"consultation", "call", "meeting", "deadline", "court_hearing", "follow_up"}
ALLOWED_STATUSES = {"scheduled", "confirmed", "tentative", "completed", "cancelled", "rescheduled"}


def normalize_scope(value: str | None, default: str = "shared") -> str:
    cleaned = (value or default).strip().lower().replace(" ", "_")
    return cleaned if cleaned in ALLOWED_VISIBILITY_SCOPES else default


def normalize_appointment_type(value: str | None, default: str = "meeting") -> str:
    cleaned = (value or default).strip().lower().replace(" ", "_")
    return cleaned if cleaned in ALLOWED_APPOINTMENT_TYPES else default


def normalize_status(value: str | None, default: str = "scheduled") -> str:
    cleaned = (value or default).strip().lower().replace(" ", "_")
    return cleaned if cleaned in ALLOWED_STATUSES else default


def appointment_visible_to_staff(appointment: Appointment, current_user) -> bool:
    if getattr(current_user, "role", None) and str(getattr(current_user.role, "value", current_user.role)).lower() == UserRole.admin.value:
        return True

    scope = normalize_scope(appointment.visibility_scope)
    role_value = str(getattr(current_user, "role", "")).lower()
    if role_value == UserRole.lawyer.value:
        return scope in {"shared", "lawyer", "assistant", "internal"} or appointment.lawyer_id == current_user.id
    if role_value == UserRole.assistant.value:
        return scope in {"shared", "assistant", "internal"}
    return False


def appointment_visible_to_client(appointment: Appointment, client_id: int) -> bool:
    scope = normalize_scope(appointment.visibility_scope)
    return appointment.client_id == client_id and scope in {"shared", "client"}


def serialize_appointment(appointment: Appointment, *, is_ai_suggested: bool = False) -> dict[str, Any]:
    case = appointment.case
    client = appointment.client
    lawyer = appointment.lawyer

    return {
        "id": appointment.id,
        "case_id": appointment.case_id,
        "tenant_id": appointment.tenant_id,
        "lawyer_id": appointment.lawyer_id,
        "client_id": appointment.client_id,
        "consultation_request_id": appointment.consultation_request_id,
        "created_by_user_id": appointment.created_by_user_id,
        "title": appointment.title,
        "description": appointment.description,
        "appointment_type": appointment.appointment_type,
        "visibility_scope": appointment.visibility_scope,
        "status": appointment.status,
        "scheduled_at": appointment.scheduled_at,
        "duration_minutes": appointment.duration_minutes,
        "location": appointment.location,
        "timezone_name": appointment.timezone_name,
        "ai_summary": appointment.ai_summary,
        "ai_recommendation": appointment.ai_recommendation,
        "ai_confidence": appointment.ai_confidence,
        "ai_source": appointment.ai_source,
        "notes": appointment.notes,
        "case_title": case.title if case else None,
        "client_name": client.name if client else None,
        "lawyer_name": lawyer.name if lawyer else None,
        "is_ai_suggested": is_ai_suggested,
        "created_at": appointment.created_at,
        "updated_at": appointment.updated_at,
    }


def build_case_calendar_entries(
    *,
    case: Case,
    appointments: list[Appointment],
    consultations: list[ConsultationRequest] | None = None,
) -> list[dict[str, Any]]:
    entries = [serialize_appointment(appointment) for appointment in appointments]

    if entries or not consultations:
        return entries

    latest_consultation = consultations[0]
    scheduled_at = latest_consultation.created_at or datetime.now(timezone.utc)
    entries.append(
        {
            "id": -latest_consultation.id,
            "case_id": case.id,
            "tenant_id": case.tenant_id,
            "lawyer_id": case.lawyer_id,
            "client_id": case.client_id,
            "consultation_request_id": latest_consultation.id,
            "created_by_user_id": None,
            "title": "Suggested consultation follow-up",
            "description": latest_consultation.issue_summary,
            "appointment_type": "consultation",
            "visibility_scope": "shared",
            "status": "suggested",
            "scheduled_at": scheduled_at,
            "duration_minutes": 30,
            "location": None,
            "timezone_name": "UTC",
            "ai_summary": latest_consultation.issue_summary,
            "ai_recommendation": (
                latest_consultation.preferred_schedule
                or "Review the request and confirm a concrete time with the client."
            ),
            "ai_confidence": "medium",
            "ai_source": "consultation_request",
            "notes": "AI planning placeholder generated from the latest consultation request.",
            "case_title": case.title,
            "client_name": case.client.name if case.client else None,
            "lawyer_name": case.lawyer.name if case.lawyer else None,
            "is_ai_suggested": True,
            "created_at": scheduled_at,
            "updated_at": scheduled_at,
        }
    )
    return entries


def build_ai_calendar_brief(
    *,
    case: Case,
    appointment: Appointment,
    consultations: list[ConsultationRequest] | None = None,
) -> dict[str, str]:
    relevant_consultations = consultations or []
    if not relevant_consultations and appointment.consultation_request:
        relevant_consultations = [appointment.consultation_request]

    if relevant_consultations:
        result = booking_agent.analyze_consultations(
            case_id=case.id,
            case_title=case.title,
            consultations=relevant_consultations,
        )
        if result.success and result.payload:
            narrative = AgentOutputFormatter.sanitize_text(result.payload.get("narrative_summary"))
            recommendation = AgentOutputFormatter.sanitize_text(result.payload.get("recommended_action"))
            if narrative or recommendation:
                return {
                    "ai_summary": narrative or _fallback_summary(case=case, appointment=appointment),
                    "ai_recommendation": recommendation or _fallback_recommendation(appointment=appointment),
                    "ai_confidence": "high" if not result.warnings else "medium",
                    "ai_source": "booking_agent",
                }

    return {
        "ai_summary": _fallback_summary(case=case, appointment=appointment),
        "ai_recommendation": _fallback_recommendation(appointment=appointment),
        "ai_confidence": "medium",
        "ai_source": "heuristic",
    }


def build_scheduled_at_text(value: datetime) -> str:
    scheduled = value.astimezone(timezone.utc)
    return scheduled.strftime("%Y-%m-%d %H:%M UTC")


def _fallback_summary(*, case: Case, appointment: Appointment) -> str:
    return (
        f"{appointment.title} is scheduled for {build_scheduled_at_text(appointment.scheduled_at)} "
        f"for case #{case.id} - {case.title}."
    )


def _fallback_recommendation(*, appointment: Appointment) -> str:
    appointment_type = normalize_appointment_type(appointment.appointment_type)
    if appointment_type == "deadline":
        return "Prepare the file in advance, review the timeline, and notify the client before the deadline."
    if appointment_type == "call":
        return "Review the case notes and keep a concise follow-up summary ready after the call."
    return "Confirm the client details, prepare the relevant case documents, and keep the next action visible."


class CalendarService:
    def list_events(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int | None = None,
        client_id: int | None = None,
        event_type: str | None = None,
        priority: str | None = None,
        status: str | None = None,
        requires_review: bool | None = None,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
        include_deleted: bool = False,
        limit: int = 500,
    ) -> list[CalendarEvent]:
        query = db.query(CalendarEvent).filter(CalendarEvent.tenant_id == tenant_id)
        if not include_deleted:
            query = query.filter(CalendarEvent.deleted_at.is_(None))
        if case_id is not None:
            query = query.filter(CalendarEvent.case_id == case_id)
        if client_id is not None:
            query = query.filter(CalendarEvent.client_id == client_id)
        if event_type:
            query = query.filter(CalendarEvent.event_type == normalize_choice(event_type, EVENT_TYPES, "other"))
        if priority:
            query = query.filter(CalendarEvent.priority == normalize_choice(priority, EVENT_PRIORITIES, "medium"))
        if status:
            query = query.filter(CalendarEvent.status == normalize_choice(status, EVENT_STATUSES, "scheduled"))
        if requires_review is not None:
            query = query.filter(CalendarEvent.requires_review == requires_review)
        if from_datetime:
            query = query.filter(CalendarEvent.start_datetime >= from_datetime)
        if to_datetime:
            query = query.filter(CalendarEvent.start_datetime <= to_datetime)

        return query.order_by(CalendarEvent.start_datetime.asc(), CalendarEvent.id.asc()).limit(limit).all()

    def create_event(
        self,
        *,
        db: Session,
        tenant_id: int,
        created_by: int | None,
        payload: CalendarEventCreate,
        case: Case | None = None,
        dedupe: bool = True,
        commit: bool = True,
    ) -> tuple[CalendarEvent, bool]:
        event_type = normalize_choice(payload.event_type, EVENT_TYPES, "other")
        priority = normalize_choice(payload.priority, EVENT_PRIORITIES, "medium")
        source_type = normalize_choice(payload.source_type, SOURCE_TYPES, "manual")

        case_id = case.id if case else payload.case_id
        client_id = case.client_id if case else payload.client_id
        lawyer_id = payload.lawyer_id or (case.lawyer_id if case else None)
        requires_review = bool(payload.requires_review or source_type in {"document_extraction", "ai_generated"})

        duplicate = None
        if dedupe:
            duplicate = calendar_event_deduplication_service.find_duplicate(
                db=db,
                tenant_id=tenant_id,
                case_id=case_id,
                start_datetime=payload.start_datetime,
                title=payload.title,
                source_document_id=payload.source_document_id,
                source_quote=payload.source_quote,
            )
        if duplicate:
            self._merge_extracted_payload(duplicate, payload)
            db.flush()
            if commit:
                db.commit()
                db.refresh(duplicate)
            return duplicate, False

        event = CalendarEvent(
            tenant_id=tenant_id,
            case_id=case_id,
            client_id=client_id,
            lawyer_id=lawyer_id,
            title=payload.title.strip(),
            description=payload.description,
            event_type=event_type,
            status=normalize_choice(payload.status, EVENT_STATUSES, "scheduled"),
            priority=priority,
            start_datetime=payload.start_datetime,
            end_datetime=payload.end_datetime,
            all_day=payload.all_day,
            timezone=(payload.timezone or "UTC").strip() or "UTC",
            location=payload.location,
            source_type=source_type,
            source_document_id=payload.source_document_id,
            source_chunk_id=payload.source_chunk_id,
            source_quote=payload.source_quote,
            extraction_confidence=payload.extraction_confidence,
            requires_review=requires_review,
            created_by=created_by,
        )
        db.add(event)
        db.flush()
        self._create_source_from_event(db=db, event=event)

        calendar_automation_hook_service.emit("calendar.event.created", {"event_id": event.id, "tenant_id": tenant_id})
        if event.priority == "critical":
            calendar_automation_hook_service.emit("calendar.deadline.critical", {"event_id": event.id, "case_id": event.case_id})
        if event.requires_review:
            calendar_automation_hook_service.emit("document.date.requires_review", {"event_id": event.id, "document_id": event.source_document_id})

        if commit:
            db.commit()
            db.refresh(event)
        return event, True

    def update_event(self, *, db: Session, event: CalendarEvent, payload: CalendarEventUpdate, reviewer_id: int | None = None) -> CalendarEvent:
        if payload.case_id is not None:
            event.case_id = payload.case_id
        if payload.client_id is not None:
            event.client_id = payload.client_id
        if payload.lawyer_id is not None:
            event.lawyer_id = payload.lawyer_id
        if payload.title is not None:
            event.title = payload.title.strip()
        if payload.description is not None:
            event.description = payload.description
        if payload.event_type is not None:
            event.event_type = normalize_choice(payload.event_type, EVENT_TYPES, event.event_type)
        if payload.status is not None:
            event.status = normalize_choice(payload.status, EVENT_STATUSES, event.status)
        if payload.priority is not None:
            event.priority = normalize_choice(payload.priority, EVENT_PRIORITIES, event.priority)
        if payload.start_datetime is not None:
            event.start_datetime = payload.start_datetime
        if payload.end_datetime is not None:
            event.end_datetime = payload.end_datetime
        if payload.all_day is not None:
            event.all_day = payload.all_day
        if payload.timezone is not None:
            event.timezone = (payload.timezone or "UTC").strip() or "UTC"
        if payload.location is not None:
            event.location = payload.location
        if payload.source_quote is not None:
            event.source_quote = payload.source_quote
        if payload.requires_review is not None:
            event.requires_review = payload.requires_review
            if not payload.requires_review:
                event.reviewed_by = reviewer_id
                event.reviewed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(event)
        calendar_reminder_service.ensure_default_critical_reminders(db=db, event=event)
        db.commit()
        db.refresh(event)
        calendar_automation_hook_service.emit("calendar.event.updated", {"event_id": event.id, "tenant_id": event.tenant_id})
        return event

    def accept_event(self, *, db: Session, event: CalendarEvent, reviewer_id: int) -> CalendarEvent:
        event.requires_review = False
        event.status = "scheduled"
        event.reviewed_by = reviewer_id
        event.reviewed_at = datetime.now(timezone.utc)
        db.flush()
        calendar_reminder_service.ensure_default_critical_reminders(db=db, event=event)
        db.commit()
        db.refresh(event)
        calendar_automation_hook_service.emit("calendar.event.updated", {"event_id": event.id, "accepted": True})
        return event

    def reject_event(self, *, db: Session, event: CalendarEvent, reviewer_id: int) -> CalendarEvent:
        event.requires_review = False
        event.status = "rejected"
        event.reviewed_by = reviewer_id
        event.reviewed_at = datetime.now(timezone.utc)
        event.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(event)
        calendar_automation_hook_service.emit("calendar.event.deleted", {"event_id": event.id, "rejected": True})
        return event

    def soft_delete_event(self, *, db: Session, event: CalendarEvent) -> CalendarEvent:
        event.deleted_at = datetime.now(timezone.utc)
        event.status = "cancelled"
        db.commit()
        db.refresh(event)
        calendar_automation_hook_service.emit("calendar.event.deleted", {"event_id": event.id, "tenant_id": event.tenant_id})
        return event

    def serialize_event(self, event: CalendarEvent) -> dict[str, Any]:
        reminder_count = len(getattr(event, "reminders", []) or [])
        document: Document | None = getattr(event, "source_document", None)
        case: Case | None = getattr(event, "case", None)
        client = getattr(event, "client", None)
        return {
            "id": event.id,
            "tenant_id": event.tenant_id,
            "case_id": event.case_id,
            "client_id": event.client_id,
            "lawyer_id": event.lawyer_id,
            "title": event.title,
            "description": event.description,
            "event_type": event.event_type,
            "status": event.status,
            "priority": event.priority,
            "start_datetime": event.start_datetime,
            "end_datetime": event.end_datetime,
            "all_day": event.all_day,
            "timezone": event.timezone,
            "location": event.location,
            "source_type": event.source_type,
            "source_document_id": event.source_document_id,
            "source_chunk_id": event.source_chunk_id,
            "source_quote": event.source_quote,
            "extraction_confidence": event.extraction_confidence,
            "requires_review": event.requires_review,
            "reviewed_by": event.reviewed_by,
            "reviewed_at": event.reviewed_at,
            "created_by": event.created_by,
            "created_at": event.created_at,
            "updated_at": event.updated_at,
            "deleted_at": event.deleted_at,
            "case_title": case.title if case else None,
            "client_name": client.name if client else None,
            "document_filename": document.filename if document else None,
            "reminder_count": reminder_count,
        }

    def _merge_extracted_payload(self, event: CalendarEvent, payload: CalendarEventCreate) -> None:
        if payload.extraction_confidence and (
            event.extraction_confidence is None or payload.extraction_confidence > event.extraction_confidence
        ):
            event.extraction_confidence = payload.extraction_confidence
            event.source_quote = payload.source_quote or event.source_quote
            event.source_chunk_id = payload.source_chunk_id or event.source_chunk_id
        if payload.description and payload.description not in (event.description or ""):
            event.description = payload.description
        event.requires_review = event.requires_review or payload.requires_review

    def _create_source_from_event(self, *, db: Session, event: CalendarEvent) -> None:
        if event.source_type == "manual" and not (event.source_document_id or event.source_quote):
            return
        db.add(
            CalendarEventSource(
                tenant_id=event.tenant_id,
                event_id=event.id,
                source_type=event.source_type,
                document_id=event.source_document_id,
                chunk_id=event.source_chunk_id,
                quote=event.source_quote,
                confidence=event.extraction_confidence,
            )
        )


calendar_event_service = CalendarService()
