from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PublicIntakeSubmitResponse(BaseModel):
    message: str
    public_reference: str
    consultation_request_id: int
    case_id: int
    client_name: str
    status: str


class PublicIntakeStatusResponse(BaseModel):
    public_reference: str
    status: str
    client_name: Optional[str] = None
    issue_summary: str
    preferred_schedule: Optional[str] = None
    created_at: datetime
