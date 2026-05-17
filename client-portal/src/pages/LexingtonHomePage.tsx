import { useNavigate } from "react-router-dom";
import { usePortal } from "../context/PortalContext";
import { formatDate, label } from "../portalPresentation";

const PHASES = ["Initiation", "Discovery", "Mediation", "Resolution"];

// Map a case status to how far along the 4-phase track it is (1-based, inclusive).
function phaseReached(status?: string | null): number {
    const s = (status || "").toLowerCase();
    if (["completed", "closed", "resolved", "approved"].includes(s)) return 4;
    if (["mediation", "negotiation"].includes(s)) return 3;
    if (["in_progress", "ready_for_review", "open", "discovery"].includes(s)) return 2;
    return 1;
}

const ACTIVITY_ICON: Record<string, string> = {
    document: "description",
    document_uploaded: "description",
    message: "chat_bubble",
    message_received: "chat_bubble",
    appointment: "calendar_today",
    appointment_scheduled: "calendar_today",
    calendar: "calendar_today",
};

function activityIcon(eventType: string): string {
    const key = (eventType || "").toLowerCase();
    return ACTIVITY_ICON[key] ?? "bolt";
}

export default function LexingtonHomePage() {
    const { dashboard, dashboardLoading, dashboardError, refreshDashboard, account } = usePortal();
    const navigate = useNavigate();

    if (dashboardLoading && !dashboard) {
        return (
            <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
                <div className="bg-surface-container-lowest p-stack-lg border border-outline-variant rounded-lg">
                    <p className="font-body-md text-body-md text-on-surface-variant">Loading your portal…</p>
                </div>
            </main>
        );
    }

    if (dashboardError) {
        return (
            <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
                <div className="bg-surface-container-lowest p-stack-lg border border-outline-variant rounded-lg">
                    <p className="font-body-md text-body-md text-error mb-stack-md">{dashboardError}</p>
                    <button
                        type="button"
                        onClick={() => void refreshDashboard()}
                        className="bg-primary text-on-primary py-3 px-6 rounded font-label-md text-label-md hover:opacity-90 transition-all"
                    >
                        Retry
                    </button>
                </div>
            </main>
        );
    }

    if (!dashboard) return null;

    const firstName = (account?.full_name ?? "").trim().split(/\s+/)[0] || "there";
    const activeCase = dashboard.cases[0] ?? null;
    const attorneyName = activeCase?.lawyer_name ?? "Your legal team";
    const caseRef = activeCase ? `#LX-${String(activeCase.id).padStart(5, "0")}` : "—";
    const nextMilestone = activeCase?.next_recommended_step ?? "Pending review";
    const reached = phaseReached(activeCase?.status);

    const statusText = activeCase
        ? `Status: ${activeCase.next_recommended_step || `Your matter is currently in ${label(activeCase.status)}.`}`
        : "No active case yet — submit a consultation request to begin.";

    const recentActivity = dashboard.activity.slice(0, 3);

    return (
        <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
            {/* Welcome Header */}
            <section className="mb-stack-lg">
                <p className="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest mb-unit">
                    Overview
                </p>
                <h1 className="font-display-lg text-display-lg text-primary">Welcome back, {firstName}</h1>
            </section>

            {/* Bento Grid Layout */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-stack-md items-start">
                {/* Left Column: Primary Status & Action */}
                <div className="md:col-span-8 space-y-stack-md">
                    {/* Status Card */}
                    <div className="bg-surface-container-lowest p-stack-lg border border-outline-variant shadow-[0_16px_16px_-4px_rgba(0,18,51,0.04)] rounded-lg">
                        <div className="flex items-start gap-x-4 mb-stack-md">
                            <span className="material-symbols-outlined text-secondary text-3xl">info</span>
                            <div>
                                <p className="font-label-md text-label-md text-on-surface-variant mb-unit">
                                    Current Status
                                </p>
                                <p className="font-headline-md text-headline-md text-primary leading-snug">
                                    {statusText}
                                </p>
                            </div>
                        </div>
                        {/* Phase Pills */}
                        <div className="flex flex-wrap gap-2 pt-stack-md border-t border-outline-variant">
                            {PHASES.map((phase, i) => {
                                const done = i < reached;
                                return (
                                    <div
                                        key={phase}
                                        className={
                                            done
                                                ? "px-4 py-1.5 bg-secondary text-on-secondary rounded-full font-label-md text-label-md"
                                                : "px-4 py-1.5 bg-surface-container text-on-surface-variant rounded-full font-label-md text-label-md"
                                        }
                                    >
                                        {phase}
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Recent Activity List */}
                    <div className="bg-surface-container-lowest p-stack-lg border border-outline-variant rounded-lg">
                        <h3 className="font-headline-md text-headline-md text-primary mb-stack-md">Recent Activity</h3>
                        {recentActivity.length > 0 ? (
                            <div className="divide-y divide-outline-variant">
                                {recentActivity.map((item) => (
                                    <div
                                        key={item.id}
                                        className="py-4 flex justify-between items-center hover:bg-surface-container-low transition-all duration-300 px-2 -mx-2 rounded"
                                    >
                                        <div className="flex items-center gap-x-4">
                                            <span className="material-symbols-outlined text-on-surface-variant">
                                                {activityIcon(item.event_type)}
                                            </span>
                                            <div>
                                                <p className="font-body-md text-body-md text-primary">{item.title}</p>
                                                <p className="font-label-md text-label-md text-on-surface-variant">
                                                    {item.description || label(item.event_type)}
                                                </p>
                                            </div>
                                        </div>
                                        <span className="font-label-md text-label-md text-on-surface-variant">
                                            {formatDate(item.created_at)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="font-body-md text-body-md text-on-surface-variant">
                                No activity yet. Your case events will appear here.
                            </p>
                        )}
                    </div>
                </div>

                {/* Right Column: Professional Profile & Support */}
                <div className="md:col-span-4 space-y-stack-md">
                    {/* Attorney Profile Card */}
                    <div className="bg-surface-container-low p-stack-lg border border-outline-variant rounded-lg text-center">
                        <p className="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest mb-stack-md">
                            Your Attorney
                        </p>
                        <div className="relative inline-block mb-stack-md">
                            <div className="w-32 h-32 rounded-full mx-auto flex items-center justify-center bg-secondary-container border-4 border-surface-container-lowest shadow-md">
                                <span className="font-display-lg text-primary" style={{ fontSize: "40px" }}>
                                    {attorneyName
                                        .split(/\s+/)
                                        .map((p) => p[0])
                                        .filter(Boolean)
                                        .slice(0, 2)
                                        .join("")
                                        .toUpperCase()}
                                </span>
                            </div>
                        </div>
                        <h2 className="font-headline-md text-headline-md text-primary">{attorneyName}</h2>
                        <p className="font-body-md text-body-md text-on-surface-variant mb-stack-md">
                            Lead Counsel
                        </p>
                        <button
                            type="button"
                            onClick={() => navigate("/assistant")}
                            className="w-full bg-primary text-on-primary py-4 px-6 rounded font-label-md text-label-md hover:opacity-90 transition-all flex items-center justify-center gap-x-2"
                        >
                            <span className="material-symbols-outlined text-[18px]">send</span>
                            Send a Message
                        </button>
                    </div>

                    {/* Secondary Info Card */}
                    <div className="bg-surface-container-lowest p-stack-md border border-outline-variant rounded-lg">
                        <div className="flex items-center justify-between mb-unit">
                            <p className="font-label-md text-label-md text-on-surface-variant">Case ID</p>
                            <p className="font-label-md text-label-md text-primary font-semibold">{caseRef}</p>
                        </div>
                        <div className="flex items-center justify-between">
                            <p className="font-label-md text-label-md text-on-surface-variant">Next Milestone</p>
                            <p className="font-label-md text-label-md text-primary font-semibold">{nextMilestone}</p>
                        </div>
                    </div>

                    {/* Support CTA */}
                    <button
                        type="button"
                        onClick={() => navigate("/assistant")}
                        className="w-full p-stack-md border border-outline-variant border-dashed rounded-lg flex items-center justify-between group cursor-pointer hover:bg-surface-container-low transition-colors bg-transparent"
                    >
                        <div className="flex items-center gap-x-3">
                            <span className="material-symbols-outlined text-on-surface-variant">help_outline</span>
                            <span className="font-label-md text-label-md text-primary">Need assistance?</span>
                        </div>
                        <span className="material-symbols-outlined text-on-surface-variant group-hover:translate-x-1 transition-transform">
                            chevron_right
                        </span>
                    </button>
                </div>
            </div>
        </main>
    );
}
