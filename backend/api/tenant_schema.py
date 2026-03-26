from pydantic import BaseModel, ConfigDict
from datetime import datetime


class TenantCreate(BaseModel):
    name: str


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime