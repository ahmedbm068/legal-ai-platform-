export interface PublicIntakeResponse {
  message: string;
  tenant_slug?: string | null;
  public_reference: string;
  consultation_request_id: number;
  case_id: number;
  client_name: string;
  status: string;
  jobs: BackgroundJobItem[];
}

export interface PublicIntakeStatus {
  public_reference: string;
  status: string;
  client_name?: string | null;
  issue_summary: string;
  preferred_schedule?: string | null;
  created_at: string;
}

export interface ClientPortalToken {
  access_token: string;
  token_type: string;
}

export interface ClientPortalMessageResponse {
  message: string;
}

export interface ClientPortalAccount {
  id: number;
  full_name: string;
  email: string;
  phone: string | null;
  address: string | null;
  tenant_id: number;
  client_id: number | null;
  tenant_name?: string | null;
  tenant_slug?: string | null;
  requires_email_verification: boolean;
  created_at: string;
}

export interface ClientPortalConsultation {
  id: number;
  case_id: number;
  case_title: string;
  public_reference: string | null;
  status: string;
  issue_summary: string;
  preferred_schedule: string | null;
  legal_area: string | null;
  urgency_level: string;
  created_at: string;
}

export interface ClientPortalCase {
  id: number;
  title: string;
  description: string | null;
  status: string;
  jurisdiction_country: string;
  lawyer_name: string | null;
  document_count: number;
  consultation_count: number;
  next_recommended_step: string | null;
  created_at: string;
  updated_at: string;
}

export interface ClientPortalDocument {
  id: number;
  case_id: number;
  case_title: string;
  filename: string;
  file_type: string;
  file_size: number;
  processing_status: string;
  upload_timestamp: string;
}

export interface ClientPortalActivity {
  id: string;
  event_type: string;
  title: string;
  description: string;
  created_at: string;
  case_id: number | null;
}

export interface ClientPortalDashboardMetrics {
  total_cases: number;
  active_cases: number;
  total_documents: number;
  pending_documents: number;
  consultation_requests: number;
  requests_under_review: number;
}

export interface ClientPortalDashboard {
  account: ClientPortalAccount;
  consultations: ClientPortalConsultation[];
  cases: ClientPortalCase[];
  documents: ClientPortalDocument[];
  activity: ClientPortalActivity[];
  metrics: ClientPortalDashboardMetrics;
  jobs: BackgroundJobItem[];
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

export interface CitationItem {
  label: string;
  document_id?: number | null;
  case_id?: number | null;
  snippet: string;
}

export interface ExecutionTraceItem {
  stage?: string;
  name?: string;
  status?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface ClientPortalAssistantResponse {
  answer: string;
  confidence: string;
  scope: string;
  sources: Array<{
    chunk_id?: number | null;
    document_id?: number | null;
    case_id?: number | null;
    filename: string;
    chunk_index?: number | null;
    score: number;
    snippet: string;
  }>;
  citations: CitationItem[];
  execution_trace: ExecutionTraceItem[];
  case_snapshot_version?: number | null;
}
