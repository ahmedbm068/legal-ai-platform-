from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.api.voice_schema import VoiceRecordingOut


class CallSessionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider_name: Optional[str] = Field(default="twilio", max_length=80)
    caller_phone: Optional[str] = Field(default=None, max_length=40)
    client_phone: Optional[str] = Field(default=None, max_length=40)
    notes: Optional[str] = Field(default=None, max_length=4000)
    consent_accepted: bool = False


class WhatsAppConsentWebhookRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    from_phone: Optional[str] = Field(default=None, max_length=40)
    body: Optional[str] = Field(default=None, max_length=4000)
    client_phone: Optional[str] = Field(default=None, max_length=40)
    case_id: Optional[int] = None
    call_session_id: Optional[int] = None
    message_id: Optional[str] = Field(default=None, max_length=120)
    transcript_text: Optional[str] = Field(default=None, max_length=200000)
    conversation_turns: list[dict[str, Any]] = Field(default_factory=list)
    transcript_source: Optional[str] = Field(default=None, max_length=120)
    transcript_language: Optional[str] = Field(default=None, max_length=40)


class CallSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    tenant_id: int
    client_id: int
    started_by_user_id: Optional[int] = None
    provider_name: Optional[str] = None
    provider_call_id: Optional[str] = None
    caller_phone: Optional[str] = None
    client_phone: Optional[str] = None
    call_status: str
    recording_status: str
    summary_status: str
    consent_accepted: bool
    consent_accepted_at: Optional[datetime] = None
    consent_request_status: Optional[str] = None
    consent_requested_at: Optional[datetime] = None
    consent_message: Optional[str] = None
    consent_response_text: Optional[str] = None
    consent_responded_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    summary_text: Optional[str] = None
    transcript_text: Optional[str] = None
    conversation_transcript_text: Optional[str] = None
    transcript_source: Optional[str] = None
    transcription_error: Optional[str] = None
    notes: Optional[str] = None
    voice_recording: Optional[VoiceRecordingOut] = None
    created_at: datetime
    updated_at: datetime


class CallSessionCreateResponse(BaseModel):
    call_session: CallSessionOut
    message: str
    consent_message: Optional[str] = None
    whatsapp_chat_url: Optional[str] = None
    consent_delivery_mode: Optional[str] = None