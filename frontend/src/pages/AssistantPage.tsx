import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ChatMessageBubble, { type MessageFeedbackState } from "../components/ChatMessageBubble";
import { workspaceApi } from "../workspaceApi";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import type { ChatMessage, FeedbackRootCause } from "../types";

type WorkspaceMode = "chat" | "agent" | "legal_search";
type ReasoningLevel = "low" | "medium" | "high";

const REASONING_TOP_K: Record<ReasoningLevel, number> = {
    low: 4,
    medium: 6,
    high: 8,
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

function parseCaseId(value?: string) {
    const parsed = Number(value);
    if (!value || Number.isNaN(parsed) || parsed <= 0) {
        return null;
    }
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

function TypingIndicator() {
    return (
        <div className="typing-indicator">
            <span />
            <span />
            <span />
        </div>
    );
}

export default function AssistantPage() {
    const navigate = useNavigate();
    const params = useParams();
    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);

    const {
        token,
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
        copilotLoading,
        stopCopilotRequest,
        language,
        locale,
        t,
    } = useRoutedWorkspace();

    const [draft, setDraft] = useState("");
    const [notice, setNotice] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [chatHistoryOpen, setChatHistoryOpen] = useState(true);
    const [historySidebarOpen, setHistorySidebarOpen] = useState(true);
    const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
    const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("chat");
    const [reasoningLevel, setReasoningLevel] = useState<ReasoningLevel>("medium");
    const [externalModeEnabled, setExternalModeEnabled] = useState(false);
    const [optimizingPrompt, setOptimizingPrompt] = useState(false);
    const [composerRecording, setComposerRecording] = useState(false);
    const [chatFeedback, setChatFeedback] = useState<Record<string, MessageFeedbackState>>({});
    const messageEndRef = useRef<HTMLDivElement | null>(null);
    const composerRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
    const composerDictationSeedRef = useRef("");
    const composerDictationFinalRef = useRef("");
    const activeCaseId = routeCaseId ?? selectedCaseId;

    useEffect(() => {
        if (routeCaseId && routeCaseId !== selectedCaseId) {
            setSelectedCaseId(routeCaseId);
        }
    }, [routeCaseId, selectedCaseId, setSelectedCaseId]);

    const sessions = useMemo(() => (activeCaseId ? getSessionsForCase(activeCaseId) : []), [activeCaseId, getSessionsForCase]);
    const activeSessionId = useMemo(
        () => (activeCaseId ? getActiveSessionId(activeCaseId) : null),
        [activeCaseId, getActiveSessionId]
    );
    const activeMessages = useMemo(
        () => (activeCaseId ? getActiveMessages(activeCaseId) : []),
        [activeCaseId, getActiveMessages]
    );

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
        return () => {
            if (composerRecognitionRef.current) {
                composerRecognitionRef.current.abort();
                composerRecognitionRef.current = null;
            }
        };
    }, []);

    const canSend = useMemo(() => Boolean(activeCaseId), [activeCaseId]);

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

                    if (result?.isFinal) {
                        finalTranscript = `${finalTranscript}${transcript} `;
                    } else {
                        interimTranscript = `${interimTranscript}${transcript} `;
                    }
                }

                composerDictationFinalRef.current = finalTranscript;
                const nextValue = `${composerDictationSeedRef.current}${finalTranscript}${interimTranscript}`
                    .replace(/\s+/g, " ")
                    .trim();
                setDraft(nextValue);
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

    async function submitPrompt(promptText: string) {
        if (!canSend || !activeCaseId) return;
        const outbound = promptText.trim();
        if (!outbound) return;
        setError(null);
        setNotice(null);
        await sendCaseMessage(activeCaseId, outbound, {
            workspaceMode,
            externalModeEnabled,
            topK: REASONING_TOP_K[reasoningLevel],
            reasoningLevel,
        });
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!draft.trim() || copilotLoading || composerRecording) return;
        const outbound = draft;
        setDraft("");
        await submitPrompt(outbound);
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
        setDraft("");
        void submitPrompt(outbound);
    }

    async function optimizePromptDraft() {
        if (!token || !activeCaseId) return;
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
            const unchanged = Boolean(response.unchanged) || optimizedPrompt === trimmed;

            if (!unchanged) {
                setDraft(optimizedPrompt);
            }

            const strategyLabel = response.used_llm
                ? "LLM"
                : String(response.strategy || "heuristic").toUpperCase();
            const note = response.notes?.trim() || (unchanged
                ? t("promptAlreadyStrong", "Prompt already strong.")
                : t("promptOptimizedNotice", "Prompt optimized for clearer legal reasoning."));
            const improvements = (response.applied_improvements || []).slice(0, 2);
            const improvementText = improvements.length ? ` ${improvements.join(" ")}` : "";
            setNotice(`[${strategyLabel}] ${note}${improvementText}`);
        } catch (caught) {
            if (caught instanceof Error && caught.message.trim()) {
                setError(caught.message);
            } else {
                setError(t("optimizeFailed", "Unable to optimize the prompt."));
            }
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
                const prompt = activeMessages[cursor].content;
                await submitPrompt(prompt);
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
                    root_cause: value === "down" ? (rootCause || null) : null,
                    legal_domain: true,
                    jurisdiction: selectedCase?.jurisdiction_country || null,
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
        const prompt = [
            "Missing information follow-up:",
            missingInfo,
            "",
            "Explain why this missing fact matters, what document or fact the lawyer should request, and how it could change the analysis.",
        ].join("\n");
        void submitPrompt(prompt);
    }

    async function handleTrustReview(message: ChatMessage, decision: "approved" | "needs_revision") {
        if (!token || !activeCaseId) return;
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
            [message.id]: {
                value: decision === "approved" ? "up" : "down",
                status: "saving",
                rootCause: decision === "needs_revision" ? "other" : null,
            },
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
                feedback_value: decision === "approved" ? "up" : "down",
                root_cause: decision === "needs_revision" ? "other" : null,
                legal_domain: true,
                jurisdiction: selectedCase?.jurisdiction_country || null,
                source_count: message.meta?.sources?.length || 0,
                metadata: {
                    review_decision: decision,
                    review_surface: "trust_panel",
                    trust_panel: message.meta?.trustPanel || null,
                    mode: workspaceMode,
                },
            });
            setChatFeedback((current) => ({
                ...current,
                [message.id]: {
                    value: decision === "approved" ? "up" : "down",
                    status: "submitted",
                    rootCause: decision === "needs_revision" ? "other" : null,
                },
            }));
            setNotice(decision === "approved" ? "AI output marked reviewed." : "AI output marked for correction.");
        } catch {
            setChatFeedback((current) => ({
                ...current,
                [message.id]: {
                    value: decision === "approved" ? "up" : "down",
                    status: "error",
                    rootCause: decision === "needs_revision" ? "other" : null,
                },
            }));
        }
    }

    const starterPrompts = [
        t("starterPrompt1", "Summarize this case in 8 bullet points with contractual context."),
        t("starterPrompt2", "Identify top legal and operational risks with evidence anchors."),
        t("starterPrompt3", "Draft a concise client email explaining current posture and next steps."),
    ];

    return (
        <section className="shell-page assistant-route-page">
            <section className="copilot-shell chat-only-shell assistant-route-shell">
                <header className="assistant-topbar">
                    <div>
                        <p className="meta">{t("caseContext", "Case Context")}</p>
                        <h2>{selectedCase?.title || t("assistantDefaultTitle", "Assistant")}</h2>
                        <p className="workspace-subtitle">
                            {canSend
                                ? `Case #${activeCaseId} · ${sessions.length} ${t("sessionCount", "chat session(s)")}`
                                : t("selectCaseForAssistant", "Select a case to activate full assistant context.")}
                        </p>
                    </div>
                    <div className="assistant-topbar-actions">
                        <button
                            onClick={() => {
                                if (!activeCaseId) return;
                                const sessionId = createChatSession(activeCaseId);
                                selectChatSession(activeCaseId, sessionId);
                            }}
                            type="button"
                        >
                            {t("newChat", "New chat")}
                        </button>
                    </div>
                </header>

                {notice ? <div className="notice-banner">{notice}</div> : null}
                {error ? <div className="error-banner">{error}</div> : null}

                {!canSend ? (
                    <div className="chat-surface chat-surface-minimal">
                        <div className="empty-chat conversation-empty assistant-no-case">
                            <h3>{t("noCaseSelected", "No case selected")}</h3>
                            <p>{t("openCaseFirst", "Open a case first to get the full assistant workspace.")}</p>
                            <div className="empty-chat-actions">
                                <button onClick={() => navigate("/cases")} type="button">{t("openCases", "Open Cases")}</button>
                                <Link className="shell-inline-link" to="/dashboard">{t("goDashboard", "Go to Dashboard")}</Link>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className={`assistant-workbench ${historySidebarOpen ? "" : "history-hidden"}`}>
                        <div className="chat-surface assistant-main-surface">
                            <details
                                className="workspace-collapsible chat-history-collapsible chat-history-collapsible-main"
                                onToggle={(event) => setChatHistoryOpen((event.currentTarget as HTMLDetailsElement).open)}
                                open={chatHistoryOpen}
                            >
                                <summary>{t("conversationOutputs", "Conversation and outputs")}</summary>
                                <div className="message-stream">
                                    {!activeMessages.length && !copilotLoading ? (
                                        <div className="empty-chat conversation-empty">
                                            <h3>{t("noConversationYet", "No conversation yet")}</h3>
                                            <p>{t("startWithPrompt", "Use the prompt box below to start.")}</p>
                                            <p className="starter-prompt-note">{t("starterPrompts", "Starter prompts")}</p>
                                            <div className="empty-chat-actions starter-prompt-actions">
                                                {starterPrompts.map((prompt) => (
                                                    <button
                                                        className="starter-prompt-chip"
                                                        disabled={copilotLoading}
                                                        key={prompt}
                                                        onClick={() => {
                                                            if (!activeCaseId) return;
                                                            void submitPrompt(prompt);
                                                        }}
                                                        type="button"
                                                    >
                                                        {prompt}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    ) : null}

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
                                            onRegenerate={() => {
                                                void handleRegenerate(message);
                                            }}
                                            onTrustReview={(msg, decision) => {
                                                void handleTrustReview(msg, decision);
                                            }}
                                        />
                                    ))}

                                    {copilotLoading ? <TypingIndicator /> : null}
                                    <div ref={messageEndRef} aria-hidden="true" />
                                </div>
                            </details>

                            <footer className="composer-shell">
                                {attachmentMenuOpen ? (
                                    <div className="attachment-menu">
                                        <div className="menu-group">
                                            <small className="menu-group-title">{t("modes", "Modes")}</small>
                                            <button
                                                className={`menu-item mode ${workspaceMode === "chat" ? "active" : ""}`}
                                                onClick={() => {
                                                    setWorkspaceMode("chat");
                                                    setAttachmentMenuOpen(false);
                                                }}
                                                type="button"
                                            >
                                                <strong>{t("modeChat", "Chat Mode")}</strong>
                                                <small>{t("modeChatDesc", "Fast legal discussion")}</small>
                                            </button>
                                            <button
                                                className={`menu-item mode ${workspaceMode === "agent" ? "active" : ""}`}
                                                onClick={() => {
                                                    setWorkspaceMode("agent");
                                                    setAttachmentMenuOpen(false);
                                                }}
                                                type="button"
                                            >
                                                <strong>{t("modeAgent", "Agent Mode")}</strong>
                                                <small>{t("modeAgentDesc", "Step-by-step execution")}</small>
                                            </button>
                                            <button
                                                className={`menu-item mode ${workspaceMode === "legal_search" ? "active" : ""}`}
                                                onClick={() => {
                                                    setWorkspaceMode("legal_search");
                                                    setAttachmentMenuOpen(false);
                                                }}
                                                type="button"
                                            >
                                                <strong>{t("modeLegalSearch", "Legal Search Mode")}</strong>
                                                <small>{t("modeLegalSearchDesc", "Source-grounded legal answers")}</small>
                                            </button>
                                            <button
                                                className={`menu-item mode ${externalModeEnabled ? "active" : ""}`}
                                                onClick={() => {
                                                    setExternalModeEnabled((current) => !current);
                                                    setAttachmentMenuOpen(false);
                                                }}
                                                type="button"
                                            >
                                                <strong>{t("modeExternal", "External Mode")}</strong>
                                                <small>{t("modeExternalDesc", "Web-enhanced legal research")}</small>
                                            </button>
                                        </div>
                                        <div className="menu-group">
                                            <small className="menu-group-title">{t("attachments", "Attachments")}</small>
                                            <p className="muted">
                                                {t("attachmentsRemovedNotice", "Chat image analysis was removed. Use scanned-document upload from the case workspace instead.")}
                                            </p>
                                        </div>
                                    </div>
                                ) : null}

                                <form
                                    className={`composer ${copilotLoading || optimizingPrompt ? "busy" : ""}`}
                                    onSubmit={(event) => {
                                        void handleSubmit(event);
                                    }}
                                >
                                    <button
                                        aria-label={t("addOptions", "Add options")}
                                        className="composer-plus"
                                        onClick={() => {
                                            setAttachmentMenuOpen((current) => !current);
                                        }}
                                        title={attachmentMenuOpen ? t("closeMenu", "Close menu") : t("openMenu", "Open menu")}
                                        type="button"
                                    >
                                        {attachmentMenuOpen ? "-" : "+"}
                                    </button>

                                    <textarea
                                        onKeyDown={handleComposerKeyDown}
                                        onChange={(event) => setDraft(event.target.value)}
                                        placeholder={t("askPlaceholder", "Ask about your case, risks, deadlines, or draft something...")}
                                        value={draft}
                                    />

                                    <div className="composer-controls">
                                        <button
                                            aria-label={optimizingPrompt ? t("optimizing", "Optimizing...") : t("optimize", "Optimize")}
                                            className={`composer-optimize ${optimizingPrompt ? "busy" : ""}`}
                                            disabled={!draft.trim() || copilotLoading || optimizingPrompt || composerRecording}
                                            onClick={() => {
                                                void optimizePromptDraft();
                                            }}
                                            title={optimizingPrompt ? t("optimizing", "Optimizing...") : t("optimize", "Optimize")}
                                            type="button"
                                        >
                                            <svg aria-hidden="true" viewBox="0 0 20 20">
                                                <path d="M10 2.8 11.3 6l3.2 1.3-3.2 1.3L10 11.8 8.7 8.6 5.5 7.3 8.7 6 10 2.8Z" />
                                                <path d="M15.5 11.2 16.2 13l1.8.7-1.8.7-0.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8Z" />
                                                <path d="M5.1 11.8 5.7 13.3l1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6.6-1.5Z" />
                                            </svg>
                                        </button>
                                        <button
                                            aria-label={composerRecording ? t("stopVoiceInput", "Stop voice input") : t("voiceInput", "Voice input")}
                                            className={`composer-icon-button ${composerRecording ? "recording" : ""}`}
                                            disabled={!token || copilotLoading || optimizingPrompt}
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
                                            className={`composer-send ${copilotLoading ? "is-stop" : ""}`}
                                            disabled={!copilotLoading && (!draft.trim() || optimizingPrompt || composerRecording)}
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
                                    </div>
                                </form>

                                <div className="composer-selected-row">
                                    <label className="reasoning-inline-control" aria-label={t("reasoningLabel", "Reasoning")}
                                    >
                                        <span>{t("reasoningLabel", "Reasoning")}</span>
                                        <select
                                            aria-label={t("reasoningLabel", "Reasoning")}
                                            disabled={copilotLoading || optimizingPrompt || composerRecording}
                                            onChange={(event) => setReasoningLevel(event.target.value as ReasoningLevel)}
                                            value={reasoningLevel}
                                        >
                                            <option value="low">{t("reasoningLow", "Low")}</option>
                                            <option value="medium">{t("reasoningMedium", "Medium")}</option>
                                            <option value="high">{t("reasoningHigh", "High")}</option>
                                        </select>
                                    </label>
                                    <button
                                        className="selected-mode-chip primary"
                                        onClick={() => setAttachmentMenuOpen(true)}
                                        type="button"
                                    >
                                        {workspaceMode === "chat"
                                            ? t("modeChat", "Chat Mode")
                                            : workspaceMode === "agent"
                                                ? t("modeAgent", "Agent Mode")
                                                : t("modeLegalSearch", "Legal Search Mode")}
                                        {" "}v
                                    </button>
                                    {externalModeEnabled ? (
                                        <button
                                            className="selected-mode-chip external"
                                            onClick={() => setExternalModeEnabled(false)}
                                            type="button"
                                        >
                                            {t("modeExternal", "External Mode")}
                                        </button>
                                    ) : null}
                                </div>
                            </footer>
                        </div>

                        {historySidebarOpen ? (
                            <aside className="assistant-history-sidebar" aria-label={t("chatHistory", "Chat history")}>
                                <button
                                    aria-label={t("hideHistory", "Hide history")}
                                    className="assistant-history-edge-toggle open"
                                    onClick={() => setHistorySidebarOpen(false)}
                                    title={t("hideHistory", "Hide history")}
                                    type="button"
                                >
                                    -
                                </button>
                                <div className="assistant-history-head">
                                    <h3>{t("chatHistory", "Chat history")}</h3>
                                </div>
                                <div className="assistant-history-list">
                                    {sessions.length ? sessions.map((session) => (
                                        <div className={`assistant-history-row ${activeSessionId === session.id ? "active" : ""}`} key={session.id}>
                                            <button
                                                className={`assistant-history-item ${activeSessionId === session.id ? "active" : ""}`}
                                                onClick={() => {
                                                    if (!activeCaseId) return;
                                                    selectChatSession(activeCaseId, session.id);
                                                }}
                                                type="button"
                                            >
                                                <strong>{session.title || t("newChat", "New chat")}</strong>
                                                <small>{formatTimestamp(session.updatedAt, locale)}</small>
                                            </button>
                                            <button
                                                aria-label={t("deleteChat", "Delete chat")}
                                                className="assistant-history-delete"
                                                onClick={(event) => {
                                                    event.stopPropagation();
                                                    if (!activeCaseId) return;
                                                    removeChatSession(activeCaseId, session.id);
                                                }}
                                                title={t("deleteChat", "Delete chat")}
                                                type="button"
                                            >
                                                <svg aria-hidden="true" viewBox="0 0 20 20">
                                                    <path d="M5.6 6.8h8.8" />
                                                    <path d="M8 6.8V5.5h4v1.3" />
                                                    <path d="M7.3 6.8v7.1" />
                                                    <path d="M10 6.8v7.1" />
                                                    <path d="M12.7 6.8v7.1" />
                                                    <path d="M6.6 6.8h6.8v8.1a1 1 0 0 1-1 1H7.6a1 1 0 0 1-1-1Z" />
                                                </svg>
                                            </button>
                                        </div>
                                    )) : <p className="assistant-history-empty">{t("noHistoryYet", "No history yet.")}</p>}
                                </div>
                            </aside>
                        ) : (
                            <button
                                aria-label={t("showHistory", "Show history")}
                                className="assistant-history-edge-toggle closed"
                                onClick={() => setHistorySidebarOpen(true)}
                                title={t("showHistory", "Show history")}
                                type="button"
                            >
                                +
                            </button>
                        )}
                    </div>
                )}
            </section>
        </section>
    );
}
