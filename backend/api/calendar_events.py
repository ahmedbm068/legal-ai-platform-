from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from backend.api.calendar_schema import (
    CalendarEventActionResponse,
    CalendarEventCreate,
    CalendarEventOut,
    CalendarEventUpdate,
    CalendarReminderCreate,
    CalendarReminderOut,
)
from backend.core.deps import get_current_user, get_db
from backend.core.enums import UserRole
from backend.core.permissions import require_roles
from backend.models.calendar_event import CalendarEvent
from backend.models.calendar_reminder import CalendarReminder
from backend.models.case import Case
from backend.models.user import User
from backend.services.calendar_reminder_service import calendar_reminder_service
from backend.services.calendar_service import calendar_event_service


router = APIRouter(tags=["Legal Calendar"])


def _tenant_id(current_user: User) -> int:
    tenant_id = int(current_user.tenant_id or 0)
    if tenant_id <= 0:
        raise HTTPException(status_code=403, detail="Current user is not attached to a tenant")
    return tenant_id


def _event_query(db: Session):
    return db.query(CalendarEvent).options(
        selectinload(CalendarEvent.case),
        selectinload(CalendarEvent.client),
        selectinload(CalendarEvent.source_document),
        selectinload(CalendarEvent.reminders),
    )


def get_tenant_event_or_404(db: Session, event_id: int, current_user: User, *, include_deleted: bool = False) -> CalendarEvent:
    query = _event_query(db).filter(CalendarEvent.id == event_id, CalendarEvent.tenant_id == _tenant_id(current_user))
    if not include_deleted:
        query = query.filter(CalendarEvent.deleted_at.is_(None))
    event = query.first()
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    return event


def get_tenant_case_or_404(db: Session, case_id: int, current_user: User) -> Case:
    case = (
        db.query(Case)
        .filter(Case.id == case_id, Case.tenant_id == _tenant_id(current_user), Case.deleted_at.is_(None))
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/calendar/events", response_model=list[CalendarEventOut])
def list_global_events(
    case_id: Optional[int] = Query(default=None, ge=1),
    client_id: Optional[int] = Query(default=None, ge=1),
    event_type: Optional[str] = None,
    priority: Optional[str] = None,
    status_value: Optional[str] = Query(default=None, alias="status"),
    requires_review: Optional[bool] = None,
    from_datetime: Optional[datetime] = None,
    to_datetime: Optional[datetime] = None,
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = calendar_event_service.list_events(
        db=db,
        tenant_id=_tenant_id(current_user),
        case_id=case_id,
        client_id=client_id,
        event_type=event_type,
        priority=priority,
        status=status_value,
        requires_review=requires_review,
        from_datetime=from_datetime,
        to_datetime=to_datetime,
        limit=limit,
    )
    return [calendar_event_service.serialize_event(row) for row in rows]


@router.post("/calendar/events", response_model=CalendarEventActionResponse, status_code=status.HTTP_201_CREATED)
def create_global_event(
    payload: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])
    case = get_tenant_case_or_404(db, payload.case_id, current_user) if payload.case_id else None
    event, _created = calendar_event_service.create_event(
        db=db,
        tenant_id=_tenant_id(current_user),
        created_by=current_user.id,
        payload=payload,
        case=case,
    )
    event = get_tenant_event_or_404(db, event.id, current_user)
    return {"message": "Calendar event created.", "event": calendar_event_service.serialize_event(event)}


@router.get("/calendar/events/{event_id}", response_model=CalendarEventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calendar_event_service.serialize_event(get_tenant_event_or_404(db, event_id, current_user))


@router.patch("/calendar/events/{event_id}", response_model=CalendarEventActionResponse)
def update_event(
    event_id: int,
    payload: CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])
    event = get_tenant_event_or_404(db, event_id, current_user)
    updated = calendar_event_service.update_event(db=db, event=event, payload=payload, reviewer_id=current_user.id)
    updated = get_tenant_event_or_404(db, updated.id, current_user)
    return {"message": "Calendar event updated.", "event": calendar_event_service.serialize_event(updated)}


@router.delete("/calendar/events/{event_id}", response_model=CalendarEventActionResponse)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])
    event = get_tenant_event_or_404(db, event_id, current_user)
    deleted = calendar_event_service.soft_delete_event(db=db, event=event)
    return {"message": "Calendar event archived.", "event": calendar_event_service.serialize_event(deleted)}


