import { Navigate, Route, Routes } from "react-router-dom";
import PortalShell from "../layout/PortalShell";
import PortalAssistantPage from "../pages/PortalAssistantPage";
import PortalAuthPage from "../pages/PortalAuthPage";
import PortalCalendarPage from "../pages/PortalCalendarPage";
import PortalCasesPage from "../pages/PortalCasesPage";
import PortalDashboardPage from "../pages/PortalDashboardPage";
import PortalDocumentsPage from "../pages/PortalDocumentsPage";
import PortalIntakePage from "../pages/PortalIntakePage";
import PortalProfilePage from "../pages/PortalProfilePage";
import PortalProtectedRoute from "./PortalProtectedRoute";

export default function PortalRouter() {
    return (
        <Routes>
            <Route path="/auth" element={<PortalAuthPage />} />

            <Route element={<PortalProtectedRoute />}>
                <Route element={<PortalShell />}>
                    <Route index element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<PortalDashboardPage />} />
                    <Route path="/cases" element={<PortalCasesPage />} />
                    <Route path="/documents" element={<PortalDocumentsPage />} />
                    <Route path="/requests" element={<PortalIntakePage />} />
                    <Route path="/assistant" element={<PortalAssistantPage />} />
                    <Route path="/calendar" element={<PortalCalendarPage />} />
                    <Route path="/profile" element={<PortalProfilePage />} />
                </Route>
            </Route>

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
    );
}
