import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
    ApiError,
    askPortalAssistant,
    fetchPortalDashboard,
    fetchPortalThread,
    fetchPortalUnreadCount,
    loginPortalAccount,
    registerPortalAccount,
    requestPortalLoginCode,
    sendPortalMessage,
    sendPortalMessageAttachment,
    submitAuthenticatedPortalIntake,
    uploadPortalCaseMaterials,
    verifyPortalLoginCode,
} from "../lib/api";
import { THEME_STORAGE_KEY, TOKEN_STORAGE_KEY } from "../portalPresentation";
import type {
    ClientPortalAccount,
    ClientPortalAssistantResponse,
    ClientPortalDashboard,
    ClientPortalThread,
} from "../types";

export type ThemeMode = "light" | "dark";

type RegisterPayload = {
    tenant_slug: string;
    full_name: string;
    email: string;
    password: string;
    phone?: string;
    address?: string;
};

export type PortalContextValue = {
    // Theme
    theme: ThemeMode;
    toggleTheme: () => void;
    // Auth
    token: string | null;
    account: ClientPortalAccount | null;
    sessionReady: boolean;
    isAuthenticated: boolean;
    authBusy: boolean;
    authError: string | null;
    authMessage: string | null;
    loginCodePending: boolean;
    login: (email: string, password: string) => Promise<boolean>;
    verifyCode: (email: string, code: string) => Promise<boolean>;
    requestCode: (email: string, password: string) => Promise<boolean>;
    register: (payload: RegisterPayload) => Promise<boolean>;
    logout: () => void;
    clearAuthMessages: () => void;
    // Dashboard
    dashboard: ClientPortalDashboard | null;
    dashboardLoading: boolean;
    dashboardError: string | null;
    refreshDashboard: () => Promise<void>;
    // Selection
    selectedCaseId: number | null;
    setSelectedCaseId: (id: number | null) => void;
    // Intake / upload
    submitIntake: (formData: FormData) => Promise<boolean>;
    submitLoading: boolean;
    submitError: string | null;
    submitMessage: string | null;
    clearSubmitMessages: () => void;
    uploadCaseMaterials: (caseId: number, formData: FormData) => Promise<boolean>;
    uploadLoading: boolean;
    // Assistant
    assistantBusy: boolean;
    assistantError: string | null;
    assistantResult: ClientPortalAssistantResponse | null;
    askAssistant: (message: string, caseId?: number | null) => Promise<void>;
    clearAssistant: () => void;
    // Messaging
    thread: ClientPortalThread | null;
    threadLoading: boolean;
    threadError: string | null;
    messageSending: boolean;
    unreadMessages: number;
    loadThread: (caseId?: number | null) => Promise<void>;
    refreshActiveThread: () => Promise<void>;
    sendMessage: (body: string, caseId?: number | null) => Promise<boolean>;
    sendMessageWithAttachment: (file: File, body: string, caseId?: number | null) => Promise<boolean>;
    refreshUnreadCount: () => Promise<void>;
};

const PortalContext = createContext<PortalContextValue | null>(null);

