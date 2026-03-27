from typing import Optional, List, Literal
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


class SearchResponse(BaseModel):
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