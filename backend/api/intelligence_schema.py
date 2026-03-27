from typing import List, Optional, Literal
from datetime import datetime

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    case_id: Optional[int] = None
    document_id: Optional[int] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    case_id: Optional[int] = None
    document_id: Optional[int] = None


class CopilotRequest(BaseModel):
    message: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)


class RetrievedChunk(BaseModel):
    chunk_id: Optional[int] = None
    document_id: int
    case_id: Optional[int] = None
    filename: str
    chunk_index: int
    chunk_text: str
    score: float
    bm25_score: float = 0.0
    semantic_score: float = 0.0
    retrieval_method: Literal["semantic", "hybrid", "lexical"] = "hybrid"


class RetrievalSearchResponse(BaseModel):
    query: str
    top_k: int
    scope: str
    results: List[RetrievedChunk]


class SourceItem(BaseModel):
    chunk_id: Optional[int] = None
    document_id: int
    case_id: Optional[int] = None
    filename: str
    chunk_index: Optional[int] = None
    score: float
    snippet: str


class AskResponse(BaseModel):
    answer: str
    used_fallback: bool
    fallback_reason: Optional[str] = None
    confidence: str
    scope: str
    sources: List[SourceItem]


class CopilotResponse(BaseModel):
    message: str
    parsed_intent: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    answer: str
    used_fallback: bool
    fallback_reason: Optional[str] = None
    confidence: str
    scope: str
    sources: List[SourceItem]


class EntityOut(BaseModel):
    label: str
    value: str
    start_char: Optional[int] = None
    end_char: Optional[int] = None

    class Config:
        from_attributes = True


class ProcessDocumentResponse(BaseModel):
    document_id: int
    extracted_text_length: int
    entities: List[EntityOut]
    redacted_preview: str
    status: str
    pii_items_count: int


class ImportantDateItem(BaseModel):
    label: str
    value: str


class DocumentSummaryOut(BaseModel):
    document_id: int
    summary: Optional[str] = None
    summary_short: Optional[str] = None
    summary_status: str
    summary_error: Optional[str] = None
    summary_generated_at: Optional[datetime] = None
    document_type: Optional[str] = None
    summary_version: Optional[str] = None
    summary_source: Optional[str] = None

    class Config:
        from_attributes = True


class StructuredDocumentInsightsOut(BaseModel):
    document_type: str
    document_type_confidence: float
    general_summary: str
    key_points: List[str]
    important_dates: List[ImportantDateItem]
    parties_detected: List[str]
    legal_risks: List[str]
    recommended_next_actions: List[str]
    summary_source: str
    summary_version: str


class DocumentSummarizeResponse(BaseModel):
    message: str
    data: DocumentSummaryOut


class FullDocumentAnalysisOut(BaseModel):
    document_id: int
    filename: str
    processing_status: str
    processing_error: Optional[str] = None
    summary_status: str
    summary_error: Optional[str] = None
    extracted_text_length: int
    redacted_preview: str
    entity_count: int
    entities: List[EntityOut]
    summary: Optional[str] = None
    summary_short: Optional[str] = None
    document_type: Optional[str] = None
    summary_version: Optional[str] = None
    summary_source: Optional[str] = None
    last_intelligence_run_at: Optional[datetime] = None
    insights: Optional[StructuredDocumentInsightsOut] = None


class SearchResultItem(BaseModel):
    document_id: int
    filename: str
    matched_text: str


class IntelligenceSearchResponse(BaseModel):
    query: str
    results: List[SearchResultItem]