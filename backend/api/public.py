from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.api.public_schema import PublicIntakeStatusResponse, PublicIntakeSubmitResponse
from backend.database.database import SessionLocal
from backend.models.case import Case
from backend.models.client import Client
from backend.models.consultation_request import ConsultationRequest
from backend.models.document import Document
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.intake_agent import intake_agent
from backend.services.ai.document_ai_pipeline import DocumentAIPipeline
from backend.services.ai.transcription_service import transcription_service
from backend.services.storage_service import download_file_to_temp, upload_file


router = APIRouter(prefix="/public", tags=["Public Intake"])

pipeline = DocumentAIPipeline()


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
            User.deleted_at.is_(None)
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
    client_address: str | None
) -> Client:
    client = None

    if client_email:
        client = (
            db.query(Client)
            .filter(
                Client.tenant_id == tenant_id,
                Client.email == client_email,
                Client.deleted_at.is_(None)
            )
            .first()
        )

    if not client and client_phone:
        client = (
            db.query(Client)
            .filter(
                Client.tenant_id == tenant_id,
                Client.phone == client_phone,
                Client.deleted_at.is_(None)
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


@router.post("/intake/submit", response_model=PublicIntakeSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_public_intake(
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
        normalized_tenant_name = tenant_name.strip()
        normalized_client_name = client_name.strip()
        normalized_client_email = client_email.lower().strip() if client_email else None

        tenant = db.query(Tenant).filter(Tenant.name == normalized_tenant_name).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Target tenant not found.")

        lawyer = find_tenant_lawyer(db, tenant.id)
        if not lawyer:
            raise HTTPException(
                status_code=400,
                detail="This tenant has no staff account available to receive public intake requests."
            )

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
                tenant_id=tenant.id,
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
                consultation.client_name = extracted.get("client_name") or consultation.client_name
                consultation.client_email = extracted.get("client_email") or consultation.client_email
                consultation.client_phone = extracted.get("client_phone") or consultation.client_phone
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
                consultation.extraction_source = (
                    extracted.get("extraction_source")
                    or consultation.extraction_source
                )
            else:
                recording.transcription_status = "failed"
                recording.transcription_error = transcription["error"]
                recording.transcript_source = transcription["source"]
                recording.transcript_language = transcription["language"]

            db.commit()
            db.refresh(consultation)

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
                prefix="documents"
            )

            document = Document(
                filename=supporting_document.filename.strip(),
                storage_path=document_storage_path,
                file_size=document_size,
                file_type=normalized_content_type or "application/pdf",
                case_id=case.id,
                tenant_id=tenant.id,
                processing_status="pending",
            )
            db.add(document)
            db.commit()
            db.refresh(document)

            if document.file_type == "application/pdf":
                pipeline.process_document(document, db)

        db.commit()
        db.refresh(consultation)

        return {
            "message": "Consultation request submitted successfully.",
            "public_reference": consultation.public_reference,
            "consultation_request_id": consultation.id,
            "case_id": case.id,
            "client_name": consultation.client_name or normalized_client_name,
            "status": consultation.status,
        }
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
