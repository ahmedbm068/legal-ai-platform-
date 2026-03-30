from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from backend.core.enums import CaseStatus
from backend.core.enums import JurisdictionCountry


class CaseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=2, max_length=200)

    description: Optional[str] = Field(default=None, max_length=4000)

    status: CaseStatus = CaseStatus.open

    client_id: int = Field(..., ge=1)
    jurisdiction_country: JurisdictionCountry = JurisdictionCountry.tunisia


class CaseUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=2, max_length=200)

    description: Optional[str] = Field(default=None, max_length=4000)

    status: Optional[CaseStatus] = None

    client_id: Optional[int] = Field(default=None, ge=1)
    jurisdiction_country: Optional[JurisdictionCountry] = None


class CaseOut(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int

    title: str

    description: Optional[str]

    status: CaseStatus

    tenant_id: int

    lawyer_id: int

    client_id: int
    jurisdiction_country: JurisdictionCountry

    created_at: datetime
