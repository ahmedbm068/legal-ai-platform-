import type {
    ClientPortalAssistantResponse,
    ClientPortalCase,
    ClientPortalDashboard,
    ClientPortalDocument,
} from "./types";

export const TOKEN_STORAGE_KEY = "legal-ai-client-portal-token";
export const THEME_STORAGE_KEY = "legal-ai-client-portal-theme";
export const PASSWORD_POLICY_REGEX = /^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{10,}$/;
export const PASSWORD_HINT =
    "Password must be at least 10 characters and include one uppercase letter and one symbol.";

export type PortalView = "dashboard" | "cases" | "documents" | "requests" | "assistant" | "calendar" | "book" | "profile";
export type ThemeMode = "light" | "dark";

export const NAV_ITEMS: Array<{ id: PortalView; title: string; subtitle: string }> = [
    { id: "dashboard", title: "Dashboard", subtitle: "Overview and next actions" },
    { id: "cases", title: "Case intelligence", subtitle: "Status, risk, and evidence" },
    { id: "documents", title: "Document viewer", subtitle: "Files, highlights, and insights" },
    { id: "requests", title: "Intake requests", subtitle: "Submit updates and materials" },
    { id: "assistant", title: "AI assistant", subtitle: "Structured legal guidance" },
    { id: "calendar", title: "Calendar", subtitle: "Appointments and AI planning" },
    { id: "book", title: "Book a meeting", subtitle: "Schedule a new rendez-vous" },
    { id: "profile", title: "Profile", subtitle: "Account and workspace" },
];

export const ASSISTANT_SUGGESTIONS = [
    "Summarize my case",
    "What are the risks?",
    "What should I do next?",
    "What is missing in my file?",
];

export function formatDate(value?: string | null) {
    if (!value) return "No date";
    return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
    }).format(new Date(value));
}

export function formatDateTime(value?: string | null) {
    if (!value) return "No date";
    return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(new Date(value));
}

