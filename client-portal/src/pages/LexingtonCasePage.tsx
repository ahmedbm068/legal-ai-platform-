import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { usePortal } from "../context/PortalContext";
import { formatDate, label } from "../portalPresentation";

const PHASES = ["Discovery", "Negotiation", "Resolution"];

// Map case status -> index of the *current* phase (0-based). -1 before Discovery.
function phaseIndex(status?: string | null): number {
    const s = (status || "").toLowerCase();
    if (["completed", "closed", "resolved", "approved"].includes(s)) return 2;
    if (["mediation", "negotiation", "ready_for_review"].includes(s)) return 1;
    return 0;
}

function daysSince(iso?: string | null): number {
    if (!iso) return 0;
    const ms = Date.now() - new Date(iso).getTime();
    return Math.max(0, Math.floor(ms / 86_400_000));
}

export default function LexingtonCasePage() {
    const { dashboard, selectedCaseId, setSelectedCaseId } = usePortal();
    const navigate = useNavigate();

    const activeCase = useMemo(() => {
        if (!dashboard) return null;
        return (
            dashboard.cases.find((c) => c.id === selectedCaseId) ??
            dashboard.cases[0] ??
            null
        );
    }, [dashboard, selectedCaseId]);

    const timeline = useMemo(() => {
        if (!dashboard || !activeCase) return [];
        return dashboard.activity
            .filter((a) => a.case_id === activeCase.id)
            .sort((a, b) => b.created_at.localeCompare(a.created_at));
    }, [dashboard, activeCase]);

    const caseDocs = useMemo(() => {
        if (!dashboard || !activeCase) return [];
        return dashboard.documents.filter((d) => d.case_id === activeCase.id);
    }, [dashboard, activeCase]);

    if (!dashboard) {
        return (
            <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
                <div className="bg-surface-container-lowest p-stack-lg border border-outline-variant rounded-lg">
                    <p className="font-body-md text-body-md text-on-surface-variant">Loading your case…</p>
                </div>
            </main>
        );
    }

    if (!activeCase) {
        return (
            <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
                <div className="bg-surface-container-lowest p-stack-lg border border-outline-variant rounded-lg text-center">
                    <h2 className="font-headline-md text-headline-md text-primary mb-stack-sm">No active case yet</h2>
                    <p className="font-body-md text-body-md text-on-surface-variant">
                        Once your consultation is accepted, your case overview will appear here.
                    </p>
                </div>
            </main>
        );
    }

    const lawyer = activeCase.lawyer_name ?? "Your legal team";
    const curPhase = phaseIndex(activeCase.status);

    return (
        <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
            {/* Case Header Section */}
            <section className="mb-stack-lg">
                <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-stack-md">
                    <div>
                        <span className="font-label-md text-label-md text-secondary uppercase tracking-widest mb-2 block">
                            Case Overview
                        </span>
                        <h1 className="font-headline-lg text-headline-lg md:text-display-lg text-primary mb-2">
                            {activeCase.title}
                        </h1>
                        <div className="flex flex-wrap gap-x-6 gap-y-2 text-on-surface-variant font-body-md">
                            <div className="flex items-center gap-2">
                                <span className="material-symbols-outlined text-[18px]">category</span>
                                <span>{label(activeCase.jurisdiction_country) || "Legal matter"}</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="material-symbols-outlined text-[18px]">gavel</span>
                                <span>{lawyer}{activeCase.lawyer_name ? ", Lead Counsel" : ""}</span>
                            </div>
                        </div>
                    </div>
                    <div className="flex flex-col items-start md:items-end gap-3">
                        <button
                            type="button"
                            onClick={() => navigate("/assistant")}
                            className="px-8 py-3 bg-primary text-on-primary font-label-md text-label-md rounded-lg hover:opacity-90 transition-opacity"
                        >
                            Contact {lawyer.split(/\s+/)[0]}
                        </button>
                    </div>
                </div>

                {/* Progress Phase Pills */}
                <div className="flex items-center gap-2 overflow-x-auto pb-4">
                    {PHASES.map((phase, i) => {
                        const done = i < curPhase;
                        const current = i === curPhase;
                        const pillClass = done
                            ? "flex items-center gap-2 px-4 py-2 bg-secondary text-on-secondary rounded-full font-label-md text-label-md whitespace-nowrap"
                            : current
                              ? "flex items-center gap-2 px-4 py-2 bg-secondary-container text-on-secondary-container border border-secondary rounded-full font-label-md text-label-md ring-2 ring-secondary ring-offset-2 ring-offset-surface whitespace-nowrap"
                              : "flex items-center gap-2 px-4 py-2 bg-surface-container-high text-on-surface-variant rounded-full font-label-md text-label-md opacity-60 whitespace-nowrap";
                        return (
                            <div key={phase} className="flex items-center gap-2">
                                <div className={pillClass}>
                                    {done ? (
                                        <span
                                            className="material-symbols-outlined text-[16px]"
                                            style={{ fontVariationSettings: "'FILL' 1" }}
                                        >
                                            check_circle
                                        </span>
                                    ) : null}
                                    {phase}
                                </div>
                                {i < PHASES.length - 1 ? (
                                    <div className="w-8 h-px bg-outline-variant" />
                                ) : null}
                            </div>
                        );
                    })}
                </div>
            </section>

            {/* Main Content Layout */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter">
                {/* Timeline Column */}
                <div className="lg:col-span-7 bg-surface-container-lowest rounded-xl p-8 border border-surface-container-high shadow-sm">
                    <div className="flex items-center justify-between mb-stack-md">
                        <h2 className="font-headline-md text-headline-md text-primary">Case Timeline</h2>
                        <span className="text-label-md font-label-md text-secondary">
                            Updated {formatDate(activeCase.updated_at)}
                        </span>
                    </div>

                    {timeline.length === 0 ? (
                        <p className="font-body-md text-on-surface-variant">
                            No timeline events yet. Milestones will appear here as your case progresses.
                        </p>
                    ) : (
                        <div className="space-y-0">
                            {timeline.map((ev, i) => {
                                const isLast = i === timeline.length - 1;
                                return (
                                    <div
                                        key={ev.id}
                                        className={`relative pl-8 ${isLast ? "pb-4" : "pb-10"}`}
                                    >
                                        {!isLast ? (
                                            <div
                                                className="absolute w-px bg-outline-variant"
                                                style={{ left: 7, top: 24, bottom: -16 }}
                                            />
                                        ) : null}
                                        <div
                                            className={
                                                isLast
                                                    ? "absolute left-0 top-1 w-4 h-4 rounded-full border-2 border-secondary bg-surface-container-lowest"
                                                    : "absolute left-0 top-1 w-4 h-4 rounded-full bg-secondary ring-4 ring-secondary-container"
                                            }
                                        />
                                        <div className="flex flex-col gap-1">
                                            <div className="flex items-center gap-3">
                                                <span className="font-label-md text-label-md text-on-surface-variant">
                                                    {formatDate(ev.created_at)}
                                                </span>
                                                {isLast ? (
                                                    <span className="px-2 py-0.5 bg-primary text-on-primary text-[10px] uppercase font-bold tracking-tight rounded">
                                                        Latest
                                                    </span>
                                                ) : null}
                                            </div>
                                            <h3 className="font-body-lg text-body-lg font-semibold text-primary">
                                                {ev.title}
                                            </h3>
                                            {ev.description ? (
                                                <p className="text-on-surface-variant font-body-md mt-2 leading-relaxed">
                                                    {ev.description}
                                                </p>
                                            ) : null}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Sidebar Details */}
                <div className="lg:col-span-5 flex flex-col gap-gutter">
                    {/* Quick Stats Card */}
                    <div className="bg-surface-container-high rounded-xl p-8 border border-outline-variant">
                        <h2 className="font-headline-md text-headline-md text-primary mb-6">Quick Stats</h2>
                        <div className="space-y-6">
                            <div className="flex justify-between items-center pb-4 border-b border-outline-variant">
                                <span className="text-on-surface-variant font-body-md">Status</span>
                                <span className="font-semibold text-primary">{label(activeCase.status)}</span>
                            </div>
                            <div className="flex justify-between items-center pb-4 border-b border-outline-variant">
                                <span className="text-on-surface-variant font-body-md">Days Since Filing</span>
                                <span className="font-semibold text-primary">
                                    {daysSince(activeCase.created_at)} Days
                                </span>
                            </div>
                            <div className="flex justify-between items-center pb-4 border-b border-outline-variant">
                                <span className="text-on-surface-variant font-body-md">Documents</span>
                                <span className="font-semibold text-primary">
                                    {caseDocs.length} Total
                                </span>
                            </div>
                            <div className="flex justify-between items-center">
                                <span className="text-on-surface-variant font-body-md">Next Action</span>
                                <span className="font-semibold text-secondary text-right max-w-[55%]">
                                    {activeCase.next_recommended_step ?? "Awaiting review"}
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Case description / context card */}
                    {activeCase.description ? (
                        <div className="bg-surface-container-lowest rounded-xl p-8 border border-outline-variant">
                            <h3 className="font-headline-md text-headline-md text-primary mb-3">About this matter</h3>
                            <p className="text-on-surface-variant font-body-md leading-relaxed">
                                {activeCase.description}
                            </p>
                        </div>
                    ) : null}

                    {/* Other cases switcher */}
                    {dashboard.cases.length > 1 ? (
                        <div className="bg-surface-container-lowest rounded-xl p-8 border border-outline-variant">
                            <h3 className="font-headline-md text-headline-md text-primary mb-4">Your other matters</h3>
                            <div className="space-y-2">
                                {dashboard.cases
                                    .filter((c) => c.id !== activeCase.id)
                                    .map((c) => (
                                        <button
                                            key={c.id}
                                            type="button"
                                            onClick={() => setSelectedCaseId(c.id)}
                                            className="w-full text-left flex justify-between items-center px-4 py-3 rounded-lg bg-surface-container-low hover:bg-surface-container-high transition-colors"
                                        >
                                            <span className="font-body-md text-primary">{c.title}</span>
                                            <span className="font-label-md text-label-md text-on-surface-variant">
                                                {label(c.status)}
                                            </span>
                                        </button>
                                    ))}
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>
        </main>
    );
}
