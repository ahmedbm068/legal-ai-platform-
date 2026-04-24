import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";

export default function SettingsPage() {
    const { user, clients, cases, logout, t } = useRoutedWorkspace();

    return (
        <section className="shell-page">
            <header className="shell-page-header">
                <p className="shell-page-kicker">{t("settingsKicker", "Settings / Profile")}</p>
                <h2>{t("settingsTitle", "Admin and workspace preferences")}</h2>
                <p>{t("settingsSubtitle", "Profile and system settings are separated from day-to-day legal workflow pages.")}</p>
            </header>

            <div className="shell-grid shell-grid-2">
                <article className="shell-card">
                    <h3>{t("profile", "Profile")}</h3>
                    <ul className="shell-list shell-tight-list">
                        <li>{t("name", "Name")}: {user?.name || "N/A"}</li>
                        <li>{t("role", "Role")}: {user?.role || "N/A"}</li>
                        <li>{t("email", "Email")}: {user?.email || "N/A"}</li>
                        <li>{t("phone", "Phone")}: {user?.phone || t("noPhoneSaved", "No phone saved")}</li>
                    </ul>
                </article>

                <article className="shell-card">
                    <h3>{t("workspacePreferences", "Workspace preferences")}</h3>
                    <ul className="shell-list shell-tight-list">
                        <li>{t("clientsInWorkspace", "Clients in workspace")}: {clients.length}</li>
                        <li>{t("casesInWorkspace", "Cases in workspace")}: {cases.length}</li>
                        <li>{t("routedThemeLanguageNotice", "Theme/language controls remain available in the routed workspace.")}</li>
                    </ul>
                    <div className="shell-action-row">
                        <button onClick={logout} type="button">{t("logout", "Logout")}</button>
                    </div>
                </article>
            </div>
        </section>
    );
}
