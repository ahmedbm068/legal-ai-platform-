import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import type { CalendarEvent, LegalCalendarEventType, LegalCalendarPriority } from "../types";
import { workspaceApi } from "../workspaceApi";

const EVENT_TYPES: Array<{ value: LegalCalendarEventType; label: string }> = [
    { value: "hearing", label: "Hearing" },
    { value: "deadline", label: "Deadline" },
    { value: "filing_deadline", label: "Filing" },
    { value: "limitation_period", label: "Limitation" },
    { value: "payment_due", label: "Payment" },
    { value: "meeting", label: "Meeting" },
    { value: "task", label: "Task" },
    { value: "document_date", label: "Document date" },
    { value: "contract_date", label: "Contract" },
    { value: "reminder", label: "Reminder" },
    { value: "other", label: "Other" },
];

const PRIORITIES: LegalCalendarPriority[] = ["low", "medium", "high", "critical"];
type ViewMode = "month" | "week" | "day" | "agenda" | "deadlines" | "timeline" | "pending";

function parseCaseId(value?: string) {
    const parsed = Number(value);
    if (!value || Number.isNaN(parsed) || parsed <= 0) return null;
    return parsed;
}

function normalizeLabel(value: string | null | undefined, fallback = "Unknown") {
    const cleaned = String(value || "").replace(/_/g, " ").trim();
    return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : fallback;
}

