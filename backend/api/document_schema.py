from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field


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
    job: dict = Field(default_factory=dict)


class CaseImageAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    case_id: int
    batch_id: Optional[int] = None
    filename: str
    storage_path: str
    mime_type: str
    file_size: int
    page_order: Optional[int] = None
    source_scope: str
    processing_status: str
    processing_error: Optional[str] = None
    extracted_text: Optional[str] = None
    detected_language: Optional[str] = None
    ocr_confidence: Optional[float] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ImageDocumentBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    case_id: int
    title: str
    status: str
    processing_error: Optional[str] = None
    asset_count: int
    generate_document: bool
    run_authenticity_check: bool
    ocr_provider: Optional[str] = None
    generated_document_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class EvidenceAnalysisReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    case_id: int
    image_asset_id: Optional[int] = None
    image_batch_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    reviewed_by_user_id: Optional[int] = None
    status: str
    review_decision: Optional[str] = None
    risk_score: int
    confidence: str
    analysis_text: str
    signals: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    reviewed_at: Optional[datetime] = None


class ImageBatchUploadResponse(BaseModel):
    batch: ImageDocumentBatchOut
    job: dict = Field(default_factory=dict)


class ImageBatchDetailResponse(BaseModel):
    batch: ImageDocumentBatchOut
    assets: List[CaseImageAssetOut] = Field(default_factory=list)
    generated_document: Optional[DocumentListItemOut] = None
    review: Optional[EvidenceAnalysisReviewOut] = None
