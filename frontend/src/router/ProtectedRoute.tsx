import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";

export default function ProtectedRoute() {
    const location = useLocation();
    const { isAuthenticated, sessionReady, t } = useRoutedWorkspace();

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

    return <Outlet />;
}
