import type {
  AgentWorkflowResponse,
  ArtifactVersionListResponse,
  ArtifactVersionMutationResponse,
  CaseItem,
  Client,
  ConsultationFromTranscriptResponse,
  ConsultationRequest,
  CopilotAttachment,
  CopilotFeedback,
  CopilotFeedbackWeeklySummaryResponse,
  CopilotResponse,
  DocumentItem,
  EvidenceAnalysisReview,
  EvidenceReviewListResponse,
  FullDocumentAnalysis,
  ImageBatchUploadResponse,
  ImageDocumentBatch,
  JurisdictionCountry,
  LLMTestResponse,
  PromptOptimizationResponse,
  PromptLibraryEntry,
  ProviderStatusResponse,
  CaseReviewTable,
  SemanticTranslateResponse,
  TokenResponse,
  UploadedDocumentResponse,
  UploadedVoiceRecordingResponse,
  User,
  VoiceRecording,
  VoiceTranscriptionResponse,
} from "./types";

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

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

interface RequestOptions {
  method?: HttpMethod;
  token?: string | null;
  body?: unknown;
  formData?: FormData;
  timeoutMs?: number;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: HeadersInit = {};
  const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timeoutMs = options.timeoutMs && options.timeoutMs > 0 ? options.timeoutMs : 20000;
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;

  if (!options.formData) {
    headers["Content-Type"] = "application/json";
  }

  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  if (controller && timeoutMs) {
    timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.formData ? options.formData : options.body ? JSON.stringify(options.body) : undefined,
      signal: controller?.signal,
    });
  } catch (error) {
    if ((error as Error)?.name === "AbortError") {
      const seconds = timeoutMs ? Math.max(1, Math.round(timeoutMs / 1000)) : 0;
      throw new Error(
        seconds
          ? `Request timed out after ${seconds}s. Please try again.`
          : "Request timed out. Please try again."
      );
    }
    throw new Error("Unable to reach the server. Check that the backend is running and reachable on this network.");
  } finally {
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
    }
  }

  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: string };
      throw new Error(payload.detail || `Request failed with status ${response.status}`);
    }

    const textResponse = await response.text();
    throw new Error(textResponse || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const textResponse = await response.text();
    throw new Error(
      textResponse.trim().startsWith("<")
        ? "The app received an HTML page instead of API JSON. Restart the frontend dev server and refresh the browser."
        : (textResponse || "Unexpected non-JSON response from the server.")
    );
  }

  return response.json() as Promise<T>;
}

export const workspaceApi = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  register: (payload: {
    name: string;
    email: string;
    password: string;
    tenant_name?: string;
    invite_token?: string;
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

  uploadImageBatch: (
    token: string,
    caseId: number,
    files: File[],
    options?: {
      title?: string;
      generateDocument?: boolean;
      runAuthenticityCheck?: boolean;
    }
  ) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    if (options?.title) {
      formData.append("title", options.title);
    }
    formData.append("generate_document", String(options?.generateDocument ?? true));
    formData.append("run_authenticity_check", String(options?.runAuthenticityCheck ?? false));

    return request<ImageBatchUploadResponse>(`/documents/upload-images?case_id=${caseId}`, {
      method: "POST",
      token,
      formData,
    });
  },

  listCaseImageBatches: (token: string, caseId: number) =>
    request<ImageDocumentBatch[]>(`/documents/case/${caseId}/image-batches`, {
      token,
    }),

  listEvidenceReviews: (token: string, caseId: number) =>
    request<EvidenceReviewListResponse>(`/evidence-reviews/case/${caseId}`, {
      token,
    }),

  getCaseReviewTable: (token: string, caseId: number) =>
    request<CaseReviewTable>(`/intelligence/cases/${caseId}/review-table`, {
      token,
    }),

  listPromptLibrary: (token: string) =>
    request<PromptLibraryEntry[]>("/prompt-library/", {
      token,
    }),

  createPromptLibraryEntry: (
    token: string,
    payload: {
      title: string;
      prompt_text: string;
      description?: string | null;
      category?: string | null;
      is_favorite?: boolean;
    }
  ) =>
    request<PromptLibraryEntry>("/prompt-library/", {
      method: "POST",
      token,
      body: payload,
    }),

  deletePromptLibraryEntry: (token: string, entryId: number) =>
    request<void>(`/prompt-library/${entryId}`, {
      method: "DELETE",
      token,
    }),

  decideEvidenceReview: (
    token: string,
    reviewId: number,
    payload: { decision: "approved" | "rejected"; note?: string | null }
  ) =>
    request<EvidenceAnalysisReview>(`/evidence-reviews/${reviewId}/decision`, {
      method: "POST",
      token,
      body: payload,
    }),

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

  transcribeVoiceInput: (token: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);

    return request<VoiceTranscriptionResponse>("/voice/transcribe", {
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
      mode?: "default" | "legal_search";
      legalSearchMultilingualOutput?: boolean;
      agentMode?: boolean;
      workspaceCaseId?: number | null;
      workspaceDocumentId?: number | null;
      conversationHistory?: Array<{
        role: "user" | "assistant";
        content: string;
        parsed_intent?: string;
        case_id?: number | null;
        document_id?: number | null;
      }>;
      attachments?: CopilotAttachment[];
      saveAttachmentsToCase?: boolean;
      attachmentCaseId?: number | null;
    }
  ) =>
    request<CopilotResponse>("/ai/copilot", {
      method: "POST",
      token,
      timeoutMs: 65000,
      body: {
        message,
        top_k: options?.topK ?? 5,
        use_external_research: options?.useExternalResearch ?? false,
        mode: options?.mode ?? "default",
        legal_search_multilingual_output: options?.legalSearchMultilingualOutput ?? false,
        agent_mode: options?.agentMode ?? false,
        workspace_case_id: options?.workspaceCaseId ?? null,
        workspace_document_id: options?.workspaceDocumentId ?? null,
        conversation_history: options?.conversationHistory ?? [],
        attachments: options?.attachments ?? [],
        save_attachments_to_case: options?.saveAttachmentsToCase ?? false,
        attachment_case_id: options?.attachmentCaseId ?? null,
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

  optimizePrompt: (
    token: string,
    payload: {
      prompt: string;
      workspaceCaseId?: number | null;
      workspaceDocumentId?: number | null;
    }
  ) =>
    request<PromptOptimizationResponse>("/ai/optimize-prompt", {
      method: "POST",
      token,
      body: {
        prompt: payload.prompt,
        workspace_case_id: payload.workspaceCaseId ?? null,
        workspace_document_id: payload.workspaceDocumentId ?? null,
      },
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
