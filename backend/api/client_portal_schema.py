from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClientPortalRegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_slug: str = Field(..., min_length=2, max_length=80)
    full_name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=256)
    phone: Optional[str] = None
    address: Optional[str] = None


class ClientPortalLoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


class ClientPortalToken(BaseModel):
    access_token: str
    token_type: str


class ClientPortalMessageResponse(BaseModel):
    message: str


class ClientPortalLoginCodeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


class ClientPortalLoginCodeVerifyRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    code: str = Field(..., pattern=r"^\d{6}$")


class ClientPortalAccountOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    tenant_id: int
    client_id: Optional[int] = None
    tenant_name: Optional[str] = None
    tenant_slug: Optional[str] = None
    requires_email_verification: bool = False
    created_at: datetime


class ClientPortalConsultationItem(BaseModel):
    id: int
    case_id: int
    case_title: str
    public_reference: Optional[str] = None
    status: str
    issue_summary: str
    preferred_schedule: Optional[str] = None
    legal_area: Optional[str] = None
    urgency_level: str
    created_at: datetime


class ClientPortalCaseItem(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    jurisdiction_country: str
    lawyer_name: Optional[str] = None
    document_count: int = 0
    consultation_count: int = 0
    next_recommended_step: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ClientPortalDocumentItem(BaseModel):
    id: int
    case_id: int
    case_title: str
    filename: str
    file_type: str
    file_size: int
    processing_status: str
    upload_timestamp: datetime


class ClientPortalActivityItem(BaseModel):
    id: str
    event_type: str
    title: str
    description: str
    created_at: datetime
    case_id: Optional[int] = None


class ClientPortalDashboardMetrics(BaseModel):
    total_cases: int = 0
    active_cases: int = 0
    total_documents: int = 0
    pending_documents: int = 0
    consultation_requests: int = 0
    requests_under_review: int = 0


class ClientPortalDashboardResponse(BaseModel):
    account: ClientPortalAccountOut
    consultations: list[ClientPortalConsultationItem]
    cases: list[ClientPortalCaseItem] = Field(default_factory=list)
    documents: list[ClientPortalDocumentItem] = Field(default_factory=list)
    activity: list[ClientPortalActivityItem] = Field(default_factory=list)
    metrics: ClientPortalDashboardMetrics = Field(default_factory=ClientPortalDashboardMetrics)
    jobs: list[dict] = Field(default_factory=list)


class ClientPortalAssistantRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(..., min_length=1, max_length=6000)
    case_id: Optional[int] = Field(default=None, ge=1)
    document_id: Optional[int] = Field(default=None, ge=1)
    conversation_history: list[dict] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=5, ge=1, le=10)


class ClientPortalAssistantResponse(BaseModel):
    answer: str
    confidence: str
    scope: str
    sources: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    execution_trace: list[dict] = Field(default_factory=list)
    case_snapshot_version: Optional[int] = None
