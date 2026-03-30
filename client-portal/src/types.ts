export interface PublicIntakeResponse {
  message: string;
  public_reference: string;
  consultation_request_id: number;
  case_id: number;
  client_name: string;
  status: string;
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
  tenant_id: number;
  client_id: number | null;
  tenant_name?: string | null;
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
}
