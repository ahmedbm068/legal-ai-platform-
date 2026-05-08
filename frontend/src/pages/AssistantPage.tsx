import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ChatMessageBubble, { type MessageFeedbackState } from "../components/ChatMessageBubble";
import ExecutionTracePanel from "../components/ExecutionTracePanel";
import LegalEditorPanel from "../components/LegalEditorPanel";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { saveEditorDraftSeed } from "../editorDraftSeed";
import type { ChatMessage, DraftDocument, DraftDocumentPayload, FeedbackRootCause } from "../types";
import { workspaceApi } from "../workspaceApi";

type WorkspaceMode = "chat" | "agent" | "legal_search";
type ReasoningLevel = "low" | "medium" | "high" | "deep";
type OutputLanguage = "auto" | "fr" | "ar" | "en";
type AssistantMode = "chat" | "agent" | "legal_search" | "external";
type AttachmentStatus = "ready" | "uploading" | "uploaded" | "error";
type DraftDocumentType = "Email" | "Client update letter" | "Demand letter" | "Legal memo" | "Strategy note" | "Contract clause" | "General draft";

type PendingAssistantFile = {
    id: string;
    file: File;
    status: AttachmentStatus;
    error?: string | null;
    uploadedId?: string | null;
    temporary?: boolean;
};

type AssistantDraftDocument = {
    title: string;
    documentType: DraftDocumentType;
    content: string;
    updatedAt: string;
    caseId: number | null;
};

const REASONING_TOP_K: Record<ReasoningLevel, number> = {
    low: 4,
    medium: 6,
    high: 8,
    deep: 8,
};

type BrowserSpeechRecognition = {
    lang: string;
    continuous: boolean;
    interimResults: boolean;
    maxAlternatives: number;
    onresult: ((event: {
        resultIndex: number;
        results: ArrayLike<ArrayLike<{ transcript?: string }> & { isFinal?: boolean }>;
    }) => void) | null;
    onerror: ((event: { error?: string }) => void) | null;
    onend: (() => void) | null;
    start: () => void;
    stop: () => void;
    abort: () => void;
};

declare global {
    interface Window {
        SpeechRecognition?: new () => BrowserSpeechRecognition;
        webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
    }
}

const ASSISTANT_MODES: Array<{ id: AssistantMode; label: string; description: string }> = [
    { id: "chat", label: "Chat Mode", description: "Fast legal discussion" },
    { id: "agent", label: "Agent Mode", description: "Step-by-step execution" },
    { id: "legal_search", label: "Legal Search Mode", description: "Source-grounded legal answers" },
    { id: "external", label: "External Mode", description: "Web-enhanced legal research" },
];

function parseCaseId(value?: string) {
    const parsed = Number(value);
    if (!value || Number.isNaN(parsed) || parsed <= 0) return null;
    return parsed;
}

