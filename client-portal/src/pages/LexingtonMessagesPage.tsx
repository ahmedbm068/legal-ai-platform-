import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePortal } from "../context/PortalContext";
import { fetchPortalAttachmentObjectUrl, scanPortalMessagePii } from "../lib/api";
import { useMessageSocket } from "../lib/useMessageSocket";
import { formatBytes } from "../portalPresentation";
import type { ClientPortalMessage } from "../types";

// Polling cadence used only as a fallback when the WebSocket is down.
const THREAD_POLL_MS = 8000;
const TYPING_TIMEOUT_MS = 4000;

type OutgoingMessage = ClientPortalMessage & {
    _localId: string;
    _status: "sending" | "failed";
    _file?: File;
    _localUrl?: string;
};

type AnyMessage = ClientPortalMessage | OutgoingMessage;

function isOutgoing(m: AnyMessage): m is OutgoingMessage {
    return "_localId" in m;
}

function isImage(type?: string | null): boolean {
    return !!type && type.startsWith("image/");
}

function isVideo(type?: string | null): boolean {
    return !!type && type.startsWith("video/");
}

/** Inline attachment: image/video render inline, other types as a chip.
 *  Reports resolved image URLs upward so the page can build a gallery. */
function PortalAttachment({
    message,
    token,
    localUrl,
    onImageReady,
    onOpenImage,
}: {
    message: AnyMessage;
    token: string;
    localUrl?: string;
    onImageReady?: (key: string, url: string, name: string) => void;
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
            if (isImg) onImageReady?.(galleryKey, localUrl, message.attachment_filename || "image");
            return;
        }
        if (!media || isOutgoing(message)) return;
        let revoked = false;
        let made: string | null = null;
        fetchPortalAttachmentObjectUrl(token, (message as ClientPortalMessage).id)
            .then((objectUrl) => {
                if (revoked) {
                    URL.revokeObjectURL(objectUrl);
                    return;
                }
                made = objectUrl;
                setUrl(objectUrl);
                if (isImg) onImageReady?.(galleryKey, objectUrl, message.attachment_filename || "image");
            })
            .catch(() => setFailed(true));
        return () => {
            revoked = true;
            if (made) URL.revokeObjectURL(made);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [token, localUrl]);

    if (media && !failed) {
        if (!url) {
            return (
                <div className="bg-surface-container-lowest border border-outline-variant p-4 rounded-xl w-72 text-on-surface-variant font-label-md text-label-md italic">
                    {message.attachment_filename}…
                </div>
            );
        }
        if (isImg) {
            return (
                <button
                    type="button"
                    onClick={() => onOpenImage?.(galleryKey)}
                    aria-label={message.attachment_filename || "Open image"}
                    className="block p-0 border-0 bg-transparent cursor-pointer"
                >
                    <img
                        src={url}
                        alt={message.attachment_filename || "image"}
                        className="max-w-[280px] max-h-[320px] w-auto rounded-xl border border-outline-variant"
                    />
                </button>
            );
        }
        return (
            <video
                src={url}
                controls
                preload="metadata"
                className="max-w-[280px] max-h-[320px] w-auto rounded-xl bg-black"
            />
        );
    }

    return (
        <a
            href={url ?? undefined}
            target="_blank"
            rel="noreferrer noopener"
            onClick={(e) => {
                if (!url) e.preventDefault();
            }}
            className="bg-surface-container-lowest border border-outline-variant p-4 rounded-xl flex items-center gap-x-4 w-72 hover:bg-surface-container-low transition-colors"
        >
            <div className="w-10 h-10 bg-error-container text-error flex items-center justify-center rounded">
                <span className="material-symbols-outlined">
                    {message.attachment_content_type?.includes("pdf") ? "picture_as_pdf" : "attach_file"}
                </span>
            </div>
            <div className="flex-1 overflow-hidden">
                <p className="font-label-md text-label-md text-primary truncate">
                    {message.attachment_filename}
                </p>
                <p className="text-[10px] text-on-surface-variant">
                    {message.attachment_size ? formatBytes(message.attachment_size) : "Attachment"}
                </p>
            </div>
            <span className="material-symbols-outlined text-on-surface-variant">download</span>
        </a>
    );
}

/** Shared gallery lightbox: blurred backdrop, prev/next across all
 *  thread images, keyboard nav, download. */
