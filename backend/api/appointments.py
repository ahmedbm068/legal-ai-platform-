from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from backend.api.appointment_schema import AppointmentActionResponse, AppointmentCreate, AppointmentOut, AppointmentUpdate
from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope, require_lawyer
from backend.models.appointment import Appointment
from backend.models.case import Case
from backend.models.consultation_request import ConsultationRequest
from backend.models.user import User
from backend.services.appointment_n8n_service import (
    emit_appointment_cancelled,
    emit_appointment_created,
    emit_appointment_updated,
)
from backend.services.calendar_service import (
    build_ai_calendar_brief,
    build_case_calendar_entries,
    normalize_appointment_type,
    normalize_scope,
    normalize_status,
    appointment_visible_to_staff,
    serialize_appointment,
)


router = APIRouter(prefix="/calendar", tags=["Calendar"])


def get_tenant_case_or_404(db: Session, case_id: int, current_user: User) -> Case:
    case_query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def get_tenant_appointment_or_404(db: Session, appointment_id: int, current_user: User) -> Appointment:
    query = (
        db.query(Appointment)
        .options(
            selectinload(Appointment.case),
            selectinload(Appointment.client),
            selectinload(Appointment.lawyer),
            selectinload(Appointment.consultation_request),
        )
        .filter(Appointment.id == appointment_id)
    )
    appointment = apply_tenant_scope(query, Appointment.tenant_id, current_user).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appointment


@router.get("/case/{case_id}", response_model=list[AppointmentOut])
def list_case_appointments(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    query = (
        db.query(Appointment)
        .options(
            selectinload(Appointment.case),
            selectinload(Appointment.client),
            selectinload(Appointment.lawyer),
            selectinload(Appointment.consultation_request),
        )
        .filter(Appointment.case_id == case.id)
        .order_by(Appointment.scheduled_at.asc(), Appointment.id.asc())
    )
    appointments = apply_tenant_scope(query, Appointment.tenant_id, current_user).all()
    appointments = [appointment for appointment in appointments if appointment_visible_to_staff(appointment, current_user)]

    consultations = (
        db.query(ConsultationRequest)
        .filter(
            ConsultationRequest.case_id == case.id,
            ConsultationRequest.tenant_id == case.tenant_id,
        )
        .order_by(ConsultationRequest.created_at.desc(), ConsultationRequest.id.desc())
        .all()
    )

    return build_case_calendar_entries(case=case, appointments=appointments, consultations=consultations)


@router.get("/me", response_model=list[AppointmentOut])
def list_my_appointments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Appointment)
        .options(
            selectinload(Appointment.case),
            selectinload(Appointment.client),
            selectinload(Appointment.lawyer),
            selectinload(Appointment.consultation_request),
        )
        .filter(Appointment.tenant_id == current_user.tenant_id)
        .order_by(Appointment.scheduled_at.asc(), Appointment.id.asc())
    )
    appointments = query.all()
    appointments = [appointment for appointment in appointments if appointment_visible_to_staff(appointment, current_user)]
    return [serialize_appointment(appointment) for appointment in appointments]


@router.post("/case/{case_id}", response_model=AppointmentActionResponse, status_code=status.HTTP_201_CREATED)
def create_case_appointment(
    case_id: int,
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    case = get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    consultation = None
    if payload.consultation_request_id:
        consultation = (
            db.query(ConsultationRequest)
            .filter(
                ConsultationRequest.id == payload.consultation_request_id,
                ConsultationRequest.case_id == case.id,
                ConsultationRequest.tenant_id == case.tenant_id,
            )
            .first()
        )
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation request not found for this case")

    appointment = Appointment(
        case_id=case.id,
        tenant_id=case.tenant_id,
        lawyer_id=case.lawyer_id,
        client_id=case.client_id,
        consultation_request_id=consultation.id if consultation else None,
        created_by_user_id=current_user.id,
        title=payload.title.strip(),
        description=payload.description,
        appointment_type=normalize_appointment_type(payload.appointment_type),
        visibility_scope=normalize_scope(payload.visibility_scope),
        status=normalize_status(payload.status),
        scheduled_at=payload.scheduled_at,
        duration_minutes=payload.duration_minutes,
        location=payload.location,
        timezone_name=(payload.timezone_name or "UTC").strip() or "UTC",
        notes=payload.notes,
    )

    if payload.use_ai:
        brief = build_ai_calendar_brief(
            case=case,
            appointment=appointment,
            consultations=[consultation] if consultation else None,
        )
        appointment.ai_summary = brief["ai_summary"]
        appointment.ai_recommendation = brief["ai_recommendation"]
        appointment.ai_confidence = brief["ai_confidence"]
        appointment.ai_source = brief["ai_source"]

    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    appointment = get_tenant_appointment_or_404(db=db, appointment_id=appointment.id, current_user=current_user)
    emit_appointment_created(appointment)
    message = "Appointment created and calendar AI notes updated."
    return {"message": message, "appointment": serialize_appointment(appointment)}


@router.put("/{appointment_id}", response_model=AppointmentActionResponse)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    appointment = get_tenant_appointment_or_404(db=db, appointment_id=appointment_id, current_user=current_user)

    if current_user.role != UserRole.admin and appointment.lawyer_id not in {None, current_user.id}:
        raise HTTPException(status_code=403, detail="You can only update your own calendar appointments")

    if payload.title is not None:
        appointment.title = payload.title.strip()
    if payload.description is not None:
        appointment.description = payload.description
    if payload.appointment_type is not None:
        appointment.appointment_type = normalize_appointment_type(payload.appointment_type)
    if payload.visibility_scope is not None:
        appointment.visibility_scope = normalize_scope(payload.visibility_scope)
    if payload.status is not None:
        appointment.status = normalize_status(payload.status)
    if payload.scheduled_at is not None:
        appointment.scheduled_at = payload.scheduled_at
    if payload.duration_minutes is not None:
        appointment.duration_minutes = payload.duration_minutes
    if payload.location is not None:
        appointment.location = payload.location
    if payload.timezone_name is not None:
        appointment.timezone_name = (payload.timezone_name or "UTC").strip() or "UTC"
    if payload.notes is not None:
        appointment.notes = payload.notes

    if payload.use_ai:
        brief = build_ai_calendar_brief(case=appointment.case, appointment=appointment)
        appointment.ai_summary = brief["ai_summary"]
        appointment.ai_recommendation = brief["ai_recommendation"]
        appointment.ai_confidence = brief["ai_confidence"]
        appointment.ai_source = brief["ai_source"]

    db.commit()
    db.refresh(appointment)

    emit_appointment_updated(appointment)

    return {
        "message": "Appointment updated successfully.",
        "appointment": serialize_appointment(appointment),
    }


@router.delete("/{appointment_id}", response_model=AppointmentActionResponse)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    appointment = get_tenant_appointment_or_404(db=db, appointment_id=appointment_id, current_user=current_user)

    if current_user.role != UserRole.admin and appointment.lawyer_id not in {None, current_user.id}:
        raise HTTPException(status_code=403, detail="You can only cancel your own calendar appointments")

    appointment.status = "cancelled"
    db.commit()
    db.refresh(appointment)

    emit_appointment_cancelled(appointment)

    return {
        "message": "Appointment cancelled.",
        "appointment": serialize_appointment(appointment),
    }
