export type UserRole = "admin" | "lawyer" | "assistant";
export type CaseStatus = "open" | "in_progress" | "closed" | "archived";
export type JurisdictionCountry = "tunisia" | "germany";

export interface User {
  id: number;
  name: string;
  email: string;
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
  extracted_text: string | null;
  redacted_text: string | null;
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
  transcript_source: string | null;
  transcript_language: string | null;
  case_id: number;
  tenant_id: number;
  uploaded_by_user_id: number | null;
  created_at: string;
  updated_at: string;
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

export interface CopilotResponse {
  message: string;
  parsed_intent: string;
  target_type: string | null;
  target_id: number | null;
  answer: string;
  used_fallback: boolean;
  fallback_reason: string | null;
  confidence: string;
  scope: string;
  sources: SourceItem[];
  artifact?: ArtifactContext | null;
  jurisdiction?: JurisdictionContext | null;
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
}

export interface UploadedVoiceRecordingResponse {
  recording: VoiceRecording;
  message: string;
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
    sources?: SourceItem[];
    artifact?: ArtifactContext | null;
    jurisdiction?: JurisdictionContext | null;
  };
}
