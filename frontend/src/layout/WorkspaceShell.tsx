import { NavLink, Outlet } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { APP_ROUTES } from "../router/appRoutes";

function navClassName(isActive: boolean) {
    return isActive ? "shell-nav-link active" : "shell-nav-link";
}

export default function WorkspaceShell() {
    const {
        selectedCaseId,
        user,
        logout,
        theme,
        toggleTheme,
        language,
        setLanguage,
        t,
    } = useRoutedWorkspace();

    const routeCopyByPath: Record<string, { label: string; description: string }> = {
        "/dashboard": {
            label: t("navDashboardLabel", "Home Dashboard"),
            description: t("navDashboardDesc", "Today priorities, urgent risks, and key actions"),
        },
        "/cases": {
            label: t("navCasesLabel", "Cases"),
            description: t("navCasesDesc", "Case list and tabbed detail workflow"),
        },
        "/assistant": {
            label: t("navAssistantLabel", "Assistant"),
            description: t("navAssistantDesc", "Case-contextual legal copilot"),
        },
        "/documents": {
            label: t("navDocumentsLabel", "Documents"),
            description: t("navDocumentsDesc", "Upload and processing queue"),
        },
        "/calendar": {
            label: t("navCalendarLabel", "Calendar"),
            description: t("navCalendarDesc", "Deadlines and why-they-matter"),
        },
        "/settings": {
            label: t("navSettingsLabel", "Settings / Profile"),
            description: t("navSettingsDesc", "Admin and workspace preferences"),
        },
    };

    function buildRoutePath(path: string, useSelectedCase?: boolean) {
        if (!useSelectedCase || !selectedCaseId) {
            return path;
        }
        return `${path}/${selectedCaseId}`;
    }

    return (
        <div className="shell-root">
            <aside className="shell-sidebar">
                <div className="shell-brand">
                    <p className="shell-kicker">{t("legalAiPlatform", "Legal AI Platform")}</p>
                    <h1>{t("lawyerWorkspace", "Lawyer Workspace")}</h1>
                    <p className="shell-subtitle">
                        {t("shellSubtitle", "Focused, task-first navigation for daily legal execution.")}
                    </p>
                    {user ? (
                        <p className="shell-user-pill">
                            {user.name} ({user.role})
                        </p>
                    ) : null}
                </div>

                <nav className="shell-nav" aria-label="Primary workspace navigation">
                    {APP_ROUTES.map((route) => (
                        <NavLink
                            key={route.path}
                            className={({ isActive }) => navClassName(isActive)}
                            to={buildRoutePath(route.path, route.useSelectedCase)}
                        >
                            <strong>{routeCopyByPath[route.path]?.label || route.label}</strong>
                            <span>{routeCopyByPath[route.path]?.description || route.description}</span>
                        </NavLink>
                    ))}
                </nav>

                <div className="shell-footer">
                    <NavLink className="shell-classic-link" to="/workspace-classic">
                        {t("openWorkspaceClassic", "Open Workspace Classic")}
                    </NavLink>
                    <p>
                        {t("classicRolloutNote", "Classic keeps the current monolith unchanged while this routed workspace is being rolled out.")}
                    </p>
                    <button className="shell-logout-button" onClick={logout} type="button">
                        {t("logout", "Logout")}
                    </button>
                </div>
            </aside>

            <main className="shell-content">
                <div className="shell-content-topbar" aria-label={t("workspacePreferences", "Workspace preferences")}>
                    <label className="shell-language-select compact" aria-label={t("assistantLanguageAria", "Interface language")}>
                        <select
                            onChange={(event) => setLanguage(event.target.value as "ar" | "en" | "de")}
                            value={language}
                        >
                            <option value="ar">{t("languageArabic", "Arabic")}</option>
                            <option value="en">{t("languageEnglish", "English")}</option>
                            <option value="de">{t("languageGerman", "German")}</option>
                        </select>
                    </label>
                    <button
                        aria-label={theme === "dark" ? t("darkMode", "Dark") : t("lightMode", "Light")}
                        className="shell-theme-toggle icon-only"
                        onClick={toggleTheme}
                        title={theme === "dark" ? t("darkMode", "Dark") : t("lightMode", "Light")}
                        type="button"
                    >
                        {theme === "dark" ? (
                            <svg aria-hidden="true" viewBox="0 0 20 20">
                                <path d="M12.8 2.5a7.2 7.2 0 1 0 4.7 12.7A7.6 7.6 0 0 1 12.8 2.5Z" />
                            </svg>
                        ) : (
                            <svg aria-hidden="true" viewBox="0 0 20 20">
                                <circle cx="10" cy="10" r="3.7" />
                                <path d="M10 1.8v2.2" />
                                <path d="M10 16v2.2" />
                                <path d="M1.8 10H4" />
                                <path d="M16 10h2.2" />
                                <path d="m3.6 3.6 1.6 1.6" />
                                <path d="m14.8 14.8 1.6 1.6" />
                                <path d="m16.4 3.6-1.6 1.6" />
                                <path d="m5.2 14.8-1.6 1.6" />
                            </svg>
                        )}
                    </button>
                </div>
                <div className="shell-content-main">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
