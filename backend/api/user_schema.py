from pydantic import BaseModel, EmailStr, ConfigDict, Field
from datetime import datetime
from backend.core.enums import UserRole


class UserRegister(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    role: UserRole = UserRole.lawyer
    tenant_name: str | None = Field(default=None, min_length=2, max_length=120)
    invite_token: str | None = Field(default=None, min_length=8, max_length=120)


class UserLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: UserRole
    tenant_id: int
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StaffInviteCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    role: UserRole = UserRole.lawyer
    expires_hours: int = Field(default=72, ge=1, le=336)


class StaffInviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    tenant_id: int
    invite_token: str
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime
