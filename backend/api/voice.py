from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.api.voice_schema import VoiceRecordingOut, VoiceUploadResponse
from backend.core.deps import get_current_user, get_db
from backend.models.case import Case
from backend.models.user import User
from backend.models.voice_recording import VoiceRecording
from backend.services.ai.transcription_service import transcription_service
from backend.services.storage_service import download_file_to_temp, upload_file


router = APIRouter(prefix="/voice", tags=["Voice"])


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

    return (
        db.query(VoiceRecording)
        .filter(
            VoiceRecording.case_id == case_id,
            VoiceRecording.tenant_id == current_user.tenant_id
        )
        .order_by(VoiceRecording.created_at.desc(), VoiceRecording.id.desc())
        .all()
    )


@router.get("/{recording_id}", response_model=VoiceRecordingOut)
def get_recording(
    recording_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return get_tenant_recording_or_404(db=db, recording_id=recording_id, current_user=current_user)


@router.post("/upload", response_model=VoiceUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_voice_recording(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    get_tenant_case_or_404(db=db, case_id=case_id, current_user=current_user)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    allowed_content_types = {
        "audio/webm",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp4",
        "audio/mp3",
        "audio/ogg",
    }

    if file.content_type not in allowed_content_types:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Use webm, wav, mp3, mp4, or ogg."
        )

    filename = file.filename.strip()

    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    max_file_size = 25 * 1024 * 1024
    if file_size > max_file_size:
        raise HTTPException(status_code=400, detail="Audio file too large. Maximum allowed size is 25 MB.")

    storage_path = upload_file(file.file, filename, prefix="voice")

    recording = VoiceRecording(
        filename=filename,
        storage_path=storage_path,
        mime_type=file.content_type,
        file_size=file_size,
        transcription_status="processing",
        case_id=case_id,
        tenant_id=current_user.tenant_id,
        uploaded_by_user_id=current_user.id,
    )

    db.add(recording)
    db.commit()
    db.refresh(recording)

    local_file_path = download_file_to_temp(storage_path)

    try:
        transcription = transcription_service.transcribe_file(local_file_path, filename=filename)
    finally:
        if os.path.exists(local_file_path):
            try:
                os.remove(local_file_path)
            except OSError:
                pass

    if transcription["success"]:
        recording.transcription_status = "completed"
        recording.transcription_error = None
        recording.transcript_text = transcription["text"]
        recording.transcript_source = transcription["source"]
        recording.transcript_language = transcription["language"]
        message = "Voice recording uploaded and transcribed successfully."
    else:
        recording.transcription_status = "failed"
        recording.transcription_error = transcription["error"]
        recording.transcript_text = None
        recording.transcript_source = transcription["source"]
        recording.transcript_language = transcription["language"]
        message = "Voice recording uploaded, but transcription failed."

    db.commit()
    db.refresh(recording)

    return {
        "recording": recording,
        "message": message,
    }
