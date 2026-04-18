from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.core.enums import UserRole
from backend.models.appointment import Appointment
from backend.models.case import Case
from backend.models.consultation_request import ConsultationRequest
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
