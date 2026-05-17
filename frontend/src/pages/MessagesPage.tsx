import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { api } from "../lib/api";
import type { CaseMessage, CaseMessageThread, CaseMessageThreadSummary } from "../types";

function initials(name?: string | null): string {
    if (!name) return "?";
    return name
        .split(/\s+/)
        .map((p) => p[0])
        .filter(Boolean)
        .slice(0, 2)
        .join("")
        .toUpperCase();
}

function timeLabel(iso: string): string {
    return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(
        new Date(iso)
    );
}

function dayLabel(iso: string): string {
    const d = new Date(iso);
    const today = new Date();
    const yest = new Date();
    yest.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Today";
    if (d.toDateString() === yest.toDateString()) return "Yesterday";
    return new Intl.DateTimeFormat("en-US", {
        weekday: "long",
        month: "short",
        day: "numeric",
    }).format(d);
}

function relativeLabel(iso: string | null): string {
    if (!iso) return "";
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    return `${Math.floor(hrs / 24)}d`;
}

export default function MessagesPage() {
    const { token, t } = useRoutedWorkspace();

    const [threads, setThreads] = useState<CaseMessageThreadSummary[]>([]);
    const [threadsLoading, setThreadsLoading] = useState(false);
    const [activeCaseId, setActiveCaseId] = useState<number | null>(null);
    const [thread, setThread] = useState<CaseMessageThread | null>(null);
    const [threadLoading, setThreadLoading] = useState(false);
    const [draft, setDraft] = useState("");
    const [sending, setSending] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const scrollRef = useRef<HTMLDivElement | null>(null);

    const loadThreads = useCallback(async () => {
        if (!token) return;
        setThreadsLoading(true);
        try {
            const data = await api.listMessageThreads(token);
            setThreads(data);
            setActiveCaseId((current) => current ?? data[0]?.case_id ?? null);
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Unable to load conversations.");
        } finally {
            setThreadsLoading(false);
        }
    }, [token]);

    const loadThread = useCallback(
        async (caseId: number) => {
            if (!token) return;
            setThreadLoading(true);
            setError(null);
            try {
                const data = await api.getMessageThread(token, caseId);
                setThread(data);
                // Server marked client messages read; reflect locally.
                setThreads((prev) =>
                    prev.map((s) => (s.case_id === caseId ? { ...s, unread_count: 0 } : s))
                );
            } catch (caught) {
                setError(caught instanceof Error ? caught.message : "Unable to load this conversation.");
            } finally {
                setThreadLoading(false);
            }
        },
        [token]
    );

    useEffect(() => {
        void loadThreads();
        const id = window.setInterval(() => void loadThreads(), 20000);
        return () => window.clearInterval(id);
    }, [loadThreads]);

    useEffect(() => {
        if (activeCaseId != null) void loadThread(activeCaseId);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeCaseId]);

    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [thread?.messages.length]);

    const grouped = useMemo(() => {
        const groups: Array<{ day: string; items: CaseMessage[] }> = [];
        for (const m of thread?.messages ?? []) {
            const key = new Date(m.created_at).toDateString();
            const last = groups[groups.length - 1];
            if (last && last.day === key) last.items.push(m);
            else groups.push({ day: key, items: [m] });
        }
        return groups;
    }, [thread?.messages]);

    async function handleSend() {
        const body = draft.trim();
        if (!token || !body || sending || activeCaseId == null) return;
        setSending(true);
        setError(null);
        try {
            const message = await api.sendMessage(token, activeCaseId, body);
            setThread((prev) =>
                prev ? { ...prev, messages: [...prev.messages, message] } : prev
            );
            setDraft("");
            void loadThreads();
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Unable to send message.");
        } finally {
            setSending(false);
        }
    }

    async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0];
        if (!token || !file || activeCaseId == null) {
            e.target.value = "";
            return;
        }
        setSending(true);
        setError(null);
        try {
            const message = await api.sendMessageAttachment(token, activeCaseId, file, draft.trim());
            setThread((prev) =>
                prev ? { ...prev, messages: [...prev.messages, message] } : prev
            );
            setDraft("");
            void loadThreads();
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Unable to send attachment.");
        } finally {
            setSending(false);
            e.target.value = "";
        }
    }

    async function openAttachment(message: CaseMessage) {
        if (!token || activeCaseId == null) return;
        try {
            const url = await api.messageAttachmentUrl(token, activeCaseId, message.id);
            window.open(url, "_blank", "noopener,noreferrer");
        } catch {
            setError("Unable to open attachment.");
        }
    }

    return (
        <section className="shell-page msg-page">
            <style>{MSG_STYLES}</style>

            <header className="msg-header">
                <div>
                    <h2 className="msg-title">{t("messagesTitle", "Client Messages")}</h2>
                    <p className="msg-subtitle">
                        {t("messagesKicker", "Secure conversations with your clients, per case.")}
                    </p>
                </div>
                <button className="msg-refresh" type="button" onClick={() => void loadThreads()}>
                    {threadsLoading ? t("refreshing", "Refreshing…") : t("refresh", "Refresh")}
                </button>
            </header>

            {error ? <div className="msg-error">{error}</div> : null}

            <div className="msg-layout">
                {/* Thread list */}
                <aside className="msg-threads">
                    {threads.length === 0 && !threadsLoading ? (
                        <p className="msg-empty-list">
                            {t("noConversations", "No client conversations yet.")}
                        </p>
                    ) : (
                        threads.map((s) => (
                            <button
                                key={s.case_id}
                                type="button"
                                className={`msg-thread-row${s.case_id === activeCaseId ? " active" : ""}`}
                                onClick={() => setActiveCaseId(s.case_id)}
                            >
                                <div className="msg-avatar">{initials(s.client_name)}</div>
                                <div className="msg-thread-body">
                                    <div className="msg-thread-top">
                                        <strong>{s.client_name || t("client", "Client")}</strong>
                                        <span className="msg-thread-time">
                                            {relativeLabel(s.last_message_at)}
                                        </span>
                                    </div>
                                    <span className="msg-thread-case">{s.case_title}</span>
                                    <span className="msg-thread-preview">
                                        {s.last_message_preview || t("noMessagesYet", "No messages yet")}
                                    </span>
                                </div>
                                {s.unread_count > 0 ? (
                                    <span className="msg-badge">{s.unread_count}</span>
                                ) : null}
                            </button>
                        ))
                    )}
                </aside>

                {/* Conversation */}
                <div className="msg-conversation">
                    {activeCaseId == null ? (
                        <div className="msg-placeholder">
                            {t("selectConversation", "Select a conversation to start replying.")}
                        </div>
                    ) : (
                        <>
                            <div className="msg-conv-header">
                                <div className="msg-avatar lg">{initials(thread?.client_name)}</div>
                                <div>
                                    <strong>{thread?.client_name || t("client", "Client")}</strong>
                                    <span className="msg-conv-case">{thread?.case_title}</span>
                                </div>
                            </div>

                            <div className="msg-canvas" ref={scrollRef}>
                                {threadLoading && !thread ? (
                                    <p className="msg-center">{t("loading", "Loading…")}</p>
                                ) : (thread?.messages.length ?? 0) === 0 ? (
                                    <p className="msg-center">
                                        {t(
                                            "startReply",
                                            "No messages yet. Send the first message to your client."
                                        )}
                                    </p>
                                ) : (
                                    grouped.map((group) => (
                                        <div key={group.day} className="msg-group">
                                            <div className="msg-day">
                                                {dayLabel(group.items[0].created_at)}
                                            </div>
                                            {group.items.map((m) => (
                                                <div
                                                    key={m.id}
                                                    className={`msg-bubble-row${m.is_mine ? " mine" : ""}`}
                                                >
                                                    <div className="msg-bubble">
                                                        {!m.is_mine ? (
                                                            <span className="msg-sender">
                                                                {m.sender_name ||
                                                                    t("client", "Client")}
                                                            </span>
                                                        ) : null}
                                                        {m.body ? <p>{m.body}</p> : null}
                                                        {m.attachment_filename ? (
                                                            <button
                                                                type="button"
                                                                className="msg-attachment"
                                                                onClick={() => void openAttachment(m)}
                                                            >
                                                                <span className="msg-attach-icon">
                                                                    📎
                                                                </span>
                                                                <span className="msg-attach-name">
                                                                    {m.attachment_filename}
                                                                </span>
                                                            </button>
                                                        ) : null}
                                                        <span className="msg-time">
                                                            {timeLabel(m.created_at)}
                                                            {m.is_mine
                                                                ? m.read_at
                                                                    ? " · Read"
                                                                    : " · Sent"
                                                                : ""}
                                                        </span>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    ))
                                )}
                            </div>

                            <div className="msg-composer">
                                <textarea
                                    placeholder={t("typeReply", "Type your reply…")}
                                    value={draft}
                                    onChange={(e) => setDraft(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" && !e.shiftKey) {
                                            e.preventDefault();
                                            void handleSend();
                                        }
                                    }}
                                />
                                <div className="msg-composer-actions">
                                    <button
                                        type="button"
                                        className="msg-attach-btn"
                                        onClick={() => fileInputRef.current?.click()}
                                        disabled={sending}
                                        title={t("attachFile", "Attach a file")}
                                    >
                                        📎
                                    </button>
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        hidden
                                        onChange={handleFile}
                                    />
                                    <button
                                        type="button"
                                        className="msg-send-btn"
                                        onClick={() => void handleSend()}
                                        disabled={sending || !draft.trim()}
                                    >
                                        {sending ? t("sending", "Sending…") : t("send", "Send")}
                                    </button>
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </section>
    );
}

const MSG_STYLES = `
.msg-page { display: flex; flex-direction: column; gap: 16px; height: 100%; }
.msg-header { display: flex; justify-content: space-between; align-items: flex-start; }
.msg-title { font-size: 22px; font-weight: 700; margin: 0; }
.msg-subtitle { margin: 4px 0 0; opacity: .7; font-size: 14px; }
.msg-refresh { padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border, #d8e2e7);
  background: transparent; cursor: pointer; font-size: 13px; }
.msg-error { background: #ffdad6; color: #93000a; padding: 10px 14px; border-radius: 8px; font-size: 14px; }
.msg-layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; flex: 1; min-height: 480px; }
.msg-threads { border: 1px solid var(--border, #d8e2e7); border-radius: 12px; overflow-y: auto;
  background: var(--panel, #fff); }
.msg-empty-list { padding: 24px; text-align: center; opacity: .6; font-size: 14px; }
.msg-thread-row { width: 100%; display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px;
  border: none; border-bottom: 1px solid var(--border, #eef2f4); background: transparent;
  cursor: pointer; text-align: left; }
.msg-thread-row:hover { background: var(--panel-soft, #f8fbfc); }
.msg-thread-row.active { background: var(--primary-soft, #e4eef4); }
.msg-avatar { width: 40px; height: 40px; border-radius: 999px; background: #cde6d1; color: #1b1c19;
  display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; flex-shrink: 0; }
.msg-avatar.lg { width: 44px; height: 44px; }
.msg-thread-body { flex: 1; min-width: 0; }
.msg-thread-top { display: flex; justify-content: space-between; gap: 8px; }
.msg-thread-top strong { font-size: 14px; }
.msg-thread-time { font-size: 11px; opacity: .55; flex-shrink: 0; }
.msg-thread-case { display: block; font-size: 12px; opacity: .65; margin: 2px 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.msg-thread-preview { display: block; font-size: 12px; opacity: .55;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.msg-badge { background: #ba1a1a; color: #fff; font-size: 11px; font-weight: 700;
  min-width: 20px; height: 20px; border-radius: 999px; display: flex; align-items: center;
  justify-content: center; padding: 0 6px; flex-shrink: 0; }
.msg-conversation { border: 1px solid var(--border, #d8e2e7); border-radius: 12px;
  display: flex; flex-direction: column; background: var(--panel, #fff); overflow: hidden; }
.msg-placeholder { margin: auto; opacity: .55; font-size: 14px; }
.msg-conv-header { display: flex; gap: 12px; align-items: center; padding: 16px 20px;
  border-bottom: 1px solid var(--border, #eef2f4); }
.msg-conv-header strong { display: block; font-size: 15px; }
.msg-conv-case { font-size: 12px; opacity: .6; }
.msg-canvas { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 8px; }
.msg-center { margin: auto; opacity: .55; font-size: 14px; text-align: center; max-width: 320px; }
.msg-group { display: flex; flex-direction: column; gap: 8px; }
.msg-day { align-self: center; font-size: 11px; opacity: .55; background: var(--panel-soft, #f0eee9);
  padding: 3px 10px; border-radius: 999px; margin: 6px 0; }
.msg-bubble-row { display: flex; }
.msg-bubble-row.mine { justify-content: flex-end; }
.msg-bubble { max-width: 72%; background: var(--panel-soft, #eae8e3); padding: 10px 14px;
  border-radius: 14px; border-bottom-left-radius: 4px; font-size: 14px; }
.msg-bubble-row.mine .msg-bubble { background: #1f4c6b; color: #fff;
  border-bottom-left-radius: 14px; border-bottom-right-radius: 4px; }
.msg-bubble p { margin: 0; white-space: pre-wrap; word-break: break-word; }
.msg-sender { display: block; font-size: 11px; font-weight: 700; opacity: .7; margin-bottom: 3px; }
.msg-time { display: block; font-size: 10px; opacity: .55; margin-top: 5px; }
.msg-attachment { display: flex; align-items: center; gap: 8px; margin-top: 6px; padding: 8px 10px;
  background: rgba(0,0,0,.06); border: none; border-radius: 8px; cursor: pointer; font-size: 13px;
  color: inherit; max-width: 240px; }
.msg-bubble-row.mine .msg-attachment { background: rgba(255,255,255,.18); }
.msg-attach-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.msg-composer { border-top: 1px solid var(--border, #eef2f4); padding: 12px 16px;
  display: flex; flex-direction: column; gap: 8px; }
.msg-composer textarea { width: 100%; resize: none; min-height: 52px; border: 1px solid var(--border, #d8e2e7);
  border-radius: 10px; padding: 10px 12px; font: inherit; font-size: 14px; background: transparent; }
.msg-composer-actions { display: flex; justify-content: space-between; align-items: center; }
.msg-attach-btn { background: transparent; border: 1px solid var(--border, #d8e2e7);
  border-radius: 8px; width: 38px; height: 38px; cursor: pointer; font-size: 16px; }
.msg-send-btn { background: #1f4c6b; color: #fff; border: none; border-radius: 8px;
  padding: 10px 22px; cursor: pointer; font-size: 14px; font-weight: 600; }
.msg-send-btn:disabled, .msg-attach-btn:disabled { opacity: .5; cursor: not-allowed; }
@media (max-width: 900px) { .msg-layout { grid-template-columns: 1fr; } }
`;
