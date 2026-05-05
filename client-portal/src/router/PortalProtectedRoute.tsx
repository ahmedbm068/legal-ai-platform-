import { Navigate, Outlet } from "react-router-dom";
import { usePortal } from "../context/PortalContext";

export default function PortalProtectedRoute() {
    const { isAuthenticated, sessionReady } = usePortal();

    if (!sessionReady) {
        return (
            <div className="portal-root loading-root">
                <div className="card">
                    <p className="eyebrow">Secure Client Workspace</p>
                    <h2>Checking your session…</h2>
                    <p>Validating your portal token and loading your legal context.</p>
                </div>
            </div>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/auth" replace />;
    }

    return <Outlet />;
}
