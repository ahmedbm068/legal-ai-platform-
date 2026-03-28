import type { PublicIntakeResponse, PublicIntakeStatus } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function submitIntake(formData: FormData): Promise<PublicIntakeResponse> {
  const response = await fetch(`${API_BASE_URL}/public/intake/submit`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<PublicIntakeResponse>;
}

export async function fetchIntakeStatus(reference: string): Promise<PublicIntakeStatus> {
  const response = await fetch(`${API_BASE_URL}/public/intake/${reference}`);

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<PublicIntakeStatus>;
}
