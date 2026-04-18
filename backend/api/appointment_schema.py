from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AppointmentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=2, max_length=240)
    description: Optional[str] = Field(default=None, max_length=4000)
    appointment_type: str = Field(default="meeting", max_length=40)
    visibility_scope: str = Field(default="shared", max_length=40)
    status: str = Field(default="scheduled", max_length=40)
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=24 * 60)
    location: Optional[str] = Field(default=None, max_length=240)
    timezone_name: Optional[str] = Field(default="UTC", max_length=80)
    notes: Optional[str] = Field(default=None, max_length=4000)
    consultation_request_id: Optional[int] = Field(default=None, ge=1)
    use_ai: bool = True


class AppointmentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=2, max_length=240)
    description: Optional[str] = Field(default=None, max_length=4000)
    appointment_type: Optional[str] = Field(default=None, max_length=40)
    visibility_scope: Optional[str] = Field(default=None, max_length=40)
    status: Optional[str] = Field(default=None, max_length=40)
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(default=None, ge=5, le=24 * 60)
    location: Optional[str] = Field(default=None, max_length=240)
    timezone_name: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=4000)
    use_ai: bool = False


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    tenant_id: int
    lawyer_id: Optional[int] = None
    client_id: Optional[int] = None
    consultation_request_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    appointment_type: str
    visibility_scope: str
    status: str
    scheduled_at: datetime
    duration_minutes: int
    location: Optional[str] = None
    timezone_name: str
    ai_summary: Optional[str] = None
    ai_recommendation: Optional[str] = None
    ai_confidence: Optional[str] = None
    ai_source: Optional[str] = None
    notes: Optional[str] = None
    case_title: Optional[str] = None
    client_name: Optional[str] = None
    lawyer_name: Optional[str] = None
    is_ai_suggested: bool = False
    created_at: datetime
    updated_at: datetime


class AppointmentActionResponse(BaseModel):
    message: str
    appointment: AppointmentOut
