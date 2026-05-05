from datetime import datetime
from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    case_id: Optional[int] = None
    document_id: Optional[int] = None


class DraftOutlineRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    intent: str = Field(..., min_length=1)
    objective: Optional[str] = None
    case_id: Optional[int] = None
    jurisdiction: Optional[str] = None


class CitationInsertionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(..., min_length=0)
    marker_kind: Literal["doc", "source", "citation"] = "source"
    ref_id: int = Field(..., ge=0)
    position: Optional[int] = Field(default=None, ge=0)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)


class CitationInsertionBulkRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(..., min_length=0)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)


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


class CopilotAttachment(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    client_id: str
    name: str = Field(..., min_length=1, max_length=240)
    mime_type: str = Field(..., min_length=1, max_length=120)
    kind: Literal["image", "stored_asset"] = "image"
    data_url: Optional[str] = None
    asset_id: Optional[int] = Field(default=None, ge=1)
    page_order: Optional[int] = Field(default=None, ge=1)


class CopilotRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    use_external_research: bool = True
    mode: Literal["default", "legal_search"] = "default"
    legal_search_multilingual_output: bool = False
    legal_search_code_scope: List[str] = Field(default_factory=list, max_length=6)
    reasoning_level: Literal["low", "medium", "high"] = "medium"
    agent_mode: bool = False
    workspace_case_id: Optional[int] = Field(default=None, ge=1)
    workspace_document_id: Optional[int] = Field(default=None, ge=1)
    conversation_history: List[ConversationTurn] = Field(default_factory=list, max_length=30)
    attachments: List[CopilotAttachment] = Field(default_factory=list, max_length=8)
    save_attachments_to_case: bool = False
    attachment_case_id: Optional[int] = Field(default=None, ge=1)
    # Dev-only: bypass response cache for this request (use in tests only).
    skip_cache: bool = False


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


class PromptOptimizationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    prompt: str = Field(..., min_length=1, max_length=12000)
    workspace_case_id: Optional[int] = Field(default=None, ge=1)
    workspace_document_id: Optional[int] = Field(default=None, ge=1)


class PromptOptimizationResponse(BaseModel):
    optimized_prompt: str
    notes: Optional[str] = None
    strategy: str = "heuristic"
    used_llm: bool = False
    applied_improvements: List[str] = Field(default_factory=list)
    unchanged: bool = False
    target_type: Optional[str] = None
    target_id: Optional[int] = None


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


class CitationItem(BaseModel):
    label: str
    document_id: Optional[int] = None
    case_id: Optional[int] = None
    snippet: str = ""
    url: Optional[str] = None


class CacheMetadata(BaseModel):
    key: Optional[str] = None
    hit: bool = False
    backend: str = "none"


class BackgroundJobItem(BaseModel):
    id: str
    job_type: str
    queue_name: str
    status: str
    tenant_id: Optional[int] = None
    case_id: Optional[int] = None
    document_id: Optional[int] = None
    voice_recording_id: Optional[int] = None
    consultation_request_id: Optional[int] = None
    attempts: int = 0
    max_attempts: int = 0
    error: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


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


class VisionField(BaseModel):
    label: str
    value: str


class VisionCitationItem(BaseModel):
    label: str
    asset_id: Optional[int] = None
    page_order: Optional[int] = None
    snippet: str = ""


class VisionAuthenticityReview(BaseModel):
    risk_score: int = Field(default=0, ge=0, le=100)
    confidence: str = "low"
    signals: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    analysis_text: str = ""


class VisionResult(BaseModel):
    task_kind: str
    summary: str
    answer: str
    extracted_text: str = ""
    detected_language: Optional[str] = None
    confidence: str = "medium"
    fields: List[VisionField] = Field(default_factory=list)
    citations: List[VisionCitationItem] = Field(default_factory=list)
    authenticity_review: Optional[VisionAuthenticityReview] = None


class AskResponse(BaseModel):
    answer: str
    used_fallback: bool
    fallback_reason: Optional[str] = None
    confidence: str
    scope: str
    sources: List[SourceItem]
    citations: List[CitationItem] = Field(default_factory=list)
    trust_panel: Optional[Dict[str, Any]] = None
    cache: CacheMetadata = Field(default_factory=CacheMetadata)


class CopilotResponse(BaseModel):
    message: str
    parsed_intent: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    mode: Literal["default", "legal_search", "multimodal"] = "default"
    agent_mode: bool = False
    action_category: str = "analysis"
    action_status: Optional[str] = None
    permission_denied: bool = False
    steps: List[str] = Field(default_factory=list)
    structured_result: Dict[str, Any] = Field(default_factory=dict)
    answer: str
    used_fallback: bool
    fallback_reason: Optional[str] = None
    confidence: str
    scope: str
    sources: List[SourceItem]
    citations: List[CitationItem] = Field(default_factory=list)
    trust_panel: Optional[Dict[str, Any]] = None
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list)
    cache: CacheMetadata = Field(default_factory=CacheMetadata)
    job_id: Optional[str] = None
    case_snapshot_version: Optional[int] = None
    artifact: Optional[ArtifactContext] = None
    jurisdiction: Optional[JurisdictionContext] = None
    vision_result: Optional[VisionResult] = None
    reasoning_result: Optional[Dict[str, Any]] = None
    saved_asset_ids: List[int] = Field(default_factory=list)
    review_record_id: Optional[int] = None
    open_editor: bool = False
    draft_document: Optional[Dict[str, Any]] = None
    # Quality & insight fields (Step 4/5 — ResponseAssemblyService)
    grounding: Optional[str] = None
    confidence_reason: Optional[str] = None
    legal_warning: Optional[str] = None
    legal_sources_note: Optional[str] = None
    ai_insight: Optional[Dict[str, Any]] = None
    # Phase A1 — Verifier output: {state, reason, should_refuse}
    verification: Optional[Dict[str, Any]] = None


