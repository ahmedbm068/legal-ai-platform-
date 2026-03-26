from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime
from backend.core.enums import CaseStatus


class CaseCreate(BaseModel):

    title: str

    description: Optional[str] = None

    status: CaseStatus = CaseStatus.open

    client_id: int


class CaseUpdate(BaseModel):

    title: Optional[str] = None

    description: Optional[str] = None

    status: Optional[CaseStatus] = None

    client_id: Optional[int] = None


class CaseOut(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int

    title: str

    description: Optional[str]

    status: CaseStatus

    tenant_id: int

    lawyer_id: int

    client_id: int

    created_at: datetime