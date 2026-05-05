import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import RequireAdmin from "./components/RequireAdmin";
import AdminLayout from "./components/AdminLayout";
import LoginPage from "./pages/LoginPage";
import UsersPage from "./pages/UsersPage";
import CasesPage from "./pages/CasesPage";
import AuditLogPage from "./pages/AuditLogPage";
import HealthPage from "./pages/HealthPage";
import BigAgentsPage from "./pages/BigAgentsPage";
import "./styles.css";

export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    <Route path="/login" element={<LoginPage />} />

                    <Route element={<RequireAdmin />}>
                        <Route element={<AdminLayout />}>
                            <Route path="/users" element={<UsersPage />} />
                            <Route path="/cases" element={<CasesPage />} />
                            <Route path="/big-agents" element={<BigAgentsPage />} />
                            <Route path="/audit" element={<AuditLogPage />} />
                            <Route path="/health" element={<HealthPage />} />
                            <Route path="/" element={<Navigate to="/health" replace />} />
                            <Route path="*" element={<Navigate to="/health" replace />} />
                        </Route>
                    </Route>
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}
