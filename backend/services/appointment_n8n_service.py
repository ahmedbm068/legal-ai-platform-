from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from backend.core.config import settings
from backend.models.appointment import Appointment


logger = logging.getLogger(__name__)


APPOINTMENT_CREATED = "appointment.created"
APPOINTMENT_UPDATED = "appointment.updated"
APPOINTMENT_CANCELLED = "appointment.cancelled"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _serialize_appointment(appointment: Appointment) -> dict[str, Any]:
    lawyer = appointment.lawyer
    client = appointment.client
    case = appointment.case

    scheduled_at = appointment.scheduled_at
    end_at: datetime | None = None
    if scheduled_at is not None:
        end_at = scheduled_at + timedelta(minutes=int(appointment.duration_minutes or 30))

    return {
        "appointment_id": appointment.id,
        "tenant_id": appointment.tenant_id,
        "case_id": appointment.case_id,
        "case_title": getattr(case, "title", None),
        "title": appointment.title,
        "description": appointment.description,
        "appointment_type": appointment.appointment_type,
        "status": appointment.status,
        "scheduled_at": _iso(scheduled_at),
        "end_at": _iso(end_at),
        "duration_minutes": appointment.duration_minutes,
        "location": appointment.location,
        "timezone_name": appointment.timezone_name,
        "notes": appointment.notes,
        "lawyer": {
            "id": getattr(lawyer, "id", None),
            "name": getattr(lawyer, "name", None),
            "email": getattr(lawyer, "email", None),
            "phone": getattr(lawyer, "phone", None),
        } if lawyer else None,
        "client": {
            "id": getattr(client, "id", None),
            "name": getattr(client, "name", None),
            "email": getattr(client, "email", None),
            "phone": getattr(client, "phone", None),
        } if client else None,
    }


def _appointment_webhook_url() -> str | None:
    url = (settings.N8N_APPOINTMENT_WEBHOOK_URL or "").strip()
    if url:
        return url
    return (settings.N8N_WORKFLOW_WEBHOOK_URL or "").strip() or None


def _dispatch_async(event_type: str, payload: dict[str, Any]) -> None:
    webhook_url = _appointment_webhook_url()
    if not webhook_url:
        return

    def _run() -> None:
        try:
            headers = {"Content-Type": "application/json"}
            if settings.N8N_WEBHOOK_SECRET:
                headers["X-N8N-SECRET"] = settings.N8N_WEBHOOK_SECRET
            body = {
                "event_type": event_type,
                "dispatched_at": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
            response = requests.post(
                webhook_url,
                json=body,
                headers=headers,
                timeout=max(5, int(settings.N8N_REQUEST_TIMEOUT_SECONDS)),
            )
            response.raise_for_status()
        except Exception as exc:
            logger.warning("n8n appointment dispatch failed for %s: %s", event_type, exc)

    threading.Thread(target=_run, name=f"n8n-{event_type}", daemon=True).start()


def emit_appointment_event(event_type: str, appointment: Appointment) -> None:
    payload = {"appointment": _serialize_appointment(appointment)}
    _dispatch_async(event_type, payload)


def emit_appointment_created(appointment: Appointment) -> None:
    emit_appointment_event(APPOINTMENT_CREATED, appointment)


def emit_appointment_updated(appointment: Appointment) -> None:
    emit_appointment_event(APPOINTMENT_UPDATED, appointment)


def emit_appointment_cancelled(appointment: Appointment) -> None:
    emit_appointment_event(APPOINTMENT_CANCELLED, appointment)
