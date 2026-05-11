from __future__ import annotations

import re
import uuid
import logging
from hmac import compare_digest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import randint

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.api.client_portal_schema import (
    ClientPortalAccountOut,
    ClientPortalAppointmentRequest,
    ClientPortalAppointmentResponse,
    ClientPortalAssistantRequest,
    ClientPortalAssistantResponse,
    ClientPortalActivityItem,
    ClientPortalCaseItem,
    ClientPortalConsultationItem,
    ClientPortalDashboardMetrics,
    ClientPortalDashboardResponse,
    ClientPortalDocumentItem,
    ClientPortalLoginCodeRequest,
    ClientPortalLoginCodeVerifyRequest,
    ClientPortalLoginRequest,
    ClientPortalMessageResponse,
    ClientPortalRegisterRequest,
    ClientPortalToken,
)
from backend.core.hashing import hash_password, verify_password
from backend.core.jwt_handler import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY as STAFF_SECRET_KEY
from backend.core.config import settings
from backend.database.database import SessionLocal
from backend.models.case import Case
from backend.models.appointment import Appointment
from backend.models.client import Client
from backend.models.client_portal_account import ClientPortalAccount
from backend.models.client_portal_login_code import ClientPortalLoginCode
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.auth_rate_limiter import RateLimitConfig, auth_rate_limiter
from backend.services.appointment_n8n_service import (
    emit_appointment_cancelled,
    emit_appointment_created,
)
from backend.services.calendar_service import (
    appointment_visible_to_client,
    build_case_calendar_entries,
    normalize_appointment_type,
    serialize_appointment,
)
from backend.services.ai.runtime_services import copilot_orchestration_service
from backend.services.jobs.job_queue_service import background_job_service
from backend.services.client_portal_mail_service import client_portal_mail_service
from backend.services.use_cases.ingestion_use_case import ingestion_use_case
from backend.api.voice import is_supported_audio_upload
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


router = APIRouter(prefix="/portal", tags=["Client Portal"])
logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)
PASSWORD_POLICY_REGEX = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{10,}$")
portal_login_code_limit = RateLimitConfig.safe(
    max_attempts=settings.PORTAL_LOGIN_MAX_ATTEMPTS,
    window_seconds=settings.PORTAL_LOGIN_WINDOW_SECONDS,
    block_seconds=settings.PORTAL_LOGIN_BLOCK_SECONDS,
)
portal_verify_code_limit = RateLimitConfig.safe(
    max_attempts=settings.PORTAL_VERIFY_MAX_ATTEMPTS,
    window_seconds=settings.PORTAL_VERIFY_WINDOW_SECONDS,
    block_seconds=settings.PORTAL_VERIFY_BLOCK_SECONDS,
)
PORTAL_TOKEN_AUDIENCE = "client_portal"
DOCUMENT_DONE_STATUSES = {"processed", "completed"}


def is_document_done(status_value: str | None) -> bool:
    return (status_value or "").strip().lower() in DOCUMENT_DONE_STATUSES


def normalize_case_title(client_name: str, issue_summary: str) -> str:
    base_issue = re.sub(r"\s+", " ", issue_summary).strip()
    if len(base_issue) > 70:
        base_issue = base_issue[:67].rstrip() + "..."
    return f"Client Intake - {client_name} - {base_issue}"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_portal_account(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> ClientPortalAccount:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing portal token.")

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.PORTAL_SECRET_KEY or STAFF_SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=PORTAL_TOKEN_AUDIENCE,
        )
        account_id = payload.get("sub")
        token_type = payload.get("account_type")

        if token_type != "client_portal":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token.")

        account_id = int(account_id)
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired portal token.")

    account = db.query(ClientPortalAccount).filter(ClientPortalAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Portal account not found.")

    return account


def find_tenant_lawyer(db: Session, tenant_id: int) -> User | None:
    return (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.deleted_at.is_(None))
        .order_by(User.id.asc())
        .first()
    )


def get_portal_tenant_or_404(db: Session, tenant_slug: str) -> Tenant:
    normalized_slug = (tenant_slug or "").strip().lower()
    if settings.PORTAL_REQUIRE_TENANT_SLUG and not normalized_slug:
        raise HTTPException(status_code=400, detail="tenant_slug is required.")

    tenant = (
        db.query(Tenant)
        .filter(
            Tenant.slug == normalized_slug,
            Tenant.portal_access_enabled.is_(True),
        )
        .first()
    )
    if not tenant:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found or portal access is disabled.",
        )
    return tenant


def validate_portal_password(password: str) -> None:
    if not PASSWORD_POLICY_REGEX.match(password or ""):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 10 characters and include one uppercase letter and one symbol.",
        )


