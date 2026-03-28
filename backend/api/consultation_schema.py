from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConsultationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    tenant_id: int
    voice_recording_id: Optional[int] = None
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    booking_intent: str
    urgency_level: str
    legal_area: Optional[str] = None
    preferred_schedule: Optional[str] = None
    issue_summary: str
    extracted_case_description: Optional[str] = None
    intake_notes: Optional[str] = None
    status: str
    extraction_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConsultationFromTranscriptResponse(BaseModel):
    message: str
    consultation_request: ConsultationRequestOut
