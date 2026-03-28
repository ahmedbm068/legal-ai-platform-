from typing import Optional, List, Literal, Dict, Any
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


class AgentWorkflowRequest(BaseModel):
    case_id: int = Field(..., ge=1)
    objective: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=10)


class LLMTestRequest(BaseModel):
    prompt: str = Field(default="Reply with OK and the model family in one short sentence.", min_length=1)


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


class WorkflowStage(BaseModel):
    agent_name: str
    success: bool
    warnings: List[str] = []
    error: Optional[str] = None
    trace: List[str] = []


class AgentWorkflowResponse(BaseModel):
    case_id: int
    case_title: str
    objective: str
    retrieval_query: str
    summary: str
    verified_summary: str
    client_email: str
    sources: List[SourceItem]
    stages: Dict[str, WorkflowStage]
    stage_outputs: Dict[str, Dict[str, Any]]


class ProviderStatusResponse(BaseModel):
    provider_available: bool
    base_url: Optional[str] = None
    model: Optional[str] = None
    summary_model: Optional[str] = None
    key_present: bool
    provider_name: str


class LLMTestResponse(BaseModel):
    ok: bool
    provider_name: str
    model: str
    output: str
    error: Optional[str] = None
