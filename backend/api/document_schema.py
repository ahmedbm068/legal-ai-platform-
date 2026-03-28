from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    storage_path: str
    processing_status: str
    processing_error: Optional[str] = None
    file_size: int
    file_type: str
    upload_timestamp: datetime
    case_id: int
    tenant_id: int
    extracted_text: Optional[str] = None
    redacted_text: Optional[str] = None


class DocumentListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    storage_path: str
    processing_status: str
    processing_error: Optional[str] = None
    file_size: int
    file_type: str
    upload_timestamp: datetime
    case_id: int
    tenant_id: int


class DocumentAIProcessingOut(BaseModel):
    success: bool
    message: str
    status: str
    chunks_count: Optional[int] = None
    entities_extracted: Optional[int] = None
    pii_items_count: Optional[int] = None
    text_length: Optional[int] = None
    error: Optional[str] = None


class DocumentUploadResponse(BaseModel):
    document: DocumentOut
    ai_processing: DocumentAIProcessingOut
