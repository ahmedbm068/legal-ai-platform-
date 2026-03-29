from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.api.voice_schema import VoiceRecordingOut, VoiceUploadResponse
from backend.core.deps import get_current_user, get_db
from backend.models.case import Case
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.storage_service import upload_file
from backend.services.voice_processing_service import process_voice_recording


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
    case = (
        db.query(Case)
        .filter(
            Case.id == case_id,
            Case.tenant_id == current_user.tenant_id,
            Case.deleted_at.is_(None)
        )
        .first()
    )

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    return case


def get_tenant_recording_or_404(db: Session, recording_id: int, current_user: User) -> VoiceRecording:
    recording = (
        db.query(VoiceRecording)
        .filter(
            VoiceRecording.id == recording_id,
            VoiceRecording.tenant_id == current_user.tenant_id
        )
        .first()
    )

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

    recordings = (
        db.query(VoiceRecording)
        .filter(
            VoiceRecording.case_id == case_id,
            VoiceRecording.tenant_id == current_user.tenant_id
        )
        .order_by(VoiceRecording.created_at.desc(), VoiceRecording.id.desc())
        .all()
    )

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


@router.post("/upload", response_model=VoiceUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_voice_recording(
    background_tasks: BackgroundTasks,
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

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

    storage_path = upload_file(file.file, filename, prefix="voice")

    recording = VoiceRecording(
        filename=filename,
        storage_path=storage_path,
        mime_type=normalized_content_type,
        file_size=file_size,
        transcription_status="processing",
        case_id=case_id,
        tenant_id=current_user.tenant_id,
        uploaded_by_user_id=current_user.id,
    )

    db.add(recording)
    db.commit()
    db.refresh(recording)

    background_tasks.add_task(process_voice_recording, recording.id, None)
    message = "Voice recording uploaded. Transcription is running in the background."

    return {
        "recording": recording,
        "message": message,
    }
