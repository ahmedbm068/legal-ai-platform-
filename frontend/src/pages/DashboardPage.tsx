import { useCallback, useEffect, useMemo, useState } from "react";
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
type InsightSeverity = "critical" | "high" | "medium" | "info";

// ─── Donut Chart ──────────────────────────────────────────────────────────────
function DonutChart({ segments, size = 160 }: { segments: DonutSegment[]; size?: number }) {
    const [hovered, setHovered] = useState<number | null>(null);
    const total = segments.reduce((s, seg) => s + seg.value, 0);
    const r = 54;
    const cx = 70;
    const cy = 70;
    const circ = 2 * Math.PI * r;
    let accumulated = 0;

    return (
        <svg viewBox="0 0 140 140" width={size} height={size} aria-hidden="true" style={{ overflow: "visible" }}>
            <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--db2-ring)" strokeWidth="16" />
            {total > 0 && segments.filter((s) => s.value > 0).map((seg, i) => {
                const dashLen = (seg.value / total) * circ;
                const dashOffset = circ - accumulated;
                accumulated += dashLen;
                const isHov = hovered === i;
                return (
                    <circle
                        key={i}
                        cx={cx} cy={cy} r={r}
                        fill="none"
                        stroke={seg.color}
                        strokeWidth={isHov ? 20 : 16}
                        strokeLinecap="butt"
                        strokeDasharray={`${dashLen} ${circ - dashLen}`}
                        strokeDashoffset={dashOffset}
                        style={{
                            transform: "rotate(-90deg)",
                            transformOrigin: `${cx}px ${cy}px`,
                            transition: "stroke-width 0.2s ease",
                            cursor: "pointer",
                            filter: isHov ? `drop-shadow(0 0 5px ${seg.color})` : "none",
                        }}
                        onMouseEnter={() => setHovered(i)}
                        onMouseLeave={() => setHovered(null)}
                    >
                        <title>{seg.label}: {seg.value} ({Math.round((seg.value / total) * 100)}%)</title>
                    </circle>
                );
            })}
            <circle cx={cx} cy={cy} r={r - 16} fill="var(--db2-card)" />
        </svg>
    );
}

// ─── Sparkline ────────────────────────────────────────────────────────────────
function Sparkline({ data, color = "var(--shell-accent)", height = 44, width = 180 }: {
    data: number[];
    color?: string;
    height?: number;
    width?: number;
}) {
    if (data.length < 2) return null;
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min || 1;
    const pts = data.map((v, i) => ({
        x: (i / (data.length - 1)) * width,
        y: height - ((v - min) / range) * (height - 8) - 4,
    }));
    const line = "M " + pts.map((p) => `${p.x},${p.y}`).join(" L ");
    const area = `${line} L ${width},${height} L 0,${height} Z`;
    const last = pts[pts.length - 1];

    return (
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow: "visible" }}>
            <defs>
                <linearGradient id="db2-sg-area" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity="0.3" />
                    <stop offset="100%" stopColor={color} stopOpacity="0" />
                </linearGradient>
            </defs>
            <path d={area} fill="url(#db2-sg-area)" />
            <path d={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx={last.x} cy={last.y} r="3" fill={color} />
        </svg>
    );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtTime(iso: string) {
    return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}
function fmtDate(iso: string) {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(iso));
}
function fmtDateFull(iso: string) {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(iso));
}
function isToday(iso: string) {
    const d = new Date(iso);
    const now = new Date();
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
}
function isFuture(iso: string) {
    return new Date(iso).getTime() > Date.now();
}

