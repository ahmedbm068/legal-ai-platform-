from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.case import Case
from backend.models.document import Document
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.image_document_service import image_document_service
from backend.services.jobs.job_queue_service import background_job_service
from backend.services.storage_service import upload_file


class IngestionUseCase:
    def create_document_upload(
        self,
        *,
        db: Session,
        case: Case,
        file,
        background_tasks: BackgroundTasks | None = None,
    ) -> tuple[Document, dict[str, Any]]:
        filename = (file.filename or "").strip()
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        normalized_content_type = (file.content_type or "").split(";")[0].strip().lower()
        extension = Path(filename).suffix.lower()
        if normalized_content_type != "application/pdf" and extension != ".pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported for this endpoint")

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        max_file_size = max(1, int(settings.DOCUMENT_UPLOAD_MAX_MB)) * 1024 * 1024
        if file_size > max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum allowed size is {settings.DOCUMENT_UPLOAD_MAX_MB} MB.",
            )

        storage_path = upload_file(file.file, filename, prefix="documents")
        document = Document(
            filename=filename,
            storage_path=storage_path,
            file_size=file_size,
            file_type=normalized_content_type or "application/pdf",
            case_id=case.id,
            tenant_id=case.tenant_id,
            processing_status="queued",
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        job = background_job_service.enqueue(
            db=db,
            job_type="document_process",
            payload={"document_id": document.id},
            tenant_id=document.tenant_id,
            case_id=document.case_id,
            document_id=document.id,
            queue_name="documents",
            background_tasks=background_tasks,
        )
        return document, background_job_service.to_public_payload(job) or {}

    def create_voice_upload(
        self,
        *,
        db: Session,
        case: Case,
        file,
        uploaded_by_user_id: int | None,
        consultation_request_id: int | None = None,
        background_tasks: BackgroundTasks | None = None,
    ) -> tuple[VoiceRecording, dict[str, Any]]:
        filename = (file.filename or "").strip()
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        max_file_size = max(1, int(settings.VOICE_UPLOAD_MAX_MB)) * 1024 * 1024
        if file_size > max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"Audio file too large. Maximum allowed size is {settings.VOICE_UPLOAD_MAX_MB} MB.",
            )

        normalized_content_type = (file.content_type or "").split(";")[0].strip().lower()
        if not normalized_content_type:
            extension = Path(filename).suffix.lower()
            normalized_content_type = {
                ".webm": "audio/webm",
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
                ".mp4": "audio/mp4",
                ".ogg": "audio/ogg",
                ".m4a": "audio/x-m4a",
            }.get(extension, "application/octet-stream")

        storage_path = upload_file(file.file, filename, prefix="voice")
        recording = VoiceRecording(
            filename=filename,
            storage_path=storage_path,
            mime_type=normalized_content_type,
            file_size=file_size,
            transcription_status="queued",
            case_id=case.id,
            tenant_id=case.tenant_id,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        db.add(recording)
        db.commit()
        db.refresh(recording)

        job = background_job_service.enqueue(
            db=db,
            job_type="voice_process",
            payload={
                "recording_id": recording.id,
                "consultation_request_id": consultation_request_id,
            },
            tenant_id=recording.tenant_id,
            case_id=recording.case_id,
            voice_recording_id=recording.id,
            consultation_request_id=consultation_request_id,
            queue_name="voice",
            background_tasks=background_tasks,
        )
        return recording, background_job_service.to_public_payload(job) or {}

    def enqueue_case_snapshot_refresh(
        self,
        *,
        db: Session,
        tenant_id: int,
        case_id: int,
        background_tasks: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        job = background_job_service.enqueue(
            db=db,
            job_type="case_snapshot_refresh",
            payload={"tenant_id": tenant_id, "case_id": case_id},
            tenant_id=tenant_id,
            case_id=case_id,
            queue_name="snapshots",
            background_tasks=background_tasks,
        )
        return background_job_service.to_public_payload(job) or {}

    def create_image_batch_upload(
        self,
        *,
        db: Session,
        case: Case,
        files: list,
        title: str | None,
        generate_document: bool,
        run_authenticity_check: bool,
        created_by_user_id: int | None,
        background_tasks: BackgroundTasks | None = None,
    ):
        return image_document_service.create_image_batch_upload(
            db=db,
            case=case,
            files=files,
            title=title,
            generate_document=generate_document,
            run_authenticity_check=run_authenticity_check,
            created_by_user_id=created_by_user_id,
            background_tasks=background_tasks,
        )


ingestion_use_case = IngestionUseCase()
