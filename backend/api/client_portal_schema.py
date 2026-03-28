from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class ClientPortalRegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone: Optional[str] = None
    address: Optional[str] = None


class ClientPortalLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class ClientPortalToken(BaseModel):
    access_token: str
    token_type: str


class ClientPortalMessageResponse(BaseModel):
    message: str


class ClientPortalLoginCodeRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class ClientPortalLoginCodeVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class ClientPortalAccountOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    tenant_id: int
    client_id: Optional[int] = None
    tenant_name: Optional[str] = None
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


class ClientPortalDashboardResponse(BaseModel):
    account: ClientPortalAccountOut
    consultations: list[ClientPortalConsultationItem]
