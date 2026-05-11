import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";

type DefRowProps = { label: string; value: string };
function DefRow({ label, value }: DefRowProps) {
    return (
        <div className="settings-def-row">
            <span className="settings-def-label">{label}</span>
            <span className="settings-def-value">{value}</span>
        </div>
    );
}

export default function SettingsPage() {
    const { user, clients, cases, logout, t } = useRoutedWorkspace();

    return (
        <section className="shell-page settings-page">
            <header className="settings-header">
                <span className="settings-kicker">{t("settingsKicker", "Settings / Profile")}</span>
                <h2 className="settings-title">{t("settingsTitle", "Admin and workspace preferences")}</h2>
                <p className="settings-subtitle">{t("settingsSubtitle", "Profile and system settings are separated from day-to-day legal workflow pages.")}</p>
            </header>

            <div className="settings-grid">
                <article className="settings-card">
                    <div className="settings-card-head">
                        <h3 className="settings-card-title">{t("profile", "Profile")}</h3>
                        <span className="settings-card-meta">Account</span>
                    </div>
                    <div className="settings-def-list">
                        <DefRow label={t("name", "Name")} value={user?.name || "—"} />
                        <DefRow label={t("role", "Role")} value={user?.role || "—"} />
                        <DefRow label={t("email", "Email")} value={user?.email || "—"} />
                        <DefRow label={t("phone", "Phone")} value={user?.phone || t("noPhoneSaved", "No phone saved")} />
                    </div>
                </article>

                <article className="settings-card">
                    <div className="settings-card-head">
                        <h3 className="settings-card-title">{t("workspacePreferences", "Workspace preferences")}</h3>
                        <span className="settings-card-meta">Workspace</span>
                    </div>
                    <div className="settings-def-list">
                        <DefRow label={t("clientsInWorkspace", "Clients")} value={String(clients.length)} />
                        <DefRow label={t("casesInWorkspace", "Cases")} value={String(cases.length)} />
                    </div>
                    <p className="settings-note">{t("routedThemeLanguageNotice", "Theme and language controls remain available in the routed workspace header.")}</p>
                    <div className="settings-actions">
                        <button className="settings-danger-btn" onClick={logout} type="button">{t("logout", "Logout")}</button>
                    </div>
                </article>
            </div>
        </section>
    );
}
