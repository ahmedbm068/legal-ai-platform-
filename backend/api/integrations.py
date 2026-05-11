from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from backend.api.call_schema import CallSessionOut
from backend.core.config import settings
from backend.core.deps import get_db
from backend.models.appointment import Appointment
from backend.models.call_session import CallSession
from backend.models.voice_recording import VoiceRecording
from backend.services.calendar_service import normalize_status, serialize_appointment
from backend.services.call_transcript_service import build_conversation_transcript, build_call_summary


router = APIRouter(prefix="/integrations/n8n", tags=["Integrations"])


class N8nWebhookEvent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_type: str = Field(..., min_length=3, max_length=80)
    call_session_id: int | None = None
    voice_recording_id: int | None = None
    provider_call_id: str | None = Field(default=None, max_length=120)
    client_phone: str | None = Field(default=None, max_length=40)
    caller_phone: str | None = Field(default=None, max_length=40)
    body: str | None = Field(default=None, max_length=4000)
    consent_message: str | None = Field(default=None, max_length=4000)
    transcript_text: str | None = Field(default=None, max_length=200000)
    transcript_source: str | None = Field(default=None, max_length=120)
    transcript_language: str | None = Field(default=None, max_length=40)
    conversation_turns: list[dict[str, Any]] = Field(default_factory=list)
    status: str | None = Field(default=None, max_length=80)


class N8nWebhookResponse(BaseModel):
    success: bool
    message: str
    call_session: CallSessionOut | None = None


def _verify_shared_secret(request: Request) -> None:
    expected_secret = (settings.N8N_WEBHOOK_SECRET or "").strip()
    if not expected_secret:
        return

    provided_secret = (request.headers.get("X-N8N-SECRET") or "").strip()
    if provided_secret != expected_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid n8n webhook secret")


def _get_call_session(db: Session, call_session_id: int) -> CallSession | None:
    return (
        db.query(CallSession)
        .options(selectinload(CallSession.voice_recording))
        .filter(CallSession.id == call_session_id)
        .first()
    )


def _apply_consent_reply(call_session: CallSession, *, event: N8nWebhookEvent) -> None:
    body = (event.body or "").strip()
    normalized = body.lower()
    accepted = normalized in {"yes", "y", "oui", "ok", "okay"} or normalized.startswith("yes ") or normalized.startswith("oui ")

    call_session.consent_response_text = body or None
    call_session.consent_responded_at = datetime.now(timezone.utc)
    call_session.consent_request_status = "accepted" if accepted else "rejected"
    call_session.consent_accepted = accepted
    call_session.consent_accepted_at = datetime.now(timezone.utc) if accepted else None
    call_session.call_status = "ready" if accepted else "consent_rejected"


def _apply_transcript_updates(
    call_session: CallSession,
    *,
    event: N8nWebhookEvent,
) -> None:
    transcript_text = (event.transcript_text or "").strip() or None
    conversation_text = build_conversation_transcript(transcript_text, conversation_turns=event.conversation_turns)
    transcript_text = transcript_text or conversation_text
    summary_text = build_call_summary(conversation_text or transcript_text)

    if transcript_text:
        call_session.transcript_text = transcript_text
    if conversation_text:
        call_session.conversation_transcript_text = conversation_text

    call_session.transcript_source = event.transcript_source or call_session.transcript_source
    call_session.call_status = event.status or "completed"
    call_session.recording_status = "completed"
    call_session.summary_status = "completed"
    call_session.summary_text = summary_text
    call_session.transcription_error = None
    call_session.ended_at = call_session.ended_at or datetime.now(timezone.utc)