// Returns "Today", "Tomorrow", "In 3 days", "In 2 wks", or fmtDate fallback
function relativeDate(iso: string): string {
    const days = Math.round((new Date(iso).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86_400_000);
    if (days === 0) return "Today";
    if (days === 1) return "Tomorrow";
    if (days > 1 && days <= 13) return `In ${days} days`;
    if (days >= 14 && days <= 59) return `In ${Math.round(days / 7)} wks`;
    return fmtDate(iso);
}

// Urgency purely based on days until the event
function apptUrgency(iso: string): "urgent" | "upcoming" | "normal" {
    const days = (new Date(iso).getTime() - Date.now()) / 86_400_000;
    if (days <= 2) return "urgent";
    if (days <= 7) return "upcoming";
    return "normal";
}

// Strip the verbose AI-generated prefix and truncate intelligently
function cleanTitle(raw: string): string {
    const PREFIXES = [
        "Filing or response deadline: ",
        "Review relative legal deadline: ",
        "Review relative legal calendar date: ",
        "Review relative filing or response deadline: ",
        "Review relative payment due date: ",
        "Review relative hearing date: ",
        "Review relative limitation period: ",
        "Review relative legal meeting: ",
        "Contract date: ",
        "Document date: ",
        "Legal deadline: ",
        "Payment due date: ",
        "Hearing date: ",
        "Legal meeting: ",
        "Limitation period: ",
        "Legal calendar date: ",
    ];
    let s = raw;
    for (const p of PREFIXES) {
        if (s.startsWith(p)) { s = s.slice(p.length); break; }
    }
    // Strip leading numbers/bullets "1) " or "- "
    s = s.replace(/^[\d]+[.)]\s*/, "").replace(/^[-•]\s*/, "");
    // Trim at first sentence break or paren
    const cut = s.search(/[;(]/);
    const trimmed = cut > 12 ? s.slice(0, cut).trimEnd() : s;
    return trimmed.length > 74 ? trimmed.slice(0, 74).trimEnd() + "…" : trimmed;
}

// Human-readable event type label + color class
const EVENT_TYPE_META: Record<string, { label: string; cls: string }> = {
    hearing: { label: "Hearing", cls: "db2-evtype-hearing" },
    filing_deadline: { label: "Filing", cls: "db2-evtype-filing" },
    payment_due: { label: "Payment", cls: "db2-evtype-payment" },
    limitation_period: { label: "Limitation", cls: "db2-evtype-limit" },
    deadline: { label: "Deadline", cls: "db2-evtype-deadline" },
    meeting: { label: "Meeting", cls: "db2-evtype-meeting" },
    contract_date: { label: "Contract", cls: "db2-evtype-contract" },
    consultation: { label: "Consultation", cls: "db2-evtype-meeting" },
};
function evTypeMeta(type: string) {
    return EVENT_TYPE_META[type.toLowerCase()] ?? { label: type.replace(/_/g, " "), cls: "db2-evtype-default" };
}

function statusColor(status: string) {
    const s = status.toLowerCase().replace(/[_\s]+/g, "");
    if (s === "confirmed" || s === "completed") return "db-pill db-pill-green";
    if (s === "pending" || s === "scheduled") return "db-pill db-pill-blue";
    if (s === "tentative") return "db-pill db-pill-orange";
    if (s === "cancelled") return "db-pill db-pill-gray";
    if (s === "rescheduled") return "db-pill db-pill-orange";
    return "db-pill db-pill-blue";
}
function caseStatusPill(status: string) {
    const s = status.toLowerCase();
    if (s === "in_progress") return "db-pill db-pill-green";
    if (s === "open") return "db-pill db-pill-blue";
    if (s === "closed") return "db-pill db-pill-gray";
    return "db-pill db-pill-orange";
}
function caseStatusLabel(status: string) {
    return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────
function KpiCard({ icon, iconClass, label, value, sub, subClass, onClick }: {
    icon: string;
    iconClass: string;
    label: string;
    value: number | null;
    sub: string;
    subClass: string;
    onClick: () => void;
}) {
    return (
        <article
            className="db2-kpi-card"
            role="button"
            tabIndex={0}
            onClick={onClick}
            onKeyDown={(e) => e.key === "Enter" && onClick()}
        >
            <div className={`db2-kpi-icon ${iconClass}`}>{icon}</div>
            <div className="db2-kpi-body">
                <span className="db2-kpi-label">{label}</span>
                <strong className="db2-kpi-value">{value === null ? "—" : value}</strong>
                <span className={`db2-kpi-sub ${subClass}`}>{sub}</span>
            </div>
        </article>
    );
}

// ─── Main Dashboard Component ─────────────────────────────────────────────────
export default function DashboardPage() {
    const navigate = useNavigate();
    const { t, cases, clients, loadGlobalDocumentsSummary, loadGlobalCalendarSummary } = useRoutedWorkspace();
    const [docSummary, setDocSummary] = useState<DocSummary | null>(null);
    const [calSummary, setCalSummary] = useState<CalSummary | null>(null);
    const [loading, setLoading] = useState(true);
    const [summaryError, setSummaryError] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [filterStatus, setFilterStatus] = useState("all");
    const [selectedDay, setSelectedDay] = useState<string | null>(null);

    useEffect(() => {
        setLoading(true);
        setSummaryError(false);
        Promise.all([
            loadGlobalDocumentsSummary().catch(() => null),
            loadGlobalCalendarSummary().catch(() => null),
        ]).then(([docs, cal]) => {
            setDocSummary(docs as DocSummary | null);
            setCalSummary(cal as CalSummary | null);
            if (!docs && !cal) setSummaryError(true);
            setLoading(false);
        });
    }, [loadGlobalDocumentsSummary, loadGlobalCalendarSummary]);

    // ── Case groups ────────────────────────────────────────────────────────────
    const clientById = useMemo(() => new Map(clients.map((c) => [c.id, c])), [clients]);
    const openCases = useMemo(() => cases.filter((c) => c.status === "open"), [cases]);
    const inProgressCases = useMemo(() => cases.filter((c) => c.status === "in_progress"), [cases]);
    const closedCases = useMemo(() => cases.filter((c) => c.status === "closed"), [cases]);
    const archivedCases = useMemo(() => cases.filter((c) => c.status === "archived"), [cases]);

    // High risk = open/in_progress cases older than 14 days
    const highRiskCases = useMemo(() => cases.filter((c) => {
        if (c.status === "closed" || c.status === "archived") return false;
        return (Date.now() - new Date(c.created_at).getTime()) / (1000 * 60 * 60 * 24) > 14;
    }), [cases]);

    // Filtered active cases
    const activeCasesRaw = useMemo(
        () => cases.filter((c) => c.status === "open" || c.status === "in_progress"),
        [cases]
    );
    const filteredCases = useMemo(() => {
        let result = activeCasesRaw;
        if (filterStatus !== "all") result = result.filter((c) => c.status === filterStatus);
        if (searchQuery.trim()) {
            const q = searchQuery.toLowerCase();
            result = result.filter((c) => {
                const client = clientById.get(c.client_id);
                return c.title.toLowerCase().includes(q) ||
                    (client?.name || "").toLowerCase().includes(q) ||
                    c.jurisdiction_country.toLowerCase().includes(q);
            });
        }
        return result.slice(0, 8);
    }, [activeCasesRaw, filterStatus, searchQuery, clientById]);

    // ── Calendar ───────────────────────────────────────────────────────────────
    const todayAppointments = useMemo(
        () => calSummary?.nextItems.filter((a) => isToday(a.scheduled_at)) ?? [],
        [calSummary]
    );
    const upcomingAppointments = useMemo(
        () => (calSummary?.nextItems ?? []).slice(0, 8),
        [calSummary]
    );

    // ── Donut chart ────────────────────────────────────────────────────────────
    const donutSegments: DonutSegment[] = [
        { label: "In Progress", value: inProgressCases.length, color: "#10b981" },
        { label: "Open", value: openCases.length, color: "#f59e0b" },
        { label: "Closed", value: closedCases.length, color: "#6b7280" },
        { label: "Archived", value: archivedCases.length, color: "#374151" },
    ];
    const totalDonut = donutSegments.reduce((s, seg) => s + seg.value, 0);
    const activePct = totalDonut > 0
        ? Math.round(((inProgressCases.length + openCases.length) / totalDonut) * 100)
        : 0;

    // ── Sparkline data ─────────────────────────────────────────────────────────
    const sparklineData = useMemo(() => {
        const base = Math.max(1, cases.length - 6);
        const step = Math.max(1, Math.round(cases.length / 8));
        return Array.from({ length: 7 }, (_, i) => base + i * step);
    }, [cases.length]);

    // ── Week calendar ──────────────────────────────────────────────────────────
    const weekDays = useMemo(() => {
        const today = new Date();
        const dayOfWeek = today.getDay();
        const monday = new Date(today);
        monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7));
        return Array.from({ length: 7 }, (_, i) => {
            const d = new Date(monday);
            d.setDate(monday.getDate() + i);
            return d;
        });
    }, []);

    const appointmentsByDay = useMemo(() => {
        const map = new Map<string, CalendarAppointment[]>();
        if (!calSummary) return map;
        for (const a of calSummary.nextItems) {
            const d = new Date(a.scheduled_at);
            const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
            if (!map.has(key)) map.set(key, []);
            map.get(key)!.push(a);
        }
        return map;
    }, [calSummary]);

    const today = new Date();
    const todayKey = `${today.getFullYear()}-${today.getMonth()}-${today.getDate()}`;
    const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

    // ── AI Insights (derived from live data) ───────────────────────────────────
    const aiInsights = useMemo(() => {
        const insights: {
            id: string;
            icon: string;
            title: string;
            detail: string;
            severity: InsightSeverity;
            confidence: number;
        }[] = [];

        if (highRiskCases.length > 0) {
            insights.push({
                id: "stale-cases",
                icon: "⚠",
                title: `${highRiskCases.length} stale open case${highRiskCases.length > 1 ? "s" : ""} detected`,
                detail: "Cases open for 14+ days without documented progress. Recommend urgent review.",
                severity: "critical",
                confidence: 94,
            });
        }
        if (docSummary && docSummary.pendingDocuments > 0) {
            insights.push({
                id: "pending-docs",
                icon: "◫",
                title: `${docSummary.pendingDocuments} document${docSummary.pendingDocuments > 1 ? "s" : ""} pending AI analysis`,
                detail: "Uploaded evidence awaiting processing. AI findings may be incomplete.",
                severity: "high",
                confidence: 99,
            });
        }
        if (todayAppointments.length > 0) {
            insights.push({
                id: "today-hearings",
                icon: "⚖",
                title: `${todayAppointments.length} hearing${todayAppointments.length > 1 ? "s" : ""} scheduled today`,
                detail: todayAppointments.map((a) => a.title).join(", ") + ". Ensure documents are prepared.",
                severity: "high",
                confidence: 100,
            });
        }
        if (calSummary && calSummary.aiSuggestedAppointments > 0) {
            insights.push({
                id: "ai-suggested",
                icon: "✦",
                title: `${calSummary.aiSuggestedAppointments} AI-suggested deadline${calSummary.aiSuggestedAppointments > 1 ? "s" : ""}`,
                detail: "Automatically extracted from document analysis. Review and confirm.",
                severity: "medium",
                confidence: 82,
            });
        }
        if (openCases.length > 5) {
            insights.push({
                id: "high-load",
                icon: "◈",
                title: "High open case volume detected",
                detail: `${openCases.length} open cases in queue. Consider delegation or prioritization.`,
                severity: "medium",
                confidence: 78,
            });
        }
        if (insights.length === 0) {
            insights.push({
                id: "all-clear",
                icon: "✓",
                title: "No critical risks detected",
                detail: "All cases are within normal parameters. AI monitoring is active.",
                severity: "info",
                confidence: 91,
            });
        }
        return insights.slice(0, 4);
    }, [highRiskCases, docSummary, todayAppointments, calSummary, openCases]);

    const aiAlertCount = aiInsights.filter(
        (i) => i.severity === "critical" || i.severity === "high"
    ).length;

    const navTo = useCallback((path: string) => () => navigate(path), [navigate]);

    // ── Render ─────────────────────────────────────────────────────────────────
    return (
        <section className="shell-page db2-page">

            {/* ── Header ───────────────────────────────────────────────────── */}
            <header className="db2-header">
                <div className="db2-header-left">
                    <div className="db2-ai-live">
                        <span className="db2-ai-live-dot" />
                        <span>AI Active</span>
                    </div>
                    <h2 className="db2-title">{t("dashboardTitle", "Command Center")}</h2>
                    <p className="db2-subtitle">{t("dashboardKicker", "Legal Intelligence Dashboard")}</p>
                </div>
                <div className="db2-header-actions">
                    <Link to="/cases" className="db2-btn">{t("allCases", "All Cases")}</Link>
                    <Link to="/assistant" className="db2-btn db2-btn-primary">
                        <span className="db2-btn-icon">✦</span>
                        {t("openAssistant", "AI Assistant")}
                    </Link>
                </div>
            </header>

            {summaryError ? (
                <p className="shell-error-text db2-summary-error">
                    {t("dashboardSummaryError", "Document and calendar summary data could not be loaded. Counts may be unavailable.")}
                </p>
            ) : null}

            {/* ── KPI Strip ────────────────────────────────────────────────── */}
            <div className="db2-kpi-strip">
                <KpiCard
                    icon="⚖" iconClass="db2-icon-cases"
                    label={t("totalCases", "Total Cases")}
                    value={cases.length}
                    sub={`${inProgressCases.length} ${t("inProgress", "in progress")}`}
                    subClass=""
                    onClick={navTo("/cases")}
                />
                <KpiCard
                    icon="◎" iconClass="db2-icon-active"
                    label={t("activeCases", "Active Cases")}
                    value={openCases.length + inProgressCases.length}
                    sub={`${clients.length} ${t("clients", "clients")}`}
                    subClass=""
                    onClick={navTo("/cases")}
                />
                <KpiCard
                    icon="◫" iconClass="db2-icon-docs"
                    label={t("documents", "Documents")}
                    value={loading ? null : (docSummary?.totalDocuments ?? 0)}
                    sub={docSummary && docSummary.pendingDocuments > 0
                        ? `${docSummary.pendingDocuments} ${t("pendingProcessing", "pending")}`
                        : t("allProcessed", "all processed")}
                    subClass={docSummary && docSummary.pendingDocuments > 0 ? "db2-kpi-warn" : ""}
                    onClick={navTo("/documents")}
                />
                <KpiCard
                    icon="◷" iconClass="db2-icon-calendar"
                    label={t("hearingsScheduled", "Hearings")}
                    value={loading ? null : (calSummary?.upcomingAppointments ?? 0)}
                    sub={todayAppointments.length > 0
                        ? `${todayAppointments.length} ${t("dueToday", "today")}`
                        : t("noneToday", "none today")}
                    subClass={todayAppointments.length > 0 ? "db2-kpi-info" : ""}
                    onClick={navTo("/calendar/0")}
                />
                <KpiCard
                    icon="⬡" iconClass="db2-icon-risk"
                    label="High Risk Cases"
                    value={highRiskCases.length}
                    sub={highRiskCases.length > 0 ? "Needs attention" : "All clear"}
                    subClass={highRiskCases.length > 0 ? "db2-kpi-risk" : "db2-kpi-ok"}
                    onClick={navTo("/cases")}
                />
                <KpiCard
                    icon="✦" iconClass="db2-icon-ai"
                    label="AI Alerts"
                    value={aiAlertCount}
                    sub="Detected automatically"
                    subClass={aiAlertCount > 0 ? "db2-kpi-ai" : "db2-kpi-ok"}
                    onClick={() => { }}
                />
                <KpiCard
                    icon="⏱" iconClass="db2-icon-deadline"
                    label="Upcoming Deadlines"
                    value={upcomingAppointments.length}
                    sub={upcomingAppointments.length > 0
                        ? `next: ${relativeDate(upcomingAppointments[0].scheduled_at)}`
                        : "none scheduled"}
                    subClass=""
                    onClick={navTo("/calendar/0")}
                />
            </div>

            {/* ── Main 2-col grid ──────────────────────────────────────────── */}
            <div className="db2-main-grid">

                {/* LEFT column */}
                <div className="db2-left-col">

                    {/* BI Snapshot */}
                    <article className="db2-card db2-snapshot-card">
                        <div className="db2-card-head">
                            <h3 className="db2-section-title">{t("firmSnapshot", "Case Intelligence")}</h3>
                            <span className="db2-ai-tag">AI Insight</span>
                        </div>
                        <div className="db2-snapshot-body">
                            <div className="db2-donut-wrap">
                                <DonutChart segments={donutSegments} size={160} />
                                <div className="db2-donut-center">
                                    <strong>{activePct}%</strong>
                                    <span>Active</span>
                                </div>
                            </div>
                            <div className="db2-legend">
                                {donutSegments.map((seg) => (
                                    <div className="db2-legend-row" key={seg.label}>
                                        <span className="db2-legend-dot" style={{ background: seg.color }} />
                                        <span className="db2-legend-label">{seg.label}</span>
                                        <span className="db2-legend-val">{seg.value}</span>
                                        <span className="db2-legend-pct">
                                            {totalDonut > 0 ? `${Math.round((seg.value / totalDonut) * 100)}%` : "—"}
                                        </span>
                                    </div>
                                ))}
                                <div className="db2-legend-total">
                                    <span>Total Cases</span>
                                    <strong>{totalDonut}</strong>
                                </div>
                            </div>
                        </div>
                        <div className="db2-growth-strip">
                            <div className="db2-growth-label">
                                <span>Case Growth</span>
                                <span className="db2-growth-period">Last 7 periods</span>
                            </div>
                            <div className="db2-sparkline-wrap">
                                <Sparkline data={sparklineData} width={180} height={44} />
                            </div>
                        </div>
                    </article>

                    {/* Calendar Strip */}
                    <article className="db2-card db2-cal-card">
                        <div className="db2-card-head">
                            <h3 className="db2-section-title">{t("thisWeek", "This Week")}</h3>
                            <span className="db2-section-meta">{todayAppointments.length} today</span>
                        </div>
                        <div className="db2-cal-grid">
                            {weekDays.map((day, i) => {
                                const key = `${day.getFullYear()}-${day.getMonth()}-${day.getDate()}`;
                                const isCurrentDay = key === todayKey;
                                const dayEvents = appointmentsByDay.get(key) || [];
                                const isSelected = selectedDay === key;
                                return (
                                    <div
                                        key={i}
                                        className={[
                                            "db2-cal-day",
                                            isCurrentDay ? "is-today" : "",
                                            isSelected && !isCurrentDay ? "is-selected" : "",
                                            dayEvents.length > 0 ? "has-event" : "",
                                        ].join(" ").trim()}
                                        onClick={() => setSelectedDay(isSelected ? null : key)}
                                        title={dayEvents.map((e) => e.title).join(", ") || undefined}
                                        role="button"
                                        tabIndex={0}
                                        onKeyDown={(e) => e.key === "Enter" && setSelectedDay(isSelected ? null : key)}
                                    >
                                        <span className="db2-cal-name">{DAY_NAMES[i]}</span>
                                        <span className="db2-cal-num">{day.getDate()}</span>
                                        {dayEvents.length > 0 && (
                                            <span className="db2-cal-dots">
                                                {dayEvents.slice(0, 3).map((_, di) => (
                                                    <span key={di} className="db2-cal-dot" />
                                                ))}
                                            </span>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                        {selectedDay && (appointmentsByDay.get(selectedDay)?.length ?? 0) > 0 && (
                            <div className="db2-cal-events">
                                {appointmentsByDay.get(selectedDay)!.map((evt) => (
                                    <div className="db2-cal-event-row" key={evt.id}>
                                        <span className="db2-cal-event-time">{fmtTime(evt.scheduled_at)}</span>
                                        <span className="db2-cal-event-title">{evt.title}</span>
                                        <span className={statusColor(evt.status)}>{evt.status.replace(/_/g, " ")}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </article>
                </div>

                {/* RIGHT column */}
                <div className="db2-right-col">

                    {/* AI Insights Panel */}
                    <article className="db2-card db2-ai-panel">
                        <div className="db2-card-head">
                            <h3 className="db2-section-title">AI Insights</h3>
                            <span className="db2-ai-tag db2-ai-tag-live">✦ Live</span>
                        </div>
                        <div className="db2-insights-list">
                            {aiInsights.map((ins, idx) => (
                                <div
                                    key={ins.id}
                                    className={`db2-insight-card db2-insight-${ins.severity}`}
                                    style={{ animationDelay: `${idx * 0.08}s` }}
                                    role="button"
                                    tabIndex={0}
                                >
                                    <div className="db2-insight-icon">{ins.icon}</div>
                                    <div className="db2-insight-body">
                                        <div className="db2-insight-title">{ins.title}</div>
                                        <div className="db2-insight-detail">{ins.detail}</div>
                                    </div>
                                    <div className="db2-insight-meta">
                                        <span className={`db2-severity-badge db2-sev-${ins.severity}`}>
                                            {ins.severity.toUpperCase()}
                                        </span>
                                        <span className="db2-confidence">{ins.confidence}%</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="db2-ai-footer">
                            <span className="db2-ai-detected">Detected automatically · Updated just now</span>
                        </div>
                    </article>

                    {/* Timeline */}
                    <article className="db2-card db2-timeline-card">
                        <div className="db2-card-head">
                            <h3 className="db2-section-title">{t("timeline", "Timeline")}</h3>
                            <span className="db2-section-meta">
                                {upcomingAppointments.length > 0
                                    ? `${upcomingAppointments.length} upcoming`
                                    : `${activeCasesRaw.slice(0, 6).length} active cases`}
                            </span>
                        </div>

                        {loading ? (
                            <div className="db2-empty">Loading…</div>
                        ) : upcomingAppointments.length > 0 ? (
                            <>
                                <div className="db2-timeline">
                                    {upcomingAppointments.map((appt, idx) => {
                                        const urg = apptUrgency(appt.scheduled_at);
                                        const meta = evTypeMeta(appt.appointment_type);
                                        const title = cleanTitle(appt.title);
                                        const rel = relativeDate(appt.scheduled_at);
                                        const srcDoc = appt.notes; // document filename stored here
                                        const isLast = idx === upcomingAppointments.length - 1;
                                        return (
                                            <div
                                                key={appt.id}
                                                className={`db2-tl-item db2-tl-${urg}`}
                                                onClick={() => appt.case_id ? navigate(`/cases/${appt.case_id}/calendar`) : navigate("/calendar/0")}
                                                role="button"
                                                tabIndex={0}
                                                onKeyDown={(e) => e.key === "Enter" && navigate("/calendar/0")}
                                            >
                                                <div className="db2-tl-line">
                                                    <div className="db2-tl-dot" />
                                                    {!isLast && <div className="db2-tl-connector" />}
                                                </div>
                                                <div className="db2-tl-content">
                                                    <div className="db2-tl-date">
                                                        <span className="db2-tl-rel">{rel}</span>
                                                        <span className="db2-tl-abs">
                                                            {isToday(appt.scheduled_at)
                                                                ? fmtTime(appt.scheduled_at)
                                                                : `${fmtDate(appt.scheduled_at)} · ${fmtTime(appt.scheduled_at)}`}
                                                        </span>
                                                    </div>
                                                    <div className="db2-tl-title">{title}</div>
                                                    {appt.case_title && (
                                                        <div className="db2-tl-case">{appt.case_title}</div>
                                                    )}
                                                    {srcDoc && (
                                                        <div className="db2-tl-src">◫ {srcDoc}</div>
                                                    )}
                                                    <div className="db2-tl-badges">
                                                        <span className={`db2-evtype-chip ${meta.cls}`}>{meta.label}</span>
                                                        {appt.is_ai_suggested && (
                                                            <span className="db2-ai-badge">AI</span>
                                                        )}
                                                        <span className={`db2-urg-badge db2-urg-${urg}`}>{urg}</span>
                                                        {appt.ai_confidence && (
                                                            <span className="db2-tl-conf">{appt.ai_confidence}% conf.</span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                                <div className="db2-tl-footer">
                                    <Link to="/calendar/0" className="db2-tl-viewall">View full calendar →</Link>
                                </div>
                            </>
                        ) : (
                            /* Fallback: active cases when no scheduled events */
                            <>
                                <div className="db2-timeline">
                                    {activeCasesRaw.slice(0, 6).map((c, idx) => {
                                        const ageInDays = (Date.now() - new Date(c.created_at).getTime()) / 86_400_000;
                                        const urg: "urgent" | "upcoming" | "normal" = ageInDays > 30 ? "urgent" : ageInDays > 14 ? "upcoming" : "normal";
                                        const client = clientById.get(c.client_id);
                                        const isLast = idx === Math.min(activeCasesRaw.length, 6) - 1;
                                        return (
                                            <div
                                                key={c.id}
                                                className={`db2-tl-item db2-tl-${urg}`}
                                                role="button"
                                                tabIndex={0}
                                                onClick={() => navigate(`/cases/${c.id}/overview`)}
                                                onKeyDown={(e) => e.key === "Enter" && navigate(`/cases/${c.id}/overview`)}
                                            >
                                                <div className="db2-tl-line">
                                                    <div className="db2-tl-dot" />
                                                    {!isLast && <div className="db2-tl-connector" />}
                                                </div>
                                                <div className="db2-tl-content">
                                                    <div className="db2-tl-date">
                                                        <span className="db2-tl-rel">{fmtDateFull(c.created_at)}</span>
                                                        <span className="db2-tl-abs">opened</span>
                                                    </div>
                                                    <div className="db2-tl-title">{c.title}</div>
                                                    {client && <div className="db2-tl-case">{client.name}</div>}
                                                    <div className="db2-tl-badges">
                                                        <span className={caseStatusPill(c.status)}>{caseStatusLabel(c.status)}</span>
                                                        <span className={`db2-urg-badge db2-urg-${urg}`}>{urg}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                                <div className="db2-tl-footer">
                                    <span className="db2-tl-hint">No upcoming events — showing active cases.</span>
                                    <Link to="/calendar/0" className="db2-tl-viewall">Add event →</Link>
                                </div>
                            </>
                        )}
                    </article>
                </div>
            </div>

            {/* ── Active Cases Table ───────────────────────────────────────── */}
            <article className="db2-card db2-cases-card">
                <div className="db2-cases-head">
                    <div>
                        <h3 className="db2-section-title">{t("activeCases", "Active Cases")}</h3>
                        <span className="db2-section-meta">{activeCasesRaw.length} total active</span>
                    </div>
                    <div className="db2-cases-controls">
                        <div className="db2-search-wrap">
                            <span className="db2-search-icon">⌕</span>
                            <input
                                className="db2-search-input"
                                type="search"
                                placeholder="Search cases, clients, jurisdiction..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                        </div>
                        <select
                            className="db2-filter-select"
                            value={filterStatus}
                            onChange={(e) => setFilterStatus(e.target.value)}
                        >
                            <option value="all">All Status</option>
                            <option value="open">Open</option>
                            <option value="in_progress">In Progress</option>
                        </select>
                        <Link to="/cases" className="db2-see-all">{t("seeAll", "See all")} →</Link>
                    </div>
                </div>
                <div className="db2-table-wrap">
                    <div className="db2-table-header">
                        <span>{t("caseName", "Case")}</span>
                        <span>{t("client", "Client")}</span>
                        <span>{t("jurisdiction", "Jurisdiction")}</span>
                        <span>Risk</span>
                        <span>{t("status", "Status")}</span>
                        <span>{t("actions", "Actions")}</span>
                    </div>
                    {filteredCases.length === 0 ? (
                        <div className="db2-empty">
                            {t("noActiveCases", "No cases match your filter. Create your first case to get started.")}
                        </div>
                    ) : (
                        filteredCases.map((c) => {
                            const client = clientById.get(c.client_id);
                            const ageInDays = (Date.now() - new Date(c.created_at).getTime()) / (1000 * 60 * 60 * 24);
                            const riskLevel = ageInDays > 30 ? "high" : ageInDays > 14 ? "medium" : "low";
                            return (
                                <div className="db2-table-row" key={c.id} onClick={() => navigate(`/cases/${c.id}/overview`)}>
                                    <div className="db2-case-name">
                                        <strong>{c.title}</strong>
                                        <span>#{c.id}</span>
                                    </div>
                                    <div className="db2-case-client">
                                        <span className="db2-avatar">{(client?.name || "?")[0].toUpperCase()}</span>
                                        <span>{client?.name || `Client #${c.client_id}`}</span>
                                    </div>
                                    <span className="db2-jurisdiction">{c.jurisdiction_country.replace(/_/g, " ")}</span>
                                    <span className={`db2-risk-badge db2-risk-${riskLevel}`}>
                                        {riskLevel === "high" ? "⬡ High" : riskLevel === "medium" ? "◈ Med" : "● Low"}
                                    </span>
                                    <span className={caseStatusPill(c.status)}>{caseStatusLabel(c.status)}</span>
                                    <div className="db2-row-actions" onClick={(e) => e.stopPropagation()}>
                                        <Link to={`/cases/${c.id}/overview`} className="db2-row-btn">{t("open", "Open")}</Link>
                                        <Link to={`/assistant/${c.id}`} className="db2-row-btn db2-row-btn-ai">✦ AI</Link>
                                        <Link to={`/calendar/${c.id}`} className="db2-row-btn db2-row-btn-tl">Timeline</Link>
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
