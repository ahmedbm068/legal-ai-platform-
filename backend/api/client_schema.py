from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime


class ClientCreate(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: Optional[EmailStr]
    phone: Optional[str]
    address: Optional[str]
    tenant_id: int
    created_at: datetime