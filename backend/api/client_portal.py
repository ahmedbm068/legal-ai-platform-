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
from backend.core.jwt_handler import ALGORITHM, SECRET_KEY, create_access_token
from backend.core.config import settings
from backend.database.database import SessionLocal
from backend.models.case import Case
from backend.models.client import Client
from backend.models.client_portal_account import ClientPortalAccount
from backend.models.client_portal_login_code import ClientPortalLoginCode
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.auth_rate_limiter import RateLimitConfig, auth_rate_limiter
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.client_portal_mail_service import client_portal_mail_service
from backend.services.storage_service import upload_file
from backend.services.voice_processing_service import process_voice_recording
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


router = APIRouter(prefix="/portal", tags=["Client Portal"])
logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)
pipeline = DocumentAIPipeline()
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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


def get_default_tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
    if not tenant:
        raise HTTPException(
            status_code=400,
            detail="No tenant is configured for the platform yet.",
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
    access_token = create_access_token(
        data={
            "sub": str(account.id),
            "tenant_id": account.tenant_id,
            "client_id": account.client_id,
            "account_type": "client_portal",
        }
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


def build_account_out(account: ClientPortalAccount) -> dict:
    return {
        "id": account.id,
        "full_name": account.full_name,
        "email": account.email,
        "tenant_id": account.tenant_id,
        "client_id": account.client_id,
        "tenant_name": account.tenant.name if account.tenant else None,
        "created_at": account.created_at,
    }


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
        pending_documents = sum(1 for document in case_documents if (document.processing_status or "").lower() != "completed")

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


def build_dashboard_metrics(
    consultations: list[dict],
    cases: list[dict],
    documents: list[dict],
) -> dict:
    active_cases = sum(1 for case in cases if (case.get("status") or "").lower() in {"open", "in_progress"})
    pending_documents = sum(1 for document in documents if (document.get("processing_status") or "").lower() != "completed")
    requests_under_review = sum(
        1
        for consultation in consultations
        if (consultation.get("status") or "").lower() in {"submitted", "new", "ready_for_review"}
    )
    return {
        "total_cases": len(cases),
        "active_cases": active_cases,
        "total_documents": len(documents),
        "pending_documents": pending_documents,
        "consultation_requests": len(consultations),
        "requests_under_review": requests_under_review,
    }


def build_activity_feed(
    consultations: list[dict],
    documents: list[dict],
    cases: list[dict],
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
        activity.append(
            {
                "id": f"document-{document['id']}",
                "event_type": "document_update",
                "title": f"Document '{document['filename']}' is {document['processing_status']}",
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

    activity.sort(key=lambda item: item.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return activity[:18]


@router.post("/auth/register", response_model=ClientPortalMessageResponse, status_code=status.HTTP_201_CREATED)
def register_portal_account(data: ClientPortalRegisterRequest, db: Session = Depends(get_db)):
    normalized_email = data.email.lower().strip()
    normalized_name = data.full_name.strip()

    existing = db.query(ClientPortalAccount).filter(ClientPortalAccount.email == normalized_email).first()
    if existing:
        raise HTTPException(status_code=400, detail="A portal account already exists for this email.")

    validate_portal_password(data.password)
    tenant = get_default_tenant(db)

    client = get_or_create_client(
        db,
        tenant_id=tenant.id,
        client_name=normalized_name,
        client_email=normalized_email,
        client_phone=data.phone,
        client_address=data.address,
    )

    account = ClientPortalAccount(
        full_name=normalized_name,
        email=normalized_email,
        hashed_password=hash_password(data.password),
        tenant_id=tenant.id,
        client_id=client.id,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return {"message": "Account created successfully. Sign in to receive your six-digit access code."}


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

    login_code.consumed_at = datetime.now(timezone.utc)
    db.commit()

    return issue_portal_token(account)


@router.post("/auth/login", response_model=ClientPortalMessageResponse)
def login_portal_account(data: ClientPortalLoginRequest, db: Session = Depends(get_db)):
    _ = db
    _ = data
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Portal login now requires the request-code and verify-code flow.",
    )


@router.get("/auth/me", response_model=ClientPortalAccountOut)
def me_portal_account(account: ClientPortalAccount = Depends(get_current_portal_account)):
    return build_account_out(account)


@router.get("/dashboard", response_model=ClientPortalDashboardResponse)
def dashboard(
    db: Session = Depends(get_db),
    account: ClientPortalAccount = Depends(get_current_portal_account),
):
    db.refresh(account)
    consultations = build_consultation_items(db, account)
    case_items, _ = build_case_items(db, account)
    document_items = build_document_items(db, account)
    activity = build_activity_feed(consultations=consultations, documents=document_items, cases=case_items)
    metrics = build_dashboard_metrics(consultations=consultations, cases=case_items, documents=document_items)
    return {
        "account": build_account_out(account),
        "consultations": consultations,
        "cases": case_items,
        "documents": document_items,
        "activity": activity,
        "metrics": metrics,
    }


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

    client = account.client or get_or_create_client(
        db,
        tenant_id=account.tenant_id,
        client_name=account.full_name,
        client_email=account.email,
        client_phone=None,
        client_address=None,
    )

    if not account.client_id:
        account.client_id = client.id
        db.commit()
        db.refresh(account)

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

    if voice_note and voice_note.filename:
        voice_note.file.seek(0, 2)
        voice_size = voice_note.file.tell()
        voice_note.file.seek(0)
        max_voice_bytes = max(1, int(settings.VOICE_UPLOAD_MAX_MB)) * 1024 * 1024
        if voice_size > max_voice_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Voice note too large. Maximum allowed size is {settings.VOICE_UPLOAD_MAX_MB} MB.",
            )
        voice_storage_path = upload_file(voice_note.file, voice_note.filename.strip(), prefix="voice")

        recording = VoiceRecording(
            filename=voice_note.filename.strip(),
            storage_path=voice_storage_path,
            mime_type=voice_note.content_type or "audio/webm",
            file_size=voice_size,
            transcription_status="processing",
            case_id=case.id,
            tenant_id=account.tenant_id,
            uploaded_by_user_id=None,
        )
        db.add(recording)
        db.commit()
        db.refresh(recording)

        consultation.voice_recording_id = recording.id
        db.commit()
        background_tasks.add_task(process_voice_recording, recording.id, consultation.id)

    if supporting_document and supporting_document.filename:
        normalized_content_type = (supporting_document.content_type or "").split(";")[0].strip().lower()
        extension = Path(supporting_document.filename).suffix.lower()
        if normalized_content_type != "application/pdf" and extension != ".pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are accepted as supporting documents.")

        supporting_document.file.seek(0, 2)
        document_size = supporting_document.file.tell()
        supporting_document.file.seek(0)
        max_document_bytes = max(1, int(settings.DOCUMENT_UPLOAD_MAX_MB)) * 1024 * 1024
        if document_size > max_document_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Supporting document too large. Maximum allowed size is {settings.DOCUMENT_UPLOAD_MAX_MB} MB.",
            )
        document_storage_path = upload_file(
            supporting_document.file,
            supporting_document.filename.strip(),
            prefix="documents",
        )

        document = Document(
            filename=supporting_document.filename.strip(),
            storage_path=document_storage_path,
            file_size=document_size,
            file_type=normalized_content_type or "application/pdf",
            case_id=case.id,
            tenant_id=account.tenant_id,
            processing_status="pending",
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        if document.file_type == "application/pdf":
            pipeline.process_document(document, db)

    consultations = build_consultation_items(db, account)
    case_items, _ = build_case_items(db, account)
    document_items = build_document_items(db, account)

    return {
        "account": build_account_out(account),
        "consultations": consultations,
        "cases": case_items,
        "documents": document_items,
        "activity": build_activity_feed(
            consultations=consultations,
            documents=document_items,
            cases=case_items,
        ),
        "metrics": build_dashboard_metrics(
            consultations=consultations,
            cases=case_items,
            documents=document_items,
        ),
    }
