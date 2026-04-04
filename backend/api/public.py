from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.api.public_schema import PublicIntakeStatusResponse, PublicIntakeSubmitResponse
from backend.api.voice import is_supported_audio_upload
from backend.database.database import SessionLocal
from backend.models.case import Case
from backend.models.client import Client
from backend.models.consultation_request import ConsultationRequest
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.services.use_cases.ingestion_use_case import ingestion_use_case


router = APIRouter(prefix="/public", tags=["Public Intake"])


def normalize_case_title(client_name: str, issue_summary: str) -> str:
    base_issue = re.sub(r"\s+", " ", issue_summary).strip()
    if len(base_issue) > 70:
        base_issue = base_issue[:67].rstrip() + "..."
    return f"Intake - {client_name} - {base_issue}"


def find_tenant_lawyer(db: Session, tenant_id: int) -> User | None:
    return (
        db.query(User)
        .filter(
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
        .order_by(User.id.asc())
        .first()
    )


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


def resolve_public_tenant_or_404(
    db: Session,
    *,
    tenant_slug: str | None = None,
    tenant_name: str | None = None,
) -> Tenant:
    normalized_slug = (tenant_slug or "").strip().lower()
    if normalized_slug:
        tenant = (
            db.query(Tenant)
            .filter(
                Tenant.slug == normalized_slug,
                Tenant.portal_access_enabled.is_(True),
            )
            .first()
        )
        if tenant:
            return tenant

    normalized_name = (tenant_name or "").strip()
    if normalized_name:
        tenant = (
            db.query(Tenant)
            .filter(
                Tenant.name == normalized_name,
                Tenant.portal_access_enabled.is_(True),
            )
            .first()
        )
        if tenant:
            return tenant

    raise HTTPException(status_code=404, detail="Target tenant not found.")


def submit_public_intake_for_tenant(
    *,
    db: Session,
    background_tasks: BackgroundTasks,
    tenant: Tenant,
    client_name: str,
    client_email: str | None,
    client_phone: str | None,
    client_address: str | None,
    issue_summary: str,
    case_description: str | None,
    preferred_schedule: str | None,
    voice_note: UploadFile | None,
    supporting_document: UploadFile | None,
) -> dict:
    lawyer = find_tenant_lawyer(db, tenant.id)
    if not lawyer:
        raise HTTPException(
            status_code=400,
            detail="This tenant has no staff account available to receive public intake requests.",
        )

    normalized_client_name = client_name.strip()
    normalized_client_email = client_email.lower().strip() if client_email else None

    client = get_or_create_client(
        db,
        tenant_id=tenant.id,
        client_name=normalized_client_name,
        client_email=normalized_client_email,
        client_phone=client_phone,
        client_address=client_address,
    )

    case = Case(
        title=normalize_case_title(normalized_client_name, issue_summary),
        description=case_description or issue_summary,
        status="open",
        jurisdiction_country="tunisia",
        tenant_id=tenant.id,
        lawyer_id=lawyer.id,
        client_id=client.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    consultation = ConsultationRequest(
        case_id=case.id,
        tenant_id=tenant.id,
        client_name=normalized_client_name,
        client_email=normalized_client_email,
        client_phone=client_phone,
        booking_intent="requested" if preferred_schedule else "not_detected",
        urgency_level="normal",
        preferred_schedule=preferred_schedule,
        issue_summary=issue_summary,
        extracted_case_description=case_description,
        intake_notes="Submitted through the public client portal.",
        status="submitted",
        extraction_source="public_portal_form",
        public_reference=f"INT-{uuid.uuid4().hex[:10].upper()}",
        source_channel="public_portal",
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
        tenant_id=tenant.id,
        case_id=case.id,
        background_tasks=background_tasks,
    )
    if snapshot_job:
        jobs.append(snapshot_job)

    db.refresh(consultation)
    return {
        "message": "Consultation request submitted successfully.",
        "tenant_slug": tenant.slug,
        "public_reference": consultation.public_reference,
        "consultation_request_id": consultation.id,
        "case_id": case.id,
        "client_name": consultation.client_name or normalized_client_name,
        "status": consultation.status,
        "jobs": jobs,
    }


@router.post("/tenants/{tenant_slug}/intake/submit", response_model=PublicIntakeSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_public_intake_scoped(
    tenant_slug: str,
    background_tasks: BackgroundTasks,
    client_name: str = Form(...),
    client_email: str | None = Form(None),
    client_phone: str | None = Form(None),
    client_address: str | None = Form(None),
    issue_summary: str = Form(...),
    case_description: str | None = Form(None),
    preferred_schedule: str | None = Form(None),
    voice_note: UploadFile | None = File(None),
    supporting_document: UploadFile | None = File(None),
):
    db = SessionLocal()
    try:
        tenant = resolve_public_tenant_or_404(db, tenant_slug=tenant_slug)
        return submit_public_intake_for_tenant(
            db=db,
            background_tasks=background_tasks,
            tenant=tenant,
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            client_address=client_address,
            issue_summary=issue_summary,
            case_description=case_description,
            preferred_schedule=preferred_schedule,
            voice_note=voice_note,
            supporting_document=supporting_document,
        )
    finally:
        db.close()


@router.post("/intake/submit", response_model=PublicIntakeSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_public_intake(
    background_tasks: BackgroundTasks,
    tenant_name: str = Form(...),
    client_name: str = Form(...),
    client_email: str | None = Form(None),
    client_phone: str | None = Form(None),
    client_address: str | None = Form(None),
    issue_summary: str = Form(...),
    case_description: str | None = Form(None),
    preferred_schedule: str | None = Form(None),
    voice_note: UploadFile | None = File(None),
    supporting_document: UploadFile | None = File(None),
):
    db = SessionLocal()
    try:
        tenant = resolve_public_tenant_or_404(db, tenant_name=tenant_name)
        return submit_public_intake_for_tenant(
            db=db,
            background_tasks=background_tasks,
            tenant=tenant,
            client_name=client_name,
            client_email=client_email,
            client_phone=client_phone,
            client_address=client_address,
            issue_summary=issue_summary,
            case_description=case_description,
            preferred_schedule=preferred_schedule,
            voice_note=voice_note,
            supporting_document=supporting_document,
        )
    finally:
        db.close()


@router.get("/intake/{public_reference}", response_model=PublicIntakeStatusResponse)
def get_public_intake_status(public_reference: str):
    db = SessionLocal()
    try:
        consultation = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.public_reference == public_reference)
            .first()
        )
        if not consultation:
            raise HTTPException(status_code=404, detail="Intake request not found.")

        return {
            "public_reference": consultation.public_reference,
            "status": consultation.status,
            "client_name": consultation.client_name,
            "issue_summary": consultation.issue_summary,
            "preferred_schedule": consultation.preferred_schedule,
            "created_at": consultation.created_at,
        }
    finally:
        db.close()
