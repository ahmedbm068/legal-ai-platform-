import { useMemo, useState } from "react";
import { usePortal } from "../context/PortalContext";
import { bookPortalAppointment, cancelPortalAppointment } from "../lib/api";
import { formatDateTime } from "../portalPresentation";
import type { ClientPortalCalendarItem } from "../types";

const DURATION_OPTIONS = [
    { label: "30 minutes", value: 30 },
    { label: "45 minutes", value: 45 },
    { label: "1 hour", value: 60 },
    { label: "1h30", value: 90 },
];

const TYPE_OPTIONS = [
    { label: "Meeting", value: "meeting" },
    { label: "Consultation", value: "consultation" },
    { label: "Phone call", value: "call" },
    { label: "Follow-up", value: "follow_up" },
];

function toLocalDatetimeInputValue(date: Date): string {
    const pad = (n: number) => String(n).padStart(2, "0");
    return (
        `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
        `T${pad(date.getHours())}:${pad(date.getMinutes())}`
    );
}

function defaultScheduledAt(): string {
    const next = new Date();
    next.setDate(next.getDate() + 1);
    next.setHours(10, 0, 0, 0);
    return toLocalDatetimeInputValue(next);
}

export default function PortalBookingPage() {
    const { dashboard, token, selectedCaseId, setSelectedCaseId, refreshDashboard } = usePortal();

    const cases = dashboard?.cases ?? [];
    const [caseId, setCaseId] = useState<number | null>(selectedCaseId ?? cases[0]?.id ?? null);
    const [title, setTitle] = useState("Rendez-vous avec mon avocat");
    const [scheduledAtLocal, setScheduledAtLocal] = useState<string>(defaultScheduledAt());
    const [durationMinutes, setDurationMinutes] = useState<number>(30);
    const [appointmentType, setAppointmentType] = useState<string>("meeting");
    const [location, setLocation] = useState<string>("");
    const [notes, setNotes] = useState<string>("");
    const [submitting, setSubmitting] = useState(false);
    const [success, setSuccess] = useState<string | null>(null);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [cancellingId, setCancellingId] = useState<number | null>(null);

    const myAppointments: ClientPortalCalendarItem[] = useMemo(() => {
        const events = dashboard?.calendar_events ?? [];
        return events.filter(
            (event) =>
                event.appointment_type !== undefined &&
                !event.is_ai_suggested &&
                event.status !== "cancelled" &&
                new Date(event.scheduled_at).getTime() >= Date.now() - 60 * 60 * 1000,
        );
    }, [dashboard]);

    const timezone = useMemo(
        () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        [],
    );

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setErrorMessage(null);
        setSuccess(null);

        if (!token) {
            setErrorMessage("Your session expired. Please sign in again.");
            return;
        }
        if (!caseId) {
            setErrorMessage("Select a case first.");
            return;
        }
        if (!title.trim()) {
            setErrorMessage("Give the appointment a title.");
            return;
        }

        const scheduledAtIso = new Date(scheduledAtLocal).toISOString();
        if (new Date(scheduledAtIso).getTime() <= Date.now()) {
            setErrorMessage("Pick a future date and time.");
            return;
        }

        setSubmitting(true);
        try {
            await bookPortalAppointment(token, caseId, {
                title: title.trim(),
                scheduled_at: scheduledAtIso,
                duration_minutes: durationMinutes,
                appointment_type: appointmentType,
                location: location.trim() || null,
                timezone_name: timezone,
                notes: notes.trim() || null,
            });
            setSuccess("Appointment booked. A confirmation will be sent by email.");
            setNotes("");
            await refreshDashboard();
        } catch (caught) {
            setErrorMessage(caught instanceof Error ? caught.message : "Booking failed.");
        } finally {
            setSubmitting(false);
        }
    }

    async function handleCancel(appointmentId: number) {
        if (!token) return;
        setCancellingId(appointmentId);
        setErrorMessage(null);
        setSuccess(null);
        try {
            await cancelPortalAppointment(token, appointmentId);
            setSuccess("Appointment cancelled.");
            await refreshDashboard();
        } catch (caught) {
            setErrorMessage(caught instanceof Error ? caught.message : "Cancellation failed.");
        } finally {
            setCancellingId(null);
        }
    }

    if (!dashboard) {
        return (
            <div className="card">
                <p>Loading booking workspace…</p>
            </div>
        );
    }

    if (cases.length === 0) {
        return (
            <div className="view-panel">
                <div className="view-header">
                    <h2>Book a meeting</h2>
                    <p>You need an active case before you can book a rendez-vous.</p>
                </div>
                <div className="card">
                    <p>Submit an intake request first — your lawyer will open a case and you'll be able to schedule meetings here.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="view-panel">
            <div className="view-header">
                <h2>Book a meeting</h2>
                <p>Schedule a rendez-vous with your lawyer. You'll receive an email confirmation.</p>
            </div>

            <form className="card" onSubmit={handleSubmit}>
                <div className="form-grid">
                    <label className="form-field">
                        <span>Case</span>
                        <select
                            value={caseId ?? ""}
                            onChange={(e) => {
                                const next = Number(e.target.value) || null;
                                setCaseId(next);
                                if (next) setSelectedCaseId(next);
                            }}
                        >
                            {cases.map((c) => (
                                <option key={c.id} value={c.id}>
                                    {c.title}
                                </option>
                            ))}
                        </select>
                    </label>

                    <label className="form-field">
                        <span>Title</span>
                        <input
                            type="text"
                            value={title}
                            maxLength={200}
                            onChange={(e) => setTitle(e.target.value)}
                            placeholder="Rendez-vous initial"
                        />
                    </label>

                    <label className="form-field">
                        <span>Date &amp; time</span>
                        <input
                            type="datetime-local"
                            value={scheduledAtLocal}
                            onChange={(e) => setScheduledAtLocal(e.target.value)}
                        />
                        <small>Timezone: {timezone}</small>
                    </label>

                    <label className="form-field">
                        <span>Duration</span>
                        <select
                            value={durationMinutes}
                            onChange={(e) => setDurationMinutes(Number(e.target.value))}
                        >
                            {DURATION_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>
                                    {opt.label}
                                </option>
                            ))}
                        </select>
                    </label>

                    <label className="form-field">
                        <span>Type</span>
                        <select
                            value={appointmentType}
                            onChange={(e) => setAppointmentType(e.target.value)}
                        >
                            {TYPE_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>
                                    {opt.label}
                                </option>
                            ))}
                        </select>
                    </label>

                    <label className="form-field">
                        <span>Location (optional)</span>
                        <input
                            type="text"
                            value={location}
                            maxLength={200}
                            onChange={(e) => setLocation(e.target.value)}
                            placeholder="Cabinet, Tunis — or 'Google Meet'"
                        />
                    </label>

                    <label className="form-field form-field-wide">
                        <span>Notes (optional)</span>
                        <textarea
                            value={notes}
                            maxLength={2000}
                            rows={3}
                            onChange={(e) => setNotes(e.target.value)}
                            placeholder="Context, documents to bring, questions to discuss…"
                        />
                    </label>
                </div>

                {errorMessage ? <p className="form-error">{errorMessage}</p> : null}
                {success ? <p className="form-success">{success}</p> : null}

                <div className="form-actions">
                    <button type="submit" className="btn primary" disabled={submitting}>
                        {submitting ? "Booking…" : "Book appointment"}
                    </button>
                </div>
            </form>

            <section className="card">
                <div className="section-header">
                    <h3>Your upcoming appointments</h3>
                    <small>{myAppointments.length} scheduled</small>
                </div>

                {myAppointments.length === 0 ? (
                    <p>No upcoming appointments yet.</p>
                ) : (
                    <ul className="appointment-list">
                        {myAppointments.map((appointment) => (
                            <li key={appointment.id} className="appointment-row">
                                <div>
                                    <strong>{appointment.title}</strong>
                                    <div>{formatDateTime(appointment.scheduled_at)} · {appointment.duration_minutes} min</div>
                                    {appointment.location ? <small>{appointment.location}</small> : null}
                                </div>
                                <button
                                    type="button"
                                    className="btn ghost"
                                    onClick={() => handleCancel(appointment.id)}
                                    disabled={cancellingId === appointment.id}
                                >
                                    {cancellingId === appointment.id ? "Cancelling…" : "Cancel"}
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            </section>
        </div>
    );
}
