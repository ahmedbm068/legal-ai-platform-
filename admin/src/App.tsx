import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import RequireAdmin from "./components/RequireAdmin";
import AdminLayout from "./components/AdminLayout";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import UsersPage from "./pages/UsersPage";
import ClientsPage from "./pages/ClientsPage";
import CasesPage from "./pages/CasesPage";
import BillingPage from "./pages/BillingPage";
import JobsPage from "./pages/JobsPage";
import AuditLogPage from "./pages/AuditLogPage";
import BigAgentsPage from "./pages/BigAgentsPage";
import SettingsPage from "./pages/SettingsPage";
import "./styles.css";

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />

                    <Route element={<RequireAdmin />}>
                        <Route element={<AdminLayout />}>
                            <Route path="/overview" element={<OverviewPage />} />
                            <Route path="/users" element={<UsersPage />} />
                            <Route path="/clients" element={<ClientsPage />} />
                            <Route path="/cases" element={<CasesPage />} />
                            <Route path="/billing" element={<BillingPage />} />
                            <Route path="/jobs" element={<JobsPage />} />
                            <Route path="/audit" element={<AuditLogPage />} />
                            <Route path="/big-agents" element={<BigAgentsPage />} />
                            <Route path="/settings" element={<SettingsPage />} />
                            <Route path="/health" element={<Navigate to="/overview" replace />} />
                            <Route path="/" element={<Navigate to="/overview" replace />} />
                            <Route path="*" element={<Navigate to="/overview" replace />} />
                        </Route>
                    </Route>
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}