function formatDate(value: string, locale: string) {
    return new Intl.DateTimeFormat(locale, {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(new Date(value));
}

function formatDay(value: Date) {
    return value.toISOString().slice(0, 10);
}

function toInputDateTime(value?: string | null) {
    if (!value) return "";
    const date = new Date(value);
    const offset = date.getTimezoneOffset() * 60000;
    return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function fromInputDateTime(value: string) {
    return new Date(value).toISOString();
}

function eventIcon(type: string) {
    if (type === "hearing") return "§";
    if (type.includes("deadline") || type === "limitation_period") return "!";
    if (type === "meeting") return "@";
    if (type === "payment_due") return "$";
    if (type === "task") return "✓";
    return "•";
}

function buildMonthDays(anchor: Date) {
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const start = new Date(first);
    start.setDate(first.getDate() - first.getDay());
    return Array.from({ length: 42 }, (_, index) => {
        const day = new Date(start);
        day.setDate(start.getDate() + index);
        return day;
    });
}

function emptyForm(caseId: number | null) {
    const start = new Date();
    start.setMinutes(0, 0, 0);
    start.setHours(start.getHours() + 1);
    return {
        id: null as number | null,
        caseId,
        title: "",
        description: "",
        eventType: "deadline",
        priority: "medium",
        status: "scheduled",
        startDatetime: toInputDateTime(start.toISOString()),
        endDatetime: "",
        allDay: false,
        location: "",
    };
}

export default function CalendarPage() {
    const params = useParams();
    const navigate = useNavigate();
    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);
    const {
        token,
        cases,
        selectedCaseId,
        setSelectedCaseId,
        selectedCase,
        locale,
    } = useRoutedWorkspace();

    const activeCaseId = routeCaseId;
    const activeCase = useMemo(
        () => (activeCaseId ? cases.find((item) => item.id === activeCaseId) || selectedCase : null),
        [activeCaseId, cases, selectedCase]
    );

    const [events, setEvents] = useState<CalendarEvent[]>([]);
    const [pendingEvents, setPendingEvents] = useState<CalendarEvent[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [viewMode, setViewMode] = useState<ViewMode>("agenda");
    const [anchorDate, setAnchorDate] = useState(() => new Date());
    const [query, setQuery] = useState("");
    const [caseFilter, setCaseFilter] = useState<number | "all">(activeCaseId || "all");
    const [typeFilter, setTypeFilter] = useState("all");
    const [priorityFilter, setPriorityFilter] = useState("all");
    const [statusFilter, setStatusFilter] = useState("all");
    const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(null);
    const [eventForm, setEventForm] = useState(() => emptyForm(activeCaseId));
    const [modalOpen, setModalOpen] = useState(false);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (activeCaseId && activeCaseId !== selectedCaseId) {
            setSelectedCaseId(activeCaseId);
        }
    }, [activeCaseId, selectedCaseId, setSelectedCaseId]);

    useEffect(() => {
        setCaseFilter(activeCaseId || "all");
    }, [activeCaseId]);

    async function loadCalendar() {
        if (!token) return;
        setLoading(true);
        setError(null);
        try {
            const [eventRows, pendingRows] = await Promise.all([
                activeCaseId
                    ? workspaceApi.listCaseCalendarEvents(token, activeCaseId)
                    : workspaceApi.listCalendarEvents(token),
                workspaceApi.listPendingExtractedDates(token, activeCaseId),
            ]);
            setEvents(eventRows);
            setPendingEvents(pendingRows);
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Unable to load calendar.");
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        void loadCalendar();
    }, [token, activeCaseId]);

    const filteredEvents = useMemo(() => {
        const search = query.trim().toLowerCase();
        return events.filter((event) => {
            if (caseFilter !== "all" && event.case_id !== caseFilter) return false;
            if (typeFilter !== "all" && event.event_type !== typeFilter) return false;
            if (priorityFilter !== "all" && event.priority !== priorityFilter) return false;
            if (statusFilter !== "all" && event.status !== statusFilter) return false;
            if (!search) return true;
            return [
                event.title,
                event.description,
                event.case_title,
                event.client_name,
                event.document_filename,
                event.source_quote,
            ].join(" ").toLowerCase().includes(search);
        });
    }, [caseFilter, events, priorityFilter, query, statusFilter, typeFilter]);

    const now = Date.now();
    const upcoming = filteredEvents
        .filter((event) => new Date(event.start_datetime).getTime() >= now && event.status !== "cancelled")
        .sort((left, right) => left.start_datetime.localeCompare(right.start_datetime));
    const critical = upcoming.filter((event) => event.priority === "critical").slice(0, 6);
    const overdue = filteredEvents.filter((event) => {
        const time = new Date(event.start_datetime).getTime();
        return time < now && ["scheduled", "tentative"].includes(String(event.status));
    });
    const visibleEvents = viewMode === "deadlines"
        ? filteredEvents.filter((event) => ["deadline", "filing_deadline", "limitation_period", "payment_due"].includes(String(event.event_type)) || event.priority === "critical")
        : viewMode === "pending"
            ? pendingEvents
            : filteredEvents;

    function openCreateModal() {
        setEventForm(emptyForm(activeCaseId || (caseFilter !== "all" ? caseFilter : null)));
        setModalOpen(true);
    }

    function openEditModal(event: CalendarEvent) {
        setEventForm({
            id: event.id,
            caseId: event.case_id ?? null,
            title: event.title,
            description: event.description || "",
            eventType: event.event_type || "deadline",
            priority: event.priority || "medium",
            status: event.status || "scheduled",
            startDatetime: toInputDateTime(event.start_datetime),
            endDatetime: toInputDateTime(event.end_datetime),
            allDay: event.all_day,
            location: event.location || "",
        });
        setModalOpen(true);
    }

    async function saveEvent() {
        if (!token || !eventForm.title.trim() || !eventForm.startDatetime) return;
        setSaving(true);
        try {
            if (eventForm.id) {
                await workspaceApi.updateCalendarEvent(token, eventForm.id, {
                    caseId: eventForm.caseId,
                    title: eventForm.title,
                    description: eventForm.description || null,
                    eventType: eventForm.eventType,
                    priority: eventForm.priority,
                    status: eventForm.status,
                    startDatetime: fromInputDateTime(eventForm.startDatetime),
                    endDatetime: eventForm.endDatetime ? fromInputDateTime(eventForm.endDatetime) : null,
                    allDay: eventForm.allDay,
                    location: eventForm.location || null,
                    requiresReview: false,
                });
            } else {
                await workspaceApi.createCalendarEvent(token, {
                    caseId: eventForm.caseId,
                    title: eventForm.title,
                    description: eventForm.description || null,
                    eventType: eventForm.eventType,
                    priority: eventForm.priority,
                    status: eventForm.status,
                    startDatetime: fromInputDateTime(eventForm.startDatetime),
                    endDatetime: eventForm.endDatetime ? fromInputDateTime(eventForm.endDatetime) : null,
                    allDay: eventForm.allDay,
                    location: eventForm.location || null,
                });
            }
            setModalOpen(false);
            await loadCalendar();
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Unable to save event.");
        } finally {
            setSaving(false);
        }
    }

    async function acceptEvent(event: CalendarEvent) {
        if (!token) return;
        await workspaceApi.acceptExtractedDate(token, event.id);
        await loadCalendar();
    }

    async function rejectEvent(event: CalendarEvent) {
        if (!token) return;
        await workspaceApi.rejectExtractedDate(token, event.id);
        if (selectedEvent?.id === event.id) setSelectedEvent(null);
        await loadCalendar();
    }

    async function archiveEvent(event: CalendarEvent) {
        if (!token) return;
        await workspaceApi.archiveCalendarEvent(token, event.id);
        if (selectedEvent?.id === event.id) setSelectedEvent(null);
        await loadCalendar();
    }

    async function addReminder(event: CalendarEvent, daysBefore: number) {
        if (!token) return;
        const remindAt = new Date(new Date(event.start_datetime).getTime() - daysBefore * 24 * 60 * 60 * 1000);
        await workspaceApi.createCalendarReminder(token, event.id, { remindAt: remindAt.toISOString(), method: "in_app" });
        await loadCalendar();
    }

    const monthDays = useMemo(() => buildMonthDays(anchorDate), [anchorDate]);
    const eventsByDay = useMemo(() => {
        const map = new Map<string, CalendarEvent[]>();
        visibleEvents.forEach((event) => {
            const key = formatDay(new Date(event.start_datetime));
            map.set(key, [...(map.get(key) || []), event]);
        });
        return map;
    }, [visibleEvents]);

    return (
        <section className="shell-page legal-calendar-page">
            <header className="shell-page-header legal-calendar-hero">
                <div>
                    <p className="shell-page-kicker">{activeCaseId ? "Case calendar" : "Global lawyer calendar"}</p>
                    <h2>{activeCaseId ? activeCase?.title || `Case #${activeCaseId}` : "Legal calendar command center"}</h2>
                    <p>
                        {activeCaseId
                            ? "Matter-specific hearings, deadlines, extracted document dates, reminders, and review traceability."
                            : "All lawyer events across matters, with review queues and deadline risk surfaced in one workspace."}
                    </p>
                </div>
                <div className="legal-calendar-actions">
                    {activeCaseId ? (
                        <button className="shell-secondary-button" onClick={() => navigate("/cases")} type="button">
                            Choose another case
                        </button>
                    ) : null}
                    <button className="shell-primary-button" onClick={openCreateModal} type="button">
                        New event
                    </button>
                </div>
            </header>

            <div className="calendar-metric-strip">
                <span><strong>{filteredEvents.length}</strong> events</span>
                <span><strong>{critical.length}</strong> critical upcoming</span>
                <span><strong>{pendingEvents.length}</strong> pending review</span>
                <span className={overdue.length ? "danger" : ""}><strong>{overdue.length}</strong> overdue</span>
            </div>

            <div className="legal-calendar-layout">
                <aside className="calendar-side-panel">
                    <section>
                        <p className="shell-page-kicker">Critical next</p>
                        <h3>Deadline watch</h3>
                        <div className="calendar-mini-list">
                            {critical.length ? critical.map((event) => (
                                <button key={event.id} className="calendar-alert-card" onClick={() => setSelectedEvent(event)} type="button">
                                    <span>{formatDate(event.start_datetime, locale)}</span>
                                    <strong>{event.title}</strong>
                                    <em>{normalizeLabel(event.event_type)}</em>
                                </button>
                            )) : <p className="calendar-empty-copy">No critical deadlines in the current filter.</p>}
                        </div>
                    </section>

                    <section>
                        <p className="shell-page-kicker">AI review</p>
                        <h3>Detected dates</h3>
                        <div className="calendar-mini-list">
                            {pendingEvents.slice(0, 5).map((event) => (
                                <button key={event.id} className="calendar-review-mini" onClick={() => setSelectedEvent(event)} type="button">
                                    <strong>{event.title}</strong>
                                    <span>{event.document_filename || "Document extraction"}</span>
                                </button>
                            ))}
                            {!pendingEvents.length ? <p className="calendar-empty-copy">No AI-detected dates waiting for review.</p> : null}
                        </div>
                    </section>
                </aside>

                <main className="calendar-workbench">
                    <div className="calendar-toolbar">
                        <div className="calendar-view-tabs" role="tablist" aria-label="Calendar views">
                            {(["month", "week", "day", "agenda", "deadlines", "timeline", "pending"] as ViewMode[]).map((view) => (
                                <button
                                    key={view}
                                    className={viewMode === view ? "active" : ""}
                                    onClick={() => setViewMode(view)}
                                    type="button"
                                >
                                    {normalizeLabel(view)}
                                </button>
                            ))}
                        </div>
                        <div className="calendar-period-controls">
                            <button onClick={() => setAnchorDate(new Date(anchorDate.getFullYear(), anchorDate.getMonth() - 1, 1))} type="button" aria-label="Previous period">‹</button>
                            <strong>{new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(anchorDate)}</strong>
                            <button onClick={() => setAnchorDate(new Date(anchorDate.getFullYear(), anchorDate.getMonth() + 1, 1))} type="button" aria-label="Next period">›</button>
                        </div>
                    </div>

                    <div className="calendar-filters">
                        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search event, source, case..." type="search" />
                        {!activeCaseId ? (
                            <select value={caseFilter} onChange={(event) => setCaseFilter(event.target.value === "all" ? "all" : Number(event.target.value))}>
                                <option value="all">All cases</option>
                                {cases.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                            </select>
                        ) : null}
                        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
                            <option value="all">All types</option>
                            {EVENT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                        </select>
                        <select value={priorityFilter} onChange={(event) => setPriorityFilter(event.target.value)}>
                            <option value="all">All priorities</option>
                            {PRIORITIES.map((item) => <option key={item} value={item}>{normalizeLabel(item)}</option>)}
                        </select>
                        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                            <option value="all">All statuses</option>
                            {["scheduled", "tentative", "completed", "missed", "cancelled"].map((item) => <option key={item} value={item}>{normalizeLabel(item)}</option>)}
                        </select>
                    </div>

                    {loading ? <p className="calendar-empty-copy">Loading legal calendar...</p> : null}
                    {error ? <p className="shell-error-text">{error}</p> : null}

                    {viewMode === "month" ? (
                        <div className="calendar-month-grid">
                            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <strong key={day}>{day}</strong>)}
                            {monthDays.map((day) => {
                                const key = formatDay(day);
                                const rows = eventsByDay.get(key) || [];
                                return (
                                    <div key={key} className={day.getMonth() === anchorDate.getMonth() ? "calendar-day-cell" : "calendar-day-cell muted"}>
                                        <span>{day.getDate()}</span>
                                        {rows.slice(0, 3).map((event) => (
                                            <button key={event.id} className={`calendar-dot-event priority-${event.priority}`} onClick={() => setSelectedEvent(event)} type="button">
                                                {eventIcon(event.event_type)} {event.title}
                                            </button>
                                        ))}
                                        {rows.length > 3 ? <em>{rows.length - 3} more</em> : null}
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <div className={`calendar-agenda-list view-${viewMode}`}>
                            {visibleEvents.length ? visibleEvents
                                .slice()
                                .sort((left, right) => left.start_datetime.localeCompare(right.start_datetime))
                                .map((event) => (
                                    <article key={event.id} className={`calendar-event-row priority-${event.priority} ${event.requires_review ? "needs-review" : ""}`}>
                                        <button className="calendar-event-main" onClick={() => setSelectedEvent(event)} type="button">
                                            <span className="calendar-event-icon">{eventIcon(event.event_type)}</span>
                                            <span>
                                                <strong>{event.title}</strong>
                                                <small>{formatDate(event.start_datetime, locale)}{event.case_title ? ` | ${event.case_title}` : ""}</small>
                                            </span>
                                        </button>
                                        <span className={`calendar-badge priority-${event.priority}`}>{normalizeLabel(event.priority)}</span>
                                        <span className="calendar-badge">{normalizeLabel(event.event_type)}</span>
                                        {event.requires_review ? <span className="calendar-badge warning">Review</span> : null}
                                        <div className="calendar-row-actions">
                                            <button onClick={() => openEditModal(event)} type="button" title="Edit event" aria-label="Edit event">✎</button>
                                            {event.requires_review ? <button onClick={() => acceptEvent(event)} type="button" title="Accept detected date" aria-label="Accept detected date">✓</button> : null}
                                            <button onClick={() => archiveEvent(event)} type="button" title="Archive event" aria-label="Archive event">×</button>
                                        </div>
                                    </article>
                                )) : (
                                <div className="calendar-empty-state">
                                    <strong>No calendar events match this view.</strong>
                                    <p>Create an event manually or upload a document with dates to populate the review queue.</p>
                                </div>
                            )}
                        </div>
                    )}
                </main>
            </div>

            {selectedEvent ? (
                <aside className="calendar-detail-drawer" aria-label="Calendar event details">
                    <button className="calendar-drawer-close" onClick={() => setSelectedEvent(null)} type="button" aria-label="Close">×</button>
                    <p className="shell-page-kicker">{normalizeLabel(selectedEvent.event_type)}</p>
                    <h3>{selectedEvent.title}</h3>
                    <p>{formatDate(selectedEvent.start_datetime, locale)}</p>
                    <div className="calendar-detail-badges">
                        <span className={`calendar-badge priority-${selectedEvent.priority}`}>{normalizeLabel(selectedEvent.priority)}</span>
                        <span className="calendar-badge">{normalizeLabel(selectedEvent.status)}</span>
                        {selectedEvent.requires_review ? <span className="calendar-badge warning">Needs lawyer review</span> : null}
                    </div>
                    {selectedEvent.description ? <p>{selectedEvent.description}</p> : null}
                    {selectedEvent.source_quote ? (
                        <blockquote className="calendar-source-quote">{selectedEvent.source_quote}</blockquote>
                    ) : null}
                    <div className="calendar-detail-links">
                        {selectedEvent.case_id ? <Link to={`/cases/${selectedEvent.case_id}/overview`}>Open related case</Link> : null}
                        {selectedEvent.source_document_id && selectedEvent.case_id ? <Link to={`/documents/${selectedEvent.case_id}`}>Open source document</Link> : null}
                        {selectedEvent.case_id ? <Link to={`/assistant/${selectedEvent.case_id}`}>Ask assistant</Link> : null}
                    </div>
                    <div className="calendar-reminder-actions">
                        <strong>Reminder</strong>
                        {[1, 3, 7].map((days) => (
                            <button key={days} onClick={() => addReminder(selectedEvent, days)} type="button">{days}d before</button>
                        ))}
                    </div>
                    <div className="calendar-drawer-actions">
                        <button onClick={() => openEditModal(selectedEvent)} type="button">Edit</button>
                        {selectedEvent.requires_review ? <button onClick={() => acceptEvent(selectedEvent)} type="button">Accept</button> : null}
                        {selectedEvent.requires_review ? <button onClick={() => rejectEvent(selectedEvent)} type="button">Reject</button> : null}
                    </div>
                </aside>
            ) : null}

            {modalOpen ? (
                <div className="calendar-modal-backdrop" role="presentation">
                    <div className="calendar-event-modal" role="dialog" aria-modal="true" aria-label="Calendar event form">
                        <div className="calendar-modal-head">
                            <div>
                                <p className="shell-page-kicker">{eventForm.id ? "Edit event" : "Create event"}</p>
                                <h3>{eventForm.id ? "Update legal calendar item" : "Add legal calendar item"}</h3>
                            </div>
                            <button onClick={() => setModalOpen(false)} type="button" aria-label="Close">×</button>
                        </div>
                        <label>
                            <span>Title</span>
                            <input value={eventForm.title} onChange={(event) => setEventForm((current) => ({ ...current, title: event.target.value }))} />
                        </label>
                        <div className="calendar-form-grid">
                            <label>
                                <span>Case</span>
                                <select value={eventForm.caseId || ""} onChange={(event) => setEventForm((current) => ({ ...current, caseId: event.target.value ? Number(event.target.value) : null }))}>
                                    <option value="">Personal / global</option>
                                    {cases.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                                </select>
                            </label>
                            <label>
                                <span>Type</span>
                                <select value={eventForm.eventType} onChange={(event) => setEventForm((current) => ({ ...current, eventType: event.target.value }))}>
                                    {EVENT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                                </select>
                            </label>
                            <label>
                                <span>Priority</span>
                                <select value={eventForm.priority} onChange={(event) => setEventForm((current) => ({ ...current, priority: event.target.value }))}>
                                    {PRIORITIES.map((item) => <option key={item} value={item}>{normalizeLabel(item)}</option>)}
                                </select>
                            </label>
                            <label>
                                <span>Status</span>
                                <select value={eventForm.status} onChange={(event) => setEventForm((current) => ({ ...current, status: event.target.value }))}>
                                    {["scheduled", "tentative", "completed", "missed", "cancelled"].map((item) => <option key={item} value={item}>{normalizeLabel(item)}</option>)}
                                </select>
                            </label>
                            <label>
                                <span>Start</span>
                                <input type="datetime-local" value={eventForm.startDatetime} onChange={(event) => setEventForm((current) => ({ ...current, startDatetime: event.target.value }))} />
                            </label>
                            <label>
                                <span>End</span>
                                <input type="datetime-local" value={eventForm.endDatetime} onChange={(event) => setEventForm((current) => ({ ...current, endDatetime: event.target.value }))} />
                            </label>
                        </div>
                        <label>
                            <span>Location</span>
                            <input value={eventForm.location} onChange={(event) => setEventForm((current) => ({ ...current, location: event.target.value }))} />
                        </label>
                        <label>
                            <span>Description / note</span>
                            <textarea value={eventForm.description} onChange={(event) => setEventForm((current) => ({ ...current, description: event.target.value }))} />
                        </label>
                        <div className="calendar-modal-actions">
                            <button className="shell-secondary-button" onClick={() => setModalOpen(false)} type="button">Cancel</button>
                            <button className="shell-primary-button" onClick={saveEvent} disabled={saving} type="button">{saving ? "Saving..." : "Save event"}</button>
                        </div>
                    </div>
                </div>
            ) : null}
        </section>
    );
}