export function formatBytes(size: number) {
    if (!size) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    let value = size;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
        value /= 1024;
        index += 1;
    }
    return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`;
}

export function label(value?: string | null) {
    const normalized = (value || "").toLowerCase().trim();
    if (!normalized) return "Unknown";
    return normalized.replace(/_/g, " ").replace(/\b\w/g, (x) => x.toUpperCase());
}

export function tone(value?: string | null) {
    const normalized = (value || "").toLowerCase().trim();
    if (["completed", "approved", "closed", "resolved"].includes(normalized)) return "ok";
    if (["failed", "rejected", "blocked"].includes(normalized)) return "danger";
    if (["processing", "submitted", "new", "ready_for_review", "in_progress", "open"].includes(normalized)) return "attention";
    return "neutral";
}

export function riskFromCase(row: ClientPortalCase) {
    const status = (row.status || "").toLowerCase();
    if (["blocked", "failed", "rejected"].includes(status)) {
        return { label: "High", tone: "danger" };
    }
    if (row.document_count === 0 && row.consultation_count === 0) {
        return { label: "High", tone: "danger" };
    }
    if (["new", "open", "in_progress", "ready_for_review"].includes(status)) {
        return { label: "Medium", tone: "attention" };
    }
    return { label: "Low", tone: "ok" };
}

export function intakePipelineStage(props: {
    submitting: boolean;
    hasPayload: boolean;
    pendingDocuments: number;
}) {
    if (props.submitting) return "uploading";
    if (props.pendingDocuments > 0) return "processing";
    if (props.hasPayload) return "analyzed";
    return "idle";
}

export function helperReply(prompt: string, dashboard: ClientPortalDashboard, selectedCase: ClientPortalCase | null) {
    const q = prompt.toLowerCase();

    if (q.includes("next step") || q.includes("what should i do")) {
        const target = selectedCase || dashboard.cases.find((row) => tone(row.status) === "attention") || dashboard.cases[0];
        if (!target) return "No active case yet. Submit a consultation request first.";
        return `${target.title}: ${target.next_recommended_step || "Your legal team is reviewing your matter."}`;
    }

    if (q.includes("risk")) {
        if (!dashboard.cases.length) return "No active case yet, so risk cannot be estimated.";
        const risks = dashboard.cases.slice(0, 4).map((row) => {
            const risk = riskFromCase(row);
            return `- ${row.title}: ${risk.label} risk`;
        });
        return risks.join("\n");
    }

    if (q.includes("status") || q.includes("progress")) {
        if (!dashboard.cases.length) return "No case is active yet.";
        return dashboard.cases.slice(0, 4).map((row) => `- ${row.title}: ${label(row.status)}`).join("\n");
    }

    if (q.includes("document") || q.includes("missing")) {
        const pending = dashboard.documents.filter((row) => tone(row.processing_status) !== "ok");
        if (!pending.length) return "All uploaded documents are processed.";
        return pending.slice(0, 5).map((row) => `- ${row.filename}: ${label(row.processing_status)}`).join("\n");
    }

    return `Workspace summary: ${dashboard.metrics.active_cases} active case(s), ${dashboard.metrics.total_documents} document(s), ${dashboard.metrics.requests_under_review} request(s) under review.`;
}

export function StatusBadge({ value }: { value?: string | null }) {
    return <span className={`status-badge ${tone(value)}`}>{label(value)}</span>;
}

export function RiskBadge({ row }: { row: ClientPortalCase }) {
    const risk = riskFromCase(row);
    return <span className={`status-badge ${risk.tone}`}>Risk {risk.label}</span>;
}

export function sectionTitle(view: PortalView) {
    if (view === "dashboard") return "Client dashboard";
    if (view === "cases") return "Case intelligence";
    if (view === "documents") return "Document intelligence";
    if (view === "requests") return "Consultation requests";
    if (view === "assistant") return "AI assistant";
    if (view === "calendar") return "Calendar";
    return "Profile";
}

export function documentInsights(
    selectedDocument: ClientPortalDocument | null,
    selectedCase: ClientPortalCase | null,
    activity: ClientPortalDashboard["activity"]
) {
    if (!selectedDocument) return null;

    const linkedActivity = activity
        .filter((item) => item.case_id === selectedDocument.case_id)
        .slice(0, 3)
        .map((item) => `${item.title} (${formatDate(item.created_at)})`);

    const riskText = tone(selectedDocument.processing_status) === "ok"
        ? "Low extraction risk. Document is fully processed."
        : "Medium processing risk. Document may still be under analysis.";

    return {
        summary: `${selectedDocument.filename} is linked to ${selectedCase?.title || "your case"} and currently marked as ${label(
            selectedDocument.processing_status
        )}.`,
        riskText,
        dates:
            linkedActivity.length > 0
                ? linkedActivity
                : [
                    `Uploaded on ${formatDate(selectedDocument.upload_timestamp)}`,
                    "No additional date events detected yet",
                ],
    };
}

export function renderAssistantResponse(result: ClientPortalAssistantResponse | null, answer: string) {
    return (
        <div className="assistant-response-grid">
            <div className="response-card">
                <span>Assistant response</span>
                <p>{answer}</p>
            </div>

            <div className="response-card">
                <span>Grounding</span>
                <p>Confidence: {label(result?.confidence)}</p>
                <p>Scope: {label(result?.scope)}</p>
                <p>Snapshot version: {result?.case_snapshot_version ?? "Pending"}</p>
            </div>

            <div className="response-card">
                <span>Citations</span>
                {result?.citations?.length ? (
                    <ul>
                        {result.citations.slice(0, 4).map((citation) => (
                            <li key={`${citation.label}-${citation.snippet}`}>
                                <strong>{citation.label}</strong>
                                <p>{citation.snippet || "Grounded citation available."}</p>
                                {citation.url ? (
                                    <a href={citation.url} target="_blank" rel="noreferrer noopener">
                                        Open source
                                    </a>
                                ) : null}
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p>No citations available yet for this response.</p>
                )}
            </div>
        </div>
    );
}
