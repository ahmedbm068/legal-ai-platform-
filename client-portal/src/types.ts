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
