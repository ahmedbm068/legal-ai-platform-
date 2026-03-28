from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from random import randint

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.api.client_portal_schema import (
    ClientPortalAccountOut,
    ClientPortalConsultationItem,
    ClientPortalDashboardResponse,
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
from backend.services.ai.agents.intake_agent import intake_agent
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.transcription_service import transcription_service
from backend.services.client_portal_mail_service import client_portal_mail_service
from backend.services.storage_service import download_file_to_temp, upload_file
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


router = APIRouter(prefix="/portal", tags=["Client Portal"])

security = HTTPBearer()
pipeline = DocumentAIPipeline()
PASSWORD_POLICY_REGEX = re.compile(r"^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{10,}$")


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


@router.post("/auth/register", response_model=ClientPortalMessageResponse, status_code=status.HTTP_201_CREATED)
def register_portal_account(data: ClientPortalRegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(ClientPortalAccount).filter(ClientPortalAccount.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="A portal account already exists for this email.")

    validate_portal_password(data.password)
    tenant = get_default_tenant(db)

    client = get_or_create_client(
        db,
        tenant_id=tenant.id,
        client_name=data.full_name,
        client_email=data.email,
        client_phone=data.phone,
        client_address=data.address,
    )

    account = ClientPortalAccount(
        full_name=data.full_name,
        email=data.email,
        hashed_password=hash_password(data.password),
        tenant_id=tenant.id,
        client_id=client.id,
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    return {"message": "Account created successfully. Sign in to receive your six-digit access code."}


@router.post("/auth/login/request-code", response_model=ClientPortalMessageResponse)
def request_login_code(data: ClientPortalLoginCodeRequest, db: Session = Depends(get_db)):
    account = db.query(ClientPortalAccount).filter(ClientPortalAccount.email == data.email).first()
    if not account or not verify_password(data.password, account.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    code = generate_login_code()
    login_code = ClientPortalLoginCode(
        portal_account_id=account.id,
        email=account.email,
        code=code,
        purpose="login",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.PORTAL_LOGIN_CODE_EXPIRE_MINUTES),
        delivery_status="pending",
    )
    db.add(login_code)
    db.commit()
    db.refresh(login_code)

    try:
        client_portal_mail_service.send_login_code(recipient_email=account.email, code=code)
        login_code.delivery_status = "sent"
        login_code.delivery_error = None
        db.commit()
    except Exception as exc:
        login_code.delivery_status = "failed"
        login_code.delivery_error = str(exc)
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Unable to send the access code email. {exc}",
        )

    return {"message": "A six-digit access code has been sent to your email address."}


@router.post("/auth/login/verify-code", response_model=ClientPortalToken)
def verify_login_code(data: ClientPortalLoginCodeVerifyRequest, db: Session = Depends(get_db)):
    account = db.query(ClientPortalAccount).filter(ClientPortalAccount.email == data.email).first()
    if not account:
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active access code was found.")

    if login_code.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This access code has expired.")

    if login_code.code != data.code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access code.")

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
    return {
        "account": build_account_out(account),
        "consultations": build_consultation_items(db, account),
    }


@router.post("/intake/submit", response_model=ClientPortalDashboardResponse, status_code=status.HTTP_201_CREATED)
def submit_authenticated_intake(
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

        local_voice_path = download_file_to_temp(voice_storage_path)
        try:
            transcription = transcription_service.transcribe_file(local_voice_path, filename=recording.filename)
        finally:
            if os.path.exists(local_voice_path):
                try:
                    os.remove(local_voice_path)
                except OSError:
                    pass

        if transcription["success"]:
            recording.transcription_status = "completed"
            recording.transcription_error = None
            recording.transcript_text = transcription["text"]
            recording.transcript_source = transcription["source"]
            recording.transcript_language = transcription["language"]

            agent_result = intake_agent.process_transcript(
                transcript_text=recording.transcript_text,
                preferred_schedule=consultation.preferred_schedule,
                fallback_client_name=consultation.client_name,
                fallback_client_email=consultation.client_email,
                fallback_client_phone=consultation.client_phone,
                fallback_issue_summary=consultation.issue_summary,
                fallback_case_description=consultation.extracted_case_description,
            )

            extracted = agent_result.payload if agent_result.success else {}
            consultation.voice_recording_id = recording.id
            consultation.booking_intent = (
                "requested"
                if consultation.booking_intent == "requested" or extracted.get("booking_intent") == "requested"
                else extracted.get("booking_intent", consultation.booking_intent)
            )
            consultation.urgency_level = extracted.get("urgency_level", consultation.urgency_level)
            consultation.legal_area = extracted.get("legal_area") or consultation.legal_area
            consultation.preferred_schedule = consultation.preferred_schedule or extracted.get("preferred_schedule")
            consultation.intake_notes = extracted.get("intake_notes") or consultation.intake_notes
            consultation.issue_summary = extracted.get("issue_summary") or consultation.issue_summary
            consultation.extracted_case_description = (
                extracted.get("extracted_case_description") or consultation.extracted_case_description
            )
            consultation.extraction_source = extracted.get("extraction_source") or consultation.extraction_source
        else:
            recording.transcription_status = "failed"
            recording.transcription_error = transcription["error"]
            recording.transcript_source = transcription["source"]
            recording.transcript_language = transcription["language"]

        db.commit()

    if supporting_document and supporting_document.filename:
        supporting_document.file.seek(0, 2)
        document_size = supporting_document.file.tell()
        supporting_document.file.seek(0)
        document_storage_path = upload_file(
            supporting_document.file,
            supporting_document.filename.strip(),
            prefix="documents",
        )

        document = Document(
            filename=supporting_document.filename.strip(),
            storage_path=document_storage_path,
            file_size=document_size,
            file_type=supporting_document.content_type or "application/octet-stream",
            case_id=case.id,
            tenant_id=account.tenant_id,
            processing_status="pending",
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        if document.file_type == "application/pdf":
            pipeline.process_document(document, db)

    return {
        "account": build_account_out(account),
        "consultations": build_consultation_items(db, account),
    }
