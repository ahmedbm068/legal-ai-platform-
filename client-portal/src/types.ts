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

export interface ClientPortalDashboard {
  account: ClientPortalAccount;
  consultations: ClientPortalConsultation[];
}
