import PortalCalendarPanel from "../components/PortalCalendarPanel";
import { usePortal } from "../context/PortalContext";

export default function PortalCalendarPage() {
    const { dashboard, selectedCaseId } = usePortal();

    if (!dashboard) {
        return (
            <div className="card">
                <p>Loading calendar…</p>
            </div>
        );
    }

    const selectedCase = dashboard.cases.find((c) => c.id === selectedCaseId) ?? null;

    return (
        <div className="view-panel">
            <div className="view-header">
                <h2>Calendar</h2>
                <p>Appointments, hearings, and AI-planned scheduling for your matters.</p>
            </div>
            <PortalCalendarPanel
                caseItem={selectedCase}
                calendarEvents={dashboard.calendar_events}
                consultations={dashboard.consultations}
                locale={navigator.language || "en-US"}
            />
        </div>
    );
}
