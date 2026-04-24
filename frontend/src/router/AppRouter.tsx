import { Navigate, Route, Routes } from "react-router-dom";
import App from "../App";
import WorkspaceShell from "../layout/WorkspaceShell";
import AssistantPage from "../pages/AssistantPage";
import AuthPage from "../pages/AuthPage";
import CalendarPage from "../pages/CalendarPage";
import CasesPage from "../pages/CasesPage";
import DashboardPage from "../pages/DashboardPage";
import DocumentsPage from "../pages/DocumentsPage";
import SettingsPage from "../pages/SettingsPage";
import ProtectedRoute from "./ProtectedRoute";

export default function AppRouter() {
    return (
        <Routes>
            <Route path="/auth" element={<AuthPage />} />
            <Route path="/workspace-classic" element={<App />} />

            <Route element={<ProtectedRoute />}>
                <Route path="/" element={<WorkspaceShell />}>
                    <Route index element={<Navigate to="dashboard" replace />} />
                    <Route path="dashboard" element={<DashboardPage />} />

                    <Route path="cases" element={<CasesPage />} />
                    <Route path="cases/:caseId" element={<CasesPage />} />
                    <Route path="cases/:caseId/:tab" element={<CasesPage />} />

                    <Route path="assistant" element={<AssistantPage />} />
                    <Route path="assistant/:caseId" element={<AssistantPage />} />

                    <Route path="documents" element={<DocumentsPage />} />
                    <Route path="documents/:caseId" element={<DocumentsPage />} />

                    <Route path="calendar" element={<CalendarPage />} />
                    <Route path="calendar/:caseId" element={<CalendarPage />} />

                    <Route path="settings" element={<SettingsPage />} />
                </Route>
            </Route>

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
    );
}
