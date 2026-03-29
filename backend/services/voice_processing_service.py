from __future__ import annotations

import logging
import os

from backend.database.database import SessionLocal
from backend.models.consultation_request import ConsultationRequest
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.agents.intake_agent import intake_agent
from backend.services.ai.transcription_service import transcription_service
from backend.services.storage_service import download_file_to_temp


logger = logging.getLogger(__name__)


def process_voice_recording(recording_id: int, consultation_request_id: int | None = None) -> None:
    db = SessionLocal()
    local_file_path: str | None = None

    try:
        recording = db.query(VoiceRecording).filter(VoiceRecording.id == recording_id).first()
        if not recording:
            return

        recording.transcription_status = "processing"
        recording.transcription_error = None
        db.commit()
        db.refresh(recording)

        local_file_path = download_file_to_temp(recording.storage_path)
        transcription = transcription_service.transcribe_file(local_file_path, filename=recording.filename)

        if transcription["success"]:
            recording.transcription_status = "completed"
            recording.transcription_error = None
            recording.transcript_text = transcription["text"]
            recording.transcript_source = transcription["source"]
            recording.transcript_language = transcription["language"]
        else:
            recording.transcription_status = "failed"
            recording.transcription_error = transcription["error"]
            recording.transcript_text = None
            recording.transcript_source = transcription["source"]
            recording.transcript_language = transcription["language"]

        if consultation_request_id and recording.transcription_status == "completed" and recording.transcript_text:
            consultation = (
                db.query(ConsultationRequest)
                .filter(ConsultationRequest.id == consultation_request_id)
                .first()
            )

            if consultation:
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

        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Background voice processing failed for recording_id=%s: %s", recording_id, exc)
    finally:
        if local_file_path and os.path.exists(local_file_path):
            try:
                os.remove(local_file_path)
            except OSError:
                pass
        db.close()
