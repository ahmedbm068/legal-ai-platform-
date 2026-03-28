import type {
  CaseItem,
  Client,
  CopilotResponse,
  DocumentItem,
  FullDocumentAnalysis,
  TokenResponse,
  UploadedDocumentResponse,
  User,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

interface RequestOptions {
  method?: HttpMethod;
  token?: string | null;
  body?: unknown;
  formData?: FormData;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: HeadersInit = {};

  if (!options.formData) {
    headers["Content-Type"] = "application/json";
  }

  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.formData ? options.formData : options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  register: (payload: {
    name: string;
    email: string;
    password: string;
    tenant_name: string;
    role: string;
  }) =>
    request<User>("/auth/register", {
      method: "POST",
      body: payload,
    }),

  me: (token: string) =>
    request<User>("/auth/me", {
      token,
    }),

  listCases: (token: string) =>
    request<CaseItem[]>("/cases/", {
      token,
    }),

  createCase: (
    token: string,
    payload: { title: string; description: string; status: string; client_id: number }
  ) =>
    request<CaseItem>("/cases/", {
      method: "POST",
      token,
      body: payload,
    }),

  listClients: (token: string) =>
    request<Client[]>("/clients/", {
      token,
    }),

  createClient: (
    token: string,
    payload: { name: string; email?: string; phone?: string; address?: string }
  ) =>
    request<Client>("/clients/", {
      method: "POST",
      token,
      body: payload,
    }),

  listCaseDocuments: (token: string, caseId: number) =>
    request<DocumentItem[]>(`/documents/case/${caseId}`, {
      token,
    }),

  uploadDocument: (token: string, caseId: number, file: File) => {
    const formData = new FormData();
    formData.append("file", file);

    return request<UploadedDocumentResponse>(`/documents/upload?case_id=${caseId}`, {
      method: "POST",
      token,
      formData,
    });
  },

  getDocumentAnalysis: (token: string, documentId: number) =>
    request<FullDocumentAnalysis>(`/intelligence/documents/${documentId}/full-analysis`, {
      token,
    }),

  copilot: (token: string, message: string, topK = 5) =>
    request<CopilotResponse>("/ai/copilot", {
      method: "POST",
      token,
      body: { message, top_k: topK },
    }),
};