function PortalGalleryLightbox({
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
        <div
            role="dialog"
            aria-modal="true"
            onClick={onClose}
            className="fixed inset-0 z-[1000] flex items-center justify-center p-8 bg-black/75 backdrop-blur-md"
        >
            <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="material-symbols-outlined fixed top-5 right-6 w-10 h-10 flex items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25 backdrop-blur"
            >
                close
            </button>
            <a
                href={current.url}
                download={current.name || "image"}
                onClick={(e) => e.stopPropagation()}
                aria-label="Download"
                className="material-symbols-outlined fixed top-5 right-20 w-10 h-10 flex items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25 backdrop-blur no-underline"
            >
                download
            </a>
            {index > 0 ? (
                <button
                    type="button"
                    onClick={(e) => {
                        e.stopPropagation();
                        onIndex(index - 1);
                    }}
                    aria-label="Previous"
                    className="material-symbols-outlined fixed left-6 top-1/2 -translate-y-1/2 w-12 h-12 flex items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25 backdrop-blur"
                >
                    chevron_left
                </button>
            ) : null}
            {index < images.length - 1 ? (
                <button
                    type="button"
                    onClick={(e) => {
                        e.stopPropagation();
                        onIndex(index + 1);
                    }}
                    aria-label="Next"
                    className="material-symbols-outlined fixed right-6 top-1/2 -translate-y-1/2 w-12 h-12 flex items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25 backdrop-blur"
                >
                    chevron_right
                </button>
            ) : null}
            <img
                src={current.url}
                alt={current.name}
                onClick={(e) => e.stopPropagation()}
                className="max-w-[92vw] max-h-[88vh] w-auto h-auto rounded-xl shadow-2xl"
            />
            {images.length > 1 ? (
                <div
                    onClick={(e) => e.stopPropagation()}
                    className="fixed bottom-6 left-1/2 -translate-x-1/2 text-white text-sm bg-black/40 px-3 py-1 rounded-full"
                >
                    {index + 1} / {images.length}
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

function dayKey(iso: string): string {
    return new Date(iso).toDateString();
}

function dayLabel(iso: string): string {
    const d = new Date(iso);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Today";
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    return new Intl.DateTimeFormat("en-US", {
        weekday: "long",
        month: "short",
        day: "numeric",
    }).format(d);
}

function timeLabel(iso: string): string {
    return new Intl.DateTimeFormat("en-US", {
        hour: "numeric",
        minute: "2-digit",
    }).format(new Date(iso));
}

export default function LexingtonMessagesPage() {
    const {
        token,
        dashboard,
        selectedCaseId,
        thread,
        threadLoading,
        threadError,
        messageSending,
        loadThread,
        refreshActiveThread,
        sendMessage,
        sendMessageWithAttachment,
    } = usePortal();

    const [draft, setDraft] = useState("");
    const [outgoing, setOutgoing] = useState<OutgoingMessage[]>([]);
    const [queue, setQueue] = useState<Array<{ id: string; file: File; url?: string }>>([]);
    const [dragOver, setDragOver] = useState(false);
    const [peerTyping, setPeerTyping] = useState(false);
    const [showJump, setShowJump] = useState(false);
    const [localError, setLocalError] = useState<string | null>(null);
    const [gallery, setGallery] = useState<{ keys: string[]; index: number } | null>(null);
    const [piiPrompt, setPiiPrompt] = useState<
        null | { items: Array<{ type: string; value: string }> }
    >(null);

    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const scrollRef = useRef<HTMLDivElement | null>(null);
    const atBottomRef = useRef(true);
    const firstUnreadIdRef = useRef<number | null>(null);
    const galleryUrls = useRef<Map<string, { url: string; name: string }>>(new Map());
    const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const lastTypingSent = useRef(0);

    const caseId = selectedCaseId ?? dashboard?.cases[0]?.id ?? null;
    const MAX_MB = 15;

    useEffect(() => {
        void loadThread(caseId);
        setOutgoing([]);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [caseId]);

    useEffect(() => {
        const firstUnread = thread?.messages.find((m) => !m.is_mine && !m.read_at);
        firstUnreadIdRef.current = firstUnread ? firstUnread.id : null;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [caseId, thread?.case_id]);

    const ingestMessage = useCallback(
        (raw: Record<string, unknown>) => {
            const msg = raw as unknown as ClientPortalMessage;
            // Reuse context's silent refresh to fold the new row into `thread`.
            void refreshActiveThread();
            setOutgoing((prev) =>
                prev.filter(
                    (o) =>
                        !(
                            o._status === "sending" &&
                            o.body === (msg.body ?? "") &&
                            (o.attachment_filename ?? null) ===
                                (msg.attachment_filename ?? null)
                        )
                )
            );
        },
        [refreshActiveThread]
    );

    const { status: wsStatus, sendTyping } = useMessageSocket({
        token,
        caseId,
        onMessage: ingestMessage,
        onTyping: () => {
            setPeerTyping(true);
            if (typingTimer.current) clearTimeout(typingTimer.current);
            typingTimer.current = setTimeout(() => setPeerTyping(false), TYPING_TIMEOUT_MS);
        },
    });

    // Poll only as a fallback when the socket is not connected.
    useEffect(() => {
        if (caseId == null || wsStatus === "open") return;
        const id = window.setInterval(() => {
            void refreshActiveThread();
        }, THREAD_POLL_MS);
        return () => window.clearInterval(id);
    }, [caseId, wsStatus, refreshActiveThread]);

    const counsel = thread?.counsel_name ?? "Your legal team";

    const allMessages = useMemo<AnyMessage[]>(
        () => [...(thread?.messages ?? []), ...outgoing],
        [thread?.messages, outgoing]
    );

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
            const key = dayKey(m.created_at);
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
                setLocalError(`"${file.name}" is too large (max ${MAX_MB} MB).`);
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
            setLocalError(null);
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
        body: string,
        file: File | undefined,
        localId: string
    ) {
        const ok = file
            ? await sendMessageWithAttachment(file, body, caseId)
            : await sendMessage(body, caseId);
        if (ok) {
            // Context pushed the confirmed row into `thread`; drop placeholder.
            setOutgoing((prev) => prev.filter((o) => o._localId !== localId));
            if (wsStatus !== "open") void refreshActiveThread();
        } else {
            setOutgoing((prev) =>
                prev.map((o) =>
                    o._localId === localId ? { ...o, _status: "failed" } : o
                )
            );
            setLocalError("Unable to send. Tap retry.");
        }
    }

    async function handleSend() {
        const body = draft.trim();
        if (caseId == null) return;
        if (!body && queue.length === 0) return;

        // Warn the client before sending personal data in the clear.
        if (body && token) {
            try {
                const scan = await scanPortalMessagePii(token, body);
                if (scan.has_pii) {
                    setPiiPrompt({ items: scan.pii_items });
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
        if (caseId == null) return;
        if (!body && queue.length === 0) return;
        setPiiPrompt(null);
        const now = new Date().toISOString();

        if (queue.length === 0) {
            const localId = `t-${Date.now()}`;
            setOutgoing((prev) => [
                ...prev,
                {
                    id: -Date.now(),
                    case_id: caseId,
                    sender_role: "client",
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
            void deliver(body, undefined, localId);
        } else {
            queue.forEach((item, idx) => {
                const localId = `t-${Date.now()}-${idx}`;
                const caption = idx === 0 ? body : "";
                setOutgoing((prev) => [
                    ...prev,
                    {
                        id: -(Date.now() + idx),
                        case_id: caseId,
                        sender_role: "client",
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
                void deliver(caption, item.file, localId);
            });
        }

        setDraft("");
        setQueue([]);
        atBottomRef.current = true;
    }

    function retry(localId: string) {
        const item = outgoing.find((o) => o._localId === localId);
        if (!item) return;
        setOutgoing((prev) =>
            prev.map((o) => (o._localId === localId ? { ...o, _status: "sending" } : o))
        );
        void deliver(item.body, item._file, localId);
    }

    function discardFailed(localId: string) {
        setOutgoing((prev) => prev.filter((o) => o._localId !== localId));
    }

    // ── Input: paste / pick / drop ──────────────────────────────────────
    function handleFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
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
    const registerImage = useCallback((key: string, url: string, name: string) => {
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
        <div className="lexington-scope">
            <main className="max-w-container-max mx-auto flex h-[calc(100vh-80px)] overflow-hidden">
                {/* Message Thread View */}
                <section className="flex-1 flex flex-col bg-surface relative">
                    {/* Thread Header */}
                    <div className="px-gutter py-4 border-b border-outline-variant flex justify-between items-center bg-surface z-10">
                        <div className="flex items-center gap-x-4">
                            <div className="relative">
                                <div className="w-12 h-12 rounded-full bg-secondary-container text-on-secondary-container flex items-center justify-center font-bold border border-outline-variant">
                                    {initials(counsel)}
                                </div>
                                <span className="absolute bottom-0 right-0 w-3 h-3 bg-secondary rounded-full border-2 border-surface" />
                            </div>
                            <div>
                                <h1 className="font-headline-md text-headline-md leading-none text-primary">
                                    {counsel}
                                </h1>
                                <p className="font-label-md text-label-md text-on-surface-variant mt-1">
                                    Lead Legal Counsel
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Chat Canvas */}
                    <div
                        className={`relative flex-1 flex min-h-0 ${dragOver ? "outline-2 outline-dashed outline-primary outline-offset-[-12px]" : ""}`}
                        onDragOver={(e) => {
                            e.preventDefault();
                            setDragOver(true);
                        }}
                        onDragLeave={(e) => {
                            if (e.currentTarget === e.target) setDragOver(false);
                        }}
                        onDrop={handleDrop}
                    >
                        <div
                            ref={scrollRef}
                            onScroll={onCanvasScroll}
                            className="flex-1 overflow-y-auto px-gutter py-8 space-y-6 flex flex-col"
                        >
                            {threadLoading && !thread ? (
                                <p className="text-center font-body-md text-on-surface-variant">Loading conversation…</p>
                            ) : threadError && !thread ? (
                                <div className="text-center">
                                    <p className="font-body-md text-error mb-3">{threadError}</p>
                                    <button
                                        type="button"
                                        onClick={() => void loadThread(caseId)}
                                        className="bg-primary text-on-primary px-5 py-2 rounded-lg font-label-md text-label-md"
                                    >
                                        Retry
                                    </button>
                                </div>
                            ) : allMessages.length === 0 ? (
                                <div className="m-auto text-center max-w-sm">
                                    <span className="material-symbols-outlined text-4xl text-on-surface-variant">forum</span>
                                    <p className="font-headline-md text-headline-md text-primary mt-3">
                                        Start the conversation
                                    </p>
                                    <p className="font-body-md text-on-surface-variant mt-1">
                                        Send a message to {counsel}. Replies appear here.
                                    </p>
                                </div>
                            ) : (
                                grouped.map((group) => (
                                    <div key={group.day} className="space-y-6 flex flex-col">
                                        <div className="text-center">
                                            <span className="px-3 py-1 bg-surface-container-low text-on-surface-variant font-label-md text-label-md rounded-full">
                                                {dayLabel(group.items[0].created_at)}
                                            </span>
                                        </div>
                                        {group.items.map((m) => {
                                            const mine = m.is_mine;
                                            const out = isOutgoing(m);
                                            const showDivider =
                                                !out &&
                                                firstUnreadIdRef.current === (m as ClientPortalMessage).id;
                                            return (
                                                <div key={out ? m._localId : m.id}>
                                                    {showDivider ? (
                                                        <div className="flex items-center gap-x-3 my-2 text-error text-[11px] font-bold">
                                                            <span className="flex-1 h-px bg-error/30" />
                                                            New messages
                                                            <span className="flex-1 h-px bg-error/30" />
                                                        </div>
                                                    ) : null}
                                                    <div
                                                        className={`flex items-end gap-x-3 max-w-[80%] ${mine ? "self-end ml-auto" : ""}`}
                                                    >
                                                        <div
                                                            className={`flex flex-col gap-y-1 ${mine ? "items-end" : ""} ${
                                                                out && m._status === "sending" ? "opacity-60" : ""
                                                            }`}
                                                        >
                                                            {m.body ? (
                                                                <div
                                                                    className={
                                                                        mine
                                                                            ? "bg-primary text-on-primary px-5 py-3 rounded-2xl rounded-br-none shadow-sm"
                                                                            : "bg-surface-container-high text-on-surface px-5 py-3 rounded-2xl rounded-bl-none shadow-sm"
                                                                    }
                                                                >
                                                                    <p className="font-body-md text-body-md whitespace-pre-wrap">
                                                                        {m.body}
                                                                    </p>
                                                                </div>
                                                            ) : null}

                                                            {m.attachment_filename && token ? (
                                                                <PortalAttachment
                                                                    message={m}
                                                                    token={token}
                                                                    localUrl={out ? m._localUrl : undefined}
                                                                    onImageReady={registerImage}
                                                                    onOpenImage={openGallery}
                                                                />
                                                            ) : null}

                                                            <div className="flex items-center gap-x-1 px-1">
                                                                <span className="text-[10px] font-label-md text-on-surface-variant">
                                                                    {out && m._status === "sending"
                                                                        ? "Sending…"
                                                                        : timeLabel(m.created_at)}
                                                                </span>
                                                                {mine && !out ? (
                                                                    <span
                                                                        className={`material-symbols-outlined text-[12px] ${m.read_at ? "text-secondary" : "text-on-surface-variant"}`}
                                                                    >
                                                                        {m.read_at ? "done_all" : "done"}
                                                                    </span>
                                                                ) : null}
                                                            </div>
                                                            {out && m._status === "failed" ? (
                                                                <div className="text-[11px] text-error px-1">
                                                                    Failed.{" "}
                                                                    <button
                                                                        type="button"
                                                                        onClick={() => retry(m._localId)}
                                                                        className="font-bold underline"
                                                                    >
                                                                        Retry
                                                                    </button>{" "}
                                                                    <button
                                                                        type="button"
                                                                        onClick={() => discardFailed(m._localId)}
                                                                        className="font-bold underline"
                                                                    >
                                                                        Discard
                                                                    </button>
                                                                </div>
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
                                <div className="flex items-end gap-x-3 max-w-[80%]">
                                    <div className="bg-surface-container-high px-5 py-4 rounded-2xl rounded-bl-none flex gap-x-1">
                                        <span className="w-2 h-2 rounded-full bg-on-surface-variant/50 animate-bounce" />
                                        <span className="w-2 h-2 rounded-full bg-on-surface-variant/50 animate-bounce [animation-delay:.15s]" />
                                        <span className="w-2 h-2 rounded-full bg-on-surface-variant/50 animate-bounce [animation-delay:.3s]" />
                                    </div>
                                </div>
                            ) : null}
                        </div>
                        {showJump ? (
                            <button
                                type="button"
                                onClick={jumpToBottom}
                                className="absolute left-1/2 -translate-x-1/2 bottom-4 bg-primary text-on-primary text-xs font-semibold px-4 py-2 rounded-full shadow-lg z-10"
                            >
                                ↓ New messages
                            </button>
                        ) : null}
                    </div>

                    {/* Bottom Message Input */}
                    <div className="px-gutter pb-8 pt-4 bg-surface border-t border-outline-variant">
                        <div className="max-w-3xl mx-auto">
                            <div className="flex items-center gap-x-2 text-on-surface-variant mb-4">
                                <span className="material-symbols-outlined text-sm">schedule</span>
                                <span className="font-label-md text-label-md">
                                    {counsel} typically replies within one business day.
                                </span>
                            </div>
                            {localError ? (
                                <p className="text-error text-label-md mb-2">{localError}</p>
                            ) : null}
                            <div className="bg-surface-container-low border border-outline rounded-xl p-2 focus-within:border-primary transition-all shadow-sm">
                                {queue.length ? (
                                    <div className="flex flex-col gap-y-2 m-2">
                                        {queue.map((q) => (
                                            <div
                                                key={q.id}
                                                className="flex items-center gap-x-3 p-2 bg-surface-container rounded-lg"
                                            >
                                                {q.url && q.file.type.startsWith("image/") ? (
                                                    <img src={q.url} alt="" className="w-12 h-12 object-cover rounded-md" />
                                                ) : q.url && q.file.type.startsWith("video/") ? (
                                                    <video src={q.url} muted className="w-12 h-12 object-cover rounded-md bg-black" />
                                                ) : (
                                                    <span className="material-symbols-outlined w-12 h-12 flex items-center justify-center bg-surface-container-high rounded-md text-on-surface-variant">
                                                        attach_file
                                                    </span>
                                                )}
                                                <div className="flex-1 min-w-0">
                                                    <p className="font-label-md text-label-md text-primary truncate">
                                                        {q.file.name}
                                                    </p>
                                                    <p className="text-[10px] text-on-surface-variant">
                                                        {formatBytes(q.file.size)}
                                                    </p>
                                                </div>
                                                <button
                                                    type="button"
                                                    onClick={() => removeQueued(q.id)}
                                                    className="material-symbols-outlined text-on-surface-variant hover:text-error p-1"
                                                    aria-label="Remove attachment"
                                                >
                                                    close
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                ) : null}
                                <textarea
                                    className="w-full bg-transparent border-none focus:ring-0 resize-none font-body-md text-body-md text-primary px-3 py-2 min-h-[48px]"
                                    placeholder={
                                        queue.length
                                            ? "Add a caption…"
                                            : "Paste a screenshot, drop files, or type…"
                                    }
                                    value={draft}
                                    onChange={(e) => {
                                        setDraft(e.target.value);
                                        notifyTyping();
                                    }}
                                    onPaste={handlePaste}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" && !e.shiftKey) {
                                            e.preventDefault();
                                            handleSend();
                                        }
                                    }}
                                />
                                <div className="flex justify-between items-center px-2 py-1">
                                    <div className="flex gap-x-1">
                                        <button
                                            type="button"
                                            onClick={() => fileInputRef.current?.click()}
                                            disabled={!caseId}
                                            className="p-2 text-on-surface-variant hover:text-primary hover:bg-surface-container transition-all rounded-lg disabled:opacity-50"
                                            title="Attach files"
                                        >
                                            <span className="material-symbols-outlined">attach_file</span>
                                        </button>
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            accept="image/*,video/*,application/pdf"
                                            multiple
                                            className="hidden"
                                            onChange={handleFilePicked}
                                        />
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => handleSend()}
                                        disabled={(!draft.trim() && queue.length === 0) || !caseId}
                                        className="bg-primary text-on-primary px-6 py-2 rounded-lg font-label-md text-label-md hover:opacity-90 transition-opacity flex items-center gap-x-2 disabled:opacity-50"
                                    >
                                        <span>Send</span>
                                        <span className="material-symbols-outlined text-sm">send</span>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Right Side Panel (Case Context) */}
                <aside className="hidden xl:flex flex-col w-80 bg-surface-container-low border-l border-outline-variant p-6 gap-y-8 overflow-y-auto">
                    <div>
                        <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest mb-4">
                            Case Context
                        </h3>
                        <div className="bg-surface rounded-xl border border-outline-variant p-4">
                            <p className="font-label-md text-label-md text-secondary mb-1">Active Case</p>
                            <p className="font-headline-md text-body-lg font-semibold text-primary mb-3">
                                {thread?.case_title ?? "—"}
                            </p>
                            <div className="flex items-center gap-x-2">
                                <span className="w-2 h-2 bg-secondary rounded-full" />
                                <span className="font-label-md text-label-md text-on-surface-variant">
                                    Conversation with counsel
                                </span>
                            </div>
                        </div>
                    </div>
                    <div>
                        <h3 className="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest mb-4">
                            Participants
                        </h3>
                        <div className="space-y-4">
                            <div className="flex items-center gap-x-3">
                                <div className="w-8 h-8 rounded-full bg-secondary-container text-on-secondary-container flex items-center justify-center font-bold text-xs">
                                    {initials(counsel)}
                                </div>
                                <div className="flex flex-col">
                                    <span className="font-label-md text-label-md text-primary">{counsel}</span>
                                    <span className="text-[10px] text-on-surface-variant">Lead Counsel</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </aside>
            </main>
            {gallery && galleryImages.length ? (
                <PortalGalleryLightbox
                    images={galleryImages}
                    index={gallery.index}
                    onClose={() => setGallery(null)}
                    onIndex={(i) => setGallery((g) => (g ? { ...g, index: i } : g))}
                />
            ) : null}
            {piiPrompt ? (
                <div
                    role="dialog"
                    aria-modal="true"
                    onClick={() => setPiiPrompt(null)}
                    className="fixed inset-0 z-[1000] flex items-center justify-center p-6 bg-black/60 backdrop-blur-sm"
                >
                    <div
                        onClick={(e) => e.stopPropagation()}
                        className="bg-surface rounded-2xl p-6 max-w-md w-full shadow-2xl"
                    >
                        <h3 className="font-headline-md text-headline-md text-primary">
                            ⚠️ Sensitive information
                        </h3>
                        <p className="font-body-md text-body-md text-on-surface-variant mt-2">
                            Your message looks like it contains personal data. For your
                            security, avoid sharing this unless your lawyer asked for it:
                        </p>
                        <ul className="mt-3 mb-5 space-y-1 text-body-md">
                            {piiPrompt.items.slice(0, 6).map((p, i) => (
                                <li key={i}>
                                    <span className="font-bold text-error">{p.type}</span>: {p.value}
                                </li>
                            ))}
                        </ul>
                        <div className="flex gap-x-3 justify-end">
                            <button
                                type="button"
                                onClick={() => setPiiPrompt(null)}
                                className="px-5 py-2 rounded-lg border border-outline font-label-md text-label-md"
                            >
                                Review it
                            </button>
                            <button
                                type="button"
                                onClick={() => doSend()}
                                className="bg-primary text-on-primary px-5 py-2 rounded-lg font-label-md text-label-md"
                            >
                                Send anyway
                            </button>
                        </div>
                    </div>
                </div>
            ) : null}
        </div>
    );
}
