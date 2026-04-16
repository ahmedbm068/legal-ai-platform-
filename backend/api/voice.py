from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.api.voice_schema import VoiceRecordingOut, VoiceTranscriptionResponse, VoiceUploadResponse
from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope
from backend.models.case import Case
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.transcription_service import transcription_service
from backend.services.storage_service import stream_file_response
from backend.services.use_cases.ingestion_use_case import ingestion_use_case


router = APIRouter(prefix="/voice", tags=["Voice"])

ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/mp3",
    "audio/ogg",
    "audio/x-m4a",
    "audio/m4a",
}

ALLOWED_AUDIO_EXTENSIONS = {
    ".webm",
    ".wav",
    ".mp3",
    ".mp4",
    ".ogg",
    ".m4a",
}


def is_supported_audio_upload(filename: str, content_type: str | None) -> bool:
    normalized_type = (content_type or "").split(";")[0].strip().lower()
    extension = Path(filename).suffix.lower()
    return normalized_type in ALLOWED_AUDIO_CONTENT_TYPES or extension in ALLOWED_AUDIO_EXTENSIONS


def looks_like_html_error_page(value: str | None) -> bool:
    if not value:
        return False

    normalized = value.lstrip().lower()
    return normalized.startswith("<!doctype html") or normalized.startswith("<html")


def sanitize_recording(recording: VoiceRecording) -> bool:
    transcript_text = recording.transcript_text
    transcription_error = recording.transcription_error
    changed = False

    if looks_like_html_error_page(transcript_text):
        recording.transcript_text = None
        recording.transcription_status = "failed"
        recording.transcription_error = (
            "Transcription failed because the provider returned an HTML error page instead of text."
        )
        changed = True
    elif looks_like_html_error_page(transcription_error):
        recording.transcription_error = (
            "Transcription failed because the provider returned an HTML error page instead of text."
        )
        changed = True

    return changed


def get_tenant_case_or_404(db: Session, case_id: int, current_user: User) -> Case:
    case_query = db.query(Case).filter(
        Case.id == case_id,
        Case.deleted_at.is_(None)
    )
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return case


def get_tenant_recording_or_404(db: Session, recording_id: int, current_user: User) -> VoiceRecording:
    recording_query = db.query(VoiceRecording).filter(VoiceRecording.id == recording_id)
    recording = apply_tenant_scope(recording_query, VoiceRecording.tenant_id, current_user).first()

    if not recording:
        raise HTTPException(status_code=404, detail="Voice recording not found")

    return recording


@router.get("/case/{case_id}", response_model=list[VoiceRecordingOut])
def list_case_recordings(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    query = db.query(VoiceRecording).filter(VoiceRecording.case_id == case_id)
    recordings = apply_tenant_scope(query, VoiceRecording.tenant_id, current_user).order_by(
        VoiceRecording.created_at.desc(), VoiceRecording.id.desc()
    ).all()

    changed = False
    for recording in recordings:
        changed = sanitize_recording(recording) or changed

    if changed:
        db.commit()
        for recording in recordings:
            db.refresh(recording)

    return recordings


@router.get("/{recording_id}", response_model=VoiceRecordingOut)
def get_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    recording = get_tenant_recording_or_404(db=db, recording_id=recording_id, current_user=current_user)

    if sanitize_recording(recording):
        db.commit()
        db.refresh(recording)

    return recording


@router.get("/{recording_id}/file")
def get_recording_file(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recording = get_tenant_recording_or_404(db=db, recording_id=recording_id, current_user=current_user)
    return stream_file_response(
        recording.storage_path,
        media_type=recording.mime_type or "application/octet-stream",
        filename=recording.filename,
    )


@router.post("/upload", response_model=VoiceUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_voice_recording(
    background_tasks: BackgroundTasks,
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if not is_supported_audio_upload(file.filename, file.content_type):
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Use webm, wav, mp3, mp4, or ogg."
        )

    filename = file.filename.strip()
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

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    max_file_size = max(1, int(settings.VOICE_UPLOAD_MAX_MB)) * 1024 * 1024
    if file_size > max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"Audio file too large. Maximum allowed size is {settings.VOICE_UPLOAD_MAX_MB} MB."
        )

    recording, job_payload = ingestion_use_case.create_voice_upload(
        db=db,
        case=case,
        file=file,
        uploaded_by_user_id=current_user.id,
        background_tasks=background_tasks,
    )
    message = "Voice recording uploaded. Transcription is queued and will continue in the background."

    return {
        "recording": recording,
        "message": message,
        "job": job_payload,
    }


@router.post("/transcribe", response_model=VoiceTranscriptionResponse)
def transcribe_voice_input(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    del current_user

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if not is_supported_audio_upload(file.filename, file.content_type):
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Use webm, wav, mp3, mp4, m4a, or ogg.",
        )

    filename = file.filename.strip()
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    max_file_size = max(1, int(settings.VOICE_UPLOAD_MAX_MB)) * 1024 * 1024
    if file_size > max_file_size:
        raise HTTPException(
            status_code=400,
            detail=f"Audio file too large. Maximum allowed size is {settings.VOICE_UPLOAD_MAX_MB} MB.",
        )

    suffix = Path(filename).suffix.lower() or ".webm"
    temp_file_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_file_path = temp_file.name

        result = transcription_service.transcribe_file(temp_file_path, filename=filename)
        transcript_text = str(result.get("text") or "").strip()
        transcript_error = str(result.get("error") or "").strip() or None

        if looks_like_html_error_page(transcript_text):
            transcript_text = ""
            transcript_error = (
                "Transcription failed because the provider returned an HTML error page instead of text."
            )

        if looks_like_html_error_page(transcript_error):
            transcript_error = (
                "Transcription failed because the provider returned an HTML error page instead of text."
            )

        return {
            "success": bool(result.get("success")) and bool(transcript_text),
            "transcript_text": transcript_text,
            "transcript_source": result.get("source"),
            "transcript_language": result.get("language"),
            "error": transcript_error,
        }
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass
