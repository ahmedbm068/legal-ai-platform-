from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class VoiceRecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    storage_path: str
    mime_type: str
    file_size: int
    transcription_status: str
    transcription_error: Optional[str] = None
    transcript_text: Optional[str] = None
    transcript_source: Optional[str] = None
    transcript_language: Optional[str] = None
    case_id: int
    tenant_id: int
    uploaded_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class VoiceUploadResponse(BaseModel):
    recording: VoiceRecordingOut
    message: str
    job: dict = Field(default_factory=dict)


class VoiceTranscriptionResponse(BaseModel):
    success: bool
    transcript_text: str = ""
    transcript_source: Optional[str] = None
    transcript_language: Optional[str] = None
    error: Optional[str] = None
