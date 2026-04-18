import type {
    CalendarAppointment,
    CalendarAppointmentActionResponse,
    CaseItem,
    CaseReviewTable,
    Client,
    ConsultationFromTranscriptResponse,
    ConsultationRequest,
    CopilotAttachment,
    CopilotResponse,
    DocumentItem,
    EvidenceAnalysisReview,
    EvidenceReviewListResponse,
    FullDocumentAnalysis,
    ImageBatchDetailResponse,
    ImageBatchUploadResponse,
    ImageDocumentBatch,
    JurisdictionCountry,
    PromptLibraryEntry,
    PromptOptimizationResponse,
    ProviderStatusResponse,
    CallSession,
    CallSessionCreateResponse,
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
const SLOW_AI_TIMEOUT_MS = 90000;

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

interface RequestOptions {
    method?: HttpMethod;
    token?: string | null;
    body?: unknown;
    formData?: FormData;
    timeoutMs?: number;
    signal?: AbortSignal;
}

async function requestBlob(path: string, token: string): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        headers: {
            Authorization: `Bearer ${token}`,
        },
    });

    if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            const payload = (await response.json()) as { detail?: string };
            throw new Error(payload.detail || `Request failed with status ${response.status}`);
        }

        const textResponse = await response.text();
        throw new Error(textResponse || `Request failed with status ${response.status}`);
    }

    return response.blob();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const headers: HeadersInit = {};
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timeoutMs = options.timeoutMs && options.timeoutMs > 0 ? options.timeoutMs : 20000;
    let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
    let userAborted = false;
    const onExternalAbort = () => {
        userAborted = true;
        controller?.abort();
    };

    if (!options.formData) {
        headers["Content-Type"] = "application/json";
    }

    if (options.token) {
        headers.Authorization = `Bearer ${options.token}`;
    }

    if (options.signal) {
        if (options.signal.aborted) {
            onExternalAbort();
        } else {
            options.signal.addEventListener("abort", onExternalAbort, { once: true });
        }
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
            if (userAborted) {
                throw new Error("Request stopped.");
            }
            const seconds = timeoutMs ? Math.max(1, Math.round(timeoutMs / 1000)) : 0;
            throw new Error(
                seconds
                    ? `Request timed out after ${seconds}s. Please try again.`
                    : "Request timed out. Please try again."
            );
        }
        throw new Error("Unable to reach the server. Check that the backend is running and reachable on this network.");
    } finally {
        if (options.signal) {
            options.signal.removeEventListener("abort", onExternalAbort);
        }
        if (timeoutHandle) {
            clearTimeout(timeoutHandle);
        }
    }

    if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            const payload = (await response.json()) as { detail?: string; message?: string; error?: string };
            throw new Error(payload.detail || payload.message || payload.error || `Request failed with status ${response.status}`);
        }

        const textResponse = await response.text();
        throw new Error(
            textResponse.trim().startsWith("<")
                ? "The app received an HTML page instead of API JSON. Restart the frontend dev server and refresh the browser."
                : (textResponse || "Unexpected non-JSON response from the server.")
        );
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

    updateMyPhone: (token: string, phone: string) =>
        request<User>("/auth/me", {
            method: "PUT",
            token,
            body: { phone },
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
        payload: { name: string; email?: string; phone: string; address?: string }
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

    getDocumentFile: (token: string, documentId: number) => requestBlob(`/documents/${documentId}/file`, token),

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

    getImageBatch: (token: string, batchId: number) =>
        request<ImageBatchDetailResponse>(`/documents/image-batches/${batchId}`, {
            token,
        }),

    getImageAssetFile: (token: string, assetId: number) => requestBlob(`/documents/image-assets/${assetId}/file`, token),

    listCallSessions: (token: string, caseId: number) =>
        request<CallSession[]>(`/calls/case/${caseId}`, {
            token,
        }),

    listCalendarAppointments: (token: string, caseId: number) =>
        request<CalendarAppointment[]>(`/calendar/case/${caseId}`, {
            token,
        }),

    listMyCalendarAppointments: (token: string) =>
        request<CalendarAppointment[]>(`/calendar/me`, {
            token,
        }),

    createCalendarAppointment: (
        token: string,
        caseId: number,
        payload: {
            title: string;
            description?: string | null;
            appointmentType?: string;
            visibilityScope?: string;
            status?: string;
            scheduledAt: string;
            durationMinutes?: number;
            location?: string | null;
            timezoneName?: string | null;
            notes?: string | null;
            consultationRequestId?: number | null;
            useAi?: boolean;
        }
    ) =>
        request<CalendarAppointmentActionResponse>(`/calendar/case/${caseId}`, {
            method: "POST",
            token,
            body: {
                title: payload.title,
                description: payload.description ?? null,
                appointment_type: payload.appointmentType ?? "meeting",
                visibility_scope: payload.visibilityScope ?? "shared",
                status: payload.status ?? "scheduled",
                scheduled_at: payload.scheduledAt,
                duration_minutes: payload.durationMinutes ?? 30,
                location: payload.location ?? null,
                timezone_name: payload.timezoneName ?? "UTC",
                notes: payload.notes ?? null,
                consultation_request_id: payload.consultationRequestId ?? null,
                use_ai: payload.useAi ?? true,
            },
        }),

    updateCalendarAppointment: (
        token: string,
        appointmentId: number,
        payload: {
            title?: string;
            description?: string | null;
            appointmentType?: string;
            visibilityScope?: string;
            status?: string;
            scheduledAt?: string;
            durationMinutes?: number;
            location?: string | null;
            timezoneName?: string | null;
            notes?: string | null;
            useAi?: boolean;
        }
    ) =>
        request<CalendarAppointmentActionResponse>(`/calendar/${appointmentId}`, {
            method: "PUT",
            token,
            body: {
                title: payload.title ?? null,
                description: payload.description ?? null,
                appointment_type: payload.appointmentType ?? null,
                visibility_scope: payload.visibilityScope ?? null,
                status: payload.status ?? null,
                scheduled_at: payload.scheduledAt ?? null,
                duration_minutes: payload.durationMinutes ?? null,
                location: payload.location ?? null,
                timezone_name: payload.timezoneName ?? null,
                notes: payload.notes ?? null,
                use_ai: payload.useAi ?? false,
            },
        }),

    cancelCalendarAppointment: (token: string, appointmentId: number) =>
        request<CalendarAppointmentActionResponse>(`/calendar/${appointmentId}`, {
            method: "DELETE",
            token,
        }),

    createCallSession: (
        token: string,
        caseId: number,
        payload: {
            providerName?: string;
            callerPhone?: string;
            clientPhone?: string;
            notes?: string | null;
        }
    ) =>
        request<CallSessionCreateResponse>(`/calls/case/${caseId}`, {
            method: "POST",
            token,
            body: {
                provider_name: payload.providerName ?? "twilio",
                caller_phone: payload.callerPhone ?? null,
                client_phone: payload.clientPhone ?? null,
                notes: payload.notes ?? null,
                consent_accepted: false,
            },
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

    getVoiceRecording: (token: string, recordingId: number) =>
        request<VoiceRecording>(`/voice/${recordingId}`, {
            token,
        }),

    getVoiceRecordingFile: (token: string, recordingId: number) => requestBlob(`/voice/${recordingId}/file`, token),

    uploadVoiceRecording: (
        token: string,
        caseId: number,
        file: File,
        options?: { recordingKind?: string; callSessionId?: number | null }
    ) => {
        const formData = new FormData();
        formData.append("file", file);
        if (options?.recordingKind) {
            formData.append("recording_kind", options.recordingKind);
        }
        if (options?.callSessionId !== undefined && options.callSessionId !== null) {
            formData.append("call_session_id", String(options.callSessionId));
        }

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
            timeoutMs: SLOW_AI_TIMEOUT_MS,
        }),

    getDocumentAnalysis: (token: string, documentId: number) =>
        request<FullDocumentAnalysis>(`/intelligence/documents/${documentId}/full-analysis`, {
            token,
        }),

    providerStatus: (token: string) =>
        request<ProviderStatusResponse>("/ai/provider-status", {
            token,
        }),

    optimizePrompt: (
        token: string,
        payload: {
            prompt: string;
            workspaceCaseId?: number | null;
            workspaceDocumentId?: number | null;
        }
    ) =>
        request<PromptOptimizationResponse>("/ai/prompt-optimize", {
            method: "POST",
            token,
            body: payload,
            timeoutMs: SLOW_AI_TIMEOUT_MS,
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
                parsed_intent?: string | null;
                case_id?: number | null;
                document_id?: number | null;
            }>;
            attachments?: CopilotAttachment[];
            signal?: AbortSignal;
        }
    ) =>
        request<CopilotResponse>("/ai/copilot", {
            method: "POST",
            token,
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
            },
            signal: options?.signal,
            timeoutMs: SLOW_AI_TIMEOUT_MS,
        }),

    createCopilotFeedback: (
        token: string,
        payload: {
            message_id: string;
            case_id?: number | null;
            document_id?: number | null;
            prompt_text: string;
            response_text: string;
            parsed_intent?: string | null;
            confidence?: string | null;
            feedback_value: "up" | "down";
            source_count?: number;
            metadata?: Record<string, unknown> | null;
        }
    ) =>
        request<any>("/copilot/feedback", {
            method: "POST",
            token,
            body: payload,
        }),
};
