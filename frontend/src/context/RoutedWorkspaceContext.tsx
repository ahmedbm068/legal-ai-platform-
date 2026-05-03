import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ReactNode,
} from "react";
import { workspaceApi } from "../workspaceApi";
import { persistChatStateToLocalStorage } from "../chatStorage";
import { type ThemeMode, type UiLanguage, translateRouted } from "./routedI18n";
import type {
    CalendarAppointment,
    CaseItem,
    ChatMessage,
    Client,
    ConsultationRequest,
    CopilotResponse,
    DocumentItem,
    ImageDocumentBatch,
    User,
    VoiceRecording,
} from "../types";

const TOKEN_STORAGE_KEY = "legal-ai-platform-token";
const THEME_STORAGE_KEY = "legal-ai-platform-theme-v3";
const LANGUAGE_STORAGE_KEY = "legal-ai-platform-language-v3";
const LEGACY_CHAT_STORAGE_KEY = "legal-ai-platform-chat-map-v2";
const CHAT_STORAGE_KEY = "legal-ai-platform-chat-sessions-v3";
const CHAT_GLOBAL_SCOPE_ID = 0;

export interface ChatSession {
    id: string;
    title: string;
    createdAt: string;
    updatedAt: string;
    messages: ChatMessage[];
}

interface StoredChatSessionsState {
    sessionsByCase: Record<number, ChatSession[]>;
    activeSessionIdByCase: Record<number, string>;
}

type RegisterPayload = {
    name: string;
    email: string;
    password: string;
    role: "lawyer" | "assistant" | "admin";
    tenantName?: string;
    inviteToken?: string;
};

type GlobalDocumentsSummary = {
    caseCount: number;
    totalDocuments: number;
    pendingDocuments: number;
    pendingRecordings: number;
    pendingImageBatches: number;
};

type GlobalCalendarSummary = {
    totalAppointments: number;
    upcomingAppointments: number;
    aiSuggestedAppointments: number;
    nextItems: CalendarAppointment[];
};

type WorkspaceMode = "chat" | "agent" | "legal_search";

type SendCaseMessageOptions = {
    workspaceMode?: WorkspaceMode;
    externalModeEnabled?: boolean;
    topK?: number;
    reasoningLevel?: "low" | "medium" | "high";
    workspaceDocumentId?: number | null;
    uploadedDocumentIds?: string[];
    uploadedFiles?: Array<{
        id: string;
        filename: string;
        mimeType: string;
        temporary?: boolean;
    }>;
    displayPrompt?: string;
};

type RoutedWorkspaceContextValue = {
    theme: ThemeMode;
    toggleTheme: () => void;
    language: UiLanguage;
    setLanguage: (language: UiLanguage) => void;
    locale: string;
    t: (key: string, fallback?: string) => string;
    token: string | null;
    user: User | null;
    clients: Client[];
    cases: CaseItem[];
    isAuthenticated: boolean;
    sessionReady: boolean;
    workspaceLoading: boolean;
    workspaceError: string | null;
    authBusy: boolean;
    authError: string | null;
    authMessage: string | null;
    selectedCaseId: number | null;
    selectedCase: CaseItem | null;
    caseContextLoading: boolean;
    caseContextError: string | null;
    documents: DocumentItem[];
    recordings: VoiceRecording[];
    imageBatches: ImageDocumentBatch[];
    calendarAppointments: CalendarAppointment[];
    consultations: ConsultationRequest[];
    uploadingPdf: boolean;
    uploadingAudio: boolean;
    uploadingImages: boolean;
    copilotLoading: boolean;
    stopCopilotRequest: () => void;
    login: (email: string, password: string) => Promise<boolean>;
    register: (payload: RegisterPayload) => Promise<boolean>;
    logout: () => void;
    refreshWorkspace: () => Promise<void>;
    setSelectedCaseId: (caseId: number | null) => void;
    loadCaseContext: (caseId: number) => Promise<void>;
    uploadPdf: (caseId: number, file: File) => Promise<void>;
    uploadAudio: (caseId: number, file: File) => Promise<void>;
    uploadImageBatch: (caseId: number, files: File[]) => Promise<void>;
    getSessionsForCase: (caseId: number) => ChatSession[];
    getActiveSessionId: (caseId: number) => string | null;
    getActiveMessages: (caseId: number) => ChatMessage[];
    createChatSession: (caseId: number, seedPrompt?: string) => string;
    selectChatSession: (caseId: number, sessionId: string) => void;
    removeChatSession: (caseId: number, sessionId: string) => void;
    sendCaseMessage: (caseId: number, prompt: string, options?: SendCaseMessageOptions) => Promise<void>;
    loadGlobalDocumentsSummary: () => Promise<GlobalDocumentsSummary>;
    loadGlobalCalendarSummary: () => Promise<GlobalCalendarSummary>;
};

