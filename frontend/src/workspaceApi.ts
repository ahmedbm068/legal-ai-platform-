import type {
    AIResponseAuditLogListResponse,
    AssistantUploadResponse,
    CalendarAppointment,
    CalendarAppointmentActionResponse,
    CalendarEvent,
    CalendarEventActionResponse,
    CalendarReminder,
    CaseItem,
    CaseReviewTable,
    CaseWorkflowCatalog,
    CaseWorkflowPreview,
    CaseWorkspaceSnapshot,
    Client,
    ConsultationFromTranscriptResponse,
    ConsultationRequest,
    CitationInsertionResponse,
    CopilotAttachment,
    CopilotResponse,
    DocumentItem,
    DraftOutline,
    DraftDocument,
    DraftDocumentAiEditResponse,
    DraftDocumentPayload,
    DraftDocumentVersion,
    EvidenceAnalysisReview,
    EvidenceReviewListResponse,
    FullDocumentAnalysis,
    FeedbackRootCause,
    ImageBatchDetailResponse,
    ImageBatchUploadResponse,
    ImageDocumentBatch,
    JurisdictionCountry,
    PromptLibraryEntry,
    PromptOptimizationResponse,
    SuccessionCalculateRequest,
    SuccessionCalculateResponse,
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

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

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

async function postBlob(path: string, token: string, body?: unknown): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}${path}`, {
        method: "POST",
        headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
        },
        body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
            const payload = (await response.json()) as { detail?: string };
            throw new Error(payload.detail || `Request failed with status ${response.status}`);
        }
        throw new Error(await response.text());
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

    listArchivedCaseDocuments: (token: string, caseId: number) =>
        request<DocumentItem[]>(`/documents/case/${caseId}/archived`, { token }),

    archiveDocument: (token: string, documentId: number) =>
        request<{ message: string; document_id: number; archived: boolean }>(`/documents/${documentId}/archive`, {
            method: "POST",
            token,
        }),

    unarchiveDocument: (token: string, documentId: number) =>
        request<{ message: string; document_id: number; archived: boolean }>(`/documents/${documentId}/unarchive`, {
            method: "POST",
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

    listArchivedCaseImageBatches: (token: string, caseId: number) =>
        request<ImageDocumentBatch[]>(`/documents/case/${caseId}/image-batches/archived`, { token }),

    getImageBatch: (token: string, batchId: number) =>
        request<ImageBatchDetailResponse>(`/documents/image-batches/${batchId}`, {
            token,
        }),

    getImageAssetFile: (token: string, assetId: number) => requestBlob(`/documents/image-assets/${assetId}/file`, token),

    archiveImageBatch: (token: string, batchId: number) =>
        request<{ message: string; batch_id: number; archived: boolean }>(`/documents/image-batches/${batchId}/archive`, {
            method: "POST",
            token,
        }),

    unarchiveImageBatch: (token: string, batchId: number) =>
        request<{ message: string; batch_id: number; archived: boolean }>(`/documents/image-batches/${batchId}/unarchive`, {
            method: "POST",
            token,
        }),

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

    listCalendarEvents: (
        token: string,
        params?: {
            caseId?: number | null;
            clientId?: number | null;
            eventType?: string | null;
            priority?: string | null;
            status?: string | null;
            requiresReview?: boolean | null;
        }
    ) => {
        const search = new URLSearchParams();
        if (params?.caseId) search.set("case_id", String(params.caseId));
        if (params?.clientId) search.set("client_id", String(params.clientId));
        if (params?.eventType) search.set("event_type", params.eventType);
        if (params?.priority) search.set("priority", params.priority);
        if (params?.status) search.set("status", params.status);
        if (params?.requiresReview !== undefined && params.requiresReview !== null) {
            search.set("requires_review", String(params.requiresReview));
        }
        const query = search.toString();
        return request<CalendarEvent[]>(`/calendar/events${query ? `?${query}` : ""}`, { token });
    },

    listCaseCalendarEvents: (token: string, caseId: number) =>
        request<CalendarEvent[]>(`/cases/${caseId}/calendar/events`, { token }),

    createCalendarEvent: (
        token: string,
        payload: {
            caseId?: number | null;
            title: string;
            description?: string | null;
            eventType: string;
            status?: string;
            priority: string;
            startDatetime: string;
            endDatetime?: string | null;
            allDay?: boolean;
            timezone?: string;
            location?: string | null;
        }
    ) =>
        request<CalendarEventActionResponse>("/calendar/events", {
            method: "POST",
            token,
            body: {
                case_id: payload.caseId ?? null,
                title: payload.title,
                description: payload.description ?? null,
                event_type: payload.eventType,
                status: payload.status ?? "scheduled",
                priority: payload.priority,
                start_datetime: payload.startDatetime,
                end_datetime: payload.endDatetime ?? null,
                all_day: payload.allDay ?? false,
                timezone: payload.timezone ?? "UTC",
                location: payload.location ?? null,
                source_type: "manual",
            },
        }),

    updateCalendarEvent: (
        token: string,
        eventId: number,
        payload: Partial<{
            caseId: number | null;
            title: string;
            description: string | null;
            eventType: string;
            status: string;
            priority: string;
            startDatetime: string;
            endDatetime: string | null;
            allDay: boolean;
            timezone: string;
            location: string | null;
            requiresReview: boolean;
        }>
    ) =>
        request<CalendarEventActionResponse>(`/calendar/events/${eventId}`, {
            method: "PATCH",
            token,
            body: {
                case_id: payload.caseId ?? undefined,
                title: payload.title,
                description: payload.description,
                event_type: payload.eventType,
                status: payload.status,
                priority: payload.priority,
                start_datetime: payload.startDatetime,
                end_datetime: payload.endDatetime,
                all_day: payload.allDay,
                timezone: payload.timezone,
                location: payload.location,
                requires_review: payload.requiresReview,
            },
        }),

    archiveCalendarEvent: (token: string, eventId: number) =>
        request<CalendarEventActionResponse>(`/calendar/events/${eventId}`, {
            method: "DELETE",
            token,
        }),

    listPendingExtractedDates: (token: string, caseId?: number | null) => {
        const query = caseId ? `?case_id=${caseId}` : "";
        return request<CalendarEvent[]>(`/calendar/extracted-dates/pending${query}`, { token });
    },

    acceptExtractedDate: (token: string, eventId: number) =>
        request<CalendarEventActionResponse>(`/calendar/extracted-dates/${eventId}/accept`, {
            method: "POST",
            token,
        }),

    rejectExtractedDate: (token: string, eventId: number) =>
        request<CalendarEventActionResponse>(`/calendar/extracted-dates/${eventId}/reject`, {
            method: "POST",
            token,
        }),

    createCalendarReminder: (token: string, eventId: number, payload: { remindAt: string; method?: string }) =>
        request<CalendarReminder>(`/calendar/events/${eventId}/reminders`, {
            method: "POST",
            token,
            body: {
                remind_at: payload.remindAt,
                method: payload.method ?? "in_app",
            },
        }),

    listUpcomingCalendarReminders: (token: string) =>
        request<CalendarReminder[]>("/calendar/reminders/upcoming", { token }),

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
        request<CaseReviewTable>(`/cases/${caseId}/review-table`, {
            token,
        }),

    getCaseWorkspaceSnapshot: (token: string, caseId: number) =>
        request<CaseWorkspaceSnapshot>(`/cases/${caseId}/workspace`, {
            token,
        }),

    listCaseWorkflows: (token: string, caseId: number) =>
        request<CaseWorkflowCatalog>(`/cases/${caseId}/workflows`, {
            token,
        }),

    previewCaseWorkflow: (token: string, caseId: number, blueprintId: string) =>
        request<CaseWorkflowPreview>(`/cases/${caseId}/workflows/${blueprintId}`, {
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

    archiveVoiceRecording: (token: string, recordingId: number) =>
        request<{ message: string; recording_id: number; archived: boolean }>(`/voice/${recordingId}/archive`, {
            method: "POST",
            token,
        }),

    unarchiveVoiceRecording: (token: string, recordingId: number) =>
        request<{ message: string; recording_id: number; archived: boolean }>(`/voice/${recordingId}/unarchive`, {
            method: "POST",
            token,
        }),

    listArchivedCaseVoiceRecordings: (token: string, caseId: number) =>
        request<VoiceRecording[]>(`/voice/case/${caseId}/archived`, { token }),

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
        request<PromptOptimizationResponse>("/ai/optimize-prompt", {
            method: "POST",
            token,
            body: {
                prompt: payload.prompt,
                workspace_case_id: payload.workspaceCaseId ?? null,
                workspace_document_id: payload.workspaceDocumentId ?? null,
            },
            timeoutMs: SLOW_AI_TIMEOUT_MS,
        }),

    copilot: (
        token: string,
        message: string,
        options?: {
            topK?: number;
            reasoningLevel?: "low" | "medium" | "high" | "deep";
            useExternalResearch?: boolean;
            mode?: "default" | "legal_search";
            legalSearchMultilingualOutput?: boolean;
            legalSearchCodeScope?: string[];
            outputLanguage?: "fr" | "ar" | "en" | "auto";
            languageStrict?: boolean;
            returnCandidates?: boolean;
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
                reasoning_level: options?.reasoningLevel ?? "medium",
                use_external_research: options?.useExternalResearch ?? false,
                mode: options?.mode ?? "default",
                legal_search_multilingual_output: options?.legalSearchMultilingualOutput ?? false,
                legal_search_code_scope: options?.legalSearchCodeScope ?? [],
                output_language: options?.outputLanguage ?? "auto",
                language_strict: options?.languageStrict ?? true,
                return_candidates: options?.returnCandidates ?? false,
                agent_mode: options?.agentMode ?? false,
                workspace_case_id: options?.workspaceCaseId ?? null,
                workspace_document_id: options?.workspaceDocumentId ?? null,
                conversation_history: options?.conversationHistory ?? [],
                attachments: options?.attachments ?? [],
            },
            signal: options?.signal,
            timeoutMs: SLOW_AI_TIMEOUT_MS,
        }),

    uploadAssistantFiles: (
        token: string,
        files: File[],
        options?: {
            caseId?: number | null;
            chatSessionId?: string | null;
            message?: string | null;
        }
    ) => {
        const formData = new FormData();
        files.forEach((file) => formData.append("files", file));
        if (options?.caseId) formData.append("case_id", String(options.caseId));
        if (options?.chatSessionId) formData.append("chat_session_id", options.chatSessionId);
        if (options?.message) formData.append("message", options.message);

        return request<AssistantUploadResponse>("/assistant/upload", {
            method: "POST",
            token,
            formData,
            timeoutMs: SLOW_AI_TIMEOUT_MS,
        });
    },

    askWithFiles: (
        token: string,
        message: string,
        options: {
            uploadedDocumentIds: string[];
            caseId?: number | null;
            chatSessionId?: string | null;
            topK?: number;
            reasoningLevel?: "low" | "medium" | "high" | "deep";
            useExternalResearch?: boolean;
            mode?: "default" | "legal_search";
            legalSearchMultilingualOutput?: boolean;
            agentMode?: boolean;
            conversationHistory?: Array<{
                role: "user" | "assistant";
                content: string;
                parsed_intent?: string | null;
                case_id?: number | null;
                document_id?: number | null;
            }>;
            signal?: AbortSignal;
        }
    ) =>
        request<CopilotResponse>("/assistant/ask-with-files", {
            method: "POST",
            token,
            body: {
                message,
                case_id: options.caseId ?? null,
                chat_session_id: options.chatSessionId ?? null,
                uploaded_document_ids: options.uploadedDocumentIds,
                top_k: options.topK ?? 6,
                reasoning_level: options.reasoningLevel ?? "medium",
                use_external_research: options.useExternalResearch ?? false,
                mode: options.mode ?? "default",
                legal_search_multilingual_output: options.legalSearchMultilingualOutput ?? false,
                agent_mode: options.agentMode ?? false,
                conversation_history: options.conversationHistory ?? [],
            },
            signal: options.signal,
            timeoutMs: SLOW_AI_TIMEOUT_MS,
        }),

    createDraftDocument: (token: string, payload: DraftDocumentPayload) =>
        request<DraftDocument>("/draft-documents", {
            method: "POST",
            token,
            body: {
                case_id: payload.case_id ?? null,
                title: payload.title,
                document_type: payload.document_type || "general",
                content_json: payload.content_json || {},
                content_html: payload.content_html || "",
                content_text: payload.content_text || "",
                source_context_json: payload.source_context || {},
                citations_json: payload.citations || [],
                status: "draft",
            },
        }),

    updateDraftDocument: (
        token: string,
        documentId: number,
        payload: Partial<Pick<DraftDocument, "title" | "document_type" | "content_json" | "content_html" | "content_text" | "status" | "source_context_json" | "citations_json">> & {
            change_summary?: string;
            create_version?: boolean;
        }
    ) =>
        request<DraftDocument>(`/draft-documents/${documentId}`, {
            method: "PATCH",
            token,
            body: payload,
        }),

    listDraftDocuments: (token: string, caseId?: number | null) =>
        request<DraftDocument[]>(`/draft-documents${caseId ? `?case_id=${caseId}` : ""}`, { token }),

    getDraftDocumentVersions: (token: string, documentId: number) =>
        request<DraftDocumentVersion[]>(`/draft-documents/${documentId}/versions`, { token }),

    aiEditDraftDocument: (
        token: string,
        documentId: number,
        payload: {
            selected_text: string;
            instruction: string;
            full_document_context: string;
            case_id?: number | null;
            citation_mode?: "none" | "suggest" | "required";
        }
    ) =>
        request<DraftDocumentAiEditResponse>(`/draft-documents/${documentId}/ai-edit`, {
            method: "POST",
            token,
            body: payload,
            timeoutMs: SLOW_AI_TIMEOUT_MS,
        }),

    createDraftOutline: (
        token: string,
        payload: {
            intent: string;
            objective?: string | null;
            caseId?: number | null;
            jurisdiction?: string | null;
        }
    ) =>
        request<DraftOutline>("/ai/draft/outline", {
            method: "POST",
            token,
            body: {
                intent: payload.intent,
                objective: payload.objective ?? null,
                case_id: payload.caseId ?? null,
                jurisdiction: payload.jurisdiction ?? null,
            },
            timeoutMs: SLOW_AI_TIMEOUT_MS,
        }),

    insertDraftCitation: (
        token: string,
        payload: {
            body: string;
            markerKind?: "doc" | "source" | "citation";
            refId: number;
            position?: number | null;
            sources?: Array<Record<string, unknown>>;
            citations?: Array<Record<string, unknown>>;
        }
    ) =>
        request<CitationInsertionResponse>("/ai/draft/insert-citation", {
            method: "POST",
            token,
            body: {
                body: payload.body,
                marker_kind: payload.markerKind ?? "source",
                ref_id: payload.refId,
                position: payload.position ?? null,
                sources: payload.sources ?? [],
                citations: payload.citations ?? [],
            },
        }),

    resolveDraftCitationMarkers: (
        token: string,
        payload: {
            body: string;
            sources?: Array<Record<string, unknown>>;
            citations?: Array<Record<string, unknown>>;
        }
    ) =>
        request<CitationInsertionResponse>("/ai/draft/resolve-markers", {
            method: "POST",
            token,
            body: {
                body: payload.body,
                sources: payload.sources ?? [],
                citations: payload.citations ?? [],
            },
        }),

    exportDraftDocumentDocx: (token: string, documentId: number) =>
        postBlob(`/draft-documents/${documentId}/export/docx`, token),

    exportDraftDocumentPdf: (token: string, documentId: number) =>
        postBlob(`/draft-documents/${documentId}/export/pdf`, token),

    sendDraftDocumentEmail: (
        token: string,
        documentId: number,
        payload: { to: string; subject: string; cc?: string[]; body_html?: string; body_text?: string; confirm: boolean }
    ) =>
        request<{ message: string; document: DraftDocument | null }>(`/draft-documents/${documentId}/send-email`, {
            method: "POST",
            token,
            body: payload,
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
            comment?: string | null;
            root_cause?: FeedbackRootCause | null;
            legal_domain?: boolean | null;
            jurisdiction?: JurisdictionCountry | null;
            source_count?: number;
            metadata?: Record<string, unknown> | null;
        }
    ) =>
        request<any>("/ai/feedback", {
            method: "POST",
            token,
            body: payload,
        }),

    listAiAuditLogs: (
        token: string,
        params?: {
            caseId?: number | null;
            documentId?: number | null;
            limit?: number;
        }
    ) => {
        const search = new URLSearchParams();
        if (params?.caseId) search.set("case_id", String(params.caseId));
        if (params?.documentId) search.set("document_id", String(params.documentId));
        if (params?.limit) search.set("limit", String(params.limit));
        const query = search.toString();
        return request<AIResponseAuditLogListResponse>(`/ai/audit-logs${query ? `?${query}` : ""}`, {
            token,
        });
    },
    calculateSuccession: (
        token: string,
        body: SuccessionCalculateRequest,
        options?: { signal?: AbortSignal }
    ) =>
        request<SuccessionCalculateResponse>("/ai/succession/calculate", {
            method: "POST",
            token,
            body,
            signal: options?.signal,
        }),
};
