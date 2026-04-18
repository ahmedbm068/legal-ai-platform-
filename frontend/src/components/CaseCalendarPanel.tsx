import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { CalendarAppointment, CaseItem, Client, ConsultationRequest, User } from "../types";

export type CalendarAppointmentDraft = {
    title: string;
    description?: string | null;
    appointmentType?: string;
    visibilityScope?: string;
    status?: string;
    scheduledAt: string;
    durationMinutes?: number;
    location?: string | null;
    timezoneName?: string | null;
    notes?: string | null;
    consultationRequestId?: number | null;
    useAi?: boolean;
};

interface CaseCalendarPanelProps {
    caseItem: CaseItem | null;
    client: Client | null;
    user: User | null;
    appointments: CalendarAppointment[];
    consultations: ConsultationRequest[];
    onCreateAppointment: (payload: CalendarAppointmentDraft) => Promise<void>;
    loading?: boolean;
    locale: string;
}

function pad(value: number) {
    return String(value).padStart(2, "0");
}

function dayKey(date: Date) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function toInputValue(date: Date) {
    const offset = date.getTimezoneOffset();
    const local = new Date(date.getTime() - offset * 60_000);
    return local.toISOString().slice(0, 16);
}

function fromInputValue(value: string) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
}

function formatDayLabel(date: Date, locale: string) {
    return new Intl.DateTimeFormat(locale, {
        weekday: "short",
        day: "numeric",
        month: "short",
    }).format(date);
}

function formatMonthLabel(date: Date, locale: string) {
    return new Intl.DateTimeFormat(locale, {
        month: "long",
        year: "numeric",
    }).format(date);
}

