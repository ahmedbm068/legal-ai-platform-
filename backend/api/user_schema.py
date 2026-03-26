from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from backend.core.enums import UserRole


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.lawyer
    tenant_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


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