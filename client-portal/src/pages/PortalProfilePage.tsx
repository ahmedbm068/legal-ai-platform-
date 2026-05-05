import { usePortal } from "../context/PortalContext";
import { formatDate } from "../portalPresentation";

export default function PortalProfilePage() {
    const { account, dashboard, theme, toggleTheme, logout } = usePortal();

    if (!account) return null;

    return (
        <div className="view-panel">
            <div className="view-header">
                <h2>Profile</h2>
                <p>Account details and workspace preferences.</p>
            </div>

            <div className="card">
                <h3>Your account</h3>
                <ul className="profile-list">
                    <li><strong>Name:</strong> {account.full_name}</li>
                    <li><strong>Email:</strong> {account.email}</li>
                    {account.phone ? <li><strong>Phone:</strong> {account.phone}</li> : null}
                    {account.address ? <li><strong>Address:</strong> {account.address}</li> : null}
                    <li><strong>Firm:</strong> {account.tenant_name ?? account.tenant_slug ?? "—"}</li>
                    <li><strong>Member since:</strong> {formatDate(account.created_at)}</li>
                </ul>
            </div>

            {dashboard ? (
                <div className="card">
                    <h3>Workspace summary</h3>
                    <ul className="profile-list">
                        <li><strong>Cases:</strong> {dashboard.metrics.total_cases}</li>
                        <li><strong>Active cases:</strong> {dashboard.metrics.active_cases}</li>
                        <li><strong>Documents:</strong> {dashboard.metrics.total_documents}</li>
                        <li><strong>Consultation requests:</strong> {dashboard.metrics.consultation_requests}</li>
                    </ul>
                </div>
            ) : null}

            <div className="card">
                <h3>Preferences</h3>
                <div className="profile-actions">
                    <button className="btn secondary" onClick={toggleTheme} type="button">
                        Switch to {theme === "dark" ? "light" : "dark"} mode
                    </button>
                    <button className="btn ghost" onClick={logout} type="button">
                        Sign out
                    </button>
                </div>
            </div>
        </div>
    );
}