def generate_login_code() -> str:
    return f"{randint(0, 999999):06d}"


def get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.client.host if request.client else None


def issue_portal_token(account: ClientPortalAccount) -> dict[str, str]:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = jwt.encode(
        {
            "sub": str(account.id),
            "tenant_id": account.tenant_id,
            "client_id": account.client_id,
            "account_type": "client_portal",
            "aud": PORTAL_TOKEN_AUDIENCE,
            "exp": expire_at,
        },
        settings.PORTAL_SECRET_KEY or STAFF_SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return {"access_token": access_token, "token_type": "bearer"}


def get_or_create_client(
    db: Session,
    *,
    tenant_id: int,
    client_name: str,
    client_email: str | None,
    client_phone: str | None,
    client_address: str | None,
) -> Client:
    client = None

    if client_email:
        client = (
            db.query(Client)
            .filter(
                Client.tenant_id == tenant_id,
                Client.email == client_email,
                Client.deleted_at.is_(None),
            )
            .first()
        )

    if not client and client_phone:
        client = (
            db.query(Client)
            .filter(
                Client.tenant_id == tenant_id,
                Client.phone == client_phone,
                Client.deleted_at.is_(None),
            )
            .first()
        )

    if client:
        client.name = client.name or client_name
        client.address = client.address or client_address
        db.commit()
        db.refresh(client)
        return client

    client = Client(
        tenant_id=tenant_id,
        name=client_name,
        email=client_email,
        phone=client_phone,
        address=client_address,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


def ensure_portal_account_client_link(db: Session, account: ClientPortalAccount) -> Client:
    existing_client = None

    if account.client_id:
        existing_client = (
            db.query(Client)
            .filter(
                Client.id == account.client_id,
                Client.tenant_id == account.tenant_id,
                Client.deleted_at.is_(None),
            )
            .first()
        )

    client = existing_client or get_or_create_client(
        db,
        tenant_id=account.tenant_id,
        client_name=account.full_name,
        client_email=account.email,
        client_phone=account.phone,
        client_address=account.address,
    )

    changed = False
    if client.name != account.full_name and account.full_name:
        client.name = account.full_name
        changed = True
    if account.email and account.email != client.email:
        client.email = account.email
        changed = True
    if account.phone and account.phone != client.phone:
        client.phone = account.phone
        changed = True
    if account.address and account.address != client.address:
        client.address = account.address
        changed = True
    if account.client_id != client.id:
        account.client_id = client.id
        changed = True

    if changed:
        db.commit()
        db.refresh(client)
        db.refresh(account)

    return client


def get_portal_case_or_404(db: Session, account: ClientPortalAccount, case_id: int) -> Case:
    if not account.client_id:
        raise HTTPException(status_code=404, detail="No case is linked to this portal account yet.")

    case = (
        db.query(Case)
        .filter(
            Case.id == case_id,
            Case.client_id == account.client_id,
            Case.tenant_id == account.tenant_id,
            Case.deleted_at.is_(None),
        )
        .first()
    )

    if not case:
        raise HTTPException(status_code=404, detail="Case not found for this portal account.")

    return case


def build_account_out(account: ClientPortalAccount) -> dict:
    return {
        "id": account.id,
        "full_name": account.full_name,
        "email": account.email,
        "phone": account.phone,
        "address": account.address,
        "tenant_id": account.tenant_id,
        "client_id": account.client_id,
        "tenant_name": account.tenant.name if account.tenant else None,
        "tenant_slug": account.tenant.slug if account.tenant else None,
        "requires_email_verification": bool(account.requires_email_verification),
        "created_at": account.created_at,
    }


def build_dashboard_response(
    db: Session,
    account: ClientPortalAccount,
    *,
    jobs: list[dict] | None = None,
) -> dict:
    db.refresh(account)
    consultations = build_consultation_items(db, account)
    case_items, case_models = build_case_items(db, account)
    document_items = build_document_items(db, account)
    calendar_items = build_calendar_items(db, account, case_models)
    return {
        "account": build_account_out(account),
        "consultations": consultations,
        "cases": case_items,
        "documents": document_items,
        "calendar_events": calendar_items,
        "activity": build_activity_feed(
            consultations=consultations,
            documents=document_items,
            cases=case_items,
            calendar_events=calendar_items,
        ),
        "metrics": build_dashboard_metrics(
            consultations=consultations,
            cases=case_items,
            documents=document_items,
            calendar_events=calendar_items,
        ),
        "jobs": jobs or [],
    }


def get_accessible_case_ids(db: Session, account: ClientPortalAccount) -> list[int]:
    if not account.client_id:
        return []
    rows = (
        db.query(Case.id)
        .filter(
            Case.client_id == account.client_id,
            Case.tenant_id == account.tenant_id,
            Case.deleted_at.is_(None),
        )
        .order_by(Case.updated_at.desc(), Case.id.desc())
        .all()
    )
    return [row[0] for row in rows]


def get_accessible_document_ids(
    db: Session,
    account: ClientPortalAccount,
    *,
    case_id: int | None = None,
) -> list[int]:
    if not account.client_id:
        return []
    query = (
        db.query(Document.id)
        .join(Case, Case.id == Document.case_id)
        .filter(
            Case.client_id == account.client_id,
            Case.tenant_id == account.tenant_id,
            Case.deleted_at.is_(None),
            Document.tenant_id == account.tenant_id,
        )
    )
    if isinstance(case_id, int):
        query = query.filter(Document.case_id == case_id)
    rows = query.order_by(Document.upload_timestamp.desc(), Document.id.desc()).all()
    return [row[0] for row in rows]


def build_consultation_items(db: Session, account: ClientPortalAccount) -> list[dict]:
    if not account.client_id:
        return []

    consultations = (
        db.query(ConsultationRequest, Case)
        .join(Case, Case.id == ConsultationRequest.case_id)
        .filter(
            Case.client_id == account.client_id,
            ConsultationRequest.tenant_id == account.tenant_id,
        )
        .order_by(ConsultationRequest.created_at.desc(), ConsultationRequest.id.desc())
        .all()
    )

    return [
        {
            "id": consultation.id,
            "case_id": consultation.case_id,
            "case_title": case.title,
            "public_reference": consultation.public_reference,
            "status": consultation.status,
            "issue_summary": consultation.issue_summary,
            "preferred_schedule": consultation.preferred_schedule,
            "legal_area": consultation.legal_area,
            "urgency_level": consultation.urgency_level,
            "created_at": consultation.created_at,
        }
        for consultation, case in consultations
    ]


def build_case_items(db: Session, account: ClientPortalAccount) -> tuple[list[dict], list[Case]]:
    if not account.client_id:
        return [], []

    cases = (
        db.query(Case)
        .filter(
            Case.client_id == account.client_id,
            Case.tenant_id == account.tenant_id,
            Case.deleted_at.is_(None),
        )
        .order_by(Case.updated_at.desc(), Case.id.desc())
        .all()
    )

    if not cases:
        return [], []

    case_ids = [case.id for case in cases]

    consultations = (
        db.query(ConsultationRequest)
        .filter(
            ConsultationRequest.case_id.in_(case_ids),
            ConsultationRequest.tenant_id == account.tenant_id,
        )
        .all()
    )
    consultations_by_case: dict[int, list[ConsultationRequest]] = {}
    for row in consultations:
        consultations_by_case.setdefault(row.case_id, []).append(row)

    documents = (
        db.query(Document)
        .filter(
            Document.case_id.in_(case_ids),
            Document.tenant_id == account.tenant_id,
        )
        .all()
    )
    documents_by_case: dict[int, list[Document]] = {}
    for row in documents:
        documents_by_case.setdefault(row.case_id, []).append(row)

    items: list[dict] = []
    for case in cases:
        case_consultations = consultations_by_case.get(case.id, [])
        case_documents = documents_by_case.get(case.id, [])
        latest_consultation = sorted(
            case_consultations,
            key=lambda item: (item.updated_at or item.created_at),
            reverse=True,
        )[0] if case_consultations else None
        pending_documents = sum(1 for document in case_documents if not is_document_done(document.processing_status))

        if pending_documents > 0:
            next_step = "Your uploaded documents are currently being analyzed."
        elif latest_consultation and (latest_consultation.status or "").lower() in {"submitted", "new", "ready_for_review"}:
            next_step = "Your consultation request is under legal review."
        elif (case.status or "").lower() in {"open", "in_progress"}:
            next_step = "Your assigned lawyer is preparing the next legal step."
        else:
            next_step = "No immediate client action is required right now."

        items.append(
            {
                "id": case.id,
                "title": case.title,
                "description": case.description,
                "status": case.status,
                "jurisdiction_country": case.jurisdiction_country,
                "lawyer_name": case.lawyer.name if case.lawyer else None,
                "document_count": len(case_documents),
                "consultation_count": len(case_consultations),
                "next_recommended_step": next_step,
                "created_at": case.created_at,
                "updated_at": case.updated_at,
            }
        )

    return items, cases


def build_document_items(db: Session, account: ClientPortalAccount) -> list[dict]:
    if not account.client_id:
        return []

    documents = (
        db.query(Document, Case)
        .join(Case, Case.id == Document.case_id)
        .filter(
            Case.client_id == account.client_id,
            Case.tenant_id == account.tenant_id,
            Case.deleted_at.is_(None),
            Document.tenant_id == account.tenant_id,
        )
        .order_by(Document.upload_timestamp.desc(), Document.id.desc())
        .all()
    )

    return [
        {
            "id": document.id,
            "case_id": document.case_id,
            "case_title": case.title,
            "filename": document.filename,
            "file_type": document.file_type,
            "file_size": document.file_size,
            "processing_status": document.processing_status,
            "upload_timestamp": document.upload_timestamp,
        }
        for document, case in documents
    ]


def build_calendar_items(
    db: Session,
    account: ClientPortalAccount,
    cases: list[Case],
) -> list[dict]:
    if not account.client_id or not cases:
        return []

    case_ids = [case.id for case in cases]

    appointments = (
        db.query(Appointment)
        .join(Case, Case.id == Appointment.case_id)
        .filter(
            Appointment.tenant_id == account.tenant_id,
            Appointment.case_id.in_(case_ids),
            Case.client_id == account.client_id,
            Case.deleted_at.is_(None),
        )
        .order_by(Appointment.scheduled_at.asc(), Appointment.id.asc())
        .all()
    )
    appointments_by_case: dict[int, list[Appointment]] = {}
    for appointment in appointments:
        if appointment_visible_to_client(appointment, account.client_id):
            appointments_by_case.setdefault(appointment.case_id, []).append(appointment)

    consultations = (
        db.query(ConsultationRequest, Case)
        .join(Case, Case.id == ConsultationRequest.case_id)
        .filter(
            ConsultationRequest.tenant_id == account.tenant_id,
            ConsultationRequest.case_id.in_(case_ids),
            Case.client_id == account.client_id,
            Case.deleted_at.is_(None),
        )
        .order_by(ConsultationRequest.created_at.desc(), ConsultationRequest.id.desc())
        .all()
    )
    consultations_by_case: dict[int, list[ConsultationRequest]] = {}
    cases_by_id = {case.id: case for case in cases}
    for consultation, case in consultations:
        consultations_by_case.setdefault(consultation.case_id, []).append(consultation)
        cases_by_id.setdefault(case.id, case)

    calendar_items: list[dict] = []
    for case in cases:
        case_appointments = appointments_by_case.get(case.id, [])
        case_consultations = consultations_by_case.get(case.id, [])
        if case_appointments:
            calendar_items.extend(serialize_appointment(appointment) for appointment in case_appointments)
        elif case_consultations:
            calendar_items.extend(
                build_case_calendar_entries(
                    case=cases_by_id[case.id],
                    appointments=[],
                    consultations=case_consultations,
                )
            )

    calendar_items.sort(key=lambda item: item.get("scheduled_at") or datetime.min.replace(tzinfo=timezone.utc))
    return calendar_items


def build_dashboard_metrics(
    consultations: list[dict],
    cases: list[dict],
    documents: list[dict],
    calendar_events: list[dict],
) -> dict:
    active_cases = sum(1 for case in cases if (case.get("status") or "").lower() in {"open", "in_progress"})
    pending_documents = sum(1 for document in documents if not is_document_done(document.get("processing_status")))
    requests_under_review = sum(
        1
        for consultation in consultations
        if (consultation.get("status") or "").lower() in {"submitted", "new", "ready_for_review"}
    )
    upcoming_appointments = sum(
        1
        for event in calendar_events
        if (event.get("status") or "").lower() in {"scheduled", "confirmed", "tentative"}
    )
    return {
        "total_cases": len(cases),
        "active_cases": active_cases,
        "total_documents": len(documents),
        "pending_documents": pending_documents,
        "consultation_requests": len(consultations),
        "requests_under_review": requests_under_review,
        "upcoming_appointments": upcoming_appointments,
    }


def build_activity_feed(
    consultations: list[dict],
    documents: list[dict],
    cases: list[dict],
    calendar_events: list[dict],
) -> list[dict]:
    activity: list[dict] = []

    for consultation in consultations[:12]:
        activity.append(
            {
                "id": f"consultation-{consultation['id']}",
                "event_type": "consultation_update",
                "title": f"Consultation request is {consultation['status']}",
                "description": consultation["issue_summary"],
                "created_at": consultation["created_at"],
                "case_id": consultation["case_id"],
            }
        )

    for document in documents[:12]:
        processing_status = (document.get("processing_status") or "").strip().lower()
        status_label = "completed" if is_document_done(processing_status) else (processing_status or "pending")
        activity.append(
            {
                "id": f"document-{document['id']}",
                "event_type": "document_update",
                "title": f"Document '{document['filename']}' is {status_label}",
                "description": f"Attached to case: {document['case_title']}",
                "created_at": document["upload_timestamp"],
                "case_id": document["case_id"],
            }
        )

    for case in cases[:8]:
        activity.append(
            {
                "id": f"case-{case['id']}",
                "event_type": "case_update",
                "title": f"Case status: {case['status']}",
                "description": case["title"],
                "created_at": case["updated_at"],
                "case_id": case["id"],
            }
        )

    for event in calendar_events[:10]:
        if event.get("is_ai_suggested"):
            continue
        activity.append(
            {
                "id": f"calendar-{event['id']}",
                "event_type": "calendar_update",
                "title": f"Calendar item: {event['title']}",
                "description": event.get("ai_summary") or event.get("notes") or event.get("description") or "Appointment updated.",
                "created_at": event.get("created_at") or event.get("scheduled_at"),
                "case_id": event.get("case_id"),
            }
        )

    activity.sort(key=lambda item: item.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return activity[:18]


@router.post("/auth/register", response_model=ClientPortalMessageResponse, status_code=status.HTTP_201_CREATED)
def register_portal_account(data: ClientPortalRegisterRequest, db: Session = Depends(get_db)):
    normalized_email = data.email.lower().strip()
    normalized_name = data.full_name.strip()
    normalized_phone = data.phone.strip() if data.phone else None
    normalized_address = data.address.strip() if data.address else None

    existing = db.query(ClientPortalAccount).filter(ClientPortalAccount.email == normalized_email).first()
    if existing:
        raise HTTPException(status_code=400, detail="A portal account already exists for this email.")

    validate_portal_password(data.password)
    tenant = get_portal_tenant_or_404(db, data.tenant_slug)

    account = ClientPortalAccount(
        full_name=normalized_name,
        email=normalized_email,
        hashed_password=hash_password(data.password),
        phone=normalized_phone,
        address=normalized_address,
        tenant_id=tenant.id,
        client_id=None,
        requires_email_verification=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return {"message": "Account created successfully. First login requires one-time verification code."}


@router.post("/auth/login/request-code", response_model=ClientPortalMessageResponse)
def request_login_code(data: ClientPortalLoginCodeRequest, request: Request, db: Session = Depends(get_db)):
    normalized_email = data.email.lower().strip()
    client_ip = get_client_ip(request)

    auth_rate_limiter.assert_allowed(
        scope="portal-login-code",
        identifier=normalized_email,
        client_ip=client_ip,
        config=portal_login_code_limit,
    )

    account = db.query(ClientPortalAccount).filter(ClientPortalAccount.email == normalized_email).first()
    if not account or not verify_password(data.password, account.hashed_password):
        auth_rate_limiter.record_failure(
            scope="portal-login-code",
            identifier=normalized_email,
            client_ip=client_ip,
            config=portal_login_code_limit,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    auth_rate_limiter.record_success(
        scope="portal-login-code",
        identifier=normalized_email,
        client_ip=client_ip,
    )

    if not account.requires_email_verification:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Verification code is only required for first login. Sign in directly with email and password.",
        )

    now = datetime.now(timezone.utc)
    active_codes = (
        db.query(ClientPortalLoginCode)
        .filter(
            ClientPortalLoginCode.portal_account_id == account.id,
            ClientPortalLoginCode.purpose == "login",
            ClientPortalLoginCode.consumed_at.is_(None),
        )
        .all()
    )
    for active_code in active_codes:
        active_code.consumed_at = now

    code = generate_login_code()
    login_code = ClientPortalLoginCode(
        portal_account_id=account.id,
        email=account.email,
        code=code,
        purpose="login",
        expires_at=now + timedelta(minutes=settings.PORTAL_LOGIN_CODE_EXPIRE_MINUTES),
        delivery_status="pending",
    )
    db.add(login_code)
    db.commit()
    db.refresh(login_code)

    try:
        delivery_channel = client_portal_mail_service.send_login_code(recipient_email=account.email, code=code)
        login_code.delivery_status = "sent"
        login_code.delivery_error = None
        db.commit()
        return {"message": f"A six-digit access code has been sent via {delivery_channel}."}
    except Exception as exc:
        login_code.delivery_status = "failed"
        login_code.delivery_error = str(exc)
        db.commit()

        if settings.PORTAL_ALLOW_CONSOLE_CODE_FALLBACK:
            logger.warning(
                "Portal SMTP delivery failed for %s. Falling back to console login code delivery.",
                account.email,
            )
            logger.warning("PORTAL LOGIN CODE [%s]: %s", account.email, code)
            return {"message": "SMTP delivery failed. Your access code was generated and logged on the server console."}

        raise HTTPException(
            status_code=500,
            detail="Unable to send the access code email. Check SMTP settings and try again.",
        )


@router.post("/auth/login/verify-code", response_model=ClientPortalToken)
def verify_login_code(data: ClientPortalLoginCodeVerifyRequest, request: Request, db: Session = Depends(get_db)):
    normalized_email = data.email.lower().strip()
    client_ip = get_client_ip(request)

    auth_rate_limiter.assert_allowed(
        scope="portal-verify-code",
        identifier=normalized_email,
        client_ip=client_ip,
        config=portal_verify_code_limit,
    )

    account = db.query(ClientPortalAccount).filter(ClientPortalAccount.email == normalized_email).first()
    if not account:
        auth_rate_limiter.record_failure(
            scope="portal-verify-code",
            identifier=normalized_email,
            client_ip=client_ip,
            config=portal_verify_code_limit,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification request.")

    login_code = (
        db.query(ClientPortalLoginCode)
        .filter(
            ClientPortalLoginCode.portal_account_id == account.id,
            ClientPortalLoginCode.email == account.email,
            ClientPortalLoginCode.purpose == "login",
            ClientPortalLoginCode.consumed_at.is_(None),
        )
        .order_by(ClientPortalLoginCode.created_at.desc(), ClientPortalLoginCode.id.desc())
        .first()
    )

    if not login_code:
        auth_rate_limiter.record_failure(
            scope="portal-verify-code",
            identifier=normalized_email,
            client_ip=client_ip,
            config=portal_verify_code_limit,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active access code was found.")

    if login_code.expires_at < datetime.now(timezone.utc):
        auth_rate_limiter.record_failure(
            scope="portal-verify-code",
            identifier=normalized_email,
            client_ip=client_ip,
            config=portal_verify_code_limit,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This access code has expired.")

    if not compare_digest(login_code.code, data.code):
        auth_rate_limiter.record_failure(
            scope="portal-verify-code",
            identifier=normalized_email,
            client_ip=client_ip,
            config=portal_verify_code_limit,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code.")

    auth_rate_limiter.record_success(
        scope="portal-verify-code",
        identifier=normalized_email,
        client_ip=client_ip,
    )

    now = datetime.now(timezone.utc)
    login_code.consumed_at = now
    account.requires_email_verification = False
    account.verified_at = account.verified_at or now
    account.last_login_at = now
    ensure_portal_account_client_link(db, account)
    db.commit()
    db.refresh(account)

    return issue_portal_token(account)


@router.post("/auth/login", response_model=ClientPortalToken)
def login_portal_account(data: ClientPortalLoginRequest, request: Request, db: Session = Depends(get_db)):
    normalized_email = data.email.lower().strip()
    client_ip = get_client_ip(request)

    auth_rate_limiter.assert_allowed(
        scope="portal-login-password",
        identifier=normalized_email,
        client_ip=client_ip,
        config=portal_login_code_limit,
    )

    account = db.query(ClientPortalAccount).filter(ClientPortalAccount.email == normalized_email).first()
    if not account or not verify_password(data.password, account.hashed_password):
        auth_rate_limiter.record_failure(
            scope="portal-login-password",
            identifier=normalized_email,
            client_ip=client_ip,
            config=portal_login_code_limit,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    auth_rate_limiter.record_success(
        scope="portal-login-password",
        identifier=normalized_email,
        client_ip=client_ip,
    )

    if account.requires_email_verification:
        previously_verified = (
            db.query(ClientPortalLoginCode.id)
            .filter(
                ClientPortalLoginCode.portal_account_id == account.id,
                ClientPortalLoginCode.purpose == "login",
                ClientPortalLoginCode.consumed_at.is_not(None),
            )
            .first()
        )

        if previously_verified:
            account.requires_email_verification = False
            account.verified_at = account.verified_at or datetime.now(timezone.utc)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Verification code is required for first login. Request a code and verify once.",
            )

    account.last_login_at = datetime.now(timezone.utc)
    ensure_portal_account_client_link(db, account)
    db.commit()
    db.refresh(account)

    return issue_portal_token(account)


@router.get("/auth/me", response_model=ClientPortalAccountOut)
def me_portal_account(account: ClientPortalAccount = Depends(get_current_portal_account)):
    return build_account_out(account)


@router.get("/dashboard", response_model=ClientPortalDashboardResponse)
def dashboard(
    db: Session = Depends(get_db),
    account: ClientPortalAccount = Depends(get_current_portal_account),
):
    return build_dashboard_response(db, account)


@router.post("/cases/{case_id}/uploads", response_model=ClientPortalDashboardResponse, status_code=status.HTTP_201_CREATED)
def upload_case_materials(
    case_id: int,
    background_tasks: BackgroundTasks,
    voice_note: UploadFile | None = File(None),
    supporting_document: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    account: ClientPortalAccount = Depends(get_current_portal_account),
):
    if (not voice_note or not voice_note.filename) and (not supporting_document or not supporting_document.filename):
        raise HTTPException(status_code=400, detail="Upload at least one PDF or voice file.")

    case = get_portal_case_or_404(db=db, account=account, case_id=case_id)
    jobs: list[dict] = []

    if voice_note and voice_note.filename:
        if not is_supported_audio_upload(voice_note.filename, voice_note.content_type):
            raise HTTPException(
                status_code=400,
                detail="Unsupported audio format. Use webm, wav, mp3, mp4, ogg, or m4a.",
            )

        voice_note.file.seek(0, 2)
        voice_size = voice_note.file.tell()
        voice_note.file.seek(0)
        max_voice_bytes = max(1, int(settings.VOICE_UPLOAD_MAX_MB)) * 1024 * 1024
        if voice_size > max_voice_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Voice note too large. Maximum allowed size is {settings.VOICE_UPLOAD_MAX_MB} MB.",
            )
        _, voice_job = ingestion_use_case.create_voice_upload(
            db=db,
            case=case,
            file=voice_note,
            uploaded_by_user_id=None,
            background_tasks=background_tasks,
        )
        if voice_job:
            jobs.append(voice_job)

    if supporting_document and supporting_document.filename:
        _, document_job = ingestion_use_case.create_document_upload(
            db=db,
            case=case,
            file=supporting_document,
            background_tasks=background_tasks,
        )
        if document_job:
            jobs.append(document_job)

    return build_dashboard_response(db, account, jobs=jobs)


@router.post("/intake/submit", response_model=ClientPortalDashboardResponse, status_code=status.HTTP_201_CREATED)
def submit_authenticated_intake(
    background_tasks: BackgroundTasks,
    issue_summary: str = Form(...),
    case_description: str | None = Form(None),
    preferred_schedule: str | None = Form(None),
    voice_note: UploadFile | None = File(None),
    supporting_document: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    account: ClientPortalAccount = Depends(get_current_portal_account),
):
    lawyer = find_tenant_lawyer(db, account.tenant_id)
    if not lawyer:
        raise HTTPException(
            status_code=400,
            detail="This tenant has no staff account available to receive portal requests.",
        )

    client = ensure_portal_account_client_link(db, account)

    case = Case(
        title=normalize_case_title(account.full_name, issue_summary),
        description=case_description or issue_summary,
        status="open",
        jurisdiction_country="tunisia",
        tenant_id=account.tenant_id,
        lawyer_id=lawyer.id,
        client_id=client.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    consultation = ConsultationRequest(
        case_id=case.id,
        tenant_id=account.tenant_id,
        client_name=account.full_name,
        client_email=account.email,
        client_phone=client.phone,
        booking_intent="requested" if preferred_schedule else "not_detected",
        urgency_level="normal",
        preferred_schedule=preferred_schedule,
        issue_summary=issue_summary,
        extracted_case_description=case_description,
        intake_notes="Submitted through the authenticated client portal.",
        status="submitted",
        extraction_source="client_portal_authenticated",
        public_reference=f"INT-{uuid.uuid4().hex[:10].upper()}",
        source_channel="client_portal",
    )
    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    jobs: list[dict] = []

    if voice_note and voice_note.filename:
        if not is_supported_audio_upload(voice_note.filename, voice_note.content_type):
            raise HTTPException(
                status_code=400,
                detail="Unsupported audio format. Use webm, wav, mp3, mp4, ogg, or m4a.",
            )
        voice_note.file.seek(0, 2)
        voice_size = voice_note.file.tell()
        voice_note.file.seek(0)
        max_voice_bytes = max(1, int(settings.VOICE_UPLOAD_MAX_MB)) * 1024 * 1024
        if voice_size > max_voice_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Voice note too large. Maximum allowed size is {settings.VOICE_UPLOAD_MAX_MB} MB.",
            )
        recording, voice_job = ingestion_use_case.create_voice_upload(
            db=db,
            case=case,
            file=voice_note,
            uploaded_by_user_id=None,
            consultation_request_id=consultation.id,
            background_tasks=background_tasks,
        )

        consultation.voice_recording_id = recording.id
        db.commit()
        if voice_job:
            jobs.append(voice_job)

    if supporting_document and supporting_document.filename:
        _, document_job = ingestion_use_case.create_document_upload(
            db=db,
            case=case,
            file=supporting_document,
            background_tasks=background_tasks,
        )
        if document_job:
            jobs.append(document_job)

    snapshot_job = ingestion_use_case.enqueue_case_snapshot_refresh(
        db=db,
        tenant_id=account.tenant_id,
        case_id=case.id,
        background_tasks=background_tasks,
    )
    if snapshot_job:
        jobs.append(snapshot_job)

    return build_dashboard_response(db, account, jobs=jobs)


@router.get("/jobs/{job_id}")
def get_portal_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    account: ClientPortalAccount = Depends(get_current_portal_account),
):
    job = background_job_service.get_job(db=db, job_id=job_id)
    if not job or job.tenant_id != account.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    accessible_case_ids = set(get_accessible_case_ids(db, account))
    if job.case_id is not None and job.case_id not in accessible_case_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    return background_job_service.to_public_payload(job)


@router.post("/assistant", response_model=ClientPortalAssistantResponse)
def portal_assistant(
    data: ClientPortalAssistantRequest,
    db: Session = Depends(get_db),
    account: ClientPortalAccount = Depends(get_current_portal_account),
):
    accessible_case_ids = get_accessible_case_ids(db, account)
    if not accessible_case_ids:
        return {
            "answer": "No active case is linked to your portal account yet. Upload documents or submit a request first.",
            "confidence": "medium",
            "scope": "tenant",
            "sources": [],
            "citations": [],
            "execution_trace": [],
            "case_snapshot_version": None,
        }

    selected_case_id = data.case_id
    if selected_case_id is None:
        if len(accessible_case_ids) == 1:
            selected_case_id = accessible_case_ids[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select a case before using the portal assistant.",
            )

    if selected_case_id not in accessible_case_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found for this portal account.")

    accessible_document_ids = get_accessible_document_ids(db, account, case_id=selected_case_id)
    if data.document_id is not None and data.document_id not in accessible_document_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found for this portal account.",
        )

    result = copilot_orchestration_service.run(
        db=db,
        tenant_id=account.tenant_id,
        user_id=None,
        user_role="client",
        message=data.message,
        top_k=data.top_k,
        use_external_research=False,
        mode="default",
        legal_search_multilingual_output=False,
        agent_mode=False,
        workspace_case_id=selected_case_id,
        workspace_document_id=data.document_id,
        conversation_history=data.conversation_history,
        allowed_case_ids=accessible_case_ids,
        allowed_document_ids=accessible_document_ids,
    )

    return {
        "answer": result.get("answer", ""),
        "confidence": result.get("confidence", "medium"),
        "scope": result.get("scope", "case"),
        "sources": result.get("sources", []),
        "citations": result.get("citations", []),
        "execution_trace": result.get("execution_trace", []),
        "case_snapshot_version": result.get("case_snapshot_version"),
    }


# ── Client-facing appointment booking ──────────────────────────────────────────


@router.post(
    "/cases/{case_id}/appointments",
    response_model=ClientPortalAppointmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def book_portal_appointment(
    case_id: int,
    payload: ClientPortalAppointmentRequest,
    db: Session = Depends(get_db),
    account: ClientPortalAccount = Depends(get_current_portal_account),
):
    case = get_portal_case_or_404(db=db, account=account, case_id=case_id)

    scheduled_at = payload.scheduled_at
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    if scheduled_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Appointment must be scheduled in the future.")

    appointment = Appointment(
        case_id=case.id,
        tenant_id=account.tenant_id,
        lawyer_id=case.lawyer_id,
        client_id=case.client_id,
        created_by_user_id=None,
        title=payload.title.strip(),
        appointment_type=normalize_appointment_type(payload.appointment_type),
        visibility_scope="shared",
        status="scheduled",
        scheduled_at=scheduled_at,
        duration_minutes=payload.duration_minutes,
        location=payload.location,
        timezone_name=(payload.timezone_name or "UTC").strip() or "UTC",
        notes=payload.notes,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    emit_appointment_created(appointment)

    return {
        "message": "Appointment booked.",
        "appointment": serialize_appointment(appointment),
    }


@router.delete(
    "/appointments/{appointment_id}",
    response_model=ClientPortalAppointmentResponse,
)
def cancel_portal_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    account: ClientPortalAccount = Depends(get_current_portal_account),
):
    if not account.client_id:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.tenant_id == account.tenant_id,
            Appointment.client_id == account.client_id,
        )
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if appointment.status == "cancelled":
        return {
            "message": "Appointment was already cancelled.",
            "appointment": serialize_appointment(appointment),
        }

    appointment.status = "cancelled"
    db.commit()
    db.refresh(appointment)

    emit_appointment_cancelled(appointment)

    return {
        "message": "Appointment cancelled.",
        "appointment": serialize_appointment(appointment),
    }
