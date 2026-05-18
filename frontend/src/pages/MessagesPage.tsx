import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { api } from "../lib/api";
import { useMessageSocket } from "../lib/useMessageSocket";
import type { CaseMessage, CaseMessageThread, CaseMessageThreadSummary } from "../types";

// Polling cadence used only as a fallback when the WebSocket is down.
const THREAD_POLL_MS = 8000;
const TYPING_TIMEOUT_MS = 4000;

/** A locally-created message awaiting server confirmation. */
type OutgoingMessage = CaseMessage & {
    _localId: string;
    _status: "sending" | "failed";
    _file?: File;
    _localUrl?: string;
};

type AnyMessage = CaseMessage | OutgoingMessage;

function isOutgoing(m: AnyMessage): m is OutgoingMessage {
    return "_localId" in m;
}

function isImage(type?: string | null): boolean {
    return !!type && type.startsWith("image/");
}

function isVideo(type?: string | null): boolean {
    return !!type && type.startsWith("video/");
}

function formatBytes(bytes?: number | null): string {
    if (!bytes || bytes <= 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Inline attachment: renders image/video previews like a chat app,
 *  falls back to a download chip for other file types. */
function MessageAttachment({
    message,
    token,
    caseId,
    localUrl,
    onImageReady,
    onOpenImage,
}: {
    message: AnyMessage;
    token: string;
    caseId: number;
    /** Object URL already available locally (optimistic send). */
    localUrl?: string;
    /** Reports a resolved image URL so the page can build a gallery. */
    onImageReady?: (key: string, url: string) => void;
    /** Opens the shared gallery lightbox at this image. */
    onOpenImage?: (key: string) => void;
}) {
    const [url, setUrl] = useState<string | null>(localUrl ?? null);
    const [failed, setFailed] = useState(false);
    const media = isImage(message.attachment_content_type) || isVideo(message.attachment_content_type);
    const isImg = isImage(message.attachment_content_type);
    const galleryKey = isOutgoing(message) ? message._localId : `m${message.id}`;

    useEffect(() => {
        if (localUrl) {
            setUrl(localUrl);
            if (isImg) onImageReady?.(galleryKey, localUrl);
            return;
        }
        if (!media || isOutgoing(message)) return;
        let revoked = false;
        let made: string | null = null;
        api
            .messageAttachmentUrl(token, caseId, message.id)
            .then((objectUrl) => {
                if (revoked) {
                    URL.revokeObjectURL(objectUrl);
                    return;
                }
                made = objectUrl;
                setUrl(objectUrl);
                if (isImg) onImageReady?.(galleryKey, objectUrl);
            })
            .catch(() => setFailed(true));
        return () => {
            revoked = true;
            if (made) URL.revokeObjectURL(made);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [media, token, caseId, localUrl]);

    async function openDownload() {
        try {
            const objectUrl =
                localUrl ?? (await api.messageAttachmentUrl(token, caseId, (message as CaseMessage).id));
            window.open(objectUrl, "_blank", "noopener,noreferrer");
        } catch {
            setFailed(true);
        }
    }

    if (media && !failed) {
        if (!url) {
            return <div className="msg-media-loading">{message.attachment_filename}…</div>;
        }
        if (isImg) {
            return (
                <button
                    type="button"
                    className="msg-media-link"
                    onClick={() => onOpenImage?.(galleryKey)}
                    aria-label={message.attachment_filename || "Open image"}
                >
                    <img className="msg-media-img" src={url} alt={message.attachment_filename || "image"} />
                </button>
            );
        }
        return (
            <video className="msg-media-video" src={url} controls preload="metadata">
                {message.attachment_filename}
            </video>
        );
    }

    return (
        <button type="button" className="msg-attachment" onClick={() => void openDownload()}>
            <span className="msg-attach-icon">📎</span>
            <span className="msg-attach-name">{message.attachment_filename}</span>
            <span className="msg-attach-size">{formatBytes(message.attachment_size)}</span>
        </button>
    );
}

/** Shared gallery lightbox: blurred backdrop, prev/next across all
 *  thread images, keyboard nav, download. */
function GalleryLightbox({
    images,
    index,
    onClose,
    onIndex,
}: {
    images: Array<{ key: string; url: string; name: string }>;
    index: number;
    onClose: () => void;
    onIndex: (i: number) => void;
}) {
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
            else if (e.key === "ArrowRight") onIndex(Math.min(index + 1, images.length - 1));
            else if (e.key === "ArrowLeft") onIndex(Math.max(index - 1, 0));
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [index, images.length, onClose, onIndex]);

    const current = images[index];
    if (!current) return null;

    return (
        <div className="msg-lightbox" role="dialog" aria-modal="true" onClick={onClose}>
            <button type="button" className="msg-lightbox-close" onClick={onClose} aria-label="Close">
                ✕
            </button>
            <a
                className="msg-lightbox-download"
                href={current.url}
                download={current.name || "image"}
                onClick={(e) => e.stopPropagation()}
                aria-label="Download"
                title="Download"
            >
                ⤓
            </a>
            {index > 0 ? (
                <button
                    type="button"
                    className="msg-lightbox-nav prev"
                    onClick={(e) => {
                        e.stopPropagation();
                        onIndex(index - 1);
                    }}
                    aria-label="Previous"
                >
                    ‹
                </button>
            ) : null}
            {index < images.length - 1 ? (
                <button
                    type="button"
                    className="msg-lightbox-nav next"
                    onClick={(e) => {
                        e.stopPropagation();
                        onIndex(index + 1);
                    }}
                    aria-label="Next"
                >
                    ›
                </button>
            ) : null}
            <img
                className="msg-lightbox-img"
                src={current.url}
                alt={current.name}
                onClick={(e) => e.stopPropagation()}
            />
            {images.length > 1 ? (
                <div className="msg-lightbox-count" onClick={(e) => e.stopPropagation()}>
                    {index + 1} / {images.length}
                </div>
            ) : null}
        </div>
    );
}

/** On-demand AI insight for a document shared in chat. */
function AttachmentInsight({
    token,
    caseId,
    messageId,
}: {
    token: string;
    caseId: number;
    messageId: number;
}) {
    const [open, setOpen] = useState(false);
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<{
        document_type?: string | null;
        summary?: string | null;
        key_points: string[];
        parties: string[];
    } | null>(null);

    async function run() {
        if (data) {
            setOpen((o) => !o);
            return;
        }
        setLoading(true);
        try {
            const res = await api.aiAnalyzeAttachment(token, caseId, messageId);
            setData(res);
            setOpen(true);
        } catch {
            setData({ summary: "Unable to analyze this attachment.", key_points: [], parties: [] });
            setOpen(true);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="msg-insight">
            <button type="button" className="msg-insight-btn" onClick={() => void run()} disabled={loading}>
                {loading ? "Analyzing…" : "✨ Analyze document"}
            </button>
            {open && data ? (
                <div className="msg-insight-card">
                    {data.document_type ? (
                        <span className="msg-insight-type">{data.document_type}</span>
                    ) : null}
                    {data.summary ? <p>{data.summary}</p> : null}
                    {data.parties.length ? (
                        <p>
                            <strong>Parties:</strong> {data.parties.join(", ")}
                        </p>
                    ) : null}
                    {data.key_points.length ? (
                        <ul>
                            {data.key_points.map((k, i) => (
                                <li key={i}>{k}</li>
                            ))}
                        </ul>
                    ) : null}
                </div>
            ) : null}
        </div>
    );
}

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
    const [outgoing, setOutgoing] = useState<OutgoingMessage[]>([]);
    const [threadLoading, setThreadLoading] = useState(false);
    const [draft, setDraft] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [queue, setQueue] = useState<Array<{ id: string; file: File; url?: string }>>([]);
    const [dragOver, setDragOver] = useState(false);
    const [peerTyping, setPeerTyping] = useState(false);
    const [showJump, setShowJump] = useState(false);
    const [gallery, setGallery] = useState<{ keys: string[]; index: number } | null>(null);

    // AI assist
    const [aiBusy, setAiBusy] = useState<null | "suggest" | "summarize">(null);
    const [suggestions, setSuggestions] = useState<string[]>([]);
    const [summary, setSummary] = useState<string | null>(null);
    const [piiPrompt, setPiiPrompt] = useState<
        null | { items: Array<{ type: string; value: string }>; proceed: () => void }
    >(null);

    const activeCaseRef = useRef<number | null>(null);
    const lastSeenIdRef = useRef<number | null>(null);
    const firstUnreadIdRef = useRef<number | null>(null);
    const galleryUrls = useRef<Map<string, { url: string; name: string }>>(new Map());
    const atBottomRef = useRef(true);
    const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastTypingSent = useRef(0);

    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const scrollRef = useRef<HTMLDivElement | null>(null);

    const MAX_MB = 15;

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
                // Mark the unread boundary: first inbound message we hadn't seen.
                const firstUnread = data.messages.find((m) => !m.is_mine && !m.read_at);
                firstUnreadIdRef.current = firstUnread ? firstUnread.id : null;
                setThread(data);
                setOutgoing([]);
                lastSeenIdRef.current =
                    data.messages[data.messages.length - 1]?.id ?? null;
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

    // Append a server message (from WS or polling), de-duped, and clear any
    // optimistic placeholder it confirms.
    const ingestMessage = useCallback((raw: Record<string, unknown>) => {
        const msg = raw as unknown as CaseMessage;
        setThread((prev) => {
            if (!prev) return prev;
            if (prev.messages.some((m) => m.id === msg.id)) return prev;
            return { ...prev, messages: [...prev.messages, msg] };
        });
        // Drop optimistic copies that match (mine, same body/filename).
        setOutgoing((prev) =>
            prev.filter(
                (o) =>
                    !(
                        o._status === "sending" &&
                        o.body === msg.body &&
                        (o.attachment_filename ?? null) === (msg.attachment_filename ?? null)
                    )
            )
        );
        lastSeenIdRef.current = Math.max(lastSeenIdRef.current ?? 0, msg.id);
    }, []);

    // Delta poll — fallback only; merges anything WS missed.
    const pollDelta = useCallback(async () => {
        const caseId = activeCaseRef.current;
        if (!token || caseId == null) return;
        try {
            const data = await api.getMessageThread(token, caseId);
            if (activeCaseRef.current !== caseId) return;
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
        } catch {
            /* keep last good thread */
        }
    }, [token]);

    useEffect(() => {
        activeCaseRef.current = activeCaseId;
    }, [activeCaseId]);

    // Live socket. Falls back to polling while not "open".
    const { status: wsStatus, sendTyping } = useMessageSocket({
        token,
        caseId: activeCaseId,
        onMessage: ingestMessage,
        onTyping: () => {
            setPeerTyping(true);
            if (typingTimer.current) clearTimeout(typingTimer.current);
            typingTimer.current = setTimeout(() => setPeerTyping(false), TYPING_TIMEOUT_MS);
        },
    });

    useEffect(() => {
        void loadThreads();
        const id = window.setInterval(() => void loadThreads(), 20000);
        return () => window.clearInterval(id);
    }, [loadThreads]);

    useEffect(() => {
        if (activeCaseId != null) void loadThread(activeCaseId);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeCaseId]);

    // Poll only as a safety net when the socket is not connected.
    useEffect(() => {
        if (activeCaseId == null || wsStatus === "open") return;
        const id = window.setInterval(() => void pollDelta(), THREAD_POLL_MS);
        return () => window.clearInterval(id);
    }, [activeCaseId, wsStatus, pollDelta]);

    const allMessages = useMemo<AnyMessage[]>(
        () => [...(thread?.messages ?? []), ...outgoing],
        [thread?.messages, outgoing]
    );

    // Smart auto-scroll: only stick to bottom if the user is already there.
    useEffect(() => {
        const el = scrollRef.current;
        if (!el) return;
        if (atBottomRef.current) {
            el.scrollTop = el.scrollHeight;
            setShowJump(false);
        } else {
            setShowJump(true);
        }
    }, [allMessages.length]);

    function onCanvasScroll() {
        const el = scrollRef.current;
        if (!el) return;
        const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
        atBottomRef.current = distance < 80;
        if (atBottomRef.current) setShowJump(false);
    }

    function jumpToBottom() {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
        atBottomRef.current = true;
        setShowJump(false);
    }

    const grouped = useMemo(() => {
        const groups: Array<{ day: string; items: AnyMessage[] }> = [];
        for (const m of allMessages) {
            const key = new Date(m.created_at).toDateString();
            const last = groups[groups.length - 1];
            if (last && last.day === key) last.items.push(m);
            else groups.push({ day: key, items: [m] });
        }
        return groups;
    }, [allMessages]);

    // ── Attachment queue ────────────────────────────────────────────────
    function enqueueFiles(files: File[]) {
        const valid: Array<{ id: string; file: File; url?: string }> = [];
        for (const file of files) {
            if (file.size > MAX_MB * 1024 * 1024) {
                setError(`"${file.name}" is too large (max ${MAX_MB} MB).`);
                continue;
            }
            const isMedia = file.type.startsWith("image/") || file.type.startsWith("video/");
            valid.push({
                id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
                file,
                url: isMedia ? URL.createObjectURL(file) : undefined,
            });
        }
        if (valid.length) {
            setError(null);
            setQueue((prev) => [...prev, ...valid]);
        }
    }

    function removeQueued(id: string) {
        setQueue((prev) => {
            const found = prev.find((q) => q.id === id);
            if (found?.url) URL.revokeObjectURL(found.url);
            return prev.filter((q) => q.id !== id);
        });
    }

    // ── Sending (optimistic) ────────────────────────────────────────────
    async function deliver(
        caseId: number,
        body: string,
        file: File | undefined,
        localUrl: string | undefined,
        localId: string
    ) {
        if (!token) return;
        try {
            if (file) await api.sendMessageAttachment(token, caseId, file, body);
            else await api.sendMessage(token, caseId, body);
            // Server echoes via WS (ingestMessage clears the placeholder).
            // If WS is down, reconcile here.
            if (wsStatus !== "open") {
                setOutgoing((prev) => prev.filter((o) => o._localId !== localId));
                void pollDelta();
            }
            void loadThreads();
        } catch (caught) {
            setOutgoing((prev) =>
                prev.map((o) =>
                    o._localId === localId ? { ...o, _status: "failed" } : o
                )
            );
            setError(caught instanceof Error ? caught.message : "Unable to send message.");
        }
    }

    async function handleSend() {
        const body = draft.trim();
        if (activeCaseId == null) return;
        if (!body && queue.length === 0) return;

        // Pre-send PII guard (text only — attachments aren't scanned here).
        if (body && token) {
            try {
                const scan = await api.aiScanPii(token, body);
                if (scan.has_pii) {
                    setPiiPrompt({ items: scan.pii_items, proceed: () => doSend() });
                    return;
                }
            } catch {
                /* never block sending on a scan failure */
            }
        }
        doSend();
    }

    function doSend() {
        const body = draft.trim();
        if (activeCaseId == null) return;
        if (!body && queue.length === 0) return;
        setPiiPrompt(null);

        const caseId = activeCaseId;
        const now = new Date().toISOString();

        if (queue.length === 0) {
            const localId = `t-${Date.now()}`;
            setOutgoing((prev) => [
                ...prev,
                {
                    id: -Date.now(),
                    case_id: caseId,
                    sender_role: "lawyer",
                    sender_name: null,
                    body,
                    attachment_filename: null,
                    attachment_content_type: null,
                    attachment_size: null,
                    is_mine: true,
                    read_at: null,
                    created_at: now,
                    _localId: localId,
                    _status: "sending",
                } as OutgoingMessage,
            ]);
            void deliver(caseId, body, undefined, undefined, localId);
        } else {
            // First file carries the caption; the rest send bare.
            queue.forEach((item, idx) => {
                const localId = `t-${Date.now()}-${idx}`;
                const caption = idx === 0 ? body : "";
                setOutgoing((prev) => [
                    ...prev,
                    {
                        id: -(Date.now() + idx),
                        case_id: caseId,
                        sender_role: "lawyer",
                        sender_name: null,
                        body: caption,
                        attachment_filename: item.file.name,
                        attachment_content_type: item.file.type || null,
                        attachment_size: item.file.size,
                        is_mine: true,
                        read_at: null,
                        created_at: now,
                        _localId: localId,
                        _status: "sending",
                        _file: item.file,
                        _localUrl: item.url,
                    } as OutgoingMessage,
                ]);
                void deliver(caseId, caption, item.file, item.url, localId);
            });
        }

        setDraft("");
        setQueue([]);
        atBottomRef.current = true;
    }

    function retry(localId: string) {
        const item = outgoing.find((o) => o._localId === localId);
        if (!item || activeCaseId == null) return;
        setOutgoing((prev) =>
            prev.map((o) => (o._localId === localId ? { ...o, _status: "sending" } : o))
        );
        void deliver(activeCaseId, item.body, item._file, item._localUrl, localId);
    }

    function discardFailed(localId: string) {
        setOutgoing((prev) => prev.filter((o) => o._localId !== localId));
    }

    async function handleSuggest() {
        if (!token || activeCaseId == null || aiBusy) return;
        setAiBusy("suggest");
        setSummary(null);
        try {
            const res = await api.aiSuggestReplies(token, activeCaseId);
            setSuggestions(res.suggestions);
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "AI suggestions failed.");
        } finally {
            setAiBusy(null);
        }
    }

    async function handleSummarize() {
        if (!token || activeCaseId == null || aiBusy) return;
        setAiBusy("summarize");
        setSuggestions([]);
        try {
            const res = await api.aiSummarizeThread(token, activeCaseId);
            setSummary(res.summary);
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "AI summary failed.");
        } finally {
            setAiBusy(null);
        }
    }

    function useSuggestion(text: string) {
        setDraft((d) => (d.trim() ? `${d}\n${text}` : text));
        setSuggestions([]);
    }

    // ── Input: paste / pick / drop ──────────────────────────────────────
    function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
        const files = Array.from(e.target.files ?? []);
        e.target.value = "";
        if (files.length) enqueueFiles(files);
    }

    function handlePaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
        const items = e.clipboardData?.items;
        if (!items) return;
        const picked: File[] = [];
        for (const item of items) {
            if (item.kind === "file" && item.type.startsWith("image/")) {
                const blob = item.getAsFile();
                if (!blob) continue;
                const ext = blob.type.split("/")[1] || "png";
                const stamp = new Date().toISOString().replace(/[:.]/g, "-");
                picked.push(
                    blob instanceof File && blob.name
                        ? blob
                        : new File([blob], `pasted-${stamp}.${ext}`, { type: blob.type })
                );
            }
        }
        if (picked.length) {
            e.preventDefault();
            enqueueFiles(picked);
        }
    }

    function handleDrop(e: React.DragEvent) {
        e.preventDefault();
        setDragOver(false);
        const files = Array.from(e.dataTransfer?.files ?? []);
        if (files.length) enqueueFiles(files);
    }

    function notifyTyping() {
        const nowMs = Date.now();
        if (nowMs - lastTypingSent.current > 2000) {
            lastTypingSent.current = nowMs;
            sendTyping();
        }
    }

    // ── Gallery wiring ──────────────────────────────────────────────────
    const registerImage = useCallback((key: string, url: string) => {
        const name =
            galleryUrls.current.get(key)?.name ?? "image";
        galleryUrls.current.set(key, { url, name });
    }, []);

    const orderedImageKeys = useMemo(
        () =>
            allMessages
                .filter((m) => isImage(m.attachment_content_type))
                .map((m) => (isOutgoing(m) ? m._localId : `m${m.id}`)),
        [allMessages]
    );

    function openGallery(key: string) {
        const idx = orderedImageKeys.indexOf(key);
        if (idx >= 0) setGallery({ keys: orderedImageKeys, index: idx });
    }

    const galleryImages = useMemo(() => {
        if (!gallery) return [];
        return gallery.keys
            .map((k) => {
                const entry = galleryUrls.current.get(k);
                return entry ? { key: k, url: entry.url, name: entry.name } : null;
            })
            .filter(Boolean) as Array<{ key: string; url: string; name: string }>;
    }, [gallery]);

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
                <span className="msg-live" title={t("liveHint", "Messages update automatically")}>
                    <span className="msg-live-dot" />
                    {t("live", "Live")}
                </span>
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

                            <div
                                className={`msg-canvas-wrap${dragOver ? " drag-over" : ""}`}
                                onDragOver={(e) => {
                                    e.preventDefault();
                                    setDragOver(true);
                                }}
                                onDragLeave={(e) => {
                                    if (e.currentTarget === e.target) setDragOver(false);
                                }}
                                onDrop={handleDrop}
                            >
                                <div className="msg-canvas" ref={scrollRef} onScroll={onCanvasScroll}>
                                    {threadLoading && !thread ? (
                                        <p className="msg-center">{t("loading", "Loading…")}</p>
                                    ) : allMessages.length === 0 ? (
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
                                                {group.items.map((m) => {
                                                    const out = isOutgoing(m);
                                                    const showDivider =
                                                        !out &&
                                                        firstUnreadIdRef.current === (m as CaseMessage).id;
                                                    return (
                                                        <div key={out ? m._localId : m.id}>
                                                            {showDivider ? (
                                                                <div className="msg-unread-divider">
                                                                    <span>
                                                                        {t("newMessages", "New messages")}
                                                                    </span>
                                                                </div>
                                                            ) : null}
                                                            <div
                                                                className={`msg-bubble-row${m.is_mine ? " mine" : ""}`}
                                                            >
                                                                <div
                                                                    className={`msg-bubble${
                                                                        out && m._status === "failed"
                                                                            ? " failed"
                                                                            : out && m._status === "sending"
                                                                              ? " sending"
                                                                              : ""
                                                                    }`}
                                                                >
                                                                    {!m.is_mine ? (
                                                                        <span className="msg-sender">
                                                                            {m.sender_name ||
                                                                                t("client", "Client")}
                                                                        </span>
                                                                    ) : null}
                                                                    {m.attachment_filename && token && activeCaseId != null ? (
                                                                        <MessageAttachment
                                                                            message={m}
                                                                            token={token}
                                                                            caseId={activeCaseId}
                                                                            localUrl={out ? m._localUrl : undefined}
                                                                            onImageReady={registerImage}
                                                                            onOpenImage={openGallery}
                                                                        />
                                                                    ) : null}
                                                                    {m.attachment_filename &&
                                                                    !out &&
                                                                    token &&
                                                                    activeCaseId != null ? (
                                                                        <AttachmentInsight
                                                                            token={token}
                                                                            caseId={activeCaseId}
                                                                            messageId={(m as CaseMessage).id}
                                                                        />
                                                                    ) : null}
                                                                    {m.body ? <p>{m.body}</p> : null}
                                                                    <span className="msg-time">
                                                                        {timeLabel(m.created_at)}
                                                                        {out && m._status === "sending"
                                                                            ? " · Sending…"
                                                                            : out && m._status === "failed"
                                                                              ? ""
                                                                              : m.is_mine
                                                                                ? m.read_at
                                                                                    ? " · Read"
                                                                                    : " · Sent"
                                                                                : ""}
                                                                    </span>
                                                                    {out && m._status === "failed" ? (
                                                                        <span className="msg-failed-actions">
                                                                            {t("failedToSend", "Failed.")}{" "}
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => retry(m._localId)}
                                                                            >
                                                                                {t("retry", "Retry")}
                                                                            </button>
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => discardFailed(m._localId)}
                                                                            >
                                                                                {t("discard", "Discard")}
                                                                            </button>
                                                                        </span>
                                                                    ) : null}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        ))
                                    )}
                                    {peerTyping ? (
                                        <div className="msg-bubble-row">
                                            <div className="msg-bubble msg-typing">
                                                <span /> <span /> <span />
                                            </div>
                                        </div>
                                    ) : null}
                                </div>
                                {showJump ? (
                                    <button
                                        type="button"
                                        className="msg-jump"
                                        onClick={jumpToBottom}
                                    >
                                        ↓ {t("newMessagesShort", "New messages")}
                                    </button>
                                ) : null}
                            </div>

                            {summary ? (
                                <div className="msg-ai-panel">
                                    <div className="msg-ai-panel-head">
                                        <strong>✨ {t("aiSummary", "Conversation summary")}</strong>
                                        <button type="button" onClick={() => setSummary(null)} aria-label="Dismiss">
                                            ✕
                                        </button>
                                    </div>
                                    <p className="msg-ai-summary">{summary}</p>
                                </div>
                            ) : null}
                            {suggestions.length ? (
                                <div className="msg-ai-panel">
                                    <div className="msg-ai-panel-head">
                                        <strong>✨ {t("aiSuggested", "Suggested replies")}</strong>
                                        <button type="button" onClick={() => setSuggestions([])} aria-label="Dismiss">
                                            ✕
                                        </button>
                                    </div>
                                    <div className="msg-ai-suggestions">
                                        {suggestions.map((s, i) => (
                                            <button
                                                key={i}
                                                type="button"
                                                className="msg-ai-suggestion"
                                                onClick={() => useSuggestion(s)}
                                                title={t("insertSuggestion", "Insert into reply box")}
                                            >
                                                {s}
                                            </button>
                                        ))}
                                    </div>
                                    <span className="msg-ai-disclaimer">
                                        {t(
                                            "aiDisclaimer",
                                            "AI-drafted — review and edit before sending."
                                        )}
                                    </span>
                                </div>
                            ) : null}

                            <div className="msg-ai-toolbar">
                                <button
                                    type="button"
                                    className="msg-ai-btn"
                                    onClick={() => void handleSuggest()}
                                    disabled={aiBusy !== null}
                                >
                                    {aiBusy === "suggest"
                                        ? t("thinking", "Thinking…")
                                        : `✨ ${t("suggestReplies", "Suggest replies")}`}
                                </button>
                                <button
                                    type="button"
                                    className="msg-ai-btn"
                                    onClick={() => void handleSummarize()}
                                    disabled={aiBusy !== null}
                                >
                                    {aiBusy === "summarize"
                                        ? t("summarizing", "Summarizing…")
                                        : `✨ ${t("summarize", "Summarize")}`}
                                </button>
                            </div>

                            <div className="msg-composer">
                                {queue.length ? (
                                    <div className="msg-queue">
                                        {queue.map((q) => (
                                            <div key={q.id} className="msg-pending">
                                                {q.url && q.file.type.startsWith("image/") ? (
                                                    <img className="msg-pending-thumb" src={q.url} alt="" />
                                                ) : q.url && q.file.type.startsWith("video/") ? (
                                                    <video className="msg-pending-thumb" src={q.url} muted />
                                                ) : (
                                                    <span className="msg-pending-icon">📎</span>
                                                )}
                                                <span className="msg-pending-name">
                                                    {q.file.name}
                                                    <em>{formatBytes(q.file.size)}</em>
                                                </span>
                                                <button
                                                    type="button"
                                                    className="msg-pending-remove"
                                                    onClick={() => removeQueued(q.id)}
                                                    aria-label={t("remove", "Remove")}
                                                >
                                                    ✕
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                ) : null}
                                <textarea
                                    onPaste={handlePaste}
                                    placeholder={
                                        queue.length
                                            ? t("addCaption", "Add a caption…")
                                            : t("typeReply", "Paste a screenshot, drop files, or type…")
                                    }
                                    value={draft}
                                    onChange={(e) => {
                                        setDraft(e.target.value);
                                        notifyTyping();
                                    }}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" && !e.shiftKey) {
                                            e.preventDefault();
                                            handleSend();
                                        }
                                    }}
                                />
                                <div className="msg-composer-actions">
                                    <button
                                        type="button"
                                        className="msg-attach-btn"
                                        onClick={() => fileInputRef.current?.click()}
                                        title={t("attachFile", "Attach files")}
                                    >
                                        📎
                                    </button>
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept="image/*,video/*,application/pdf"
                                        multiple
                                        hidden
                                        onChange={handleFile}
                                    />
                                    <button
                                        type="button"
                                        className="msg-send-btn"
                                        onClick={() => handleSend()}
                                        disabled={!draft.trim() && queue.length === 0}
                                    >
                                        {t("send", "Send")}
                                    </button>
                                </div>
                            </div>
                        </>
                    )}
                    {gallery && galleryImages.length ? (
                        <GalleryLightbox
                            images={galleryImages}
                            index={gallery.index}
                            onClose={() => setGallery(null)}
                            onIndex={(i) => setGallery((g) => (g ? { ...g, index: i } : g))}
                        />
                    ) : null}
                    {piiPrompt ? (
                        <div
                            className="msg-lightbox"
                            role="dialog"
                            aria-modal="true"
                            onClick={() => setPiiPrompt(null)}
                        >
                            <div
                                className="msg-pii-modal"
                                onClick={(e) => e.stopPropagation()}
                            >
                                <strong>⚠️ {t("piiTitle", "Sensitive data detected")}</strong>
                                <p>
                                    {t(
                                        "piiBody",
                                        "This message appears to contain personal data:"
                                    )}
                                </p>
                                <ul className="msg-pii-list">
                                    {piiPrompt.items.slice(0, 6).map((p, i) => (
                                        <li key={i}>
                                            <em>{p.type}</em>: {p.value}
                                        </li>
                                    ))}
                                </ul>
                                <div className="msg-pii-actions">
                                    <button
                                        type="button"
                                        className="as-button"
                                        onClick={() => setPiiPrompt(null)}
                                    >
                                        {t("review", "Review it")}
                                    </button>
                                    <button
                                        type="button"
                                        className="msg-send-btn"
                                        onClick={() => piiPrompt.proceed()}
                                    >
                                        {t("sendAnyway", "Send anyway")}
                                    </button>
                                </div>
                            </div>
                        </div>
                    ) : null}
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
.msg-live { display: inline-flex; align-items: center; gap: 7px; font-size: 12px;
  font-weight: 600; color: #2e7d32; opacity: .85; }
.msg-live-dot { width: 8px; height: 8px; border-radius: 999px; background: #2e7d32;
  animation: msgLivePulse 1.8s ease-in-out infinite; }
@keyframes msgLivePulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
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
.msg-conversation { position: relative; border: 1px solid var(--border, #d8e2e7);
  border-radius: 12px; display: flex; flex-direction: column;
  background: var(--panel, #fff); overflow: hidden; }
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
.msg-attach-size { font-size: 11px; opacity: .6; flex-shrink: 0; }
.msg-media-link { display: block; margin-top: 4px; padding: 0; border: none;
  background: none; cursor: pointer; }
.msg-media-img, .msg-media-video { display: block; max-width: 280px; max-height: 320px;
  width: auto; border-radius: 10px; cursor: pointer; }
.msg-media-video { cursor: default; background: #000; }
.msg-lightbox { position: fixed; inset: 0; z-index: 1000; display: flex;
  align-items: center; justify-content: center; padding: 32px;
  background: rgba(8, 12, 16, 0.78); backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px); animation: msgLightboxIn 0.16s ease-out; }
.msg-lightbox-img { max-width: 92vw; max-height: 88vh; width: auto; height: auto;
  border-radius: 12px; box-shadow: 0 24px 80px rgba(0,0,0,.55); cursor: default;
  animation: msgLightboxZoom 0.18s cubic-bezier(.2,.8,.2,1); }
.msg-lightbox-close { position: fixed; top: 20px; right: 24px; width: 40px; height: 40px;
  border-radius: 999px; border: none; background: rgba(255,255,255,.14); color: #fff;
  font-size: 18px; cursor: pointer; backdrop-filter: blur(4px); }
.msg-lightbox-close:hover { background: rgba(255,255,255,.26); }
@keyframes msgLightboxIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes msgLightboxZoom { from { transform: scale(.92); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.msg-media-loading { font-size: 13px; opacity: .6; padding: 6px 0; font-style: italic; }
.msg-pending { display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  background: var(--panel-soft, #f0eee9); border-radius: 10px; }
.msg-pending-thumb { width: 44px; height: 44px; object-fit: cover; border-radius: 8px; background: #000; flex-shrink: 0; }
.msg-pending-icon { width: 44px; height: 44px; display: flex; align-items: center;
  justify-content: center; font-size: 20px; background: rgba(0,0,0,.06); border-radius: 8px; flex-shrink: 0; }
.msg-pending-name { flex: 1; min-width: 0; font-size: 13px; display: flex; flex-direction: column;
  overflow: hidden; }
.msg-pending-name { white-space: nowrap; text-overflow: ellipsis; }
.msg-pending-name em { font-style: normal; opacity: .55; font-size: 11px; }
.msg-pending-remove { background: transparent; border: none; cursor: pointer; font-size: 14px;
  opacity: .6; padding: 4px 8px; flex-shrink: 0; }
.msg-pending-remove:hover { opacity: 1; }
.msg-canvas-wrap { position: relative; flex: 1; display: flex; min-height: 0; }
.msg-canvas-wrap.drag-over::after { content: "Drop files to attach"; position: absolute;
  inset: 10px; border: 2px dashed #1f4c6b; border-radius: 12px; display: flex;
  align-items: center; justify-content: center; font-weight: 600; color: #1f4c6b;
  background: rgba(31,76,107,.07); pointer-events: none; z-index: 5; }
.msg-jump { position: absolute; left: 50%; bottom: 14px; transform: translateX(-50%);
  background: #1f4c6b; color: #fff; border: none; border-radius: 999px;
  padding: 7px 16px; font-size: 12px; font-weight: 600; cursor: pointer;
  box-shadow: 0 6px 20px rgba(0,0,0,.25); z-index: 6; }
.msg-unread-divider { display: flex; align-items: center; gap: 10px; margin: 12px 0;
  color: #ba1a1a; font-size: 11px; font-weight: 700; }
.msg-unread-divider::before, .msg-unread-divider::after { content: ""; flex: 1;
  height: 1px; background: rgba(186,26,26,.35); }
.msg-bubble.sending { opacity: .65; }
.msg-bubble.failed { outline: 1px solid #ba1a1a; }
.msg-failed-actions { display: block; margin-top: 6px; font-size: 11px; color: #ba1a1a; }
.msg-failed-actions button { background: none; border: none; color: #1f4c6b;
  font-weight: 700; cursor: pointer; padding: 0 4px; font-size: 11px; }
.msg-typing { display: inline-flex; gap: 4px; padding: 12px 14px; }
.msg-typing span { width: 7px; height: 7px; border-radius: 999px; background: currentColor;
  opacity: .4; animation: msgTyping 1.2s infinite ease-in-out; }
.msg-typing span:nth-child(2) { animation-delay: .15s; }
.msg-typing span:nth-child(3) { animation-delay: .3s; }
@keyframes msgTyping { 0%,60%,100% { opacity: .25; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); } }
.msg-queue { display: flex; flex-direction: column; gap: 6px; }
.msg-lightbox-nav { position: fixed; top: 50%; transform: translateY(-50%);
  width: 46px; height: 46px; border-radius: 999px; border: none;
  background: rgba(255,255,255,.14); color: #fff; font-size: 28px; cursor: pointer;
  backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; }
.msg-lightbox-nav:hover { background: rgba(255,255,255,.26); }
.msg-lightbox-nav.prev { left: 24px; }
.msg-lightbox-nav.next { right: 24px; }
.msg-lightbox-download { position: fixed; top: 20px; right: 74px; width: 40px; height: 40px;
  border-radius: 999px; background: rgba(255,255,255,.14); color: #fff; font-size: 18px;
  display: flex; align-items: center; justify-content: center; text-decoration: none;
  backdrop-filter: blur(4px); }
.msg-lightbox-download:hover { background: rgba(255,255,255,.26); }
.msg-lightbox-count { position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%);
  color: #fff; font-size: 13px; background: rgba(0,0,0,.4); padding: 5px 12px;
  border-radius: 999px; }
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
.msg-ai-toolbar { display: flex; gap: 8px; padding: 8px 16px 0; }
.msg-ai-btn { background: linear-gradient(135deg,#6d4ad8,#3f7be0); color: #fff;
  border: none; border-radius: 999px; padding: 6px 14px; font-size: 12px;
  font-weight: 600; cursor: pointer; }
.msg-ai-btn:disabled { opacity: .55; cursor: progress; }
.msg-ai-panel { margin: 8px 16px 0; border: 1px solid var(--border, #d8e2e7);
  border-radius: 12px; padding: 12px 14px; background: var(--panel-soft, #f6f4ff); }
.msg-ai-panel-head { display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; margin-bottom: 8px; }
.msg-ai-panel-head button { background: none; border: none; cursor: pointer;
  opacity: .55; font-size: 13px; }
.msg-ai-summary { margin: 0; font-size: 13px; white-space: pre-wrap; line-height: 1.5; }
.msg-ai-suggestions { display: flex; flex-direction: column; gap: 6px; }
.msg-ai-suggestion { text-align: left; background: var(--panel, #fff);
  border: 1px solid var(--border, #d8e2e7); border-radius: 10px; padding: 9px 12px;
  font: inherit; font-size: 13px; cursor: pointer; }
.msg-ai-suggestion:hover { border-color: #6d4ad8; }
.msg-ai-disclaimer { display: block; margin-top: 8px; font-size: 11px; opacity: .6; }
.msg-insight { margin-top: 6px; }
.msg-insight-btn { background: none; border: 1px dashed var(--border, #d8e2e7);
  border-radius: 8px; padding: 5px 10px; font-size: 12px; cursor: pointer;
  color: #6d4ad8; }
.msg-insight-card { margin-top: 6px; background: rgba(109,74,216,.06);
  border-radius: 8px; padding: 10px 12px; font-size: 12.5px; }
.msg-insight-card p { margin: 0 0 6px; }
.msg-insight-card ul { margin: 4px 0 0; padding-left: 18px; }
.msg-insight-type { display: inline-block; background: #6d4ad8; color: #fff;
  font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 999px;
  margin-bottom: 6px; text-transform: uppercase; }
.msg-pii-modal { background: var(--panel, #fff); border-radius: 14px; padding: 22px;
  max-width: 440px; width: 90%; }
.msg-pii-modal strong { font-size: 16px; }
.msg-pii-modal p { font-size: 13px; opacity: .8; margin: 8px 0; }
.msg-pii-list { margin: 8px 0 16px; padding-left: 18px; font-size: 13px; }
.msg-pii-list em { font-style: normal; font-weight: 700; color: #ba1a1a; }
.msg-pii-actions { display: flex; gap: 10px; justify-content: flex-end; }
@media (max-width: 900px) { .msg-layout { grid-template-columns: 1fr; } }
`;
