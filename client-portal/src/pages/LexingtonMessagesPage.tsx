import { useEffect, useMemo, useRef, useState } from "react";
import { usePortal } from "../context/PortalContext";
import { portalMessageAttachmentUrl } from "../lib/api";
import { formatBytes } from "../portalPresentation";
import type { ClientPortalMessage } from "../types";

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
        dashboard,
        selectedCaseId,
        thread,
        threadLoading,
        threadError,
        messageSending,
        loadThread,
        sendMessage,
        sendMessageWithAttachment,
    } = usePortal();

    const [draft, setDraft] = useState("");
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const scrollRef = useRef<HTMLDivElement | null>(null);

    const caseId = selectedCaseId ?? dashboard?.cases[0]?.id ?? null;

    useEffect(() => {
        void loadThread(caseId);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [caseId]);

    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [thread?.messages.length]);

    const counsel = thread?.counsel_name ?? "Your legal team";

    const grouped = useMemo(() => {
        const groups: Array<{ day: string; items: ClientPortalMessage[] }> = [];
        for (const m of thread?.messages ?? []) {
            const key = dayKey(m.created_at);
            const last = groups[groups.length - 1];
            if (last && last.day === key) last.items.push(m);
            else groups.push({ day: key, items: [m] });
        }
        return groups;
    }, [thread?.messages]);

    async function handleSend() {
        const body = draft.trim();
        if (!body || messageSending) return;
        const ok = await sendMessage(body, caseId);
        if (ok) setDraft("");
    }

    async function handleFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0];
        if (file) await sendMessageWithAttachment(file, draft.trim(), caseId);
        e.target.value = "";
        setDraft("");
    }

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
                    <div ref={scrollRef} className="flex-1 overflow-y-auto px-gutter py-8 space-y-6 flex flex-col">
                        {threadLoading && !thread ? (
                            <p className="text-center font-body-md text-on-surface-variant">Loading conversation…</p>
                        ) : threadError ? (
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
                        ) : (thread?.messages.length ?? 0) === 0 ? (
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
                                        return (
                                            <div
                                                key={m.id}
                                                className={`flex items-end gap-x-3 max-w-[80%] ${mine ? "self-end" : ""}`}
                                            >
                                                <div className={`flex flex-col gap-y-1 ${mine ? "items-end" : ""}`}>
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

                                                    {m.attachment_filename ? (
                                                        <a
                                                            href={portalMessageAttachmentUrl(m.id)}
                                                            target="_blank"
                                                            rel="noreferrer noopener"
                                                            className="bg-surface-container-lowest border border-outline-variant p-4 rounded-xl flex items-center gap-x-4 w-72 hover:bg-surface-container-low transition-colors"
                                                        >
                                                            <div className="w-10 h-10 bg-error-container text-error flex items-center justify-center rounded">
                                                                <span className="material-symbols-outlined">
                                                                    {m.attachment_content_type?.includes("pdf")
                                                                        ? "picture_as_pdf"
                                                                        : "attach_file"}
                                                                </span>
                                                            </div>
                                                            <div className="flex-1 overflow-hidden">
                                                                <p className="font-label-md text-label-md text-primary truncate">
                                                                    {m.attachment_filename}
                                                                </p>
                                                                <p className="text-[10px] text-on-surface-variant">
                                                                    {m.attachment_size
                                                                        ? formatBytes(m.attachment_size)
                                                                        : "Attachment"}
                                                                </p>
                                                            </div>
                                                            <span className="material-symbols-outlined text-on-surface-variant">
                                                                download
                                                            </span>
                                                        </a>
                                                    ) : null}

                                                    <div className="flex items-center gap-x-1 px-1">
                                                        <span className="text-[10px] font-label-md text-on-surface-variant">
                                                            {timeLabel(m.created_at)}
                                                        </span>
                                                        {mine ? (
                                                            <span
                                                                className={`material-symbols-outlined text-[12px] ${m.read_at ? "text-secondary" : "text-on-surface-variant"}`}
                                                            >
                                                                {m.read_at ? "done_all" : "done"}
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
                            <div className="bg-surface-container-low border border-outline rounded-xl p-2 focus-within:border-primary transition-all shadow-sm">
                                <textarea
                                    className="w-full bg-transparent border-none focus:ring-0 resize-none font-body-md text-body-md text-primary px-3 py-2 min-h-[48px]"
                                    placeholder="Type your message..."
                                    value={draft}
                                    onChange={(e) => setDraft(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" && !e.shiftKey) {
                                            e.preventDefault();
                                            void handleSend();
                                        }
                                    }}
                                />
                                <div className="flex justify-between items-center px-2 py-1">
                                    <div className="flex gap-x-1">
                                        <button
                                            type="button"
                                            onClick={() => fileInputRef.current?.click()}
                                            disabled={messageSending || !caseId}
                                            className="p-2 text-on-surface-variant hover:text-primary hover:bg-surface-container transition-all rounded-lg disabled:opacity-50"
                                            title="Attach a file"
                                        >
                                            <span className="material-symbols-outlined">attach_file</span>
                                        </button>
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            className="hidden"
                                            onChange={handleFilePicked}
                                        />
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => void handleSend()}
                                        disabled={messageSending || !draft.trim() || !caseId}
                                        className="bg-primary text-on-primary px-6 py-2 rounded-lg font-label-md text-label-md hover:opacity-90 transition-opacity flex items-center gap-x-2 disabled:opacity-50"
                                    >
                                        <span>{messageSending ? "Sending…" : "Send"}</span>
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
        </div>
    );
}
