import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { APP_ROUTES } from "../router/appRoutes";

const SIDEBAR_STORAGE_KEY = "legal-ai-shell-sidebar-expanded";

function navClassName(isActive: boolean) {
    return isActive ? "shell-nav-link active" : "shell-nav-link";
}

function routeIcon(path: string) {
    const iconPathByRoute: Record<string, string[]> = {
        "/dashboard": ["M4 10.5 10 5l6 5.5", "M6.5 9.5v6h7v-6"],
        "/cases": ["M4.5 6.5h11", "M6.5 4.5h7l1.5 2v9h-10v-9l1.5-2Z", "M7.5 10h5"],
        "/assistant": ["M5 5.5h10v7H9l-4 3v-10Z", "M8 8.5h4", "M8 10.5h2.5"],
        "/documents": ["M6 3.8h5l3 3v9.4H6V3.8Z", "M11 3.8v3h3", "M8 10h4", "M8 12.3h4"],
        "/editor": ["M5 14.5h10", "M7 12.5l5.8-5.8 1.5 1.5-5.8 5.8H7v-1.5Z"],
        "/calendar": ["M5 6.5h10v9H5v-9Z", "M7.5 4.5v3", "M12.5 4.5v3", "M5 9h10"],
        "/settings": ["M10 6.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z", "M10 3.5v2", "M10 14.5v2", "M3.5 10h2", "M14.5 10h2"],
    };
    const paths = iconPathByRoute[path] || ["M5 5h10v10H5z"];

    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            {paths.map((value) => <path d={value} key={value} />)}
        </svg>
    );
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
    const [sidebarExpanded, setSidebarExpanded] = useState(() => localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true");

    useEffect(() => {
        localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarExpanded ? "true" : "false");
    }, [sidebarExpanded]);

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
        "/editor": {
            label: t("navEditorLabel", "Legal Editor"),
            description: t("navEditorDesc", "Draft, verify, version, and export"),
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
        <div className={`shell-root ${sidebarExpanded ? "sidebar-expanded" : "sidebar-collapsed"}`}>
            <aside className="shell-sidebar">
                <button
                    aria-label={sidebarExpanded ? t("collapseSidebar", "Collapse sidebar") : t("expandSidebar", "Expand sidebar")}
                    className="shell-sidebar-toggle"
                    onClick={() => setSidebarExpanded((current) => !current)}
                    title={sidebarExpanded ? t("collapseSidebar", "Collapse sidebar") : t("expandSidebar", "Expand sidebar")}
                    type="button"
                >
                    <svg aria-hidden="true" viewBox="0 0 20 20">
                        {sidebarExpanded ? (
                            <path d="M12.5 5.5 8 10l4.5 4.5" />
                        ) : (
                            <path d="M7.5 5.5 12 10l-4.5 4.5" />
                        )}
                    </svg>
                </button>
                <div className="shell-brand">
                    <span className="shell-mini-logo">WL</span>
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

                <div className="shell-status-card" aria-label={t("workspaceStatus", "Workspace status")}>
                    <div className="shell-status-row">
                        <p className="shell-status-kicker">{t("secureWorkspace", "Secure workspace")}</p>
                        <span className="shell-secure-badge">{t("encrypted", "Secure")}</span>
                    </div>
                    <strong>{user ? user.name : t("guestUser", "Guest user")}</strong>
                    <span>{user ? `${user.role} | ${t("lawFirmWorkspace", "Law firm workspace")}` : t("signInRequired", "Sign in required for case-aware features")}</span>
                    <span>{selectedCaseId ? `${t("currentWorkspace", "Current workspace")}: Case #${selectedCaseId}` : t("noCaseWorkspace", "No case selected yet")}</span>
                </div>

                <nav className="shell-nav" aria-label="Primary workspace navigation">
                    {APP_ROUTES.filter((route) => !route.hidden).map((route) => (
                        <NavLink
                            key={route.path}
                            className={({ isActive }) => navClassName(isActive)}
                            title={routeCopyByPath[route.path]?.label || route.label}
                            to={buildRoutePath(route.path, route.useSelectedCase)}
                        >
                            <span className="shell-nav-icon">{routeIcon(route.path)}</span>
                            <span className="shell-nav-copy">
                                <strong>{routeCopyByPath[route.path]?.label || route.label}</strong>
                                <span>{routeCopyByPath[route.path]?.description || route.description}</span>
                            </span>
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
                        <svg aria-hidden="true" viewBox="0 0 20 20">
                            <path d="M8.5 5H5.8a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2.7" />
                            <path d="M11.5 6.5 15 10l-3.5 3.5" />
                            <path d="M7.8 10H15" />
                        </svg>
                        <span>{t("logout", "Logout")}</span>
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
