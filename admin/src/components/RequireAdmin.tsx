import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function RequireAdmin() {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-surface text-secondary font-body-sm text-body-sm">
                Checking session…
            </div>
        );
    }

    if (!user) return <Navigate to="/login" replace />;
    return <Outlet />;
}
