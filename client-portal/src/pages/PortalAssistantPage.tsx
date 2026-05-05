import { type FormEvent, useEffect, useRef, useState } from "react";
import { usePortal } from "../context/PortalContext";
import { ASSISTANT_SUGGESTIONS } from "../portalPresentation";

type ConversationEntry = {
    id: string;
    role: "user" | "assistant";
    content: string;
};

function generateId() {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function PortalAssistantPage() {
    const {
        dashboard,
        selectedCaseId,
        setSelectedCaseId,
        assistantBusy,
        assistantError,
        assistantResult,
        askAssistant,
        clearAssistant,
    } = usePortal();

    const [prompt, setPrompt] = useState("");
    const [conversation, setConversation] = useState<ConversationEntry[]>([]);
    const bottomRef = useRef<HTMLDivElement | null>(null);

    const cases = dashboard?.cases ?? [];

    // Append assistant result to conversation when it arrives
    useEffect(() => {
        if (!assistantResult) return;
        setConversation((prev) => [
            ...prev,
            {
                id: generateId(),
                role: "assistant",
                content: assistantResult.answer ?? "No response.",
            },
        ]);
        clearAssistant();
    }, [assistantResult, clearAssistant]);

    // Scroll to bottom on new messages
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [conversation, assistantBusy]);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const text = prompt.trim();
        if (!text || assistantBusy) return;
        setConversation((prev) => [
            ...prev,
            { id: generateId(), role: "user", content: text },
        ]);
        setPrompt("");
        await askAssistant(text, selectedCaseId);
    }

    function handleSuggestion(text: string) {
        setPrompt(text);
    }

    return (
        <div className="view-panel assistant-panel">
            <div className="view-header">
                <h2>AI Assistant</h2>
                <p>Ask structured legal questions about your case, documents, or next steps.</p>
            </div>

            <div className="assistant-case-select">
                <label htmlFor="assistant-case">Context case:</label>
                <select
                    id="assistant-case"
                    value={selectedCaseId ?? ""}
                    onChange={(e) => setSelectedCaseId(e.target.value ? Number(e.target.value) : null)}
                >
                    <option value="">No specific case</option>
                    {cases.map((c) => (
                        <option key={c.id} value={c.id}>{c.title}</option>
                    ))}
                </select>
            </div>

            <div className="assistant-conversation">
                {conversation.length === 0 ? (
                    <div className="assistant-suggestions">
                        <p className="muted">Start a conversation or pick a suggestion:</p>
                        <div className="suggestion-chips">
                            {ASSISTANT_SUGGESTIONS.map((s) => (
                                <button
                                    key={s}
                                    className="chip"
                                    onClick={() => handleSuggestion(s)}
                                    type="button"
                                >
                                    {s}
                                </button>
                            ))}
                        </div>
                    </div>
                ) : (
                    conversation.map((entry) => (
                        <div key={entry.id} className={`chat-bubble ${entry.role}`}>
                            {entry.role === "assistant" ? (
                                <div className="assistant-response">
                                    <p style={{ whiteSpace: "pre-wrap" }}>{entry.content}</p>
                                </div>
                            ) : (
                                <p>{entry.content}</p>
                            )}
                        </div>
                    ))
                )}
                {assistantBusy ? (
                    <div className="chat-bubble assistant thinking">
                        <span className="thinking-dots">Thinking…</span>
                    </div>
                ) : null}
                {assistantError ? (
                    <div className="chat-bubble assistant error">
                        <p className="error-msg">{assistantError}</p>
                    </div>
                ) : null}
                <div ref={bottomRef} />
            </div>

            <form className="assistant-composer" onSubmit={(e) => void handleSubmit(e)}>
                <textarea
                    rows={2}
                    placeholder="Ask about your case, documents, risks, or next legal steps…"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            e.currentTarget.form?.requestSubmit();
                        }
                    }}
                    disabled={assistantBusy}
                />
                <button className="btn primary" disabled={assistantBusy || !prompt.trim()} type="submit">
                    {assistantBusy ? "…" : "Send"}
                </button>
            </form>
        </div>
    );
}
