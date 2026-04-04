from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.database.database import SessionLocal
from backend.models.background_job import BackgroundJob


def process_background_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if not job:
            return

        if job.status not in {"queued", "retrying"}:
            return

        job.status = "running"
        job.attempts = int(job.attempts or 0) + 1
        job.started_at = datetime.now(timezone.utc)
        job.error = None
        db.commit()
        db.refresh(job)

        payload = _loads(job.payload_json)
        result = _dispatch(job=job, payload=payload, db=db)

        job.status = "completed"
        job.result_json = json.dumps(result or {}, ensure_ascii=False)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if failed_job:
            failed_job.status = "failed"
            failed_job.error = str(exc)
            failed_job.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def _dispatch(*, job: BackgroundJob, payload: dict[str, Any], db: Session) -> dict[str, Any]:
    if job.job_type == "document_process":
        from backend.models.document import Document
        from backend.services.ai.case_snapshot_service import case_snapshot_service
        from backend.services.ai.runtime_services import shared_document_pipeline

        document_id = int(payload["document_id"])
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError("Document job target was not found.")
        result = shared_document_pipeline.process_document(document, db)
        if document.case_id and document.tenant_id:
            case_snapshot_service.refresh_case_snapshot(
                db=db,
                tenant_id=document.tenant_id,
                case_id=document.case_id,
            )
        return result

    if job.job_type == "voice_process":
        from backend.models.voice_recording import VoiceRecording
        from backend.services.ai.case_snapshot_service import case_snapshot_service
        from backend.services.voice_processing_service import process_voice_recording

        recording_id = int(payload["recording_id"])
        consultation_request_id = payload.get("consultation_request_id")
        process_voice_recording(recording_id, consultation_request_id)
        recording = db.query(VoiceRecording).filter(VoiceRecording.id == recording_id).first()
        if recording and recording.case_id and recording.tenant_id:
            case_snapshot_service.refresh_case_snapshot(
                db=db,
                tenant_id=recording.tenant_id,
                case_id=recording.case_id,
            )
            return {
                "recording_id": recording.id,
                "case_id": recording.case_id,
                "status": recording.transcription_status,
                "transcript_available": bool(recording.transcript_text),
            }
        return {"recording_id": recording_id, "status": "processed"}

    if job.job_type == "case_snapshot_refresh":
        from backend.services.ai.case_snapshot_service import case_snapshot_service

        case_id = int(payload["case_id"])
        tenant_id = int(payload["tenant_id"])
        snapshot = case_snapshot_service.refresh_case_snapshot(
            db=db,
            tenant_id=tenant_id,
            case_id=case_id,
        )
        return snapshot or {}

    if job.job_type == "image_batch_process":
        from backend.services.ai.image_document_service import image_document_service

        batch_id = int(payload["batch_id"])
        result = image_document_service.process_image_batch(
            db=db,
            batch_id=batch_id,
        )
        review = result.get("review")
        batch = result.get("batch")
        generated_document = result.get("generated_document")
        return {
            "batch_id": batch.get("id", batch_id) if isinstance(batch, dict) else getattr(batch, "id", batch_id),
            "status": batch.get("status", "completed") if isinstance(batch, dict) else getattr(batch, "status", "completed"),
            "generated_document_id": (
                generated_document.get("id") if isinstance(generated_document, dict) else getattr(generated_document, "id", None)
            ) or (batch.get("generated_document_id") if isinstance(batch, dict) else getattr(batch, "generated_document_id", None)),
            "review_id": review.get("id") if isinstance(review, dict) else getattr(review, "id", None),
        }

    raise ValueError(f"Unsupported background job type '{job.job_type}'.")


def _loads(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        payload = json.loads(raw_value)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}