@router.post("/events", response_model=N8nWebhookResponse)
def receive_n8n_event(
    payload: N8nWebhookEvent,
    request: Request,
    db: Session = Depends(get_db),
):
    _verify_shared_secret(request)

    if not payload.call_session_id:
        raise HTTPException(status_code=400, detail="call_session_id is required")

    call_session = _get_call_session(db, payload.call_session_id)
    if not call_session:
        raise HTTPException(status_code=404, detail="Call session not found")

    event_type = payload.event_type.strip().lower()

    if event_type in {"consent.request", "consent.request.sent"}:
        call_session.consent_message = payload.consent_message or call_session.consent_message
        call_session.consent_request_status = "sent"
        call_session.consent_requested_at = datetime.now(timezone.utc)
        call_session.call_status = call_session.call_status or "awaiting_consent"
    elif event_type in {"consent.reply", "consent.reply.received", "consent.response"}:
        _apply_consent_reply(call_session, event=payload)
    elif event_type in {"call.started", "call.start"}:
        call_session.call_status = "calling"
        call_session.started_at = call_session.started_at or datetime.now(timezone.utc)
        call_session.provider_call_id = payload.provider_call_id or call_session.provider_call_id
    elif event_type in {"call.ended", "call.end"}:
        call_session.call_status = payload.status or "completed"
        call_session.ended_at = call_session.ended_at or datetime.now(timezone.utc)
        call_session.recording_status = call_session.recording_status or "waiting_for_audio"
    elif event_type in {"recording.transcribed", "transcription.completed"}:
        _apply_transcript_updates(call_session, event=payload)
        if payload.voice_recording_id:
            voice_recording = db.query(VoiceRecording).filter(VoiceRecording.id == payload.voice_recording_id).first()
            if voice_recording:
                voice_recording.transcription_status = "completed"
                voice_recording.transcription_error = None
                voice_recording.transcript_text = payload.transcript_text or call_session.transcript_text
                voice_recording.conversation_transcript_text = call_session.conversation_transcript_text
                voice_recording.transcript_source = payload.transcript_source or voice_recording.transcript_source
                voice_recording.transcript_language = payload.transcript_language or voice_recording.transcript_language
    elif event_type == "consent.request.failed":
        call_session.consent_request_status = "failed"
        call_session.call_status = "awaiting_consent"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported n8n event_type '{payload.event_type}'")

    db.commit()
    db.refresh(call_session)

    return {
        "success": True,
        "message": f"Processed n8n event '{payload.event_type}'.",
        "call_session": call_session,
    }


# ── Appointment sync (Google Calendar → DB via n8n) ────────────────────────────


class N8nAppointmentSync(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    appointment_id: int = Field(..., ge=1)
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=24 * 60)
    status: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)


class N8nAppointmentSyncResponse(BaseModel):
    success: bool
    message: str
    appointment: dict[str, Any] | None = None


@router.post("/appointments/sync", response_model=N8nAppointmentSyncResponse)
def sync_appointment_from_n8n(
    payload: N8nAppointmentSync,
    request: Request,
    db: Session = Depends(get_db),
):
    """Apply an external (Google Calendar) change back to a stored appointment.

    Called by n8n when a lawyer reschedules, renames, or cancels an event in
    their connected Google Calendar. Tenant scoping is implicit: the
    appointment_id is the source of truth, and the shared n8n secret gates
    the route.
    """
    _verify_shared_secret(request)

    appointment = (
        db.query(Appointment)
        .options(
            selectinload(Appointment.case),
            selectinload(Appointment.client),
            selectinload(Appointment.lawyer),
            selectinload(Appointment.consultation_request),
        )
        .filter(Appointment.id == payload.appointment_id)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if payload.scheduled_at is not None:
        appointment.scheduled_at = payload.scheduled_at
    if payload.duration_minutes is not None:
        appointment.duration_minutes = payload.duration_minutes
    if payload.status is not None:
        appointment.status = normalize_status(payload.status)
    if payload.location is not None:
        appointment.location = payload.location
    if payload.title is not None:
        appointment.title = payload.title.strip() or appointment.title
    if payload.notes is not None:
        appointment.notes = payload.notes

    db.commit()
    db.refresh(appointment)

    return {
        "success": True,
        "message": f"Appointment {appointment.id} synced from n8n.",
        "appointment": serialize_appointment(appointment),
    }
