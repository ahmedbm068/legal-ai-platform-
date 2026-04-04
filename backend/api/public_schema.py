from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PublicIntakeSubmitResponse(BaseModel):
    message: str
    tenant_slug: str | None = None
    public_reference: str
    consultation_request_id: int
    case_id: int
    client_name: str
    status: str
    jobs: list[dict] = Field(default_factory=list)


class PublicIntakeStatusResponse(BaseModel):
    public_reference: str
    status: str
    client_name: Optional[str] = None
    issue_summary: str
    preferred_schedule: Optional[str] = None
    created_at: datetime
