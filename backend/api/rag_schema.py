from datetime import datetime
from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    case_id: Optional[int] = None
    document_id: Optional[int] = None


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    case_id: Optional[int] = None
    document_id: Optional[int] = None


class ConversationTurn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)
    parsed_intent: Optional[str] = None
    case_id: Optional[int] = Field(default=None, ge=1)
    document_id: Optional[int] = Field(default=None, ge=1)


class CopilotRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    use_external_research: bool = True
    conversation_history: List[ConversationTurn] = Field(default_factory=list, max_length=30)


class AgentWorkflowRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_id: int = Field(..., ge=1)
    objective: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=10)


class LLMTestRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(default="Reply with OK and the model family in one short sentence.", min_length=1)


class SemanticTranslateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    texts: List[str] = Field(default_factory=list, min_length=1, max_length=40)
    target_language: Literal["en", "de", "ar"] = "en"
    source_language: Literal["auto", "en", "de", "ar"] = "auto"
    domain: Literal["legal_ui", "legal_content", "general"] = "legal_content"


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
    document_id: Optional[int] = None
    case_id: Optional[int] = None
    filename: str
    chunk_index: Optional[int] = None
    score: float
    snippet: str


class ArtifactVersionOut(BaseModel):
    id: int
    tenant_id: int
    case_id: Optional[int] = None
    document_id: Optional[int] = None
    artifact_type: Literal["document_summary", "case_email"]
    version_number: int
    content: str
    source_kind: str
    edit_instruction: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_selected: bool
    parent_version_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime


class ArtifactContext(BaseModel):
    artifact_type: Literal["document_summary", "case_email"]
    case_id: Optional[int] = None
    document_id: Optional[int] = None
    selected_version_id: Optional[int] = None
    version_count: int = 0
    latest_version: Optional[ArtifactVersionOut] = None


class JurisdictionContext(BaseModel):
    country_code: str
    country_display_name: str
    constitutional_references: List[str] = Field(default_factory=list)
    legal_guardrails: List[str] = Field(default_factory=list)
    risk_focus_areas: List[str] = Field(default_factory=list)


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
    artifact: Optional[ArtifactContext] = None
    jurisdiction: Optional[JurisdictionContext] = None


class WorkflowStage(BaseModel):
    agent_name: str
    success: bool
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    trace: List[str] = Field(default_factory=list)


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


class SemanticTranslateResponse(BaseModel):
    target_language: Literal["en", "de", "ar"]
    translations: List[str] = Field(default_factory=list)
    used_fallback: bool


class ArtifactVersionListResponse(BaseModel):
    artifact_type: Literal["document_summary", "case_email"]
    case_id: Optional[int] = None
    document_id: Optional[int] = None
    selected_version_id: Optional[int] = None
    versions: List[ArtifactVersionOut] = Field(default_factory=list)


class ArtifactVersionManualEditRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    artifact_type: Literal["document_summary", "case_email"]
    case_id: Optional[int] = Field(default=None, ge=1)
    document_id: Optional[int] = Field(default=None, ge=1)
    content: str = Field(..., min_length=1)
    edit_instruction: Optional[str] = None
    parent_version_id: Optional[int] = Field(default=None, ge=1)


class ArtifactVersionAgentReviseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    artifact_type: Literal["document_summary", "case_email"]
    case_id: Optional[int] = Field(default=None, ge=1)
    document_id: Optional[int] = Field(default=None, ge=1)
    instruction: str = Field(..., min_length=1)
    base_version_id: Optional[int] = Field(default=None, ge=1)


class ArtifactVersionMutationResponse(BaseModel):
    artifact_type: Literal["document_summary", "case_email"]
    case_id: Optional[int] = None
    document_id: Optional[int] = None
    selected_version_id: Optional[int] = None
    version: ArtifactVersionOut
    versions: List[ArtifactVersionOut] = Field(default_factory=list)
