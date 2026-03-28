import type {
  ClientPortalDashboard,
  ClientPortalMessageResponse,
  ClientPortalToken,
  PublicIntakeResponse,
  PublicIntakeStatus,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
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
