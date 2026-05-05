import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";

// Roles permitted to access the lawyer workspace.
// Defense-in-depth: the backend already enforces RBAC, but the frontend should
// not render lawyer-grade UI to a client account that somehow holds a token.
const LAWYER_WORKSPACE_ROLES: ReadonlySet<string> = new Set([
    "lawyer",
    "assistant",
    "admin",
]);

export default function ProtectedRoute() {
    const location = useLocation();
    const { isAuthenticated, sessionReady, user, t } = useRoutedWorkspace();

    if (!sessionReady) {
        return (
            <section className="shell-page shell-auth-page">
                <article className="shell-card">
                    <h2>{t("checkingSessionTitle", "Checking your session...")}</h2>
                    <p>{t("checkingSessionSubtitle", "We are validating your workspace token and loading your legal context.")}</p>
                </article>
            </section>
        );
    }

    if (!isAuthenticated) {
        const redirectTarget = `${location.pathname}${location.search}`;
        return <Navigate replace state={{ from: redirectTarget }} to="/auth" />;
    }

    // Role enforcement: a `client` account should never reach the lawyer shell.
    // Send them to /auth with a clear message rather than rendering a broken UI.
    if (user && !LAWYER_WORKSPACE_ROLES.has(user.role)) {
        return (
            <Navigate
                replace
                state={{ accessDenied: "lawyer_workspace_role_required" }}
                to="/auth"
            />
        );
    }

    return <Outlet />;
}
