from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


EVENT_TYPES = {
    "hearing",
    "deadline",
    "meeting",
    "task",
    "document_date",
    "limitation_period",
    "filing_deadline",
    "payment_due",
    "contract_date",
    "reminder",
    "other",
}
EVENT_STATUSES = {"scheduled", "completed", "cancelled", "missed", "tentative", "rejected"}
EVENT_PRIORITIES = {"low", "medium", "high", "critical"}
SOURCE_TYPES = {"manual", "document_extraction", "ai_generated", "task", "external_sync"}
REMINDER_METHODS = {"in_app", "email", "future_webhook"}


def normalize_choice(value: str | None, allowed: set[str], default: str) -> str:
    cleaned = (value or default).strip().lower().replace(" ", "_")
    return cleaned if cleaned in allowed else default


class CalendarEventCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_id: Optional[int] = Field(default=None, ge=1)
    client_id: Optional[int] = Field(default=None, ge=1)
    lawyer_id: Optional[int] = Field(default=None, ge=1)
    title: str = Field(..., min_length=2, max_length=240)
    description: Optional[str] = Field(default=None, max_length=5000)
    event_type: str = Field(default="other", max_length=60)
    status: str = Field(default="scheduled", max_length=40)
    priority: str = Field(default="medium", max_length=40)
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    all_day: bool = False
    timezone: str = Field(default="UTC", max_length=80)
    location: Optional[str] = Field(default=None, max_length=240)
    source_type: str = Field(default="manual", max_length=60)
    source_document_id: Optional[int] = Field(default=None, ge=1)
    source_chunk_id: Optional[int] = Field(default=None, ge=1)
    source_quote: Optional[str] = Field(default=None, max_length=5000)
    extraction_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    requires_review: bool = False


class CalendarEventUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_id: Optional[int] = Field(default=None, ge=1)
    client_id: Optional[int] = Field(default=None, ge=1)
    lawyer_id: Optional[int] = Field(default=None, ge=1)
    title: Optional[str] = Field(default=None, min_length=2, max_length=240)
    description: Optional[str] = Field(default=None, max_length=5000)
    event_type: Optional[str] = Field(default=None, max_length=60)
    status: Optional[str] = Field(default=None, max_length=40)
    priority: Optional[str] = Field(default=None, max_length=40)
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    all_day: Optional[bool] = None
    timezone: Optional[str] = Field(default=None, max_length=80)
    location: Optional[str] = Field(default=None, max_length=240)
    source_quote: Optional[str] = Field(default=None, max_length=5000)
    requires_review: Optional[bool] = None


class CalendarEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    case_id: Optional[int] = None
    client_id: Optional[int] = None
    lawyer_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    event_type: str
    status: str
    priority: str
    start_datetime: datetime
    end_datetime: Optional[datetime] = None
    all_day: bool
    timezone: str
    location: Optional[str] = None
    source_type: str
    source_document_id: Optional[int] = None
    source_chunk_id: Optional[int] = None
    source_quote: Optional[str] = None
    extraction_confidence: Optional[float] = None
    requires_review: bool
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    case_title: Optional[str] = None
    client_name: Optional[str] = None
    document_filename: Optional[str] = None
    reminder_count: int = 0


class CalendarEventActionResponse(BaseModel):
    message: str
    event: CalendarEventOut


class CalendarReminderCreate(BaseModel):
    remind_at: datetime
    method: str = Field(default="in_app", max_length=40)


class CalendarReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    event_id: int
    remind_at: datetime
    method: str
    status: str
    created_at: datetime
    event_title: Optional[str] = None


class CalendarExtractionSummary(BaseModel):
    document_id: int
    created_count: int
    updated_count: int
    skipped_count: int
    created_ids: list[int] = []
    updated_ids: list[int] = []