function formatTimestamp(value: string, locale: string) {
    return new Intl.DateTimeFormat(locale, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(new Date(value));
}

function workspaceModeFromAssistantMode(mode: AssistantMode): WorkspaceMode {
    if (mode === "agent") return "agent";
    if (mode === "legal_search" || mode === "external") return "legal_search";
    return "chat";
}

function caseJurisdictionLabel(value?: string | null) {
    if (value === "tunisia") return "Tunisia";
    if (value === "germany") return "Germany";
    return value || "Unconfirmed";
}

function groundingLabel(state: "grounded" | "partial" | "not-grounded") {
    if (state === "grounded") return "Grounded";
    if (state === "partial") return "Partial";
    return "Not grounded";
}

function formatFileSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isSupportedAssistantFile(file: File) {
    const extension = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
    const mimeType = (file.type || "").toLowerCase();
    return [".pdf", ".txt", ".md"].includes(extension)
        || ["application/pdf", "text/plain", "text/markdown", "text/x-markdown"].includes(mimeType);
}

function isDraftIntent(message: string): boolean {
    const text = message.toLowerCase().replace(/\s+/g, " ").trim();
    if (!text) return false;
    if (/^(summari[sz]e|analy[sz]e|explain|list|identify|compare|what is|what are|what happened|give me legal analysis)\b/.test(text)) {
        return false;
    }
    return /\b(draft|write|prepare)\b/.test(text)
        || /\bgenerate\s+(a\s+)?(letter|email|memo|document|response)\b/.test(text)
        || /\bcreate\s+(an?\s+)?(email|letter|memo|response|client update)\b/.test(text)
        || /\b(demand letter|client update|legal memo|response letter|strategy note|internal note|contract clause|summary email)\b/.test(text);
}

function isDraftRevisionIntent(message: string): boolean {
    const text = message.toLowerCase().replace(/\s+/g, " ").trim();
    if (!text) return false;
    if (/^(what|why|when|where|who|summari[sz]e|analy[sz]e|explain|list|identify|compare)\b/.test(text)) return false;
    return /\b(make|shorten|lengthen|add|remove|rewrite|revise|edit|translate|formal|professional|client-friendly|stronger|softer|tone|paragraph|clause|section)\b/.test(text);
}

function detectDraftDocumentType(message: string): DraftDocumentType {
    const text = message.toLowerCase();
    if (text.includes("demand letter")) return "Demand letter";
    if (text.includes("client update")) return "Client update letter";
    if (text.includes("legal memo") || text.includes("memorandum")) return "Legal memo";
    if (text.includes("strategy note")) return "Strategy note";
    if (text.includes("contract clause") || text.includes("clause")) return "Contract clause";
    if (text.includes("email")) return "Email";
    return "General draft";
}

function draftTitleFromType(documentType: DraftDocumentType, caseTitle?: string | null) {
    const prefix = caseTitle ? `${caseTitle} - ` : "";
    return `${prefix}${documentType}`;
}

function cleanDraftContent(value: string) {
    return value
        .replace(/^I drafted it and opened it in the editor\.?\s*/i, "")
        .replace(/^Here(?:'s| is) (?:a|the) draft[:.\s-]*/i, "")
        .trim();
}

function filenameSafe(value: string) {
    return (value || "assistant-draft").replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 120) || "assistant-draft";
}

function TypingIndicator() {
    return (
        <div className="typing-indicator legal-typing-state minimal-typing-state">
            <span />
            <span />
            <span />
            <em>Checking sources...</em>
        </div>
    );
}

export default function AssistantPage() {
    const navigate = useNavigate();
    const params = useParams();
    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);

    const {
        token,
        user,
        selectedCaseId,
        setSelectedCaseId,
        selectedCase,
        getSessionsForCase,
        getActiveSessionId,
        getActiveMessages,
        createChatSession,
        selectChatSession,
        removeChatSession,
        sendCaseMessage,
        loadCaseContext,
        copilotLoading,
        stopCopilotRequest,
        clients,
        language,
        locale,
        t,
    } = useRoutedWorkspace();

    const [draft, setDraft] = useState("");
    const [notice, setNotice] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [traceMessage, setTraceMessage] = useState<ChatMessage | null>(null);
    const [historySidebarOpen, setHistorySidebarOpen] = useState(false);
    const [historySearch, setHistorySearch] = useState("");
    const [assistantMode, setAssistantMode] = useState<AssistantMode>("chat");
    const [pendingFiles, setPendingFiles] = useState<PendingAssistantFile[]>([]);
    const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("chat");
    const [reasoningLevel, setReasoningLevel] = useState<ReasoningLevel>(() => {
        try {
            const stored = window.localStorage.getItem("lai.reasoningLevel");
            if (stored === "low" || stored === "medium" || stored === "high" || stored === "deep") return stored;
        } catch { /* localStorage unavailable */ }
        return "medium";
    });
    const [outputLanguage, setOutputLanguage] = useState<OutputLanguage>(() => {
        try {
            const stored = window.localStorage.getItem("lai.outputLanguage");
            if (stored === "auto" || stored === "fr" || stored === "ar" || stored === "en") return stored;
        } catch { /* localStorage unavailable */ }
        return "auto";
    });
    const [externalModeEnabled, setExternalModeEnabled] = useState(false);
    const [optimizingPrompt, setOptimizingPrompt] = useState(false);
    const [composerRecording, setComposerRecording] = useState(false);
    const [dragActive, setDragActive] = useState(false);
    const [draftDocument, setDraftDocument] = useState<AssistantDraftDocument | null>(null);
    const [draftPanelOpen, setDraftPanelOpen] = useState(false);
    const [editorDraftPayload, setEditorDraftPayload] = useState<DraftDocumentPayload | null>(null);
    const [editorFocusMode, setEditorFocusMode] = useState(false);
    const [chatFeedback, setChatFeedback] = useState<Record<string, MessageFeedbackState>>({});
    const messageEndRef = useRef<HTMLDivElement | null>(null);
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const dragDepthRef = useRef(0);
    const pendingDraftRef = useRef<{ mode: "create" | "revision"; documentType: DraftDocumentType; title: string } | null>(null);
    const openedEditorMessageIdRef = useRef<string | null>(null);
    const composerRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
    const composerDictationSeedRef = useRef("");
    const composerDictationFinalRef = useRef("");
    const activeCaseId = routeCaseId ?? selectedCaseId;
    const activeChatScopeId = activeCaseId ?? 0;

    useEffect(() => {
        if (routeCaseId && routeCaseId !== selectedCaseId) {
            setSelectedCaseId(routeCaseId);
        }
    }, [routeCaseId, selectedCaseId, setSelectedCaseId]);

    const sessions = useMemo(() => getSessionsForCase(activeChatScopeId), [activeChatScopeId, getSessionsForCase]);
    const activeSessionId = useMemo(() => getActiveSessionId(activeChatScopeId), [activeChatScopeId, getActiveSessionId]);
    const activeMessages = useMemo(() => getActiveMessages(activeChatScopeId), [activeChatScopeId, getActiveMessages]);
    const activeClient = useMemo(
        () => (selectedCase ? clients.find((client) => client.id === selectedCase.client_id) || null : null),
        [clients, selectedCase]
    );
    const latestAssistantMessage = useMemo(
        () => [...activeMessages].reverse().find((message) => message.role === "assistant") || null,
        [activeMessages]
    );
    const filteredSessions = useMemo(() => {
        const query = historySearch.trim().toLowerCase();
        if (!query) return sessions;
        return sessions.filter((session) =>
            `${session.title} ${session.messages.map((message) => message.content).join(" ")}`.toLowerCase().includes(query)
        );
    }, [historySearch, sessions]);

    const canSend = Boolean(token);
    const hasConversation = activeMessages.length > 0 || copilotLoading;
    const sourceCount = latestAssistantMessage?.meta?.sources?.length || latestAssistantMessage?.meta?.citations?.length || 0;
    const assistantGroundingState: "grounded" | "partial" | "not-grounded" = !activeCaseId
        ? "not-grounded"
        : sourceCount > 0
            ? "grounded"
            : assistantMode === "legal_search" || assistantMode === "external"
                ? "partial"
                : "not-grounded";
    const caseTitle = selectedCase?.title || t("generalAssistant", "General Assistant");
    const topbarCaseLabel = activeCaseId ? caseTitle : t("generalAssistant", "General Assistant");
    const compactModes = ASSISTANT_MODES;
    const composerPlaceholder = editorDraftPayload || draftPanelOpen
        ? t("draftRevisionPlaceholder", "Ask for a revision to this draft...")
        : assistantMode === "agent"
        ? t("agentPlaceholder", "Describe the action to review before execution...")
        : assistantMode === "legal_search"
            ? t("researchPlaceholder", "Ask a source-grounded legal question...")
            : assistantMode === "external"
                ? t("externalPlaceholder", "Ask for web-enhanced legal research...")
                : t("askPlaceholder", "Ask about your case, risks, deadlines, or draft something...");

    useEffect(() => {
        if (!activeCaseId) return;
        if (sessions.length === 0) {
            createChatSession(activeCaseId);
        }
    }, [activeCaseId, createChatSession, sessions.length]);

    useEffect(() => {
        messageEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }, [activeMessages, copilotLoading]);

    useEffect(() => {
        if (copilotLoading || !pendingDraftRef.current) return;
        const latestAssistant = [...activeMessages].reverse().find((message) => message.role === "assistant");
        if (!latestAssistant?.content.trim()) return;

        const pendingDraft = pendingDraftRef.current;
        pendingDraftRef.current = null;
        const nextContent = cleanDraftContent(latestAssistant.meta?.rawAnswer || latestAssistant.content);
        if (!nextContent) return;

        setDraftDocument((current) => ({
            title: current?.title || pendingDraft.title,
            documentType: pendingDraft.documentType,
            content: nextContent,
            updatedAt: new Date().toISOString(),
            caseId: activeCaseId,
        }));
        setDraftPanelOpen(false);
        setNotice(
            pendingDraft.mode === "revision"
                ? t("draftUpdatedNotice", "Draft updated. Use Edit under the assistant answer to open it in the Legal Editor.")
                : t("draftOpenedNotice", "Draft ready. Use Edit under the assistant answer to open it in the Legal Editor.")
        );
    }, [activeCaseId, activeMessages, copilotLoading, t]);

    useEffect(() => {
        if (copilotLoading) return;
        const latestAssistant = [...activeMessages].reverse().find((message) => message.role === "assistant");
        if (!latestAssistant?.meta?.openEditor || !latestAssistant.meta.draftDocument) return;
        if (openedEditorMessageIdRef.current === latestAssistant.id) return;
        openedEditorMessageIdRef.current = latestAssistant.id;
        setEditorDraftPayload(latestAssistant.meta.draftDocument);
        setDraftPanelOpen(false);
        setNotice(t("draftOpenedNotice", "I drafted it and opened it in the editor."));
    }, [activeMessages, copilotLoading, t]);

    useEffect(() => {
        return () => {
            if (composerRecognitionRef.current) {
                composerRecognitionRef.current.abort();
                composerRecognitionRef.current = null;
            }
        };
    }, []);

    function stopComposerRecording() {
        composerRecognitionRef.current?.abort();
        composerRecognitionRef.current = null;
        setComposerRecording(false);
    }

    async function startComposerRecording() {
        if (!token) return;
        if (composerRecognitionRef.current) {
            stopComposerRecording();
            return;
        }

        const RecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!RecognitionCtor) {
            setError(t("voiceUnsupported", "Voice dictation is not supported in this browser."));
            return;
        }

        try {
            setError(null);
            composerDictationSeedRef.current = draft.trim() ? `${draft.trim()} ` : "";
            composerDictationFinalRef.current = "";

            const recognition = new RecognitionCtor();
            recognition.lang = language === "de" ? "de-DE" : language === "ar" ? "ar-TN" : "en-US";
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.maxAlternatives = 1;

            recognition.onresult = (event) => {
                let finalTranscript = composerDictationFinalRef.current;
                let interimTranscript = "";

                for (let index = event.resultIndex; index < event.results.length; index += 1) {
                    const result = event.results[index];
                    const transcript = String(result?.[0]?.transcript || "").trim();
                    if (!transcript) continue;

                    if (result?.isFinal) finalTranscript = `${finalTranscript}${transcript} `;
                    else interimTranscript = `${interimTranscript}${transcript} `;
                }

                composerDictationFinalRef.current = finalTranscript;
                setDraft(`${composerDictationSeedRef.current}${finalTranscript}${interimTranscript}`.replace(/\s+/g, " ").trim());
            };

            recognition.onerror = (event) => {
                const errorCode = String(event?.error || "").trim().toLowerCase();
                setComposerRecording(false);
                composerRecognitionRef.current = null;
                if (errorCode && errorCode !== "aborted" && errorCode !== "no-speech") {
                    setError(t("voiceRecognitionFailed", "Unable to transcribe voice input."));
                }
            };
            recognition.onend = () => {
                setComposerRecording(false);
                composerRecognitionRef.current = null;
            };

            composerRecognitionRef.current = recognition;
            setComposerRecording(true);
            recognition.start();
        } catch {
            setComposerRecording(false);
            composerRecognitionRef.current = null;
            setError(t("voiceRecognitionFailed", "Unable to transcribe voice input."));
        }
    }

    function addPendingFiles(fileList: FileList | null) {
        const incoming = Array.from(fileList || []);
        if (!incoming.length) return;

        if (pendingFiles.length + incoming.length > 10) {
            setError(t("assistantUploadMaxFiles", "You can attach up to 10 files per message."));
            return;
        }

        const accepted: PendingAssistantFile[] = [];
        const rejected: string[] = [];
        incoming.forEach((file) => {
            if (!isSupportedAssistantFile(file)) {
                rejected.push(file.name);
                return;
            }
            accepted.push({
                id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
                file,
                status: "ready",
                error: null,
            });
        });

        if (accepted.length) {
            setPendingFiles((current) => [...current, ...accepted].slice(0, 10));
        }
        if (rejected.length) {
            setError(
                t("assistantUploadUnsupported", "Unsupported files: {files}. Upload PDF, TXT, or MD.")
                    .replace("{files}", rejected.join(", "))
            );
        } else {
            setError(null);
        }
    }

    function removePendingFile(fileId: string) {
        setPendingFiles((current) => current.filter((item) => item.id !== fileId));
    }

    function dragEventHasFiles(event: DragEvent<HTMLElement>) {
        return Array.from(event.dataTransfer?.types || []).includes("Files");
    }

    function handleComposerDragEnter(event: DragEvent<HTMLElement>) {
        if (!dragEventHasFiles(event)) return;
        event.preventDefault();
        dragDepthRef.current += 1;
        setDragActive(true);
    }

    function handleComposerDragOver(event: DragEvent<HTMLElement>) {
        if (!dragEventHasFiles(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        setDragActive(true);
    }

    function handleComposerDragLeave(event: DragEvent<HTMLElement>) {
        if (!dragEventHasFiles(event)) return;
        event.preventDefault();
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
        if (dragDepthRef.current === 0) setDragActive(false);
    }

    function handleComposerDrop(event: DragEvent<HTMLElement>) {
        if (!dragEventHasFiles(event)) return;
        event.preventDefault();
        dragDepthRef.current = 0;
        setDragActive(false);
        addPendingFiles(event.dataTransfer.files);
    }

    async function uploadPendingFiles(promptText: string, chatSessionId: string) {
        if (!token || !pendingFiles.length) return { uploadedIds: [] as string[], uploadedFiles: [] as PendingAssistantFile[] };

        setPendingFiles((current) => current.map((item) => ({ ...item, status: "uploading", error: null })));
        const response = await workspaceApi.uploadAssistantFiles(
            token,
            pendingFiles.map((item) => item.file),
            {
                caseId: activeCaseId,
                chatSessionId,
                message: promptText,
            }
        );

        const uploadedByName = new Map(response.files.map((item) => [item.filename, item]));
        const errorsByName = new Map(response.errors.map((item) => [item.filename, item]));
        const nextFiles = pendingFiles.map((item) => {
            const uploaded = uploadedByName.get(item.file.name);
            const failed = errorsByName.get(item.file.name);
            if (uploaded) {
                return {
                    ...item,
                    status: "uploaded" as AttachmentStatus,
                    uploadedId: uploaded.id,
                    temporary: uploaded.temporary,
                    error: null,
                };
            }
            return {
                ...item,
                status: "error" as AttachmentStatus,
                error: failed?.error || t("assistantUploadFailed", "Upload failed."),
            };
        });
        setPendingFiles(nextFiles);

        if (response.errors.length) {
            setError(response.errors.map((item) => `${item.filename}: ${item.error || "Upload failed"}`).join(" | "));
        }

        return {
            uploadedIds: response.uploaded_document_ids,
            uploadedFiles: nextFiles.filter((item) => item.status === "uploaded"),
        };
    }

    async function submitPrompt(promptText: string): Promise<boolean> {
        if (!canSend) {
            setError(t("loginRequired", "Sign in to use the assistant."));
            return false;
        }
        const outbound = promptText.trim();
        if (!outbound) return false;
        setError(null);
        setNotice(null);
        const draftRequest = isDraftIntent(outbound);
        const revisionRequest = Boolean(draftPanelOpen && draftDocument && isDraftRevisionIntent(outbound) && !draftRequest);
        const documentType = draftRequest
            ? detectDraftDocumentType(outbound)
            : draftDocument?.documentType || "General draft";
        const draftRequestPrompt = revisionRequest && draftDocument
            ? [
                "Revise the existing draft below. Return only the updated draft text, without commentary.",
                "",
                `Revision instruction: ${outbound}`,
                "",
                "Current draft:",
                draftDocument.content,
            ].join("\n")
            : outbound;

        if (draftRequest || revisionRequest) {
            pendingDraftRef.current = {
                mode: revisionRequest ? "revision" : "create",
                documentType,
                title: draftDocument?.title || draftTitleFromType(documentType, selectedCase?.title),
            };
        } else {
            pendingDraftRef.current = null;
        }

        const chatSessionId = activeSessionId || createChatSession(activeChatScopeId, outbound);
        const uploadResult = pendingFiles.length ? await uploadPendingFiles(outbound, chatSessionId) : { uploadedIds: [] as string[], uploadedFiles: [] as PendingAssistantFile[] };
        if (pendingFiles.length && uploadResult.uploadedIds.length === 0) return false;

        await sendCaseMessage(activeChatScopeId, draftRequestPrompt, {
            workspaceMode,
            externalModeEnabled,
            topK: REASONING_TOP_K[reasoningLevel],
            reasoningLevel,
            outputLanguage,
            returnCandidates: reasoningLevel === "deep",
            displayPrompt: outbound,
            uploadedDocumentIds: uploadResult.uploadedIds,
            uploadedFiles: uploadResult.uploadedFiles.map((item) => ({
                id: item.uploadedId || item.id,
                filename: item.file.name,
                mimeType: item.file.type || "application/octet-stream",
                temporary: item.temporary,
            })),
        });
        if (uploadResult.uploadedIds.length) {
            setPendingFiles([]);
            if (activeCaseId) void loadCaseContext(activeCaseId);
        }
        return true;
    }

    function selectAssistantMode(mode: AssistantMode) {
        setAssistantMode(mode);
        setWorkspaceMode(workspaceModeFromAssistantMode(mode));
        setExternalModeEnabled(mode === "external");
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!draft.trim() || copilotLoading || composerRecording) return;
        const outbound = draft;
        if (await submitPrompt(outbound)) setDraft("");
    }

    function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key !== "Enter" || event.shiftKey) return;
        event.preventDefault();
        if (copilotLoading) {
            stopCopilotRequest();
            return;
        }
        if (!draft.trim() || composerRecording) return;
        const outbound = draft;
        void submitPrompt(outbound).then((sent) => {
            if (sent) setDraft("");
        });
    }

    async function optimizePromptDraft() {
        if (!token) return;
        const trimmed = draft.trim();
        if (!trimmed || optimizingPrompt || copilotLoading || composerRecording) return;

        setOptimizingPrompt(true);
        setError(null);
        try {
            const response = await workspaceApi.optimizePrompt(token, {
                prompt: trimmed,
                workspaceCaseId: activeCaseId,
                workspaceDocumentId: null,
            });
            const optimizedPrompt = String(response.optimized_prompt || trimmed).trim() || trimmed;
            if (optimizedPrompt !== trimmed && !response.unchanged) setDraft(optimizedPrompt);
            setNotice(response.notes?.trim() || t("promptOptimizedNotice", "Prompt improved."));
        } catch (caught) {
            setError(caught instanceof Error && caught.message.trim() ? caught.message : t("optimizeFailed", "Unable to optimize the prompt."));
        } finally {
            setOptimizingPrompt(false);
        }
    }

    async function handleCopy(message: ChatMessage) {
        try {
            await navigator.clipboard.writeText(message.content);
            setNotice(t("copiedToClipboard", "Copied to clipboard."));
            setError(null);
        } catch {
            setError(t("copyFailed", "Unable to copy message."));
        }
    }

    async function handleRegenerate(message: ChatMessage) {
        if (!activeCaseId) return;
        const index = activeMessages.findIndex((item) => item.id === message.id);
        if (index < 1) return;
        for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
            if (activeMessages[cursor].role === "user") {
                await submitPrompt(activeMessages[cursor].content);
                return;
            }
        }
    }

    async function handleFeedback(message: ChatMessage, value: "up" | "down", rootCause?: FeedbackRootCause | null) {
        if (!token || !activeCaseId) return;
        if (value === "down" && !rootCause) {
            setNotice("Select a downvote reason before submitting feedback.");
            return;
        }
        const index = activeMessages.findIndex((row) => row.id === message.id);
        if (index < 0) return;

        let promptText = t("noPromptContext", "No prompt context");
        for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
            if (activeMessages[cursor].role === "user") {
                promptText = activeMessages[cursor].content;
                break;
            }
        }

        setChatFeedback((current) => ({
            ...current,
            [message.id]: { value, status: "saving", rootCause: value === "down" ? (rootCause || null) : null },
        }));

        try {
            await workspaceApi.createCopilotFeedback(token, {
                message_id: message.id,
                case_id: activeCaseId,
                document_id: null,
                prompt_text: promptText,
                response_text: message.content,
                parsed_intent: message.meta?.parsedIntent || null,
                confidence: message.meta?.confidence || null,
                feedback_value: value,
                root_cause: value === "down" ? (rootCause || null) : null,
                legal_domain: true,
                jurisdiction: selectedCase?.jurisdiction_country || null,
                source_count: message.meta?.sources?.length || 0,
                metadata: {
                    mode: workspaceMode,
                    action_category: message.meta?.actionCategory || null,
                    action_status: message.meta?.actionStatus || null,
                },
            });
            setChatFeedback((current) => ({
                ...current,
                [message.id]: { value, status: "submitted", rootCause: value === "down" ? (rootCause || null) : null },
            }));
        } catch {
            setChatFeedback((current) => ({
                ...current,
                [message.id]: { value, status: "error", rootCause: value === "down" ? (rootCause || null) : null },
            }));
        }
    }

    function handleAskMissingInfo(_message: ChatMessage, missingInfo: string) {
        void submitPrompt([
            "Missing information follow-up:",
            missingInfo,
            "",
            "Explain why this missing fact matters and what document or fact the lawyer should request.",
        ].join("\n"));
    }

    function handleGenerateDocument(message: ChatMessage) {
        handleEditInLegalEditor(message);
    }

    function handleEditInLegalEditor(message: ChatMessage) {
        if (!activeCaseId || message.role !== "assistant") return;
        const index = activeMessages.findIndex((row) => row.id === message.id);
        let promptText: string | null = null;
        for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
            if (activeMessages[cursor].role === "user") {
                promptText = activeMessages[cursor].content;
                break;
            }
        }

        saveEditorDraftSeed({
            source: "assistant",
            caseId: activeCaseId,
            caseTitle: selectedCase?.title || null,
            prompt: promptText,
            answer: cleanDraftContent(message.meta?.rawAnswer || message.content),
            sources: message.meta?.sources || [],
            citations: message.meta?.citations || [],
            createdAt: new Date().toISOString(),
        });
        navigate(`/editor/${activeCaseId}`);
    }

    async function handleTrustReview(message: ChatMessage, decision: "approved" | "needs_revision") {
        await handleFeedback(message, decision === "approved" ? "up" : "down", decision === "needs_revision" ? "other" : null);
        setNotice(decision === "approved" ? "AI output marked reviewed." : "AI output marked for correction.");
    }

    function saveQuickDraft() {
        if (!draftDocument) return;
        localStorage.setItem(`assistant-quick-draft:${activeChatScopeId}`, JSON.stringify(draftDocument));
        setNotice(t("draftSavedNotice", "Draft saved locally."));
    }

    async function copyQuickDraft() {
        if (!draftDocument) return;
        try {
            await navigator.clipboard.writeText(`${draftDocument.title}\n\n${draftDocument.content}`);
            setNotice(t("copiedToClipboard", "Copied to clipboard."));
        } catch {
            setError(t("copyFailed", "Unable to copy message."));
        }
    }

    async function exportQuickDraftDocx() {
        if (!draftDocument) return;
        const { Document: DocxDocument, HeadingLevel, Packer, Paragraph, TextRun } = await import("docx");
        const paragraphs = [
            new Paragraph({
                text: draftDocument.title,
                heading: HeadingLevel.TITLE,
            }),
            new Paragraph({
                children: [new TextRun({ text: draftDocument.documentType, italics: true })],
            }),
            ...draftDocument.content.split(/\n{2,}/).flatMap((block) => {
                const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
                if (!lines.length) return [];
                if (lines.length > 1 && lines.every((line) => /^[-*•]\s+/.test(line))) {
                    return lines.map((line) => new Paragraph({ text: line.replace(/^[-*•]\s+/, ""), bullet: { level: 0 } }));
                }
                return [new Paragraph({ text: lines.join("\n"), spacing: { after: 180 } })];
            }),
        ];
        const doc = new DocxDocument({ sections: [{ children: paragraphs }] });
        const blob = await Packer.toBlob(doc);
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        const stamp = new Date().toISOString().slice(0, 10);
        anchor.href = url;
        anchor.download = `${filenameSafe(`${selectedCase?.title || "assistant"}_${draftDocument.title}_${stamp}`)}.docx`;
        anchor.click();
        URL.revokeObjectURL(url);
    }

    function openQuickDraftInLegalEditor() {
        if (!draftDocument || !activeCaseId) return;
        saveEditorDraftSeed({
            source: "assistant",
            caseId: activeCaseId,
            caseTitle: selectedCase?.title || null,
            prompt: null,
            answer: draftDocument.content,
            sources: [],
            citations: [],
            createdAt: new Date().toISOString(),
        });
        navigate(`/editor/${activeCaseId}`);
    }

    const starterPrompts = [
        t("starterPrompt1", "Summarize this case"),
        t("starterPrompt2", "Identify legal risks"),
        t("starterPrompt3", "Draft a client email"),
        t("starterPrompt4", "List deadlines"),
        t("starterPrompt5", "Analyze contract"),
    ];

    const composer = (
        <footer
            className={`minimal-composer-shell ${hasConversation ? "dock" : "hero"} ${dragActive ? "drag-active" : ""}`}
            onDragEnter={handleComposerDragEnter}
            onDragLeave={handleComposerDragLeave}
            onDragOver={handleComposerDragOver}
            onDrop={handleComposerDrop}
        >
            {dragActive ? (
                <div className="minimal-drop-hint">
                    {t("dropFilesToAttach", "Drop files to attach")}
                </div>
            ) : null}
            {pendingFiles.length ? (
                <div className="minimal-file-chips" aria-label={t("attachedFiles", "Attached files")}>
                    {pendingFiles.map((item) => (
                        <span className={`minimal-file-chip ${item.status}`} key={item.id}>
                            <strong>{item.file.name}</strong>
                            <em>{item.status === "error" ? item.error : `${formatFileSize(item.file.size)} | ${item.status}`}</em>
                            <button
                                aria-label={t("removeFile", "Remove file")}
                                disabled={item.status === "uploading"}
                                onClick={() => removePendingFile(item.id)}
                                type="button"
                            >
                                x
                            </button>
                        </span>
                    ))}
                </div>
            ) : null}

            <form
                className={`minimal-composer ${copilotLoading || optimizingPrompt ? "busy" : ""}`}
                onSubmit={(event) => {
                    void handleSubmit(event);
                }}
            >
                <input
                    ref={fileInputRef}
                    accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown,text/x-markdown"
                    multiple
                    onChange={(event) => {
                        addPendingFiles(event.target.files);
                        event.target.value = "";
                    }}
                    type="file"
                    hidden
                />
                <button
                    aria-label={t("attachFiles", "Attach files")}
                    className="minimal-icon-button"
                    disabled={copilotLoading || optimizingPrompt || composerRecording || pendingFiles.some((item) => item.status === "uploading")}
                    onClick={() => fileInputRef.current?.click()}
                    title={t("attachFilesMax", "Attach files (10 max)")}
                    type="button"
                >
                    +
                </button>
                <textarea
                    disabled={!canSend || pendingFiles.some((item) => item.status === "uploading")}
                    onKeyDown={handleComposerKeyDown}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder={canSend ? composerPlaceholder : t("loginRequired", "Sign in to use the assistant...")}
                    value={draft}
                />
                <button
                    aria-label={optimizingPrompt ? t("optimizing", "Optimizing...") : t("optimize", "Improve prompt")}
                    className={`minimal-icon-button minimal-improve-button ${optimizingPrompt ? "busy" : ""}`}
                    disabled={!draft.trim() || copilotLoading || optimizingPrompt || composerRecording || !canSend || pendingFiles.some((item) => item.status === "uploading")}
                    onClick={() => {
                        void optimizePromptDraft();
                    }}
                    title={optimizingPrompt ? t("optimizing", "Optimizing...") : t("optimize", "Improve prompt")}
                    type="button"
                >
                    <svg aria-hidden="true" viewBox="0 0 20 20">
                        <path d="M10 2.8 11.2 6l3.2 1.2-3.2 1.2L10 11.6 8.8 8.4 5.6 7.2 8.8 6 10 2.8Z" />
                        <path d="M15.2 11.2 15.9 13l1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8Z" />
                        <path d="M5.1 11.9 5.7 13.3l1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6.6-1.4Z" />
                    </svg>
                </button>
                <button
                    aria-label={composerRecording ? t("stopVoiceInput", "Stop voice input") : t("voiceInput", "Voice input")}
                    className={`minimal-icon-button ${composerRecording ? "recording" : ""}`}
                    disabled={!token || copilotLoading || optimizingPrompt || pendingFiles.some((item) => item.status === "uploading")}
                    onClick={() => {
                        if (composerRecording) stopComposerRecording();
                        else void startComposerRecording();
                    }}
                    title={composerRecording ? t("stopVoiceInput", "Stop voice input") : t("voiceInput", "Voice input")}
                    type="button"
                >
                    <svg aria-hidden="true" viewBox="0 0 20 20">
                        <rect x="7" y="3.2" width="6" height="9.2" rx="3" />
                        <path d="M5.5 9.5a4.5 4.5 0 0 0 9 0" />
                        <path d="M10 14v3" />
                        <path d="M7 17h6" />
                    </svg>
                </button>
                <button
                    aria-label={copilotLoading ? t("stopRequest", "Stop request") : t("send", "Send")}
                    className={`minimal-send-button ${copilotLoading ? "is-stop" : ""}`}
                    disabled={!copilotLoading && (!draft.trim() || optimizingPrompt || composerRecording || !canSend || pendingFiles.some((item) => item.status === "uploading"))}
                    onClick={copilotLoading ? stopCopilotRequest : undefined}
                    title={copilotLoading ? t("stopRequest", "Stop request") : t("send", "Send")}
                    type={copilotLoading ? "button" : "submit"}
                >
                    {copilotLoading ? (
                        <svg aria-hidden="true" viewBox="0 0 20 20">
                            <rect x="5.5" y="5.5" width="9" height="9" rx="1.6" />
                        </svg>
                    ) : (
                        <svg aria-hidden="true" viewBox="0 0 20 20">
                            <path d="M4.5 10h9.8" />
                            <path d="m10.2 5.2 4.8 4.8-4.8 4.8" />
                        </svg>
                    )}
                </button>
            </form>

            <div className="minimal-composer-meta">
                <span className={`minimal-grounding-badge ${assistantGroundingState}`}>{groundingLabel(assistantGroundingState)}</span>
                <span>{activeCaseId ? `${caseTitle}${activeClient?.name ? ` | ${activeClient.name}` : ""}` : t("generalAssistant", "General Assistant")}</span>
                <label>
                    <span>{t("modes", "Mode")}</span>
                    <select disabled={copilotLoading || optimizingPrompt || composerRecording} onChange={(event) => selectAssistantMode(event.target.value as AssistantMode)} value={assistantMode}>
                        {ASSISTANT_MODES.map((mode) => <option key={mode.id} value={mode.id}>{mode.label}</option>)}
                    </select>
                </label>
                <label>
                    <span>{t("reasoningLabel", "Reasoning")}</span>
                    <select
                        disabled={copilotLoading || optimizingPrompt || composerRecording}
                        onChange={(event) => {
                            const next = event.target.value as ReasoningLevel;
                            setReasoningLevel(next);
                            try { window.localStorage.setItem("lai.reasoningLevel", next); } catch { /* ignore */ }
                        }}
                        value={reasoningLevel}
                    >
                        <option value="low">Fast</option>
                        <option value="medium">Balanced</option>
                        <option value="high">Deep</option>
                        <option value="deep">Deep + Judge (2x cost)</option>
                    </select>
                </label>
                <label>
                    <span>{t("outputLanguageLabel", "Language")}</span>
                    <select
                        disabled={copilotLoading || optimizingPrompt || composerRecording}
                        onChange={(event) => {
                            const next = event.target.value as OutputLanguage;
                            setOutputLanguage(next);
                            try { window.localStorage.setItem("lai.outputLanguage", next); } catch { /* ignore */ }
                        }}
                        value={outputLanguage}
                        title={t("outputLanguageHint", "Reply language. Citations stay in their original language.")}
                    >
                        <option value="auto">Auto</option>
                        <option value="fr">Français</option>
                        <option value="ar">العربية</option>
                        <option value="en">English</option>
                    </select>
                </label>
                {assistantMode === "agent" ? <span>{t("agentModeSafe", "Write actions require confirmation.")}</span> : null}
            </div>
        </footer>
    );

    const draftEditorPanel = draftPanelOpen && draftDocument ? (
        <aside className="assistant-draft-panel" aria-label={t("draftEditor", "Draft editor")}>
            <div className="assistant-draft-toolbar">
                <div className="assistant-draft-title-group">
                    <input
                        aria-label={t("draftTitle", "Draft title")}
                        onChange={(event) => setDraftDocument((current) => current ? { ...current, title: event.target.value, updatedAt: new Date().toISOString() } : current)}
                        value={draftDocument.title}
                    />
                    <span>{draftDocument.documentType}</span>
                </div>
                <div className="assistant-draft-actions">
                    <button onClick={saveQuickDraft} type="button">{t("save", "Save")}</button>
                    <button onClick={() => void exportQuickDraftDocx()} type="button">{t("exportDocx", "Export DOCX")}</button>
                    <button onClick={() => void copyQuickDraft()} type="button">{t("copy", "Copy")}</button>
                    {activeCaseId ? (
                        <button onClick={openQuickDraftInLegalEditor} type="button">{t("openInLegalEditor", "Open in Legal Editor")}</button>
                    ) : null}
                    <button aria-label={t("closePanel", "Close panel")} onClick={() => setDraftPanelOpen(false)} type="button">x</button>
                </div>
            </div>
            <div className="assistant-draft-canvas">
                <textarea
                    aria-label={t("editableDraft", "Editable draft")}
                    onChange={(event) => setDraftDocument((current) => current ? { ...current, content: event.target.value, updatedAt: new Date().toISOString() } : current)}
                    value={draftDocument.content}
                />
            </div>
        </aside>
    ) : null;

    function handleEditorSaved(document: DraftDocument) {
        setNotice(`${document.title} saved.`);
    }

    const legalEditorPanel = editorDraftPayload && token ? (
        <LegalEditorPanel
            key={`${editorDraftPayload.title}-${editorDraftPayload.content_text?.length || editorDraftPayload.content_html.length}`}
            token={token}
            payload={editorDraftPayload}
            onClose={() => {
                setEditorFocusMode(false);
                setEditorDraftPayload(null);
            }}
            onSaved={handleEditorSaved}
            onFocusModeChange={setEditorFocusMode}
        />
    ) : draftEditorPanel;

    return (
        <section className="shell-page assistant-route-page legal-copilot-page minimal-assistant-page">
            <section className="minimal-assistant-shell">
                <header className="assistant-minimal-topbar">
                    <div className="assistant-minimal-brand">
                        <span>AI</span>
                        <strong>{t("navAssistantLabel", "Assistant")}</strong>
                    </div>
                    <button className="assistant-minimal-case" onClick={() => navigate(activeCaseId ? `/cases/${activeCaseId}` : "/cases")} type="button">
                        <span>{activeCaseId ? topbarCaseLabel : t("generalAssistant", "General Assistant")}</span>
                        {activeCaseId ? <em>{caseJurisdictionLabel(selectedCase?.jurisdiction_country)}</em> : null}
                    </button>
                    <div className="assistant-minimal-actions">
                        <button
                            onClick={() => {
                                const sessionId = createChatSession(activeChatScopeId);
                                selectChatSession(activeChatScopeId, sessionId);
                            }}
                            type="button"
                        >
                            {t("newChat", "New chat")}
                        </button>
                        <button onClick={() => setHistorySidebarOpen((current) => !current)} type="button">{t("history", "History")}</button>
                        <span className="assistant-avatar">{(user?.name || "U").slice(0, 1).toUpperCase()}</span>
                    </div>
                </header>

                {notice ? <div className="minimal-toast">{notice}</div> : null}
                {error ? <div className="minimal-toast error">{error}</div> : null}

                <div className={`assistant-draft-split ${legalEditorPanel ? "is-open" : ""} ${editorFocusMode ? "editor-focus-mode" : ""}`}>
                    <main className={`assistant-minimal-workspace ${hasConversation ? "has-conversation" : "is-empty"}`}>
                        {hasConversation ? (
                            <div className="assistant-minimal-chat">
                                <div className="message-stream">
                                    {activeMessages.map((message) => (
                                        <ChatMessageBubble
                                            feedback={chatFeedback[message.id]}
                                            key={message.id}
                                            language={language}
                                            message={message}
                                            onCopy={() => {
                                                void handleCopy(message);
                                            }}
                                            onFeedback={(msg, value, rootCause) => {
                                                void handleFeedback(msg, value, rootCause);
                                            }}
                                            onAskMissingInfo={handleAskMissingInfo}
                                            onEditInLegalEditor={handleEditInLegalEditor}
                                            onGenerateDocument={handleGenerateDocument}
                                            onRegenerate={() => {
                                                void handleRegenerate(message);
                                            }}
                                            onTrustReview={(msg, decision) => {
                                                void handleTrustReview(msg, decision);
                                            }}
                                            onShowTrace={setTraceMessage}
                                        />
                                    ))}
                                    {copilotLoading ? <TypingIndicator /> : null}
                                    <div ref={messageEndRef} aria-hidden="true" />
                                </div>
                            </div>
                        ) : (
                            <div className="assistant-empty-center">
                                <h1>{t("howCanIAssist", "How can I assist?")}</h1>
                                <p>{activeCaseId ? topbarCaseLabel : t("generalAssistantHint", "General assistant. Attach files here for temporary document context.")}</p>
                                {composer}
                                <div className="minimal-mode-pills" aria-label="Assistant capabilities">
                                    {compactModes.map((mode) => (
                                        <button className={assistantMode === mode.id ? "active" : ""} key={mode.id} onClick={() => selectAssistantMode(mode.id)} type="button">
                                            {mode.label}
                                        </button>
                                    ))}
                                    <button className={reasoningLevel === "high" ? "active" : ""} onClick={() => setReasoningLevel((current) => current === "high" ? "medium" : "high")} type="button">
                                        Deep reasoning
                                    </button>
                                </div>
                                <div className="minimal-starter-grid">
                                    {starterPrompts.map((prompt) => (
                                        <button disabled={!canSend || copilotLoading} key={prompt} onClick={() => void submitPrompt(prompt)} type="button">
                                            {prompt}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {hasConversation ? composer : null}
                    </main>
                    {legalEditorPanel}
                </div>

                {historySidebarOpen ? (
                    <aside className="minimal-history-panel" aria-label="Chat history">
                        <div className="minimal-history-head">
                            <strong>{t("history", "History")}</strong>
                            <button onClick={() => setHistorySidebarOpen(false)} type="button">Close</button>
                        </div>
                        <input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="Search conversations..." />
                        <div className="minimal-history-list">
                            {filteredSessions.length ? filteredSessions.map((session) => (
                                <div className={`minimal-history-row ${activeSessionId === session.id ? "active" : ""}`} key={session.id}>
                                    <button
                                        onClick={() => {
                                            selectChatSession(activeChatScopeId, session.id);
                                            setHistorySidebarOpen(false);
                                        }}
                                        type="button"
                                    >
                                        <strong>{session.title || t("newChat", "New chat")}</strong>
                                        <span>{formatTimestamp(session.updatedAt, locale)}</span>
                                    </button>
                                    <button
                                        aria-label={t("deleteChat", "Delete chat")}
                                        onClick={() => {
                                            removeChatSession(activeChatScopeId, session.id);
                                        }}
                                        type="button"
                                    >
                                        x
                                    </button>
                                </div>
                            )) : <p>{t("noHistoryYet", "No history yet.")}</p>}
                        </div>
                    </aside>
                ) : null}
            </section>
            <ExecutionTracePanel
                message={traceMessage}
                language={language}
                onClose={() => setTraceMessage(null)}
            />
        </section>
    );
}
