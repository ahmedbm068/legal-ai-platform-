import { useMemo, useState } from "react";

import type { ClientPortalCalendarItem, ClientPortalCase, ClientPortalConsultation } from "../types";

interface PortalCalendarPanelProps {
    caseItem: ClientPortalCase | null;
    calendarEvents: ClientPortalCalendarItem[];
    consultations: ClientPortalConsultation[];
    locale: string;
}

function pad(value: number) {
    return String(value).padStart(2, "0");
}

function dayKey(date: Date) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatDate(value: string, locale: string) {
    return new Intl.DateTimeFormat(locale, {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric",
    }).format(new Date(value));
}

function formatTime(value: string, locale: string) {
    return new Intl.DateTimeFormat(locale, {
        hour: "2-digit",
        minute: "2-digit",
    }).format(new Date(value));
}

function formatMonthLabel(date: Date, locale: string) {
    return new Intl.DateTimeFormat(locale, {
        month: "long",
        year: "numeric",
    }).format(date);
}

function startOfMonth(date: Date) {
    return new Date(date.getFullYear(), date.getMonth(), 1);
}

function buildMonthCells(anchor: Date) {
    const first = startOfMonth(anchor);
    const startOffset = first.getDay();
    const cells: Array<{ date: Date; currentMonth: boolean }> = [];
    const gridStart = new Date(first);
    gridStart.setDate(first.getDate() - startOffset);

    for (let index = 0; index < 42; index += 1) {
        const cellDate = new Date(gridStart);
        cellDate.setDate(gridStart.getDate() + index);
        cells.push({
            date: cellDate,
            currentMonth: cellDate.getMonth() === anchor.getMonth(),
        });
    }

    return cells;
}

export default function PortalCalendarPanel({ caseItem, calendarEvents, consultations, locale }: PortalCalendarPanelProps) {
    const [monthAnchor, setMonthAnchor] = useState(() => new Date());
    const [selectedDay, setSelectedDay] = useState(() => dayKey(new Date()));

    const visibleEvents = useMemo(
        () => calendarEvents.filter((event) => !event.is_ai_suggested).sort((left, right) => left.scheduled_at.localeCompare(right.scheduled_at)),
        [calendarEvents]
    );
    const aiSuggestions = useMemo(
        () => calendarEvents.filter((event) => event.is_ai_suggested),
        [calendarEvents]
    );
    const selectedDayEvents = useMemo(
        () => visibleEvents.filter((event) => dayKey(new Date(event.scheduled_at)) === selectedDay),
        [selectedDay, visibleEvents]
    );
    const monthCells = useMemo(() => buildMonthCells(monthAnchor), [monthAnchor]);
    const counts = useMemo(() => {
        const map = new Map<string, number>();
        for (const event of visibleEvents) {
            const key = dayKey(new Date(event.scheduled_at));
            map.set(key, (map.get(key) || 0) + 1);
        }
        return map;
    }, [visibleEvents]);

    const latestConsultation = consultations[0] || null;

    if (!caseItem) {
        return (
            <article className="card portal-calendar-card">
                <h2>Calendar</h2>
                <p className="muted">Choose a case to see your appointments and AI planning notes.</p>
            </article>
        );
    }

    return (
        <div className="portal-calendar-layout">
            <article className="card portal-calendar-card">
                <div className="section-head">
                    <div>
                        <h2>Calendar</h2>
                        <p>{caseItem.title}</p>
                    </div>
                    <span className="pill-count">{visibleEvents.length}</span>
                </div>

                <div className="portal-calendar-summary">
                    <div className="summary-tile">
                        <span>Shared appointments</span>
                        <strong>{visibleEvents.length}</strong>
                    </div>
                    <div className="summary-tile">
                        <span>AI notes</span>
                        <strong>{aiSuggestions.length}</strong>
                    </div>
                    <div className="summary-tile">
                        <span>Latest request</span>
                        <strong>{latestConsultation ? formatDate(latestConsultation.created_at, locale) : "None"}</strong>
                    </div>
                </div>

                <div className="portal-calendar-shell">
                    <div className="portal-calendar-month">
                        <div className="calendar-month-header">
                            <button className="btn ghost" onClick={() => setMonthAnchor((current) => new Date(current.getFullYear(), current.getMonth() - 1, 1))} type="button">
                                Prev
                            </button>
                            <strong>{formatMonthLabel(monthAnchor, locale)}</strong>
                            <button className="btn ghost" onClick={() => setMonthAnchor((current) => new Date(current.getFullYear(), current.getMonth() + 1, 1))} type="button">
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
                                const count = counts.get(key) || 0;
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

                    <div className="portal-calendar-agenda">
                        <h3>{formatDate(`${selectedDay}T12:00:00`, locale)}</h3>
                        {selectedDayEvents.length ? (
                            <div className="calendar-agenda-list">
                                {selectedDayEvents.map((event) => (
                                    <article key={event.id} className={`calendar-agenda-item ${event.status}`}>
                                        <div className="calendar-agenda-item-head">
                                            <strong>{event.title}</strong>
                                            <span>{formatTime(event.scheduled_at, locale)}</span>
                                        </div>
                                        <p>{event.ai_summary || event.description || "No description available."}</p>
                                        <small>
                                            {event.appointment_type} · {event.visibility_scope} · {event.duration_minutes} min
                                        </small>
                                    </article>
                                ))}
                            </div>
                        ) : (
                            <p className="muted">No shared appointment is scheduled on this day.</p>
                        )}

                        <div className="portal-ai-panel">
                            <h3>AI planning notes</h3>
                            {latestConsultation ? (
                                <article className="portal-ai-card">
                                    <strong>{latestConsultation.legal_area || "Consultation"}</strong>
                                    <p>{latestConsultation.preferred_schedule || "The assistant will suggest a concrete schedule once the lawyer confirms availability."}</p>
                                    <small>{latestConsultation.issue_summary}</small>
                                </article>
                            ) : (
                                <p className="muted">No consultation context is available yet.</p>
                            )}

                            {aiSuggestions.length ? (
                                aiSuggestions.map((suggestion) => (
                                    <article key={suggestion.id} className="portal-ai-card suggested">
                                        <strong>{suggestion.title}</strong>
                                        <p>{suggestion.ai_summary || suggestion.description || "AI suggested appointment."}</p>
                                        <small>{suggestion.ai_recommendation || suggestion.notes || "This item is still a planning placeholder."}</small>
                                    </article>
                                ))
                            ) : null}
                        </div>
                    </div>
                </div>
            </article>
        </div>
    );
}
