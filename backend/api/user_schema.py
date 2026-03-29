from pydantic import BaseModel, EmailStr, ConfigDict, Field
from datetime import datetime
from backend.core.enums import UserRole


class UserRegister(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    role: UserRole = UserRole.lawyer
    tenant_name: str = Field(..., min_length=2, max_length=120)


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