class ReasoningCandidateScore(BaseModel):
    grounding_score: float = Field(default=0.0, ge=0.0, le=1.0)
    citation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    factual_consistency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    legal_usefulness_score: float = Field(default=0.0, ge=0.0, le=1.0)
    actionability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    clarity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    decision_reason: str = ""


class ReasoningCandidateResult(BaseModel):
    rank: int = Field(default=1, ge=1)
    style: str
    answer: str
    score: ReasoningCandidateScore


class HighReasoningResult(BaseModel):
    reasoning_level: Literal["low", "medium", "high"] = "medium"
    activated: bool = False
    winner_index: Optional[int] = None
    second_best_index: Optional[int] = None
    winner_reason: Optional[str] = None
    candidates: List[ReasoningCandidateResult] = Field(default_factory=list)


class CopilotFeedbackCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message_id: Optional[str] = Field(default=None, max_length=120)
    case_id: Optional[int] = Field(default=None, ge=1)
    document_id: Optional[int] = Field(default=None, ge=1)
    prompt_text: str = Field(..., min_length=1, max_length=12000)
    response_text: str = Field(..., min_length=1, max_length=16000)
    parsed_intent: Optional[str] = Field(default=None, max_length=120)
    confidence: Optional[str] = Field(default=None, max_length=24)
    feedback_value: Literal["up", "down"]
    comment: Optional[str] = Field(default=None, max_length=2000)
    lawyer_correction: Optional[str] = Field(default=None, max_length=4000)
    preferred_reasoning_path: Optional[str] = Field(default=None, max_length=500)
    root_cause: Optional[
        Literal[
            "unclear_prompt",
            "wrong_jurisdiction",
            "missing_evidence",
            "generic_answer",
            "wrong_legal_area",
            "ungrounded",
            "other",
        ]
    ] = None
    legal_domain: Optional[bool] = None
    jurisdiction: Optional[str] = Field(default=None, max_length=64)
    source_count: int = Field(default=0, ge=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CopilotFeedbackOut(BaseModel):
    id: int
    tenant_id: int
    user_id: Optional[int] = None
    case_id: Optional[int] = None
    document_id: Optional[int] = None
    message_id: Optional[str] = None
    parsed_intent: Optional[str] = None
    confidence: Optional[str] = None
    feedback_value: Literal["up", "down"]
    prompt_text: str
    response_text: str
    comment: Optional[str] = None
    lawyer_correction: Optional[str] = None
    preferred_reasoning_path: Optional[str] = None
    root_cause: Optional[str] = None
    legal_domain: Optional[bool] = None
    jurisdiction: Optional[str] = None
    source_count: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CopilotFeedbackWeeklyItem(BaseModel):
    week_start: str
    intent: str
    up: int
    down: int
    total: int
    up_rate: float


class CopilotFeedbackWeeklySummaryResponse(BaseModel):
    weeks: int
    rows: List[CopilotFeedbackWeeklyItem] = Field(default_factory=list)


class AIResponseAuditLogOut(BaseModel):
    id: int
    tenant_id: int
    user_id: Optional[int] = None
    case_id: Optional[int] = None
    document_id: Optional[int] = None
    endpoint: str
    parsed_intent: Optional[str] = None
    response_version: str
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    question_text: str
    answer_preview: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    trust_panel: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AIResponseAuditLogListResponse(BaseModel):
    total: int
    rows: List[AIResponseAuditLogOut] = Field(default_factory=list)


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
    citations: List[CitationItem] = Field(default_factory=list)
    case_snapshot_version: Optional[int] = None
    stages: Dict[str, WorkflowStage]
    stage_outputs: Dict[str, Dict[str, Any]]


class ProviderStatusResponse(BaseModel):
    provider_available: bool
    base_url: Optional[str] = None
    model: Optional[str] = None
    summary_model: Optional[str] = None
    key_present: bool
    provider_name: str
    vision_available: bool = False
    vision_provider_name: Optional[str] = None
    vision_model: Optional[str] = None
    vision_reason_unavailable: Optional[str] = None


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