export function PortalProvider({ children }: { children: React.ReactNode }) {
    // ── Theme ──────────────────────────────────────────────────────────────────
    const [theme, setTheme] = useState<ThemeMode>(() => {
        const stored = localStorage.getItem(THEME_STORAGE_KEY);
        return stored === "dark" ? "dark" : "light";
    });

    // ── Auth ───────────────────────────────────────────────────────────────────
    const [token, setTokenState] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
    const [account, setAccount] = useState<ClientPortalAccount | null>(null);
    const [sessionReady, setSessionReady] = useState(false);
    const [authBusy, setAuthBusy] = useState(false);
    const [authError, setAuthError] = useState<string | null>(null);
    const [authMessage, setAuthMessage] = useState<string | null>(null);
    const [loginCodePending, setLoginCodePending] = useState(false);

    // ── Dashboard ──────────────────────────────────────────────────────────────
    const [dashboard, setDashboard] = useState<ClientPortalDashboard | null>(null);
    const [dashboardLoading, setDashboardLoading] = useState(false);
    const [dashboardError, setDashboardError] = useState<string | null>(null);

    // ── Selection ──────────────────────────────────────────────────────────────
    const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);

    // ── Intake / upload ────────────────────────────────────────────────────────
    const [submitLoading, setSubmitLoading] = useState(false);
    const [submitError, setSubmitError] = useState<string | null>(null);
    const [submitMessage, setSubmitMessage] = useState<string | null>(null);
    const [uploadLoading, setUploadLoading] = useState(false);

    // ── Assistant ──────────────────────────────────────────────────────────────
    const [assistantBusy, setAssistantBusy] = useState(false);
    const [assistantError, setAssistantError] = useState<string | null>(null);
    const [assistantResult, setAssistantResult] = useState<ClientPortalAssistantResponse | null>(null);

    // ── Messaging ──────────────────────────────────────────────────────────────
    const [thread, setThread] = useState<ClientPortalThread | null>(null);
    const [threadLoading, setThreadLoading] = useState(false);
    const [threadError, setThreadError] = useState<string | null>(null);
    const [messageSending, setMessageSending] = useState(false);
    const [unreadMessages, setUnreadMessages] = useState(0);

    const pollTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
    const unreadTimerRef = useRef<ReturnType<typeof window.setInterval> | null>(null);
    const threadCaseRef = useRef<number | null>(null);

    // Theme sync
    useEffect(() => {
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem(THEME_STORAGE_KEY, theme);
    }, [theme]);

    // Session initialization — validate stored token by loading dashboard once
    useEffect(() => {
        if (!token) {
            setSessionReady(true);
            return;
        }
        fetchPortalDashboard(token)
            .then((data) => {
                setDashboard(data);
                setAccount(data.account);
                if (data.cases.length > 0) setSelectedCaseId(data.cases[0].id);
            })
            .catch(() => {
                localStorage.removeItem(TOKEN_STORAGE_KEY);
                setTokenState(null);
            })
            .finally(() => setSessionReady(true));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // intentionally run once on mount

    // Poll for pending background jobs
    useEffect(() => {
        if (!token || !dashboard?.jobs?.length) return;
        const hasPending = dashboard.jobs.some((j) => !["completed", "failed"].includes(j.status));
        if (!hasPending) return;
        pollTimerRef.current = window.setTimeout(() => {
            void refreshDashboard();
        }, 4000);
        return () => {
            if (pollTimerRef.current !== null) window.clearTimeout(pollTimerRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dashboard?.jobs, token]);

    // Poll unread message count while authenticated.
    useEffect(() => {
        if (!token) return;
        void fetchPortalUnreadCount(token)
            .then((res) => setUnreadMessages(res.unread_count))
            .catch(() => undefined);
        unreadTimerRef.current = window.setInterval(() => {
            void fetchPortalUnreadCount(token)
                .then((res) => setUnreadMessages(res.unread_count))
                .catch(() => undefined);
        }, 20000);
        return () => {
            if (unreadTimerRef.current !== null) window.clearInterval(unreadTimerRef.current);
        };
    }, [token]);

    const toggleTheme = useCallback(() => setTheme((prev) => (prev === "light" ? "dark" : "light")), []);
    const clearAuthMessages = useCallback(() => { setAuthError(null); setAuthMessage(null); }, []);
    const clearSubmitMessages = useCallback(() => { setSubmitError(null); setSubmitMessage(null); }, []);

    const refreshDashboard = useCallback(async () => {
        if (!token) return;
        setDashboardLoading(true);
        setDashboardError(null);
        try {
            const data = await fetchPortalDashboard(token);
            setDashboard(data);
            setAccount(data.account);
        } catch (caught) {
            setDashboardError(caught instanceof Error ? caught.message : "Unable to load dashboard.");
        } finally {
            setDashboardLoading(false);
        }
    }, [token]);

    const login = useCallback(async (email: string, password: string): Promise<boolean> => {
        setAuthBusy(true);
        setAuthError(null);
        setAuthMessage(null);
        try {
            try {
                const res = await loginPortalAccount(email, password);
                localStorage.setItem(TOKEN_STORAGE_KEY, res.access_token);
                setTokenState(res.access_token);
                setLoginCodePending(false);
                const data = await fetchPortalDashboard(res.access_token);
                setDashboard(data);
                setAccount(data.account);
                if (data.cases.length > 0) setSelectedCaseId(data.cases[0].id);
                return true;
            } catch (caught) {
                const needs2FA =
                    (caught instanceof ApiError && caught.status === 403) ||
                    (caught instanceof Error && caught.message.toLowerCase().includes("verification code"));
                if (!needs2FA) throw caught;
                const msg = await requestPortalLoginCode(email, password);
                setAuthMessage(msg.message);
                setLoginCodePending(true);
                return false;
            }
        } catch (caught) {
            setAuthError(caught instanceof Error ? caught.message : "Login failed.");
            return false;
        } finally {
            setAuthBusy(false);
        }
    }, []);

    const requestCode = useCallback(async (email: string, password: string): Promise<boolean> => {
        setAuthBusy(true);
        setAuthError(null);
        try {
            const res = await requestPortalLoginCode(email, password);
            setAuthMessage(res.message);
            setLoginCodePending(true);
            return true;
        } catch (caught) {
            setAuthError(caught instanceof Error ? caught.message : "Unable to send login code.");
            return false;
        } finally {
            setAuthBusy(false);
        }
    }, []);

    const verifyCode = useCallback(async (email: string, code: string): Promise<boolean> => {
        setAuthBusy(true);
        setAuthError(null);
        try {
            const res = await verifyPortalLoginCode(email, code);
            localStorage.setItem(TOKEN_STORAGE_KEY, res.access_token);
            setTokenState(res.access_token);
            setLoginCodePending(false);
            const data = await fetchPortalDashboard(res.access_token);
            setDashboard(data);
            setAccount(data.account);
            if (data.cases.length > 0) setSelectedCaseId(data.cases[0].id);
            return true;
        } catch (caught) {
            setAuthError(caught instanceof Error ? caught.message : "Code verification failed.");
            return false;
        } finally {
            setAuthBusy(false);
        }
    }, []);

    const register = useCallback(async (payload: RegisterPayload): Promise<boolean> => {
        setAuthBusy(true);
        setAuthError(null);
        setAuthMessage(null);
        try {
            const res = await registerPortalAccount(payload);
            setAuthMessage(res.message);
            return true;
        } catch (caught) {
            setAuthError(caught instanceof Error ? caught.message : "Registration failed.");
            return false;
        } finally {
            setAuthBusy(false);
        }
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setTokenState(null);
        setAccount(null);
        setDashboard(null);
        setSelectedCaseId(null);
        setAssistantResult(null);
        setThread(null);
        setUnreadMessages(0);
        if (unreadTimerRef.current !== null) window.clearInterval(unreadTimerRef.current);
    }, []);

    const submitIntake = useCallback(async (formData: FormData): Promise<boolean> => {
        if (!token) return false;
        setSubmitLoading(true);
        setSubmitError(null);
        setSubmitMessage(null);
        try {
            const data = await submitAuthenticatedPortalIntake(token, formData);
            setDashboard(data);
            setAccount(data.account);
            setSubmitMessage(
                data.jobs?.length
                    ? `Consultation submitted. ${data.jobs.length} background job(s) queued.`
                    : "Consultation submitted successfully."
            );
            return true;
        } catch (caught) {
            setSubmitError(caught instanceof Error ? caught.message : "Unable to submit consultation.");
            return false;
        } finally {
            setSubmitLoading(false);
        }
    }, [token]);

    const uploadCaseMaterials = useCallback(async (caseId: number, formData: FormData): Promise<boolean> => {
        if (!token) return false;
        setUploadLoading(true);
        setSubmitError(null);
        setSubmitMessage(null);
        try {
            const data = await uploadPortalCaseMaterials(token, caseId, formData);
            setDashboard(data);
            setAccount(data.account);
            setSubmitMessage("Files uploaded successfully.");
            return true;
        } catch (caught) {
            setSubmitError(caught instanceof Error ? caught.message : "Upload failed.");
            return false;
        } finally {
            setUploadLoading(false);
        }
    }, [token]);

    const askAssistant = useCallback(async (message: string, caseId?: number | null) => {
        if (!token) return;
        setAssistantBusy(true);
        setAssistantError(null);
        try {
            const result = await askPortalAssistant(token, {
                message,
                case_id: caseId !== undefined ? caseId : selectedCaseId,
            });
            setAssistantResult(result);
        } catch (caught) {
            setAssistantError(caught instanceof Error ? caught.message : "Unable to get a response.");
        } finally {
            setAssistantBusy(false);
        }
    }, [token, selectedCaseId]);

    const clearAssistant = useCallback(() => {
        setAssistantResult(null);
        setAssistantError(null);
    }, []);

    // ── Messaging ──────────────────────────────────────────────────────────────
    const refreshUnreadCount = useCallback(async () => {
        if (!token) return;
        try {
            const res = await fetchPortalUnreadCount(token);
            setUnreadMessages(res.unread_count);
        } catch {
            // Non-fatal: leave the previous count in place.
        }
    }, [token]);

    const loadThread = useCallback(async (caseId?: number | null) => {
        if (!token) return;
        threadCaseRef.current = caseId ?? null;
        setThreadLoading(true);
        setThreadError(null);
        try {
            const data = await fetchPortalThread(token, caseId);
            setThread(data);
            // Opening the thread marks lawyer messages read server-side.
            setUnreadMessages(0);
        } catch (caught) {
            setThreadError(caught instanceof Error ? caught.message : "Unable to load messages.");
        } finally {
            setThreadLoading(false);
        }
    }, [token]);

    // Silent live refresh: re-fetch the open thread on an interval without a
    // loading flicker, replacing state only when the message set changed.
    const refreshActiveThread = useCallback(async () => {
        if (!token) return;
        const caseId = threadCaseRef.current;
        try {
            const data = await fetchPortalThread(token, caseId);
            if (threadCaseRef.current !== caseId) return;
            setThread((prev) => {
                if (
                    prev &&
                    prev.messages.length === data.messages.length &&
                    prev.messages[prev.messages.length - 1]?.id ===
                        data.messages[data.messages.length - 1]?.id
                ) {
                    return prev;
                }
                return data;
            });
            setUnreadMessages(0);
        } catch {
            /* keep last good thread on transient failure */
        }
    }, [token]);

    const sendMessage = useCallback(async (body: string, caseId?: number | null): Promise<boolean> => {
        if (!token || !body.trim()) return false;
        setMessageSending(true);
        setThreadError(null);
        try {
            const message = await sendPortalMessage(token, body.trim(), caseId);
            setThread((prev) =>
                prev ? { ...prev, messages: [...prev.messages, message] } : prev
            );
            return true;
        } catch (caught) {
            setThreadError(caught instanceof Error ? caught.message : "Unable to send message.");
            return false;
        } finally {
            setMessageSending(false);
        }
    }, [token]);

    const sendMessageWithAttachment = useCallback(
        async (file: File, body: string, caseId?: number | null): Promise<boolean> => {
            if (!token || !file) return false;
            setMessageSending(true);
            setThreadError(null);
            try {
                const message = await sendPortalMessageAttachment(token, file, body.trim(), caseId);
                setThread((prev) =>
                    prev ? { ...prev, messages: [...prev.messages, message] } : prev
                );
                return true;
            } catch (caught) {
                setThreadError(caught instanceof Error ? caught.message : "Unable to send attachment.");
                return false;
            } finally {
                setMessageSending(false);
            }
        },
        [token]
    );

    return (
        <PortalContext.Provider value={{
            theme, toggleTheme,
            token, account, sessionReady, isAuthenticated: !!token,
            authBusy, authError, authMessage, loginCodePending,
            login, verifyCode, requestCode, register, logout, clearAuthMessages,
            dashboard, dashboardLoading, dashboardError, refreshDashboard,
            selectedCaseId, setSelectedCaseId,
            submitIntake, submitLoading, submitError, submitMessage, clearSubmitMessages,
            uploadCaseMaterials, uploadLoading,
            assistantBusy, assistantError, assistantResult, askAssistant, clearAssistant,
            thread, threadLoading, threadError, messageSending, unreadMessages,
            loadThread, refreshActiveThread, sendMessage, sendMessageWithAttachment, refreshUnreadCount,
        }}>
            {children}
        </PortalContext.Provider>
    );
}

export function usePortal(): PortalContextValue {
    const ctx = useContext(PortalContext);
    if (!ctx) throw new Error("usePortal must be used inside PortalProvider");
    return ctx;
}
