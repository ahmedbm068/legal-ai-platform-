import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import type { CalendarAppointment } from "../types";

type DocSummary = {
    caseCount: number;
    totalDocuments: number;
    pendingDocuments: number;
    pendingRecordings: number;
    pendingImageBatches: number;
};

type CalSummary = {
    totalAppointments: number;
    upcomingAppointments: number;
    aiSuggestedAppointments: number;
    nextItems: CalendarAppointment[];
};

type DonutSegment = { label: string; value: number; color: string };

function DonutChart({ segments }: { segments: DonutSegment[] }) {
    const total = segments.reduce((s, seg) => s + seg.value, 0);
    const r = 52;
    const cx = 60;
    const cy = 60;
    const circ = 2 * Math.PI * r;
    let accumulated = 0;

    return (
        <svg viewBox="0 0 120 120" className="db-donut-svg" aria-hidden="true">
            {total === 0 ? (
                <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--shell-border)" strokeWidth="14" />
            ) : (
                segments.filter((s) => s.value > 0).map((seg, i) => {
                    const dashLen = (seg.value / total) * circ;
                    const dashOffset = circ - accumulated;
                    accumulated += dashLen;
                    return (
                        <circle
                            key={i}
                            cx={cx} cy={cy} r={r}
                            fill="none"
                            stroke={seg.color}
                            strokeWidth="14"
                            strokeLinecap="butt"
                            strokeDasharray={`${dashLen} ${circ - dashLen}`}
                            strokeDashoffset={dashOffset}
                            style={{ transform: "rotate(-90deg)", transformOrigin: "60px 60px" }}
                        />
                    );
                })
            )}
            <circle cx={cx} cy={cy} r={r - 14} fill="var(--shell-panel)" />
        </svg>
    );
}

function fmtTime(iso: string) {
    return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}
