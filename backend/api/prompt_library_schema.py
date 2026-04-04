from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PromptLibraryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=120)
    prompt_text: str = Field(..., min_length=1, max_length=12000)
    description: Optional[str] = Field(default=None, max_length=500)
    category: Optional[str] = Field(default=None, max_length=80)
    is_favorite: bool = False


class PromptLibraryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    prompt_text: Optional[str] = Field(default=None, min_length=1, max_length=12000)
    description: Optional[str] = Field(default=None, max_length=500)
    category: Optional[str] = Field(default=None, max_length=80)
    is_favorite: Optional[bool] = None


class PromptLibraryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_by_user_id: Optional[int] = None
    title: str
    prompt_text: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_favorite: bool
    created_at: datetime
    updated_at: datetime
