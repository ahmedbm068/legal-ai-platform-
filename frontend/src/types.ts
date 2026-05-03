export type UserRole = "admin" | "lawyer" | "assistant";
export type CaseStatus = "open" | "in_progress" | "closed" | "archived";
export type JurisdictionCountry = "tunisia" | "germany";
export type FeedbackRootCause =
  | "unclear_prompt"
  | "wrong_jurisdiction"
  | "missing_evidence"
  | "generic_answer"
  | "wrong_legal_area"
  | "ungrounded"
  | "other";

export interface User {
  id: number;
  name: string;
  email: string;
  phone?: string | null;
  role: UserRole;
  tenant_id: number;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface Client {
  id: number;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  tenant_id: number;
  created_at: string;
}

export interface CaseItem {
  id: number;
  title: string;
  description: string | null;
  status: CaseStatus;
  jurisdiction_country: JurisdictionCountry;
  tenant_id: number;
  lawyer_id: number;
  client_id: number;
  created_at: string;
}

export interface DocumentItem {
  id: number;
  filename: string;
  storage_path: string;
  processing_status: string;
  processing_error: string | null;
  file_size: number;
  file_type: string;
  upload_timestamp: string;
  case_id: number;
  tenant_id: number;
  extracted_text?: string | null;
  redacted_text?: string | null;
}

export interface EntityOut {
  label: string;
  value: string;
  start_char?: number | null;
  end_char?: number | null;
}

export interface ImportantDateItem {
  label: string;
  value: string;
}

export interface StructuredDocumentInsights {
  document_type: string;
  document_type_confidence: number;
  general_summary: string;
  key_points: string[];
  important_dates: ImportantDateItem[];
  parties_detected: string[];
  legal_risks: string[];
  recommended_next_actions: string[];
  summary_source: string;
  summary_version: string;
  legal_case_analysis?: {
    case_name?: string;
    court_level?: string;
    citation?: string;
    judges?: string[];
    catchwords?: string[];
    headnote_warning?: string;
    fact_flowchart?: string[];
    legal_issues?: string[];
    holding?: string[];
    ratio?: string[];
    obiter?: string[];
    summary_bullets?: string[];
  } | null;
}

export interface FullDocumentAnalysis {
  document_id: number;
  filename: string;
  processing_status: string;
  processing_error: string | null;
  summary_status: string;
  summary_error: string | null;
  extracted_text_length: number;
  redacted_preview: string;
  entity_count: number;
  entities: EntityOut[];
  summary: string | null;
  summary_short: string | null;
  document_type: string | null;
  summary_version: string | null;
  summary_source: string | null;
  last_intelligence_run_at: string | null;
  insights: StructuredDocumentInsights | null;
}

export interface VoiceRecording {
  id: number;
  filename: string;
  storage_path: string;
  mime_type: string;
  file_size: number;
  transcription_status: string;
  transcription_error: string | null;
  transcript_text: string | null;
  conversation_transcript_text: string | null;
  transcript_source: string | null;
  transcript_language: string | null;
  case_id: number;
  tenant_id: number;
  uploaded_by_user_id: number | null;
  created_at: string;
  updated_at: string;
  recording_kind?: string | null;
  call_session_id?: number | null;
}

export interface CallSession {
  id: number;
  case_id: number;
  tenant_id: number;
  client_id: number;
  started_by_user_id?: number | null;
  provider_name?: string | null;
  provider_call_id?: string | null;
  caller_phone?: string | null;
  client_phone?: string | null;
  call_status: string;
  recording_status: string;
  summary_status: string;
  consent_accepted: boolean;
  consent_accepted_at?: string | null;
  consent_request_status?: string | null;
  consent_requested_at?: string | null;
  consent_message?: string | null;
  consent_response_text?: string | null;
  consent_responded_at?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_seconds?: number | null;
  summary_text?: string | null;
  transcript_text?: string | null;
  conversation_transcript_text?: string | null;
  transcript_source?: string | null;
  transcription_error?: string | null;
  notes?: string | null;
  voice_recording?: VoiceRecording | null;
  created_at: string;
  updated_at: string;
}

export interface CallSessionCreateResponse {
  call_session: CallSession;
  message: string;
  consent_message?: string | null;
  whatsapp_chat_url?: string | null;
  consent_delivery_mode?: string | null;
}

export interface CalendarAppointment {
  id: number;
  case_id: number;
  tenant_id: number;
  lawyer_id?: number | null;
  client_id?: number | null;
  consultation_request_id?: number | null;
  created_by_user_id?: number | null;
  title: string;
  description?: string | null;
  appointment_type: string;
  visibility_scope: string;
  status: string;
  scheduled_at: string;
  duration_minutes: number;
  location?: string | null;
  timezone_name: string;
  ai_summary?: string | null;
  ai_recommendation?: string | null;
  ai_confidence?: string | null;
  ai_source?: string | null;
  notes?: string | null;
  case_title?: string | null;
  client_name?: string | null;
  lawyer_name?: string | null;
  is_ai_suggested: boolean;
  created_at: string;
  updated_at: string;
}

export interface CalendarAppointmentActionResponse {
  message: string;
  appointment: CalendarAppointment;
}

export type LegalCalendarEventType =
  | "hearing"
  | "deadline"
  | "meeting"
  | "task"
  | "document_date"
  | "limitation_period"
  | "filing_deadline"
  | "payment_due"
  | "contract_date"
  | "reminder"
  | "other";

export type LegalCalendarStatus = "scheduled" | "completed" | "cancelled" | "missed" | "tentative" | "rejected";
export type LegalCalendarPriority = "low" | "medium" | "high" | "critical";

export interface CalendarEvent {
  id: number;
  tenant_id: number;
  case_id?: number | null;
  client_id?: number | null;
  lawyer_id?: number | null;
  title: string;
  description?: string | null;
  event_type: LegalCalendarEventType | string;
  status: LegalCalendarStatus | string;
  priority: LegalCalendarPriority | string;
  start_datetime: string;
  end_datetime?: string | null;
  all_day: boolean;
  timezone: string;
  location?: string | null;
  source_type: "manual" | "document_extraction" | "ai_generated" | "task" | "external_sync" | string;
  source_document_id?: number | null;
  source_chunk_id?: number | null;
  source_quote?: string | null;
  extraction_confidence?: number | null;
  requires_review: boolean;
  reviewed_by?: number | null;
  reviewed_at?: string | null;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  case_title?: string | null;
  client_name?: string | null;
  document_filename?: string | null;
  reminder_count: number;
}

export interface CalendarEventActionResponse {
  message: string;
  event: CalendarEvent;
}

export interface CalendarReminder {
  id: number;
  tenant_id: number;
  event_id: number;
  remind_at: string;
  method: string;
  status: string;
  created_at: string;
  event_title?: string | null;
}

export interface ConsultationRequest {
  id: number;
  case_id: number;
  tenant_id: number;
  voice_recording_id: number | null;
  client_name: string | null;
  client_email: string | null;
  client_phone: string | null;
  booking_intent: string;
  urgency_level: string;
  legal_area: string | null;
  preferred_schedule: string | null;
  issue_summary: string;
  extracted_case_description: string | null;
  intake_notes: string | null;
  status: string;
  extraction_source: string | null;
  created_at: string;
  updated_at: string;
}

export interface SourceItem {
  chunk_id: number | null;
  document_id: number | null;
  case_id: number | null;
  filename: string;
  chunk_index: number | null;
  score: number;
  snippet: string;
}

export interface CitationItem {
  label: string;
  document_id?: number | null;
  case_id?: number | null;
  snippet: string;
  url?: string | null;
}

export interface CacheMetadata {
  key?: string | null;
  hit: boolean;
  backend: string;
}

export interface BackgroundJobItem {
  id: string;
  job_type: string;
  queue_name: string;
  status: string;
  tenant_id?: number | null;
  case_id?: number | null;
  document_id?: number | null;
  voice_recording_id?: number | null;
  consultation_request_id?: number | null;
  attempts: number;
  max_attempts: number;
  error?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface CopilotAttachment {
  client_id: string;
  name: string;
  mime_type: string;
  kind: "image" | "stored_asset";
  data_url?: string | null;
  asset_id?: number | null;
  page_order?: number | null;
}

export interface VisionField {
  label: string;
  value: string;
}

export interface VisionCitationItem {
  label: string;
  asset_id?: number | null;
  page_order?: number | null;
  snippet: string;
}

export interface VisionAuthenticityReview {
  risk_score: number;
  confidence: string;
  signals: string[];
  limitations: string[];
  analysis_text: string;
}

export interface VisionResult {
  task_kind: string;
  summary: string;
  answer: string;
  extracted_text: string;
  detected_language?: string | null;
  confidence: string;
  fields: VisionField[];
  citations: VisionCitationItem[];
  authenticity_review?: VisionAuthenticityReview | null;
}

export interface CaseImageAsset {
  id: number;
  tenant_id: number;
  case_id: number;
  batch_id?: number | null;
  filename: string;
  storage_path: string;
  mime_type: string;
  file_size: number;
  page_order?: number | null;
  source_scope: string;
  processing_status: string;
  processing_error?: string | null;
  extracted_text?: string | null;
  detected_language?: string | null;
  ocr_confidence?: number | null;
  created_by_user_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface ImageDocumentBatch {
  id: number;
  tenant_id: number;
  case_id: number;
  title: string;
  status: string;
  processing_error?: string | null;
  asset_count: number;
  generate_document: boolean;
  run_authenticity_check: boolean;
  ocr_provider?: string | null;
  generated_document_id?: number | null;
  created_by_user_id?: number | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface ReviewTableRow {
  document_id: number;
  filename: string;
  processing_status: string;
  summary_status: string;
  document_type?: string | null;
  document_type_confidence?: number | null;
  parties: string[];
  important_dates: string[];
  legal_risks: string[];
  recommended_actions: string[];
  source_kind: string;
}

export interface CaseReviewTable {
  case_id: number;
  row_count: number;
  rows: ReviewTableRow[];
}

export interface PromptLibraryEntry {
  id: number;
  tenant_id: number;
  created_by_user_id?: number | null;
  title: string;
  prompt_text: string;
  description?: string | null;
  category?: string | null;
  is_favorite: boolean;
  created_at: string;
  updated_at: string;
}

export interface EvidenceAnalysisReview {
  id: number;
  tenant_id: number;
  case_id: number;
  image_asset_id?: number | null;
  image_batch_id?: number | null;
  created_by_user_id?: number | null;
  reviewed_by_user_id?: number | null;
  status: string;
  review_decision?: string | null;
  risk_score: number;
  confidence: string;
  analysis_text: string;
  signals: string[];
  limitations: string[];
  evidence: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  reviewed_at?: string | null;
}

export interface ImageBatchUploadResponse {
  batch: ImageDocumentBatch;
  job?: BackgroundJobItem;
}

export interface ImageBatchDetailResponse {
  batch: ImageDocumentBatch;
  assets: CaseImageAsset[];
  generated_document?: DocumentItem | null;
  review?: EvidenceAnalysisReview | null;
}

export interface EvidenceReviewListResponse {
  reviews: EvidenceAnalysisReview[];
}

export interface ArtifactVersion {
  id: number;
  tenant_id: number;
  case_id: number | null;
  document_id: number | null;
  artifact_type: "document_summary" | "case_email";
  version_number: number;
  content: string;
  source_kind: string;
  edit_instruction: string | null;
  metadata: Record<string, unknown>;
  is_selected: boolean;
  parent_version_id: number | null;
  created_by_user_id: number | null;
  created_at: string;
}

export interface ArtifactContext {
  artifact_type: "document_summary" | "case_email";
  case_id: number | null;
  document_id: number | null;
  selected_version_id: number | null;
  version_count: number;
  latest_version: ArtifactVersion | null;
}

export interface JurisdictionContext {
  country_code: JurisdictionCountry;
  country_display_name: string;
  constitutional_references: string[];
  legal_guardrails: string[];
  risk_focus_areas: string[];
}

export interface HighReasoningScore {
  grounding_score: number;
  citation_score: number;
  factual_consistency_score: number;
  legal_usefulness_score: number;
  actionability_score: number;
  clarity_score: number;
  overall_score: number;
  decision_reason: string;
}

export interface HighReasoningCandidate {
  rank: number;
  style: string;
  answer: string;
  score: HighReasoningScore;
}

export interface HighReasoningResult {
  reasoning_level: "low" | "medium" | "high";
  activated: boolean;
  winner_index?: number | null;
  second_best_index?: number | null;
  winner_reason?: string | null;
  candidates: HighReasoningCandidate[];
}

export interface CopilotResponse {
  message: string;
  parsed_intent: string;
  target_type: string | null;
  target_id: number | null;
  mode?: "default" | "legal_search";
  agent_mode?: boolean;
  action_category?: string;
  action_status?: string | null;
  permission_denied?: boolean;
  steps?: string[];
  structured_result?: Record<string, unknown>;
  answer: string;
  used_fallback: boolean;
  fallback_reason: string | null;
  confidence: string;
  scope: string;
  sources: SourceItem[];
  citations?: CitationItem[];
  trust_panel?: Record<string, unknown> | null;
  execution_trace?: Array<Record<string, unknown>>;
  cache?: CacheMetadata;
  job_id?: string | null;
  case_snapshot_version?: number | null;
  artifact?: ArtifactContext | null;
  jurisdiction?: JurisdictionContext | null;
  reasoning_result?: HighReasoningResult | null;
  vision_result?: VisionResult | null;
  saved_asset_ids?: number[];
  review_record_id?: number | null;
  open_editor?: boolean;
  draft_document?: DraftDocumentPayload | null;
  ai_insight?: {
    grounding_type?: string;
    confidence_level?: string;
    legal_grounding?: string;
    grounding_description?: string;
    lawyer_note?: string;
  } | null;
}

export interface DraftDocumentPayload {
  title: string;
  document_type: string;
  case_id?: number | null;
  content_json?: Record<string, unknown>;
  content_html: string;
  content_text?: string;
  citations?: CitationItem[];
  source_context?: Record<string, unknown>;
}

export interface DraftDocument {
  id: number;
  tenant_id: number;
  case_id: number | null;
  created_by_user_id: number | null;
  title: string;
  document_type: string;
  content_json: Record<string, unknown>;
  content_html: string;
  content_text: string;
  status: "draft" | "review" | "final" | "sent" | "archived";
  source_context_json: Record<string, unknown>;
  citations_json: CitationItem[];
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface DraftDocumentVersion {
  id: number;
  draft_document_id: number;
  version_number: number;
  content_json: Record<string, unknown>;
  content_html: string;
  content_text: string;
  created_by_user_id: number | null;
  change_summary: string | null;
  created_at: string;
}

export interface DraftDocumentAiEditResponse {
  proposed_text: string;
  explanation: string;
  confidence: string;
  citations_used: CitationItem[];
  diff: Record<string, unknown>;
}

export interface CopilotFeedback {
  id: number;
  tenant_id: number;
  user_id: number | null;
  case_id: number | null;
  document_id: number | null;
  message_id: string | null;
  parsed_intent: string | null;
  confidence: string | null;
  feedback_value: "up" | "down";
  prompt_text: string;
  response_text: string;
  comment: string | null;
  root_cause?: FeedbackRootCause | null;
  legal_domain?: boolean | null;
  jurisdiction?: JurisdictionCountry | null;
  source_count: number;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface CopilotFeedbackWeeklyItem {
  week_start: string;
  intent: string;
  up: number;
  down: number;
  total: number;
  up_rate: number;
}

export interface CopilotFeedbackWeeklySummaryResponse {
  weeks: number;
  rows: CopilotFeedbackWeeklyItem[];
}

export interface AIResponseAuditLog {
  id: number;
  tenant_id: number;
  user_id?: number | null;
  case_id?: number | null;
  document_id?: number | null;
  endpoint: string;
  parsed_intent?: string | null;
  response_version: string;
  model_name?: string | null;
  prompt_version?: string | null;
  question_text: string;
  answer_preview: string;
  sources: Array<Record<string, unknown>>;
  trust_panel: Record<string, unknown>;
  validation: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface AIResponseAuditLogListResponse {
  total: number;
  rows: AIResponseAuditLog[];
}

export interface ArtifactVersionListResponse {
  artifact_type: "document_summary" | "case_email";
  case_id: number | null;
  document_id: number | null;
  selected_version_id: number | null;
  versions: ArtifactVersion[];
}

export interface ArtifactVersionMutationResponse {
  artifact_type: "document_summary" | "case_email";
  case_id: number | null;
  document_id: number | null;
  selected_version_id: number | null;
  version: ArtifactVersion;
  versions: ArtifactVersion[];
}

export interface WorkflowStage {
  agent_name: string;
  success: boolean;
  warnings: string[];
  error: string | null;
  trace: string[];
}

export interface AgentWorkflowResponse {
  case_id: number;
  case_title: string;
  objective: string;
  retrieval_query: string;
  summary: string;
  verified_summary: string;
  client_email: string;
  sources: SourceItem[];
  citations?: CitationItem[];
  case_snapshot_version?: number | null;
  stages: Record<string, WorkflowStage>;
  stage_outputs: Record<string, Record<string, unknown>>;
}

export interface ProviderStatusResponse {
  provider_available: boolean;
  base_url: string | null;
  model: string | null;
  summary_model: string | null;
  key_present: boolean;
  provider_name: string;
  vision_available: boolean;
  vision_provider_name: string | null;
  vision_model: string | null;
  vision_reason_unavailable: string | null;
}

export interface LLMTestResponse {
  ok: boolean;
  provider_name: string;
  model: string;
  output: string;
  error: string | null;
}

export interface SemanticTranslateResponse {
  target_language: "en" | "de" | "ar";
  translations: string[];
  used_fallback: boolean;
}

export interface PromptOptimizationResponse {
  optimized_prompt: string;
  notes?: string | null;
  strategy: string;
  used_llm: boolean;
  applied_improvements?: string[];
  unchanged?: boolean;
  target_type?: string | null;
  target_id?: number | null;
}

export interface VoiceTranscriptionResponse {
  success: boolean;
  transcript_text: string;
  transcript_source?: string | null;
  transcript_language?: string | null;
  error?: string | null;
}

export interface UploadedDocumentResponse {
  document: DocumentItem;
  ai_processing: {
    success: boolean;
    message: string;
    status: string;
    chunks_count?: number | null;
    entities_extracted?: number | null;
    pii_items_count?: number | null;
    text_length?: number | null;
    error?: string | null;
  };
  job?: BackgroundJobItem;
}

export interface AssistantUploadedFile {
  id: string;
  document_id?: number | null;
  filename: string;
  file_size: number;
  mime_type: string;
  processing_status: string;
  extracted_text_status: "ready" | "pending" | "failed" | "unsupported";
  case_id?: number | null;
  temporary: boolean;
  error?: string | null;
}

export interface AssistantUploadResponse {
  uploaded_document_ids: string[];
  files: AssistantUploadedFile[];
  errors: AssistantUploadedFile[];
}

export interface UploadedVoiceRecordingResponse {
  recording: VoiceRecording;
  message: string;
  job?: BackgroundJobItem;
}

export interface ConsultationFromTranscriptResponse {
  message: string;
  consultation_request: ConsultationRequest;
}

export interface ChatMessage {
  id: string;
  role: "assistant" | "user";
  content: string;
  timestamp: string;
  meta?: {
    parsedIntent?: string;
    confidence?: string;
    fallbackReason?: string | null;
    actionCategory?: string;
    actionStatus?: string | null;
    permissionDenied?: boolean;
    steps?: string[];
    structuredResult?: Record<string, unknown>;
    trustPanel?: Record<string, unknown> | null;
    sources?: SourceItem[];
    citations?: CitationItem[];
    executionTrace?: Array<Record<string, unknown>>;
    cache?: CacheMetadata;
    jobId?: string | null;
    caseSnapshotVersion?: number | null;
    artifact?: ArtifactContext | null;
    jurisdiction?: JurisdictionContext | null;
    reasoningResult?: HighReasoningResult | null;
    visionResult?: VisionResult | null;
    savedAssetIds?: number[];
    reviewRecordId?: number | null;
    openEditor?: boolean;
    draftDocument?: DraftDocumentPayload | null;
    attachments?: Array<{
      clientId: string;
      name: string;
      mimeType: string;
    }>;
    rawAnswer?: string | null;
    aiInsight?: {
      grounding_type?: string;
      confidence_level?: string;
      legal_grounding?: string;
      grounding_description?: string;
      lawyer_note?: string;
    } | null;
  };
}