function formatAppointmentTime(value: string, locale: string) {
    const date = new Date(value);
    return new Intl.DateTimeFormat(locale, {
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}

function startOfMonth(date: Date) {
    return new Date(date.getFullYear(), date.getMonth(), 1);
}

function buildMonthCells(anchor: Date) {
    const first = startOfMonth(anchor);
    const startOffset = first.getDay();
    const cells: Array<{ date: Date; currentMonth: boolean }> = [];
    const leadingStart = new Date(first);
    leadingStart.setDate(first.getDate() - startOffset);

    for (let index = 0; index < 42; index += 1) {
        const cellDate = new Date(leadingStart);
        cellDate.setDate(leadingStart.getDate() + index);
        cells.push({
            date: cellDate,
            currentMonth: cellDate.getMonth() === anchor.getMonth(),
        });
    }

    return cells;
}

function appointmentSort(left: CalendarAppointment, right: CalendarAppointment) {
    return left.scheduled_at.localeCompare(right.scheduled_at) || left.id - right.id;
}

export default function CaseCalendarPanel({
    caseItem,
    client,
    user,
    appointments,
    consultations,
    onCreateAppointment,
    loading,
    locale,
}: CaseCalendarPanelProps) {
    const [monthAnchor, setMonthAnchor] = useState(() => new Date());
    const [selectedDay, setSelectedDay] = useState(() => dayKey(new Date()));
    const [form, setForm] = useState(() => ({
        title: "",
        description: "",
        appointmentType: "meeting",
        visibilityScope: "shared",
        status: "scheduled",
        scheduledAt: toInputValue(new Date(Date.now() + 60 * 60 * 1000)),
        durationMinutes: 45,
        location: "",
        timezoneName: "Africa/Tunis",
        notes: "",
        useAi: true,
    }));
    const [busy, setBusy] = useState(false);

    const canManage = user?.role === "lawyer" || user?.role === "admin";

    useEffect(() => {
        if (!caseItem) return;
        setForm((current) => ({
            ...current,
            title: current.title || `${caseItem.title} follow-up`,
            location: current.location || "",
            notes: current.notes || "",
        }));
    }, [caseItem]);

    const actualAppointments = useMemo(
        () => appointments.filter((appointment) => !appointment.is_ai_suggested).sort(appointmentSort),
        [appointments]
    );

    const aiSuggestions = useMemo(
        () => appointments.filter((appointment) => appointment.is_ai_suggested).sort(appointmentSort),
        [appointments]
    );

    const consultationsWithPreference = useMemo(
        () => [...consultations].sort((left, right) => right.created_at.localeCompare(left.created_at)),
        [consultations]
    );

    const selectedDayAppointments = useMemo(() => {
        return actualAppointments.filter((appointment) => dayKey(new Date(appointment.scheduled_at)) === selectedDay);
    }, [actualAppointments, selectedDay]);

    const monthCells = useMemo(() => buildMonthCells(monthAnchor), [monthAnchor]);

    const calendarCounts = useMemo(() => {
        const counts = new Map<string, number>();
        for (const appointment of actualAppointments) {
            const key = dayKey(new Date(appointment.scheduled_at));
            counts.set(key, (counts.get(key) || 0) + 1);
        }
        return counts;
    }, [actualAppointments]);

    const nextConsultation = consultationsWithPreference[0] || null;

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!caseItem || !canManage) return;
        setBusy(true);
        try {
            await onCreateAppointment({
                title: form.title.trim() || `${caseItem.title} follow-up`,
                description: form.description.trim() || null,
                appointmentType: form.appointmentType,
                visibilityScope: form.visibilityScope,
                status: form.status,
                scheduledAt: fromInputValue(form.scheduledAt).toISOString(),
                durationMinutes: form.durationMinutes,
                location: form.location.trim() || null,
                timezoneName: form.timezoneName.trim() || "Africa/Tunis",
                notes: form.notes.trim() || null,
                consultationRequestId: nextConsultation?.id ?? null,
                useAi: form.useAi,
            });
            setForm((current) => ({
                ...current,
                title: `${caseItem.title} follow-up`,
                description: "",
                notes: "",
            }));
        } finally {
            setBusy(false);
        }
    }

    if (!caseItem) {
        return (
            <section className="left-section calendar-panel">
                <h3>Calendar</h3>
                <p className="muted">Pick a case to view its calendar and AI planning notes.</p>
            </section>
        );
    }

    return (
        <section className="left-section calendar-panel">
            <div className="section-heading">
                <div>
                    <p className="section-kicker">Calendar</p>
                    <h3>{caseItem.title}</h3>
                </div>
                <span className="section-count">{actualAppointments.length + aiSuggestions.length}</span>
            </div>

            <div className="calendar-summary-row">
                <article className="calendar-summary-card">
                    <strong>{client?.name || "Client"}</strong>
                    <span>{client?.phone || "No client phone saved"}</span>
                </article>
                <article className="calendar-summary-card">
                    <strong>{actualAppointments.length} confirmed</strong>
                    <span>{aiSuggestions.length} AI suggestions</span>
                </article>
                <article className="calendar-summary-card">
                    <strong>{selectedDayAppointments.length} on selected day</strong>
                    <span>{formatDayLabel(fromInputValue(`${selectedDay}T12:00`), locale)}</span>
                </article>
            </div>

            <div className="calendar-shell">
                <div className="calendar-month-card">
                    <div className="calendar-month-header">
                        <button className="ghost-button history-action" type="button" onClick={() => setMonthAnchor((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))}>
                            Prev
                        </button>
                        <strong>{formatMonthLabel(monthAnchor, locale)}</strong>
                        <button className="ghost-button history-action" type="button" onClick={() => setMonthAnchor((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))}>
                            Next
                        </button>
                    </div>

                    <div className="calendar-weekdays">
                        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((label) => (
                            <span key={label}>{label}</span>
                        ))}
                    </div>

                    <div className="calendar-grid">
                        {monthCells.map(({ date, currentMonth }) => {
                            const key = dayKey(date);
                            const count = calendarCounts.get(key) || 0;
                            const isSelected = key === selectedDay;
                            const isToday = key === dayKey(new Date());
                            return (
                                <button
                                    key={key}
                                    className={`calendar-day ${currentMonth ? "current-month" : "outside-month"} ${isSelected ? "selected" : ""} ${isToday ? "today" : ""}`}
                                    onClick={() => setSelectedDay(key)}
                                    type="button"
                                >
                                    <span>{date.getDate()}</span>
                                    {count > 0 ? <em>{count} item{count === 1 ? "" : "s"}</em> : <em>&nbsp;</em>}
                                </button>
                            );
                        })}
                    </div>
                </div>

                <div className="calendar-agenda-card">
                    <h4>{formatDayLabel(fromInputValue(`${selectedDay}T12:00`), locale)}</h4>
                    <div className="calendar-agenda-list">
                        {selectedDayAppointments.length ? (
                            selectedDayAppointments.map((appointment) => (
                                <article key={appointment.id} className={`calendar-agenda-item ${appointment.status}`}>
                                    <div className="calendar-agenda-item-head">
                                        <strong>{appointment.title}</strong>
                                        <span>{formatAppointmentTime(appointment.scheduled_at, locale)}</span>
                                    </div>
                                    <p>{appointment.description || appointment.ai_summary || "No description added yet."}</p>
                                    <small>
                                        {appointment.appointment_type} · {appointment.visibility_scope} · {appointment.duration_minutes} min
                                    </small>
                                </article>
                            ))
                        ) : (
                            <p className="muted">No confirmed appointment on this day.</p>
                        )}
                    </div>

                    <div className="calendar-ai-section">
                        <h4>AI planning</h4>
                        {nextConsultation ? (
                            <article className="calendar-ai-card">
                                <strong>{nextConsultation.legal_area || "Consultation follow-up"}</strong>
                                <p>{nextConsultation.preferred_schedule || "AI suggests confirming a concrete meeting time with the client."}</p>
                                <small>{nextConsultation.issue_summary}</small>
                            </article>
                        ) : (
                            <p className="muted">No consultation request has enough detail to generate a planning note yet.</p>
                        )}
                        {aiSuggestions.length ? (
                            aiSuggestions.map((suggestion) => (
                                <article key={suggestion.id} className="calendar-ai-card suggested">
                                    <strong>{suggestion.title}</strong>
                                    <p>{suggestion.ai_summary || suggestion.description || "AI suggested calendar item."}</p>
                                    <small>{suggestion.ai_recommendation || suggestion.notes || "Review and confirm the appointment."}</small>
                                </article>
                            ))
                        ) : null}
                    </div>
                </div>
            </div>

            {canManage ? (
                <form className="calendar-form" onSubmit={handleSubmit}>
                    <div className="calendar-form-header">
                        <h4>Schedule appointment</h4>
                        <label className="composer-save-toggle call-consent-toggle">
                            <input
                                checked={form.useAi}
                                onChange={(event) => setForm((current) => ({ ...current, useAi: event.target.checked }))}
                                type="checkbox"
                            />
                            <span>Let AI add the planning note</span>
                        </label>
                    </div>

                    <div className="calendar-form-grid">
                        <label>
                            Title
                            <input
                                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                                placeholder={`${caseItem.title} follow-up`}
                                value={form.title}
                            />
                        </label>
                        <label>
                            Start time
                            <input
                                onChange={(event) => setForm((current) => ({ ...current, scheduledAt: event.target.value }))}
                                type="datetime-local"
                                value={form.scheduledAt}
                            />
                        </label>
                        <label>
                            Duration
                            <input
                                onChange={(event) => setForm((current) => ({ ...current, durationMinutes: Number(event.target.value) || 30 }))}
                                min={5}
                                step={5}
                                type="number"
                                value={form.durationMinutes}
                            />
                        </label>
                        <label>
                            Type
                            <select
                                onChange={(event) => setForm((current) => ({ ...current, appointmentType: event.target.value }))}
                                value={form.appointmentType}
                            >
                                <option value="consultation">Consultation</option>
                                <option value="meeting">Meeting</option>
                                <option value="call">Call</option>
                                <option value="deadline">Deadline</option>
                                <option value="court_hearing">Court hearing</option>
                                <option value="follow_up">Follow-up</option>
                            </select>
                        </label>
                        <label>
                            Visibility
                            <select
                                onChange={(event) => setForm((current) => ({ ...current, visibilityScope: event.target.value }))}
                                value={form.visibilityScope}
                            >
                                <option value="shared">Shared with client</option>
                                <option value="lawyer">Lawyer only</option>
                                <option value="assistant">Lawyer team</option>
                                <option value="client">Client only</option>
                                <option value="internal">Internal</option>
                            </select>
                        </label>
                        <label>
                            Location
                            <input
                                onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))}
                                placeholder="Office, video link, or court"
                                value={form.location}
                            />
                        </label>
                    </div>

                    <label>
                        Notes
                        <textarea
                            onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
                            placeholder="Key talking points, preparation, and follow-up instructions"
                            value={form.notes}
                        />
                    </label>

                    <div className="calendar-form-footer">
                        <div className="calendar-form-meta">
                            <span>Client: {client?.name || "Selected client"}</span>
                            <span>Lawyer: {user?.name || "Current user"}</span>
                        </div>
                        <button className="primary-button" disabled={busy || loading} type="submit">
                            {busy ? "Saving appointment..." : "Add to calendar"}
                        </button>
                    </div>
                </form>
            ) : (
                <p className="muted">You can view shared appointments here. Only lawyers and admins can create or change calendar items.</p>
            )}
        </section>
    );
}
