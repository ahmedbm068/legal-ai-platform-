import { Navigate, Route, Routes } from "react-router-dom";
import LexingtonShell from "../layout/LexingtonShell";
import PortalAssistantPage from "../pages/PortalAssistantPage";
import PortalAuthPage from "../pages/PortalAuthPage";
import PortalBookingPage from "../pages/PortalBookingPage";
import PortalCalendarPage from "../pages/PortalCalendarPage";
import PortalIntakePage from "../pages/PortalIntakePage";
import PortalProfilePage from "../pages/PortalProfilePage";
import LexingtonHomePage from "../pages/LexingtonHomePage";
import LexingtonCasePage from "../pages/LexingtonCasePage";
import LexingtonDocumentsPage from "../pages/LexingtonDocumentsPage";
import LexingtonMessagesPage from "../pages/LexingtonMessagesPage";
import LexingtonAppointmentsPage from "../pages/LexingtonAppointmentsPage";
import LexingtonBillingPage from "../pages/LexingtonBillingPage";
import PortalProtectedRoute from "./PortalProtectedRoute";

export default function PortalRouter() {
    return (
        <Routes>
            <Route path="/auth" element={<PortalAuthPage />} />

            <Route element={<PortalProtectedRoute />}>
                <Route element={<LexingtonShell />}>
                    <Route index element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<LexingtonHomePage />} />
                    <Route path="/cases" element={<LexingtonCasePage />} />
                    <Route path="/documents" element={<LexingtonDocumentsPage />} />
                    <Route path="/messages" element={<LexingtonMessagesPage />} />
                    <Route path="/appointments" element={<LexingtonAppointmentsPage />} />
                    <Route path="/billing" element={<LexingtonBillingPage />} />
                    <Route path="/requests" element={<PortalIntakePage />} />
                    <Route path="/assistant" element={<PortalAssistantPage />} />
                    <Route path="/calendar" element={<PortalCalendarPage />} />
                    <Route path="/book" element={<PortalBookingPage />} />
                    <Route path="/profile" element={<PortalProfilePage />} />
                </Route>
            </Route>

            <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
    );
}
