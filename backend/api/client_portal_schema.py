from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClientPortalRegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_slug: str = Field("", max_length=80)
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


class ClientPortalCalendarItem(BaseModel):
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


class ClientPortalDashboardMetrics(BaseModel):
    total_cases: int = 0
    active_cases: int = 0
    total_documents: int = 0
    pending_documents: int = 0
    consultation_requests: int = 0
    requests_under_review: int = 0
    upcoming_appointments: int = 0


class ClientPortalDashboardResponse(BaseModel):
    account: ClientPortalAccountOut
    consultations: list[ClientPortalConsultationItem]
    cases: list[ClientPortalCaseItem] = Field(default_factory=list)
    documents: list[ClientPortalDocumentItem] = Field(default_factory=list)
    calendar_events: list[ClientPortalCalendarItem] = Field(default_factory=list)
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


class ClientPortalAppointmentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=2, max_length=255)
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=15, le=8 * 60)
    appointment_type: Optional[str] = Field(default="meeting", max_length=40)
    location: Optional[str] = Field(default=None, max_length=255)
    timezone_name: Optional[str] = Field(default="UTC", max_length=80)
    notes: Optional[str] = Field(default=None, max_length=4000)


class ClientPortalAppointmentResponse(BaseModel):
    message: str
    appointment: dict


# ── Messaging (client <-> lawyer, per case) ─────────────────────────────────


class ClientPortalMessageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    sender_role: str
    sender_name: Optional[str] = None
    body: str
    attachment_filename: Optional[str] = None
    attachment_content_type: Optional[str] = None
    attachment_size: Optional[int] = None
    is_mine: bool = False
    read_at: Optional[datetime] = None
    created_at: datetime


class ClientPortalThreadResponse(BaseModel):
    case_id: int
    case_title: str
    counsel_name: Optional[str] = None
    messages: list[ClientPortalMessageItem] = Field(default_factory=list)
    unread_count: int = 0


class ClientPortalSendMessageRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(..., min_length=1, max_length=8000)


class ClientPortalPiiScanRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field("", max_length=8000)


class ClientPortalUnreadResponse(BaseModel):
    unread_count: int = 0


# ── Billing ─────────────────────────────────────────────────────────────────


class ClientPortalInvoiceLineItem(BaseModel):
    id: int
    description: str
    hours: Optional[float] = None
    amount: float


class ClientPortalInvoiceItem(BaseModel):
    id: int
    invoice_number: str
    case_id: int
    description: str
    notes: Optional[str] = None
    currency: str
    amount_total: float
    status: str
    issued_at: datetime
    due_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    payment_status: Optional[str] = None
    line_items: list[ClientPortalInvoiceLineItem] = Field(default_factory=list)


class ClientPortalBillingResponse(BaseModel):
    invoices: list[ClientPortalInvoiceItem] = Field(default_factory=list)
    total_outstanding: float = 0.0
    currency: str = "USD"


class ClientPortalPayInvoiceResponse(BaseModel):
    status: str
    message: str
    invoice: ClientPortalInvoiceItem
