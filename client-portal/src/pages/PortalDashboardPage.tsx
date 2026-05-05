import { usePortal } from "../context/PortalContext";
import { formatDate, label, riskFromCase, tone } from "../portalPresentation";

export default function PortalDashboardPage() {
    const { dashboard, dashboardLoading, dashboardError, refreshDashboard } = usePortal();

    if (dashboardLoading && !dashboard) {
        return (
            <div className="card">
                <p>Loading your dashboard…</p>
            </div>
        );
    }

    if (dashboardError) {
        return (
            <div className="card">
                <p className="error-msg">{dashboardError}</p>
                <button className="btn secondary" onClick={() => void refreshDashboard()} type="button">
                    Retry
                </button>
            </div>
        );
    }

    if (!dashboard) return null;

    const latestConsultation = dashboard.consultations[0] ?? null;
    const recentActivity = dashboard.activity.slice(0, 5);
    const upcomingEvents = dashboard.calendar_events
        .filter((e) => new Date(e.scheduled_at) >= new Date())
        .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at))
        .slice(0, 3);

    const highRiskCases = dashboard.cases.filter((c) => riskFromCase(c).tone === "danger");

    return (
        <div className="view-panel">
            <div className="view-header">
                <h2>Dashboard</h2>
                <p>Overview of your legal matters and next actions.</p>
            </div>

            {highRiskCases.length > 0 ? (
                <div className="card risk-alert">
                    <strong>⚠ {highRiskCases.length} case{highRiskCases.length > 1 ? "s" : ""} need attention</strong>
                    <ul>
                        {highRiskCases.map((c) => (
                            <li key={c.id}>{c.title} — {label(c.status)}</li>
                        ))}
                    </ul>
                </div>
            ) : null}

            {latestConsultation ? (
                <div className="card">
                    <h3>Latest consultation request</h3>
                    <p><strong>Reference:</strong> {latestConsultation.public_reference ?? "—"}</p>
                    <p>
                        <strong>Status:</strong>{" "}
                        <span className={`status-badge ${tone(latestConsultation.status)}`}>
                            {label(latestConsultation.status)}
                        </span>
                    </p>
                    <p><strong>Filed:</strong> {formatDate(latestConsultation.created_at)}</p>
                    {latestConsultation.issue_summary ? (
                        <p className="muted">{latestConsultation.issue_summary}</p>
                    ) : null}
                </div>
            ) : (
                <div className="card">
                    <h3>No consultation requests yet</h3>
                    <p>Go to <strong>Intake requests</strong> to submit your first consultation.</p>
                </div>
            )}

            {upcomingEvents.length > 0 ? (
                <div className="card">
                    <h3>Upcoming appointments</h3>
                    <ul className="event-list">
                        {upcomingEvents.map((ev) => (
                            <li key={ev.id} className="event-row">
                                <span className="event-date">{formatDate(ev.scheduled_at)}</span>
                                <span className="event-title">{ev.title}</span>
                                <span className={`status-badge ${tone(ev.status)}`}>{label(ev.status)}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            ) : null}

            {recentActivity.length > 0 ? (
                <div className="card">
                    <h3>Recent activity</h3>
                    <ul className="activity-list">
                        {recentActivity.map((item) => (
                            <li key={item.id} className="activity-row">
                                <span className="activity-title">{item.title}</span>
                                <span className="activity-date muted">{formatDate(item.created_at)}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            ) : null}

            {dashboard.jobs.some((j) => !["completed", "failed"].includes(j.status)) ? (
                <div className="card">
                    <p className="muted">
                        {dashboard.jobs.filter((j) => !["completed", "failed"].includes(j.status)).length} background job(s) still processing…
                    </p>
                </div>
            ) : null}
        </div>
    );
}