@router.get("/cases/{case_id}/calendar/events", response_model=list[CalendarEventOut])
def list_case_events(
    case_id: int,
    event_type: Optional[str] = None,
    priority: Optional[str] = None,
    status_value: Optional[str] = Query(default=None, alias="status"),
    requires_review: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = get_tenant_case_or_404(db, case_id, current_user)
    rows = calendar_event_service.list_events(
        db=db,
        tenant_id=case.tenant_id,
        case_id=case.id,
        event_type=event_type,
        priority=priority,
        status=status_value,
        requires_review=requires_review,
    )
    return [calendar_event_service.serialize_event(row) for row in rows]


@router.post("/cases/{case_id}/calendar/events", response_model=CalendarEventActionResponse, status_code=status.HTTP_201_CREATED)
def create_case_event(
    case_id: int,
    payload: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])
    case = get_tenant_case_or_404(db, case_id, current_user)
    payload.case_id = case.id
    event, _created = calendar_event_service.create_event(
        db=db,
        tenant_id=case.tenant_id,
        created_by=current_user.id,
        payload=payload,
        case=case,
    )
    event = get_tenant_event_or_404(db, event.id, current_user)
    return {"message": "Case calendar event created.", "event": calendar_event_service.serialize_event(event)}


@router.get("/calendar/extracted-dates/pending", response_model=list[CalendarEventOut])
def list_pending_extracted_dates(
    case_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = calendar_event_service.list_events(
        db=db,
        tenant_id=_tenant_id(current_user),
        case_id=case_id,
        requires_review=True,
        status="tentative",
        limit=500,
    )
    return [calendar_event_service.serialize_event(row) for row in rows]


@router.post("/calendar/extracted-dates/{event_id}/accept", response_model=CalendarEventActionResponse)
def accept_extracted_date(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])
    event = get_tenant_event_or_404(db, event_id, current_user)
    accepted = calendar_event_service.accept_event(db=db, event=event, reviewer_id=current_user.id)
    accepted = get_tenant_event_or_404(db, accepted.id, current_user)
    return {"message": "AI-detected date accepted.", "event": calendar_event_service.serialize_event(accepted)}


@router.post("/calendar/extracted-dates/{event_id}/reject", response_model=CalendarEventActionResponse)
def reject_extracted_date(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])
    event = get_tenant_event_or_404(db, event_id, current_user)
    rejected = calendar_event_service.reject_event(db=db, event=event, reviewer_id=current_user.id)
    return {"message": "AI-detected date rejected and archived for audit.", "event": calendar_event_service.serialize_event(rejected)}


@router.post("/calendar/events/{event_id}/reminders", response_model=CalendarReminderOut, status_code=status.HTTP_201_CREATED)
def create_event_reminder(
    event_id: int,
    payload: CalendarReminderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_roles(current_user, [UserRole.admin, UserRole.lawyer])
    event = get_tenant_event_or_404(db, event_id, current_user)
    reminder = calendar_reminder_service.create_reminder(
        db=db,
        event=event,
        remind_at=payload.remind_at,
        method=payload.method,
    )
    db.commit()
    db.refresh(reminder)
    return {
        "id": reminder.id,
        "tenant_id": reminder.tenant_id,
        "event_id": reminder.event_id,
        "remind_at": reminder.remind_at,
        "method": reminder.method,
        "status": reminder.status,
        "created_at": reminder.created_at,
        "event_title": event.title,
    }


@router.get("/calendar/reminders/upcoming", response_model=list[CalendarReminderOut])
def list_upcoming_reminders(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(CalendarReminder)
        .join(CalendarEvent, CalendarEvent.id == CalendarReminder.event_id)
        .filter(
            CalendarReminder.tenant_id == _tenant_id(current_user),
            CalendarReminder.status == "pending",
            CalendarReminder.remind_at >= datetime.now(timezone.utc),
            CalendarEvent.deleted_at.is_(None),
        )
        .order_by(CalendarReminder.remind_at.asc(), CalendarReminder.id.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "event_id": row.event_id,
            "remind_at": row.remind_at,
            "method": row.method,
            "status": row.status,
            "created_at": row.created_at,
            "event_title": row.event.title if row.event else None,
        }
        for row in rows
    ]
