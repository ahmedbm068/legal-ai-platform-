import type {
  ClientPortalAssistantResponse,
  ClientPortalCalendarItem,
  ClientPortalDashboard,
  ClientPortalBilling,
  ClientPortalMessage,
  ClientPortalMessageResponse,
  ClientPortalPayInvoiceResult,
  ClientPortalThread,
  ClientPortalToken,
  ClientPortalUnread,
  PublicIntakeResponse,
  PublicIntakeStatus,
} from "../types";

export interface BookPortalAppointmentPayload {
  title: string;
  scheduled_at: string;
  duration_minutes?: number;
  appointment_type?: string;
  location?: string | null;
  timezone_name?: string | null;
  notes?: string | null;
}

export interface PortalAppointmentResponse {
  message: string;
  appointment: ClientPortalCalendarItem;
}

function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configuredBaseUrl) {
    return configuredBaseUrl;
  }

  if (import.meta.env.DEV) {
    return "/api";
  }

  if (typeof window !== "undefined") {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
}

const API_BASE_URL = resolveApiBaseUrl();

export function portalApiBaseUrl(): string {
  return API_BASE_URL;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    let message = `Request failed with status ${response.status}`;

    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: string; message?: string; error?: string } | null;
      message = payload?.detail || payload?.message || payload?.error || message;
    } else {
      const text = await response.text();
      if (text?.trim()) {
        message = text.trim();
      }
    }

    throw new ApiError(response.status, message);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    throw new ApiError(
      response.status,
      text.trim().startsWith("<")
        ? "The portal received an HTML page instead of API JSON. Restart the frontend dev server and refresh the browser."
        : (text || "Unexpected non-JSON response from the server.")
    );
  }

  return response.json() as Promise<T>;
}

export async function submitIntake(formData: FormData): Promise<PublicIntakeResponse> {
  const response = await fetch(`${API_BASE_URL}/public/intake/submit`, {
    method: "POST",
    body: formData,
  });

  return parseResponse<PublicIntakeResponse>(response);
}

export async function fetchIntakeStatus(reference: string): Promise<PublicIntakeStatus> {
  const response = await fetch(`${API_BASE_URL}/public/intake/${reference}`);

  return parseResponse<PublicIntakeStatus>(response);
}

export async function registerPortalAccount(payload: {
  tenant_slug: string;
  full_name: string;
  email: string;
  password: string;
  phone?: string;
  address?: string;
}): Promise<ClientPortalMessageResponse> {
  const response = await fetch(`${API_BASE_URL}/portal/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return parseResponse<ClientPortalMessageResponse>(response);
}

export async function requestPortalLoginCode(
  email: string,
  password: string
): Promise<ClientPortalMessageResponse> {
  const response = await fetch(`${API_BASE_URL}/portal/auth/login/request-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  return parseResponse<ClientPortalMessageResponse>(response);
}

export async function loginPortalAccount(email: string, password: string): Promise<ClientPortalToken> {
  const response = await fetch(`${API_BASE_URL}/portal/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  return parseResponse<ClientPortalToken>(response);
}

export async function verifyPortalLoginCode(email: string, code: string): Promise<ClientPortalToken> {
  const response = await fetch(`${API_BASE_URL}/portal/auth/login/verify-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  });

  return parseResponse<ClientPortalToken>(response);
}

export async function fetchPortalDashboard(token: string): Promise<ClientPortalDashboard> {
  const response = await fetch(`${API_BASE_URL}/portal/dashboard`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return parseResponse<ClientPortalDashboard>(response);
}

export async function submitAuthenticatedPortalIntake(
  token: string,
  formData: FormData
): Promise<ClientPortalDashboard> {
  const response = await fetch(`${API_BASE_URL}/portal/intake/submit`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  return parseResponse<ClientPortalDashboard>(response);
}

export async function uploadPortalCaseMaterials(
  token: string,
  caseId: number,
  formData: FormData
): Promise<ClientPortalDashboard> {
  const response = await fetch(`${API_BASE_URL}/portal/cases/${caseId}/uploads`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  return parseResponse<ClientPortalDashboard>(response);
}

export async function bookPortalAppointment(
  token: string,
  caseId: number,
  payload: BookPortalAppointmentPayload
): Promise<PortalAppointmentResponse> {
  const response = await fetch(`${API_BASE_URL}/portal/cases/${caseId}/appointments`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseResponse<PortalAppointmentResponse>(response);
}

export async function cancelPortalAppointment(
  token: string,
  appointmentId: number
): Promise<PortalAppointmentResponse> {
  const response = await fetch(`${API_BASE_URL}/portal/appointments/${appointmentId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });

  return parseResponse<PortalAppointmentResponse>(response);
}

export async function askPortalAssistant(
  token: string,
  payload: {
    message: string;
    case_id?: number | null;
    document_id?: number | null;
    conversation_history?: Array<{ role: "user" | "assistant"; content: string }>;
    top_k?: number;
  }
): Promise<ClientPortalAssistantResponse> {
  const response = await fetch(`${API_BASE_URL}/portal/assistant`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseResponse<ClientPortalAssistantResponse>(response);
}

// ── Messaging (client <-> lawyer, per case) ────────────────────────────────

function caseQuery(caseId?: number | null): string {
  return caseId != null ? `?case_id=${caseId}` : "";
}

export async function fetchPortalThread(
  token: string,
  caseId?: number | null
): Promise<ClientPortalThread> {
  const response = await fetch(`${API_BASE_URL}/portal/messages${caseQuery(caseId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return parseResponse<ClientPortalThread>(response);
}

export async function sendPortalMessage(
  token: string,
  body: string,
  caseId?: number | null
): Promise<ClientPortalMessage> {
  const response = await fetch(`${API_BASE_URL}/portal/messages${caseQuery(caseId)}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ body }),
  });

  return parseResponse<ClientPortalMessage>(response);
}

export async function sendPortalMessageAttachment(
  token: string,
  file: File,
  body: string,
  caseId?: number | null
): Promise<ClientPortalMessage> {
  const formData = new FormData();
  formData.append("attachment", file);
  formData.append("body", body);

  const response = await fetch(
    `${API_BASE_URL}/portal/messages/attachment${caseQuery(caseId)}`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    }
  );

  return parseResponse<ClientPortalMessage>(response);
}

export async function fetchPortalUnreadCount(
  token: string
): Promise<ClientPortalUnread> {
  const response = await fetch(`${API_BASE_URL}/portal/messages/unread-count`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return parseResponse<ClientPortalUnread>(response);
}

export function portalMessageAttachmentUrl(messageId: number): string {
  return `${API_BASE_URL}/portal/messages/${messageId}/attachment`;
}

// ── Billing ────────────────────────────────────────────────────────────────

export async function fetchPortalBilling(token: string): Promise<ClientPortalBilling> {
  const response = await fetch(`${API_BASE_URL}/portal/billing`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return parseResponse<ClientPortalBilling>(response);
}

export async function payPortalInvoice(
  token: string,
  invoiceId: number
): Promise<ClientPortalPayInvoiceResult> {
  const response = await fetch(`${API_BASE_URL}/portal/billing/${invoiceId}/pay`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });

  return parseResponse<ClientPortalPayInvoiceResult>(response);
}
