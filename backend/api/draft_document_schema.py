from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


DraftDocumentStatus = Literal["draft", "review", "final", "sent", "archived"]


class DraftDocumentBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_id: int | None = Field(default=None, ge=1)
    title: str = Field(..., min_length=1, max_length=240)
    document_type: str = Field(default="general", min_length=1, max_length=80)
    content_json: dict[str, Any] = Field(default_factory=dict)
    content_html: str = ""
    content_text: str = ""
    status: DraftDocumentStatus = "draft"
    source_context_json: dict[str, Any] = Field(default_factory=dict)
    citations_json: list[dict[str, Any]] = Field(default_factory=list)


class DraftDocumentCreate(DraftDocumentBase):
    pass


class DraftDocumentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=240)
    document_type: str | None = Field(default=None, min_length=1, max_length=80)
    content_json: dict[str, Any] | None = None
    content_html: str | None = None
    content_text: str | None = None
    status: DraftDocumentStatus | None = None
    source_context_json: dict[str, Any] | None = None
    citations_json: list[dict[str, Any]] | None = None
    change_summary: str | None = Field(default=None, max_length=2000)
    create_version: bool = True


class DraftDocumentOut(DraftDocumentBase):
    id: int
    tenant_id: int
    created_by_user_id: int | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class DraftDocumentVersionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content_json: dict[str, Any] | None = None
    content_html: str | None = None
    content_text: str | None = None
    change_summary: str | None = Field(default=None, max_length=2000)


class DraftDocumentVersionOut(BaseModel):
    id: int
    draft_document_id: int
    version_number: int
    content_json: dict[str, Any]
    content_html: str
    content_text: str
    created_by_user_id: int | None = None
    change_summary: str | None = None
    created_at: datetime


class DraftDocumentAiEditRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    selected_text: str = Field(..., min_length=1, max_length=12000)
    instruction: str = Field(..., min_length=1, max_length=2000)
    full_document_context: str = Field(default="", max_length=50000)
    case_id: int | None = Field(default=None, ge=1)
    citation_mode: Literal["none", "suggest", "required"] = "suggest"


class DraftDocumentAiEditResponse(BaseModel):
    proposed_text: str
    explanation: str
    confidence: str = "medium"
    citations_used: list[dict[str, Any]] = Field(default_factory=list)
    diff: dict[str, Any] = Field(default_factory=dict)


class DraftDocumentSendEmailRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    to: EmailStr
    subject: str = Field(..., min_length=1, max_length=240)
    cc: list[EmailStr] = Field(default_factory=list)
    body_html: str | None = None
    body_text: str | None = None
    confirm: bool = False


class DraftDocumentActionResponse(BaseModel):
    message: str
    document: DraftDocumentOut | None = None
