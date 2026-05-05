import { useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { usePortal } from "../context/PortalContext";
import { NAV_ITEMS } from "../portalPresentation";

const ROUTE_BY_VIEW: Record<string, string> = {
    dashboard: "/dashboard",
    cases: "/cases",
    documents: "/documents",
    requests: "/requests",
    assistant: "/assistant",
    calendar: "/calendar",
    profile: "/profile",
};

export default function PortalShell() {
    const {
        dashboard,
        account,
        theme,
        toggleTheme,
        logout,
        refreshDashboard,
        dashboardLoading,
        selectedCaseId,
    } = usePortal();
    const [searchQuery, setSearchQuery] = useState("");
    const searchRef = useRef<HTMLInputElement | null>(null);
    const navigate = useNavigate();

    const selectedCase = dashboard?.cases.find((c) => c.id === selectedCaseId) ?? null;

    return (
        <div className="portal-root workspace-root">
            <div className="ambient-background" />

            <header className="card workspace-header">
                <div>
                    <p className="eyebrow">Secure Client Workspace</p>
                    <h1>Welcome, {account?.full_name ?? "…"}</h1>
                    <p>
                        {selectedCase?.title ?? "Your legal matters"}
                    </p>
                </div>

                <div className="workspace-actions">
                    <div className="search-shell">
                        <span>Search</span>
                        <input
                            ref={searchRef}
                            placeholder="cases, docs, statuses…"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && searchQuery.trim()) {
                                    navigate(`/cases?q=${encodeURIComponent(searchQuery.trim())}`);
                                }
                            }}
                        />
                        <small>Ctrl/Cmd + K</small>
                    </div>
                    <button
                        className="btn secondary"
                        onClick={() => void refreshDashboard()}
                        disabled={dashboardLoading}
                        type="button"
                    >
                        {dashboardLoading ? "Refreshing…" : "Refresh"}
                    </button>
                    <button className="btn ghost" onClick={toggleTheme} type="button">
                        {theme === "dark" ? "Light mode" : "Dark mode"}
                    </button>
                    <button className="btn ghost" onClick={logout} type="button">
                        Sign out
                    </button>
                </div>
            </header>

            {dashboard ? (
                <section className="metric-grid">
                    <article className="card metric-card">
                        <span>Active cases</span>
                        <strong>{dashboard.metrics.active_cases}</strong>
                        <small>Under your account</small>
                    </article>
                    <article className="card metric-card">
                        <span>Documents</span>
                        <strong>{dashboard.metrics.total_documents}</strong>
                        <small>
                            {dashboard.metrics.pending_documents > 0
                                ? `${dashboard.metrics.pending_documents} processing`
                                : "all processed"}
                        </small>
                    </article>
                    <article className="card metric-card">
                        <span>Requests in review</span>
                        <strong>{dashboard.metrics.requests_under_review}</strong>
                        <small>Awaiting legal action</small>
                    </article>
                    <article className="card metric-card">
                        <span>Calendar items</span>
                        <strong>{dashboard.metrics.upcoming_appointments}</strong>
                        <small>Upcoming appointments</small>
                    </article>
                </section>
            ) : null}

            <section className="workspace-grid">
                <aside className="card workspace-nav">
                    {NAV_ITEMS.map((item) => {
                        const to = ROUTE_BY_VIEW[item.id] ?? "/dashboard";
                        return (
                            <NavLink
                                key={item.id}
                                to={to}
                                className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
                            >
                                <strong>{item.title}</strong>
                                <small>{item.subtitle}</small>
                            </NavLink>
                        );
                    })}

                    {selectedCase ? (
                        <div className="nav-note">
                            <h4>Active case</h4>
                            <p>{selectedCase.title}</p>
                            {selectedCase.lawyer_name ? (
                                <p>{selectedCase.lawyer_name} is managing your file.</p>
                            ) : null}
                        </div>
                    ) : null}
                </aside>

                <main className="workspace-main">
                    <Outlet context={{ searchQuery }} />
                </main>
            </section>
        </div>
    );
}
