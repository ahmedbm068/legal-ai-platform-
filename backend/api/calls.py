from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from backend.api.call_schema import CallSessionCreate, CallSessionCreateResponse, CallSessionOut
from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope, is_admin, require_lawyer
from backend.models.call_session import CallSession
from backend.models.case import Case
from backend.models.client import Client
from backend.models.user import User
from backend.services.n8n_workflow_service import n8n_workflow_service


router = APIRouter(prefix="/calls", tags=["Calls"])


def get_tenant_case_or_404(db: Session, case_id: int, current_user: User) -> Case:
    case_query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return case


def get_tenant_call_session_or_404(db: Session, call_session_id: int, current_user: User) -> CallSession:
    query = (
        db.query(CallSession)
        .options(selectinload(CallSession.voice_recording))
        .filter(CallSession.id == call_session_id)
    )
    call_session = apply_tenant_scope(query, CallSession.tenant_id, current_user).first()

    if not call_session:
        raise HTTPException(status_code=404, detail="Call session not found")

    return call_session


@router.get("/case/{case_id}", response_model=list[CallSessionOut])
def list_case_call_sessions(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    query = (
        db.query(CallSession)
        .options(selectinload(CallSession.voice_recording))
        .filter(CallSession.case_id == case_id)
        .order_by(CallSession.created_at.desc(), CallSession.id.desc())
    )
    return apply_tenant_scope(query, CallSession.tenant_id, current_user).all()


@router.get("/{call_session_id}", response_model=CallSessionOut)
def get_call_session(
    call_session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_tenant_call_session_or_404(db=db, call_session_id=call_session_id, current_user=current_user)


@router.post("/case/{case_id}", response_model=CallSessionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_call_session(
    case_id: int,
    payload: CallSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_lawyer),
):
    case = get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    client = db.query(Client).filter(Client.id == case.client_id, Client.deleted_at.is_(None)).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    resolved_tenant_id = client.tenant_id if is_admin(current_user) else current_user.tenant_id
    if resolved_tenant_id != case.tenant_id:
        raise HTTPException(status_code=403, detail="Call sessions must stay within the current tenant")

    caller_phone = (payload.caller_phone or current_user.phone or "").strip()
    if not caller_phone:
        raise HTTPException(status_code=400, detail="Lawyer phone number is required before creating a call session")

    client_phone = (payload.client_phone or client.phone or "").strip() or None

    consent_message = n8n_workflow_service.build_consent_message(
        case=case,
        client=client,
        lawyer=current_user,
        caller_phone=caller_phone,
    )

    call_session = CallSession(
        case_id=case.id,
        tenant_id=case.tenant_id,
        client_id=case.client_id,
        started_by_user_id=current_user.id,
        provider_name=(payload.provider_name or "whatsapp").strip() or "whatsapp",
        caller_phone=caller_phone,
        client_phone=client_phone,
        call_status="awaiting_consent",
        recording_status="waiting_for_audio",
        summary_status="pending",
        consent_accepted=False,
        consent_request_status="pending",
        consent_message=consent_message,
        notes=payload.notes,
    )
    db.add(call_session)
    db.commit()
    db.refresh(call_session)

    dispatch_result = n8n_workflow_service.request_consent(
        call_session=call_session,
        case=case,
        client=client,
        lawyer=current_user,
    )

    if not dispatch_result.get("success"):
        call_session.consent_request_status = "manual"
        call_session.consent_requested_at = datetime.now(timezone.utc)
        call_session.consent_message = dispatch_result.get("consent_message") or consent_message
        db.commit()
        db.refresh(call_session)
        return {
            "call_session": call_session,
            "message": "WhatsApp opened in manual mode. Send the consent message there to continue.",
            "consent_message": consent_message,
            "whatsapp_chat_url": dispatch_result.get("whatsapp_chat_url"),
            "consent_delivery_mode": "manual",
        }

    call_session.consent_request_status = "sent"
    call_session.consent_requested_at = datetime.now(timezone.utc)
    call_session.consent_message = dispatch_result.get("consent_message") or consent_message
    db.commit()
    db.refresh(call_session)
    message = "WhatsApp consent draft is ready. Open it and send the message to the client to continue."
    consent_delivery_mode = "manual"
    whatsapp_chat_url = dispatch_result.get("whatsapp_chat_url")

    call_session = get_tenant_call_session_or_404(db=db, call_session_id=call_session.id, current_user=current_user)
    return {
        "call_session": call_session,
        "message": message,
        "consent_message": consent_message,
        "whatsapp_chat_url": whatsapp_chat_url,
        "consent_delivery_mode": consent_delivery_mode,
    }