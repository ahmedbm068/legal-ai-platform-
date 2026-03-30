import type {
  AgentWorkflowResponse,
  ArtifactVersionListResponse,
  ArtifactVersionMutationResponse,
  CaseItem,
  Client,
  ConsultationFromTranscriptResponse,
  ConsultationRequest,
  CopilotResponse,
  CopilotFeedback,
  CopilotFeedbackWeeklySummaryResponse,
  DocumentItem,
  FullDocumentAnalysis,
  LLMTestResponse,
  ProviderStatusResponse,
  SemanticTranslateResponse,
  TokenResponse,
  UploadedDocumentResponse,
  UploadedVoiceRecordingResponse,
  User,
  JurisdictionCountry,
  VoiceRecording,
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
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: string };
      throw new Error(payload.detail || `Request failed with status ${response.status}`);
    }

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
    payload: {
      title: string;
      description: string;
      status: string;
      client_id: number;
      jurisdiction_country: JurisdictionCountry;
    }
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

  listVoiceRecordings: (token: string, caseId: number) =>
    request<VoiceRecording[]>(`/voice/case/${caseId}`, {
      token,
    }),

  uploadVoiceRecording: (token: string, caseId: number, file: File) => {
    const formData = new FormData();
    formData.append("file", file);

    return request<UploadedVoiceRecordingResponse>(`/voice/upload?case_id=${caseId}`, {
      method: "POST",
      token,
      formData,
    });
  },

  listConsultationRequests: (token: string, caseId: number) =>
    request<ConsultationRequest[]>(`/consultations/case/${caseId}`, {
      token,
    }),

  createConsultationFromRecording: (token: string, recordingId: number) =>
    request<ConsultationFromTranscriptResponse>(`/consultations/from-recording/${recordingId}`, {
      method: "POST",
      token,
    }),

  getDocumentAnalysis: (token: string, documentId: number) =>
    request<FullDocumentAnalysis>(`/intelligence/documents/${documentId}/full-analysis`, {
      token,
    }),

  copilot: (
    token: string,
    message: string,
    options?: {
      topK?: number;
      useExternalResearch?: boolean;
      conversationHistory?: Array<{
        role: "user" | "assistant";
        content: string;
        parsed_intent?: string;
        case_id?: number | null;
        document_id?: number | null;
      }>;
    }
  ) =>
    request<CopilotResponse>("/ai/copilot", {
      method: "POST",
      token,
      body: {
        message,
        top_k: options?.topK ?? 5,
        use_external_research: options?.useExternalResearch ?? true,
        conversation_history: options?.conversationHistory ?? [],
      },
    }),

  runAgentWorkflow: (token: string, caseId: number, objective?: string, topK = 5) =>
    request<AgentWorkflowResponse>("/ai/agent-workflow", {
      method: "POST",
      token,
      body: { case_id: caseId, objective, top_k: topK },
    }),

  createCopilotFeedback: (
    token: string,
    payload: {
      message_id?: string | null;
      case_id?: number | null;
      document_id?: number | null;
      prompt_text: string;
      response_text: string;
      parsed_intent?: string | null;
      confidence?: string | null;
      feedback_value: "up" | "down";
      comment?: string | null;
      source_count?: number;
      metadata?: Record<string, unknown>;
    }
  ) =>
    request<CopilotFeedback>("/ai/feedback", {
      method: "POST",
      token,
      body: payload,
    }),

  getCopilotFeedbackWeeklySummary: (token: string, weeks = 8) =>
    request<CopilotFeedbackWeeklySummaryResponse>(`/ai/feedback/weekly-summary?weeks=${weeks}`, {
      token,
    }),

  providerStatus: (token: string) =>
    request<ProviderStatusResponse>("/ai/provider-status", {
      token,
    }),

  testLlm: (token: string, prompt: string) =>
    request<LLMTestResponse>("/ai/test-llm", {
      method: "POST",
      token,
      body: { prompt },
    }),

  semanticTranslate: (
    token: string,
    payload: {
      texts: string[];
      target_language: "en" | "de" | "ar";
      source_language?: "auto" | "en" | "de" | "ar";
      domain?: "legal_ui" | "legal_content" | "general";
    }
  ) =>
    request<SemanticTranslateResponse>("/ai/translate", {
      method: "POST",
      token,
      body: payload,
    }),

  listArtifactVersions: (
    token: string,
    params: {
      artifactType: "document_summary" | "case_email";
      caseId?: number | null;
      documentId?: number | null;
    }
  ) => {
    const search = new URLSearchParams({ artifact_type: params.artifactType });
    if (params.caseId) {
      search.set("case_id", String(params.caseId));
    }
    if (params.documentId) {
      search.set("document_id", String(params.documentId));
    }
    return request<ArtifactVersionListResponse>(`/ai/artifacts/versions?${search.toString()}`, {
      token,
    });
  },

  editArtifactVersion: (
    token: string,
    payload: {
      artifact_type: "document_summary" | "case_email";
      case_id?: number | null;
      document_id?: number | null;
      content: string;
      edit_instruction?: string | null;
      parent_version_id?: number | null;
    }
  ) =>
    request<ArtifactVersionMutationResponse>("/ai/artifacts/versions/edit", {
      method: "POST",
      token,
      body: payload,
    }),

  reviseArtifactVersionWithAgent: (
    token: string,
    payload: {
      artifact_type: "document_summary" | "case_email";
      case_id?: number | null;
      document_id?: number | null;
      instruction: string;
      base_version_id?: number | null;
    }
  ) =>
    request<ArtifactVersionMutationResponse>("/ai/artifacts/versions/agent-revise", {
      method: "POST",
      token,
      body: payload,
    }),

  selectArtifactVersion: (token: string, versionId: number) =>
    request<ArtifactVersionMutationResponse>(`/ai/artifacts/versions/${versionId}/select`, {
      method: "POST",
      token,
    }),
};