const RoutedWorkspaceContext = createContext<RoutedWorkspaceContextValue | null>(null);

function generateId() {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
        return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function truncateText(value: string, limit: number) {
    const trimmed = value.trim();
    if (!trimmed) return "";
    if (trimmed.length <= limit) return trimmed;
    return `${trimmed.slice(0, Math.max(0, limit - 1)).trim()}...`;
}

function normalizeArray(value: unknown) {
    return Array.isArray(value) ? value : [];
}

function normalizeStoredMessage(message: Partial<ChatMessage> | null | undefined): ChatMessage {
    const meta = message && typeof message.meta === "object" && message.meta ? message.meta : {};
    const rawAnswer = typeof meta.rawAnswer === "string" ? meta.rawAnswer : null;
    const role = message?.role === "assistant" || message?.role === "user" ? message.role : "assistant";
    const content = String(message?.content || rawAnswer || "");
    const normalized: ChatMessage = {
        id: String(message?.id || generateId()),
        role,
        content,
        timestamp: String(message?.timestamp || new Date().toISOString()),
        meta: {
            ...meta,
            sources: normalizeArray(meta.sources),
            citations: normalizeArray(meta.citations),
            executionTrace: normalizeArray(meta.executionTrace),
            steps: normalizeArray(meta.steps),
            savedAssetIds: normalizeArray(meta.savedAssetIds),
            rawAnswer,
        },
    };

    if (normalized.role === "assistant" && rawAnswer && normalized.content !== rawAnswer) {
        return {
            ...normalized,
            content: rawAnswer,
        };
    }
    return normalized;
}

function buildChatSessionTitle(messages: ChatMessage[], fallback = "New chat"): string {
    const firstUserMessage = messages.find((message) => message.role === "user")?.content || "";
    return truncateText(firstUserMessage, 52) || fallback;
}

function normalizeStoredSession(rawSession: Partial<ChatSession> | null | undefined): ChatSession | null {
    if (!rawSession || !Array.isArray(rawSession.messages)) {
        return null;
    }

    const messages = rawSession.messages.map(normalizeStoredMessage);
    const createdAt = rawSession.createdAt || messages[0]?.timestamp || new Date().toISOString();
    const updatedAt = rawSession.updatedAt || messages[messages.length - 1]?.timestamp || createdAt;

    return {
        id: rawSession.id || generateId(),
        title: rawSession.title || buildChatSessionTitle(messages),
        createdAt,
        updatedAt,
        messages,
    };
}

function parseStoredChatState(): StoredChatSessionsState {
    try {
        const raw = localStorage.getItem(CHAT_STORAGE_KEY);
        if (raw) {
            const parsed = JSON.parse(raw) as Partial<StoredChatSessionsState>;
            const sessionsByCase: Record<number, ChatSession[]> = {};
            const activeSessionIdByCase: Record<number, string> = {};

            Object.entries(parsed.sessionsByCase || {}).forEach(([key, value]) => {
                const numeric = Number(key);
                if (Number.isNaN(numeric) || !Array.isArray(value)) return;
                const sessions = value
                    .map((session) => normalizeStoredSession(session))
                    .filter((session): session is ChatSession => Boolean(session));
                sessionsByCase[numeric] = sessions;
            });

            Object.entries(parsed.activeSessionIdByCase || {}).forEach(([key, value]) => {
                const numeric = Number(key);
                if (!Number.isNaN(numeric) && typeof value === "string" && value.trim()) {
                    activeSessionIdByCase[numeric] = value;
                }
            });

            return { sessionsByCase, activeSessionIdByCase };
        }

        const legacyRaw = localStorage.getItem(LEGACY_CHAT_STORAGE_KEY);
        if (!legacyRaw) {
            return { sessionsByCase: {}, activeSessionIdByCase: {} };
        }

        const parsed = JSON.parse(legacyRaw) as Record<string, ChatMessage[]>;
        const sessionsByCase: Record<number, ChatSession[]> = {};
        const activeSessionIdByCase: Record<number, string> = {};

        Object.entries(parsed).forEach(([key, value]) => {
            const numeric = Number(key);
            if (!Number.isNaN(numeric) && Array.isArray(value)) {
                const messages = value.map(normalizeStoredMessage);
                const createdAt = messages[0]?.timestamp || new Date().toISOString();
                const updatedAt = messages[messages.length - 1]?.timestamp || createdAt;
                const sessionId = generateId();
                sessionsByCase[numeric] = [{
                    id: sessionId,
                    title: buildChatSessionTitle(messages),
                    createdAt,
                    updatedAt,
                    messages,
                }];
                activeSessionIdByCase[numeric] = sessionId;
            }
        });

        return { sessionsByCase, activeSessionIdByCase };
    } catch {
        return { sessionsByCase: {}, activeSessionIdByCase: {} };
    }
}

function createMessage(role: "user" | "assistant", content: string, meta?: ChatMessage["meta"]): ChatMessage {
    return {
        id: generateId(),
        role,
        content,
        timestamp: new Date().toISOString(),
        meta,
    };
}

function normalizeError(caught: unknown, fallback: string) {
    if (caught instanceof Error && caught.message.trim()) {
        return caught.message;
    }
    return fallback;
}

function createAssistantMessage(response: CopilotResponse): ChatMessage {
    return createMessage("assistant", response.answer || response.message, {
        parsedIntent: response.parsed_intent,
        confidence: response.confidence,
        fallbackReason: response.fallback_reason,
        actionCategory: response.action_category,
        actionStatus: response.action_status,
        permissionDenied: response.permission_denied,
        steps: response.steps,
        structuredResult: response.structured_result,
        trustPanel: response.trust_panel,
        sources: normalizeArray(response.sources),
        citations: normalizeArray(response.citations),
        executionTrace: normalizeArray(response.execution_trace),
        cache: response.cache,
        jobId: response.job_id,
        caseSnapshotVersion: response.case_snapshot_version,
        artifact: response.artifact,
        jurisdiction: response.jurisdiction,
        reasoningResult: response.reasoning_result,
        openEditor: response.open_editor,
        draftDocument: response.draft_document,
        rawAnswer: response.answer,
        aiInsight: response.ai_insight,
    });
}

export function RoutedWorkspaceProvider({ children }: { children: ReactNode }) {
    const [theme, setTheme] = useState<ThemeMode>(() => {
        const stored = localStorage.getItem(THEME_STORAGE_KEY);
        return stored === "dark" ? "dark" : "light";
    });
    const [language, setLanguageState] = useState<UiLanguage>(() => {
        const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
        if (stored === "ar" || stored === "de" || stored === "en") {
            return stored;
        }
        return "en";
    });
    const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
    const [user, setUser] = useState<User | null>(null);
    const [clients, setClients] = useState<Client[]>([]);
    const [cases, setCases] = useState<CaseItem[]>([]);
    const [workspaceLoading, setWorkspaceLoading] = useState(false);
    const [workspaceError, setWorkspaceError] = useState<string | null>(null);
    const [sessionReady, setSessionReady] = useState(false);

    const [authBusy, setAuthBusy] = useState(false);
    const [authError, setAuthError] = useState<string | null>(null);
    const [authMessage, setAuthMessage] = useState<string | null>(null);

    const [selectedCaseId, setSelectedCaseIdState] = useState<number | null>(null);
    const [caseContextLoading, setCaseContextLoading] = useState(false);
    const [caseContextError, setCaseContextError] = useState<string | null>(null);
    const [documents, setDocuments] = useState<DocumentItem[]>([]);
    const [recordings, setRecordings] = useState<VoiceRecording[]>([]);
    const [imageBatches, setImageBatches] = useState<ImageDocumentBatch[]>([]);
    const [calendarAppointments, setCalendarAppointments] = useState<CalendarAppointment[]>([]);
    const [consultations, setConsultations] = useState<ConsultationRequest[]>([]);

    const [chatState, setChatState] = useState<StoredChatSessionsState>(() => parseStoredChatState());
    const [copilotLoading, setCopilotLoading] = useState(false);
    const copilotAbortRef = useRef<AbortController | null>(null);

    const [uploadingPdf, setUploadingPdf] = useState(false);
    const [uploadingAudio, setUploadingAudio] = useState(false);
    const [uploadingImages, setUploadingImages] = useState(false);

    const selectedCase = useMemo(
        () => (selectedCaseId ? cases.find((item) => item.id === selectedCaseId) || null : null),
        [cases, selectedCaseId]
    );

    const isAuthenticated = Boolean(token);
    const locale = language === "de" ? "de-DE" : language === "ar" ? "ar-TN" : "en-US";
    const t = useCallback((key: string, fallback?: string) => translateRouted(language, key, fallback), [language]);

    const toggleTheme = useCallback(() => {
        setTheme((current) => (current === "dark" ? "light" : "dark"));
    }, []);

    const setLanguage = useCallback((value: UiLanguage) => {
        setLanguageState(value);
    }, []);

    useEffect(() => {
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem(THEME_STORAGE_KEY, theme);
    }, [theme]);

    useEffect(() => {
        document.documentElement.lang = language;
        document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
        localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    }, [language]);

    useEffect(() => {
        const compacted = persistChatStateToLocalStorage(CHAT_STORAGE_KEY, chatState);
        if (compacted) {
            setChatState(compacted);
        }
    }, [chatState]);

    const refreshWorkspace = useCallback(async () => {
        if (!token) {
            return;
        }

        setWorkspaceLoading(true);
        setWorkspaceError(null);
        try {
            const [profile, clientRows, caseRows] = await Promise.all([
                workspaceApi.me(token),
                workspaceApi.listClients(token),
                workspaceApi.listCases(token),
            ]);

            setUser(profile);
            setClients(clientRows);
            setCases(caseRows);

            if (!selectedCaseId && caseRows.length > 0) {
                setSelectedCaseIdState(caseRows[0].id);
            }
        } catch (caught) {
            const message = normalizeError(caught, "Unable to load workspace session.");
            setWorkspaceError(message);
            localStorage.removeItem(TOKEN_STORAGE_KEY);
            setToken(null);
            setUser(null);
            setClients([]);
            setCases([]);
            setSelectedCaseIdState(null);
        } finally {
            setWorkspaceLoading(false);
        }
    }, [selectedCaseId, token]);

    useEffect(() => {
        let cancelled = false;

        async function bootstrap() {
            if (!token) {
                if (cancelled) return;
                setUser(null);
                setClients([]);
                setCases([]);
                setSelectedCaseIdState(null);
                setDocuments([]);
                setRecordings([]);
                setImageBatches([]);
                setCalendarAppointments([]);
                setConsultations([]);
                setSessionReady(true);
                return;
            }

            setSessionReady(false);
            await refreshWorkspace();
            if (!cancelled) {
                setSessionReady(true);
            }
        }

        void bootstrap();
        return () => {
            cancelled = true;
        };
    }, [token, refreshWorkspace]);

    const loadCaseContext = useCallback(async (caseId: number) => {
        if (!token || !caseId) return;

        setCaseContextLoading(true);
        setCaseContextError(null);

        try {
            const [docRows, recordingRows, imageBatchRows, calendarRows, consultationRows] = await Promise.all([
                workspaceApi.listCaseDocuments(token, caseId),
                workspaceApi.listVoiceRecordings(token, caseId),
                workspaceApi.listCaseImageBatches(token, caseId),
                workspaceApi.listCalendarAppointments(token, caseId),
                workspaceApi.listConsultationRequests(token, caseId),
            ]);

            setDocuments(docRows);
            setRecordings(recordingRows);
            setImageBatches(imageBatchRows);
            setCalendarAppointments(calendarRows);
            setConsultations(consultationRows);
        } catch (caught) {
            setCaseContextError(normalizeError(caught, "Unable to load case context."));
        } finally {
            setCaseContextLoading(false);
        }
    }, [token]);

    useEffect(() => {
        if (!token || !selectedCaseId) {
            return;
        }
        void loadCaseContext(selectedCaseId);
    }, [loadCaseContext, selectedCaseId, token]);

    const login = useCallback(async (email: string, password: string) => {
        setAuthBusy(true);
        setAuthError(null);
        setAuthMessage(null);
        try {
            const result = await workspaceApi.login(email, password);
            localStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
            setToken(result.access_token);
            return true;
        } catch (caught) {
            setAuthError(normalizeError(caught, t("authFailed", "Authentication failed.")));
            return false;
        } finally {
            setAuthBusy(false);
        }
    }, [t]);

    const register = useCallback(async (payload: RegisterPayload) => {
        setAuthBusy(true);
        setAuthError(null);
        setAuthMessage(null);
        try {
            await workspaceApi.register({
                name: payload.name,
                email: payload.email,
                password: payload.password,
                role: payload.role,
                tenant_name: payload.tenantName || undefined,
                invite_token: payload.inviteToken || undefined,
            });
            setAuthMessage(t("accountCreated", "Account created. Sign in to continue."));
            return true;
        } catch (caught) {
            setAuthError(normalizeError(caught, t("registrationFailed", "Registration failed.")));
            return false;
        } finally {
            setAuthBusy(false);
        }
    }, [t]);

    const logout = useCallback(() => {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setToken(null);
        setUser(null);
        setClients([]);
        setCases([]);
        setSelectedCaseIdState(null);
        setDocuments([]);
        setRecordings([]);
        setImageBatches([]);
        setCalendarAppointments([]);
        setConsultations([]);
        setWorkspaceError(null);
        setAuthError(null);
        setAuthMessage(null);
    }, []);

    const setSelectedCaseId = useCallback((caseId: number | null) => {
        setSelectedCaseIdState(caseId);
    }, []);

    const createChatSession = useCallback((caseId: number, seedPrompt?: string) => {
        const now = new Date().toISOString();
        const sessionId = generateId();
        const session: ChatSession = {
            id: sessionId,
            title: truncateText((seedPrompt || "").trim(), 52) || "New chat",
            createdAt: now,
            updatedAt: now,
            messages: [],
        };

        setChatState((current) => ({
            sessionsByCase: {
                ...current.sessionsByCase,
                [caseId]: [session, ...(current.sessionsByCase[caseId] || [])],
            },
            activeSessionIdByCase: {
                ...current.activeSessionIdByCase,
                [caseId]: sessionId,
            },
        }));

        return sessionId;
    }, []);

    const selectChatSession = useCallback((caseId: number, sessionId: string) => {
        setChatState((current) => ({
            sessionsByCase: current.sessionsByCase,
            activeSessionIdByCase: {
                ...current.activeSessionIdByCase,
                [caseId]: sessionId,
            },
        }));
    }, []);

    const removeChatSession = useCallback((caseId: number, sessionId: string) => {
        setChatState((current) => {
            const sessions = current.sessionsByCase[caseId] || [];
            const nextSessions = sessions.filter((session) => session.id !== sessionId);
            const nextActiveSessionByCase = { ...current.activeSessionIdByCase };

            if (nextActiveSessionByCase[caseId] === sessionId) {
                const fallbackSessionId = nextSessions
                    .slice()
                    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))[0]?.id;
                if (fallbackSessionId) {
                    nextActiveSessionByCase[caseId] = fallbackSessionId;
                } else {
                    delete nextActiveSessionByCase[caseId];
                }
            }

            return {
                sessionsByCase: {
                    ...current.sessionsByCase,
                    [caseId]: nextSessions,
                },
                activeSessionIdByCase: nextActiveSessionByCase,
            };
        });
    }, []);

    const getSessionsForCase = useCallback(
        (caseId: number) => chatState.sessionsByCase[caseId] || [],
        [chatState.sessionsByCase]
    );

    const getActiveSessionId = useCallback(
        (caseId: number) => {
            const active = chatState.activeSessionIdByCase[caseId];
            if (active && (chatState.sessionsByCase[caseId] || []).some((session) => session.id === active)) {
                return active;
            }
            const fallback = (chatState.sessionsByCase[caseId] || [])
                .slice()
                .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))[0]?.id;
            return fallback || null;
        },
        [chatState.activeSessionIdByCase, chatState.sessionsByCase]
    );

    const getActiveMessages = useCallback((caseId: number) => {
        const sessionId = getActiveSessionId(caseId);
        if (!sessionId) return [];
        const session = (chatState.sessionsByCase[caseId] || []).find((item) => item.id === sessionId);
        return session?.messages || [];
    }, [chatState.sessionsByCase, getActiveSessionId]);

    const appendMessage = useCallback((caseId: number, sessionId: string, message: ChatMessage) => {
        setChatState((current) => {
            const sessions = current.sessionsByCase[caseId] || [];
            const nextSessions = sessions.map((session) => {
                if (session.id !== sessionId) return session;
                const nextMessages = [...session.messages, message];
                return {
                    ...session,
                    title:
                        session.messages.length === 0 && message.role === "user"
                            ? truncateText(message.content, 52) || "New chat"
                            : session.title,
                    updatedAt: message.timestamp,
                    messages: nextMessages,
                };
            });

            return {
                sessionsByCase: {
                    ...current.sessionsByCase,
                    [caseId]: nextSessions,
                },
                activeSessionIdByCase: {
                    ...current.activeSessionIdByCase,
                    [caseId]: sessionId,
                },
            };
        });
    }, []);

    const stopCopilotRequest = useCallback(() => {
        copilotAbortRef.current?.abort();
        copilotAbortRef.current = null;
        setCopilotLoading(false);
    }, []);

    const sendCaseMessage = useCallback(async (caseId: number, prompt: string, options?: SendCaseMessageOptions) => {
        if (!token || caseId < 0) return;
        const trimmed = prompt.trim();
        const displayPrompt = (options?.displayPrompt || trimmed).trim();
        if (!trimmed || !displayPrompt) return;

        const mode = options?.workspaceMode || "chat";
        const requestMode = mode === "legal_search" ? "legal_search" : "default";
        const topK = options?.topK && options.topK > 0 ? options.topK : 6;
        const reasoningLevel = options?.reasoningLevel ?? "medium";
        const useExternalResearch = Boolean(options?.externalModeEnabled) || mode === "legal_search";
        const workspaceDocumentId = options?.workspaceDocumentId ?? null;
        const uploadedDocumentIds = options?.uploadedDocumentIds || [];
        const uploadedFiles = options?.uploadedFiles || [];
        const workspaceCaseId = caseId > 0 ? caseId : null;

        const sessions = chatState.sessionsByCase[caseId] || [];
        const activeSessionId = getActiveSessionId(caseId);
        const sessionId = activeSessionId || createChatSession(caseId, displayPrompt);

        const cachedSession = sessions.find((item) => item.id === sessionId);
        const existingMessages = cachedSession?.messages || [];

        const userMessage = createMessage("user", displayPrompt, uploadedFiles.length ? {
            attachments: uploadedFiles.map((file) => ({
                clientId: file.id,
                name: file.filename,
                mimeType: file.mimeType,
            })),
        } : undefined);
        appendMessage(caseId, sessionId, userMessage);

        const abortController = new AbortController();
        copilotAbortRef.current = abortController;

        setCopilotLoading(true);
        try {
            const conversationHistory = [...existingMessages, userMessage]
                .slice(-12)
                .map((message) => ({
                    role: message.role,
                    content: message.content,
                    parsed_intent: message.meta?.parsedIntent,
                    case_id: workspaceCaseId,
                    document_id: null,
                }));
            const response = uploadedDocumentIds.length
                ? await workspaceApi.askWithFiles(token, trimmed, {
                    uploadedDocumentIds,
                    caseId: workspaceCaseId,
                    chatSessionId: sessionId,
                    topK,
                    reasoningLevel,
                    useExternalResearch,
                    mode: requestMode,
                    legalSearchMultilingualOutput: mode === "legal_search",
                    agentMode: mode === "agent",
                    conversationHistory,
                    signal: abortController.signal,
                })
                : await workspaceApi.copilot(token, trimmed, {
                    topK,
                    reasoningLevel,
                    workspaceCaseId,
                    workspaceDocumentId,
                    useExternalResearch,
                    mode: requestMode,
                    legalSearchMultilingualOutput: mode === "legal_search",
                    agentMode: mode === "agent",
                    conversationHistory,
                    signal: abortController.signal,
                });

            appendMessage(caseId, sessionId, createAssistantMessage(response));
        } catch (caught) {
            if (caught instanceof Error && caught.message === "Request stopped.") {
                return;
            }
            appendMessage(
                caseId,
                sessionId,
                createMessage("assistant", normalizeError(caught, t("copilotFailed", "Copilot request failed.")))
            );
        } finally {
            if (copilotAbortRef.current === abortController) {
                copilotAbortRef.current = null;
            }
            setCopilotLoading(false);
        }
    }, [appendMessage, chatState.sessionsByCase, createChatSession, getActiveSessionId, t, token]);

    const uploadPdf = useCallback(async (caseId: number, file: File) => {
        if (!token) return;
        setUploadingPdf(true);
        try {
            await workspaceApi.uploadDocument(token, caseId, file);
            await loadCaseContext(caseId);
        } finally {
            setUploadingPdf(false);
        }
    }, [loadCaseContext, token]);

    const uploadAudio = useCallback(async (caseId: number, file: File) => {
        if (!token) return;
        setUploadingAudio(true);
        try {
            await workspaceApi.uploadVoiceRecording(token, caseId, file);
            await loadCaseContext(caseId);
        } finally {
            setUploadingAudio(false);
        }
    }, [loadCaseContext, token]);

    const uploadImageBatch = useCallback(async (caseId: number, files: File[]) => {
        if (!token || !files.length) return;
        setUploadingImages(true);
        try {
            await workspaceApi.uploadImageBatch(token, caseId, files, {
                generateDocument: true,
                runAuthenticityCheck: true,
            });
            await loadCaseContext(caseId);
        } finally {
            setUploadingImages(false);
        }
    }, [loadCaseContext, token]);

    const loadGlobalDocumentsSummary = useCallback(async (): Promise<GlobalDocumentsSummary> => {
        if (!token) {
            return {
                caseCount: 0,
                totalDocuments: 0,
                pendingDocuments: 0,
                pendingRecordings: 0,
                pendingImageBatches: 0,
            };
        }

        const caseRows = cases;
        const records = await Promise.all(caseRows.map(async (item) => {
            const [docs, voices, batches] = await Promise.all([
                workspaceApi.listCaseDocuments(token, item.id).catch(() => [] as DocumentItem[]),
                workspaceApi.listVoiceRecordings(token, item.id).catch(() => [] as VoiceRecording[]),
                workspaceApi.listCaseImageBatches(token, item.id).catch(() => [] as ImageDocumentBatch[]),
            ]);

            return {
                docs,
                voices,
                batches,
            };
        }));

        const totalDocuments = records.reduce((total, item) => total + item.docs.length, 0);
        const pendingDocuments = records.reduce(
            (total, item) => total + item.docs.filter((doc) => doc.processing_status !== "completed").length,
            0
        );
        const pendingRecordings = records.reduce(
            (total, item) => total + item.voices.filter((voice) => voice.transcription_status !== "completed").length,
            0
        );
        const pendingImageBatches = records.reduce(
            (total, item) => total + item.batches.filter((batch) => ["queued", "processing"].includes(batch.status)).length,
            0
        );

        return {
            caseCount: caseRows.length,
            totalDocuments,
            pendingDocuments,
            pendingRecordings,
            pendingImageBatches,
        };
    }, [cases, token]);

    const loadGlobalCalendarSummary = useCallback(async (): Promise<GlobalCalendarSummary> => {
        if (!token) {
            return {
                totalAppointments: 0,
                upcomingAppointments: 0,
                aiSuggestedAppointments: 0,
                nextItems: [],
            };
        }

        const items = await workspaceApi.listMyCalendarAppointments(token);
        const now = Date.now();
        const sorted = items.slice().sort((left, right) => left.scheduled_at.localeCompare(right.scheduled_at));

        return {
            totalAppointments: items.length,
            upcomingAppointments: items.filter((item) => new Date(item.scheduled_at).getTime() >= now).length,
            aiSuggestedAppointments: items.filter((item) => item.is_ai_suggested).length,
            nextItems: sorted.slice(0, 5),
        };
    }, [token]);

    const value = useMemo<RoutedWorkspaceContextValue>(() => ({
        theme,
        toggleTheme,
        language,
        setLanguage,
        locale,
        t,
        token,
        user,
        clients,
        cases,
        isAuthenticated,
        sessionReady,
        workspaceLoading,
        workspaceError,
        authBusy,
        authError,
        authMessage,
        selectedCaseId,
        selectedCase,
        caseContextLoading,
        caseContextError,
        documents,
        recordings,
        imageBatches,
        calendarAppointments,
        consultations,
        uploadingPdf,
        uploadingAudio,
        uploadingImages,
        copilotLoading,
        stopCopilotRequest,
        login,
        register,
        logout,
        refreshWorkspace,
        setSelectedCaseId,
        loadCaseContext,
        uploadPdf,
        uploadAudio,
        uploadImageBatch,
        getSessionsForCase,
        getActiveSessionId,
        getActiveMessages,
        createChatSession,
        selectChatSession,
        removeChatSession,
        sendCaseMessage,
        loadGlobalDocumentsSummary,
        loadGlobalCalendarSummary,
    }), [
        theme,
        toggleTheme,
        language,
        setLanguage,
        locale,
        t,
        token,
        user,
        clients,
        cases,
        isAuthenticated,
        sessionReady,
        workspaceLoading,
        workspaceError,
        authBusy,
        authError,
        authMessage,
        selectedCaseId,
        selectedCase,
        caseContextLoading,
        caseContextError,
        documents,
        recordings,
        imageBatches,
        calendarAppointments,
        consultations,
        uploadingPdf,
        uploadingAudio,
        uploadingImages,
        copilotLoading,
        stopCopilotRequest,
        login,
        register,
        logout,
        refreshWorkspace,
        setSelectedCaseId,
        loadCaseContext,
        uploadPdf,
        uploadAudio,
        uploadImageBatch,
        getSessionsForCase,
        getActiveSessionId,
        getActiveMessages,
        createChatSession,
        selectChatSession,
        removeChatSession,
        sendCaseMessage,
        loadGlobalDocumentsSummary,
        loadGlobalCalendarSummary,
    ]);

    return <RoutedWorkspaceContext.Provider value={value}>{children}</RoutedWorkspaceContext.Provider>;
}

export function useRoutedWorkspace() {
    const context = useContext(RoutedWorkspaceContext);
    if (!context) {
        throw new Error("useRoutedWorkspace must be used inside RoutedWorkspaceProvider");
    }
    return context;
}