function fmtDate(iso: string) {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(iso));
}
function isToday(iso: string) {
    const d = new Date(iso);
    const now = new Date();
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}
function isFuture(iso: string) {
    return new Date(iso).getTime() > Date.now();
}
function statusColor(status: string) {
    const s = status.toLowerCase().replace(/[_\s]+/g, "");
    if (s === "confirmed" || s === "completed") return "db-pill db-pill-green";
    if (s === "pending" || s === "scheduled") return "db-pill db-pill-blue";
    if (s === "cancelled") return "db-pill db-pill-gray";
    if (s === "rescheduled") return "db-pill db-pill-orange";
    return "db-pill db-pill-blue";
}
function caseStatusColor(status: string) {
    const s = status.toLowerCase();
    if (s === "in_progress") return "db-pill db-pill-green";
    if (s === "open") return "db-pill db-pill-blue";
    if (s === "closed") return "db-pill db-pill-gray";
    return "db-pill db-pill-orange";
}
function caseStatusLabel(status: string) {
    return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function DashboardPage() {
    const navigate = useNavigate();
    const { t, cases, clients, loadGlobalDocumentsSummary, loadGlobalCalendarSummary } = useRoutedWorkspace();
    const [docSummary, setDocSummary] = useState<DocSummary | null>(null);
    const [calSummary, setCalSummary] = useState<CalSummary | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        Promise.all([
            loadGlobalDocumentsSummary().catch(() => null),
            loadGlobalCalendarSummary().catch(() => null),
        ]).then(([docs, cal]) => {
            setDocSummary(docs as DocSummary | null);
            setCalSummary(cal as CalSummary | null);
            setLoading(false);
        });
    }, [loadGlobalDocumentsSummary, loadGlobalCalendarSummary]);

    const clientById = useMemo(() => new Map(clients.map((c) => [c.id, c])), [clients]);
    const openCases = useMemo(() => cases.filter((c) => c.status === "open"), [cases]);
    const inProgressCases = useMemo(() => cases.filter((c) => c.status === "in_progress"), [cases]);
    const closedCases = useMemo(() => cases.filter((c) => c.status === "closed"), [cases]);
    const archivedCases = useMemo(() => cases.filter((c) => c.status === "archived"), [cases]);
    const activeCases = useMemo(() => cases.filter((c) => c.status === "open" || c.status === "in_progress").slice(0, 6), [cases]);

    const todayAppointments = useMemo(
        () => calSummary?.nextItems.filter((a) => isToday(a.scheduled_at)) ?? [],
        [calSummary]
    );
    const upcomingAppointments = useMemo(
        () => calSummary?.nextItems.filter((a) => isFuture(a.scheduled_at)).slice(0, 5) ?? [],
        [calSummary]
    );

    const donutSegments: DonutSegment[] = [
        { label: "In Progress", value: inProgressCases.length, color: "var(--shell-accent)" },
        { label: "Open", value: openCases.length, color: "#f0a500" },
        { label: "Closed", value: closedCases.length, color: "#6b7280" },
        { label: "Archived", value: archivedCases.length, color: "var(--shell-border)" },
    ];

    const totalDonut = donutSegments.reduce((s, seg) => s + seg.value, 0);
    const activePct = totalDonut > 0 ? Math.round(((inProgressCases.length + openCases.length) / totalDonut) * 100) : 0;

    // Build a 7-day week starting from Monday
    const weekDays = useMemo(() => {
        const today = new Date();
        const dayOfWeek = today.getDay(); // 0=Sun
        const monday = new Date(today);
        monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7));
        return Array.from({ length: 7 }, (_, i) => {
            const d = new Date(monday);
            d.setDate(monday.getDate() + i);
            return d;
        });
    }, []);

    const appointmentDaySet = useMemo(() => {
        if (!calSummary) return new Set<string>();
        return new Set(
            calSummary.nextItems.map((a) => {
                const d = new Date(a.scheduled_at);
                return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
            })
        );
    }, [calSummary]);

    const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const today = new Date();

    return (
        <section className="shell-page db-page">
            <header className="db-page-header">
                <div>
                    <p className="shell-page-kicker">{t("dashboardKicker", "Home Dashboard")}</p>
                    <h2 className="db-title">{t("dashboardTitle", "Dashboard")}</h2>
                </div>
                <div className="db-header-actions">
                    <Link to="/cases" className="db-action-btn">{t("allCases", "All Cases")}</Link>
                    <Link to="/assistant" className="db-action-btn db-action-btn-primary">{t("openAssistant", "AI Assistant")}</Link>
                </div>
            </header>

            {/* KPI row */}
            <div className="db-kpi-row">
                <article className="db-kpi-card" role="button" tabIndex={0} onClick={() => navigate("/cases")} onKeyDown={(e) => e.key === "Enter" && navigate("/cases")}>
                    <div className="db-kpi-icon db-icon-cases">⚖</div>
                    <div className="db-kpi-body">
                        <span className="db-kpi-label">{t("totalCases", "Total Cases")}</span>
                        <strong className="db-kpi-value">{cases.length}</strong>
                        <span className="db-kpi-sub">{inProgressCases.length} {t("inProgress", "in progress")}</span>
                    </div>
                </article>
                <article className="db-kpi-card" role="button" tabIndex={0} onClick={() => navigate("/cases")} onKeyDown={(e) => e.key === "Enter" && navigate("/cases")}>
                    <div className="db-kpi-icon db-icon-active">◎</div>
                    <div className="db-kpi-body">
                        <span className="db-kpi-label">{t("activeCases", "Active Cases")}</span>
                        <strong className="db-kpi-value">{openCases.length + inProgressCases.length}</strong>
                        <span className="db-kpi-sub">{clients.length} {t("clients", "clients")}</span>
                    </div>
                </article>
                <article className="db-kpi-card" role="button" tabIndex={0} onClick={() => navigate("/documents")} onKeyDown={(e) => e.key === "Enter" && navigate("/documents")}>
                    <div className="db-kpi-icon db-icon-docs">📄</div>
                    <div className="db-kpi-body">
                        <span className="db-kpi-label">{t("documents", "Documents")}</span>
                        <strong className="db-kpi-value">{loading ? "—" : (docSummary?.totalDocuments ?? 0)}</strong>
                        {docSummary && docSummary.pendingDocuments > 0 ? (
                            <span className="db-kpi-sub db-kpi-warn">{docSummary.pendingDocuments} {t("pendingProcessing", "pending")}</span>
                        ) : (
                            <span className="db-kpi-sub">{t("allProcessed", "all processed")}</span>
                        )}
                    </div>
                </article>
                <article className="db-kpi-card" role="button" tabIndex={0} onClick={() => navigate("/calendar/0")} onKeyDown={(e) => e.key === "Enter" && navigate("/calendar/0")}>
                    <div className="db-kpi-icon db-icon-calendar">📅</div>
                    <div className="db-kpi-body">
                        <span className="db-kpi-label">{t("hearingsScheduled", "Hearings")}</span>
                        <strong className="db-kpi-value">{loading ? "—" : (calSummary?.upcomingAppointments ?? 0)}</strong>
                        <span className="db-kpi-sub">{todayAppointments.length > 0 ? `${todayAppointments.length} ${t("dueToday", "due today")}` : t("noneToday", "none today")}</span>
                    </div>
                </article>
            </div>

            {/* Main grid: Firm Snapshot + Upcoming Hearings */}
            <div className="db-main-grid">
                {/* Left: Firm Snapshot */}
                <article className="shell-card db-snapshot-card">
                    <h3 className="db-section-title">{t("firmSnapshot", "Firm Snapshot")}</h3>
                    <div className="db-snapshot-body">
                        <div className="db-donut-wrap">
                            <DonutChart segments={donutSegments} />
                            <div className="db-donut-center">
                                <strong>{activePct}%</strong>
                                <span>{t("caseStatus", "Active")}</span>
                            </div>
                        </div>
                        <div className="db-snapshot-stats">
                            <div className="db-stat-row">
                                <span className="db-stat-label">{t("totalCases", "Total Cases")}</span>
                                <strong className="db-stat-val">{cases.length}</strong>
                            </div>
                            <div className="db-stat-row">
                                <span className="db-stat-dot" style={{ background: "var(--shell-accent)" }} />
                                <span className="db-stat-label">{t("inProgress", "In Progress")}</span>
                                <strong className="db-stat-val">{inProgressCases.length}</strong>
                            </div>
                            <div className="db-stat-row">
                                <span className="db-stat-dot" style={{ background: "#f0a500" }} />
                                <span className="db-stat-label">{t("open", "Open")}</span>
                                <strong className="db-stat-val">{openCases.length}</strong>
                            </div>
                            <div className="db-stat-row">
                                <span className="db-stat-dot" style={{ background: "#6b7280" }} />
                                <span className="db-stat-label">{t("closed", "Closed")}</span>
                                <strong className="db-stat-val">{closedCases.length}</strong>
                            </div>
                            <div className="db-stat-row">
                                <span className="db-stat-dot" style={{ background: "var(--shell-border)" }} />
                                <span className="db-stat-label">{t("archived", "Archived")}</span>
                                <strong className="db-stat-val">{archivedCases.length}</strong>
                            </div>
                            <hr className="db-divider" />
                            <div className="db-stat-row">
                                <span className="db-stat-label">{t("clients", "Clients")}</span>
                                <strong className="db-stat-val">{clients.length}</strong>
                            </div>
                            {docSummary ? (
                                <div className="db-stat-row">
                                    <span className="db-stat-label">{t("documents", "Documents")}</span>
                                    <strong className="db-stat-val">{docSummary.totalDocuments}</strong>
                                </div>
                            ) : null}
                        </div>
                    </div>
                </article>

                {/* Right: Priority Hearings + mini calendar */}
                <div className="db-right-col">
                    <article className="shell-card db-hearings-card">
                        <div className="db-hearings-head">
                            <h3 className="db-section-title">{t("priorityTimeline", "Priority Timeline")}</h3>
                            <span className="db-section-meta">{upcomingAppointments.length} {t("upcoming", "upcoming")}</span>
                        </div>
                        <div className="db-hearings-table">
                            <div className="db-hearings-header">
                                <span>{t("timeline", "Timeline")}</span>
                                <span>{t("matter", "Matter")}</span>
                                <span>{t("status", "Status")}</span>
                            </div>
                            {loading ? (
                                <div className="db-empty-row">{t("loadingAppointments", "Loading...")}</div>
                            ) : upcomingAppointments.length === 0 ? (
                                <div className="db-empty-row">{t("noUpcomingHearings", "No upcoming hearings scheduled.")}</div>
                            ) : (
                                upcomingAppointments.map((appt) => (
                                    <div className="db-hearing-row" key={appt.id}>
                                        <div className="db-hearing-date">
                                            <strong>{isToday(appt.scheduled_at) ? t("today", "Today") : fmtDate(appt.scheduled_at)}</strong>
                                            <span>{fmtTime(appt.scheduled_at)}</span>
                                        </div>
                                        <div className="db-hearing-title">
                                            <strong>{appt.title}</strong>
                                            {appt.case_title ? <span>{appt.case_title}</span> : null}
                                        </div>
                                        <div>
                                            <span className={statusColor(appt.status)}>{appt.status.replace(/_/g, " ")}</span>
                                            {appt.is_ai_suggested ? <span className="db-ai-badge">AI</span> : null}
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </article>

                    {/* Mini calendar */}
                    <article className="shell-card db-minical-card">
                        <h3 className="db-section-title">{t("thisWeek", "This Week")}</h3>
                        <div className="db-minical-grid">
                            {weekDays.map((day, i) => {
                                const key = `${day.getFullYear()}-${day.getMonth()}-${day.getDate()}`;
                                const isCurrentDay = day.getDate() === today.getDate() && day.getMonth() === today.getMonth();
                                const hasEvent = appointmentDaySet.has(key);
                                return (
                                    <div key={i} className={`db-cal-day ${isCurrentDay ? "is-today" : ""} ${hasEvent ? "has-event" : ""}`}>
                                        <span className="db-cal-name">{DAY_NAMES[i]}</span>
                                        <span className="db-cal-num">{day.getDate()}</span>
                                        {hasEvent ? <span className="db-cal-dot" /> : null}
                                    </div>
                                );
                            })}
                        </div>
                    </article>
                </div>
            </div>

            {/* Active Cases table */}
            <article className="shell-card db-cases-card">
                <div className="db-cases-head">
                    <h3 className="db-section-title">{t("activeCases", "Active Cases")}</h3>
                    <Link to="/cases" className="db-see-all">{t("seeAll", "See all")} →</Link>
                </div>
                <div className="db-cases-table">
                    <div className="db-cases-header">
                        <span>{t("caseName", "Case Name")}</span>
                        <span>{t("client", "Client")}</span>
                        <span>{t("jurisdiction", "Jurisdiction")}</span>
                        <span>{t("status", "Status")}</span>
                        <span>{t("actions", "Actions")}</span>
                    </div>
                    {activeCases.length === 0 ? (
                        <div className="db-empty-row">{t("noActiveCases", "No active cases. Create your first case to get started.")}</div>
                    ) : (
                        activeCases.map((c) => {
                            const client = clientById.get(c.client_id);
                            return (
                                <div className="db-case-row" key={c.id}>
                                    <div className="db-case-name">
                                        <strong>{c.title}</strong>
                                        <span>#{c.id}</span>
                                    </div>
                                    <div className="db-case-client">
                                        <span className="db-client-avatar">{(client?.name || "?")[0].toUpperCase()}</span>
                                        <span>{client?.name || `Client #${c.client_id}`}</span>
                                    </div>
                                    <span className="db-jurisdiction">{c.jurisdiction_country.replace(/_/g, " ")}</span>
                                    <span className={caseStatusColor(c.status)}>{caseStatusLabel(c.status)}</span>
                                    <div className="db-case-actions">
                                        <Link to={`/cases/${c.id}/overview`} className="db-row-link">{t("open", "Open")}</Link>
                                        <Link to={`/assistant/${c.id}`} className="db-row-link db-row-link-ai">AI</Link>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </article>
        </section>
    );
}
