import { useMemo, useState } from "react";
import { usePortal } from "../context/PortalContext";
import { cancelPortalAppointment } from "../lib/api";
import { label } from "../portalPresentation";
import type { ClientPortalCalendarItem } from "../types";

function fmtDate(iso: string): string {
    return new Intl.DateTimeFormat("en-US", {
        month: "long",
        day: "2-digit",
        year: "numeric",
    }).format(new Date(iso));
}

function fmtShortDate(iso: string): string {
    return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "2-digit",
        year: "numeric",
    }).format(new Date(iso));
}

function fmtTimeRange(iso: string, durationMinutes: number): string {
    const start = new Date(iso);
    const end = new Date(start.getTime() + durationMinutes * 60000);
    const fmt = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });
    return `${fmt.format(start)} — ${fmt.format(end)}`;
}

function isVideo(item: ClientPortalCalendarItem): boolean {
    const t = `${item.appointment_type ?? ""} ${item.location ?? ""}`.toLowerCase();
    return t.includes("video") || t.includes("virtual") || t.includes("call") || t.includes("remote");
}

export default function LexingtonAppointmentsPage() {
    const { dashboard, token, refreshDashboard } = usePortal();
    const [cancelingId, setCancelingId] = useState<number | null>(null);
    const [error, setError] = useState<string | null>(null);

    const now = Date.now();

    const { upcoming, past } = useMemo(() => {
        const events = (dashboard?.calendar_events ?? [])
            .filter((e) => (e.status || "").toLowerCase() !== "cancelled")
            .slice()
            .sort((a, b) => a.scheduled_at.localeCompare(b.scheduled_at));
        return {
            upcoming: events.filter((e) => new Date(e.scheduled_at).getTime() >= now),
            past: events
                .filter((e) => new Date(e.scheduled_at).getTime() < now)
                .sort((a, b) => b.scheduled_at.localeCompare(a.scheduled_at)),
        };
    }, [dashboard, now]);

    const confirmedThisMonth = useMemo(() => {
        const d = new Date();
        return upcoming.filter((e) => {
            const ev = new Date(e.scheduled_at);
            return (
                ev.getMonth() === d.getMonth() &&
                ev.getFullYear() === d.getFullYear() &&
                ["scheduled", "confirmed", "tentative"].includes((e.status || "").toLowerCase())
            );
        }).length;
    }, [upcoming]);

    async function handleCancel(id: number) {
        if (!token) return;
        setCancelingId(id);
        setError(null);
        try {
            await cancelPortalAppointment(token, id);
            await refreshDashboard();
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Unable to cancel appointment.");
        } finally {
            setCancelingId(null);
        }
    }

    if (!dashboard) {
        return (
            <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
                <div className="bg-surface-container-lowest p-stack-lg border border-outline-variant rounded-lg">
                    <p className="font-body-md text-body-md text-on-surface-variant">Loading appointments…</p>
                </div>
            </main>
        );
    }

    return (
        <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
            <section className="mb-stack-lg">
                <h1 className="font-display-lg text-display-lg text-primary mb-2">Upcoming Appointments</h1>
                <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl">
                    Manage your upcoming legal consultations and case reviews. Connect with your legal team
                    through our secure, quiet interface.
                </p>
            </section>

            {error ? (
                <div className="mb-stack-md bg-error-container text-on-error-container px-4 py-3 rounded-lg font-body-md text-body-md">
                    {error}
                </div>
            ) : null}

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter items-start">
                {/* Appointment list */}
                <div className="lg:col-span-8 space-y-stack-md">
                    {upcoming.length === 0 ? (
                        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-lg text-center">
                            <span className="material-symbols-outlined text-4xl text-on-surface-variant">
                                event_busy
                            </span>
                            <h3 className="font-headline-md text-headline-md text-primary mt-3">
                                No upcoming appointments
                            </h3>
                            <p className="font-body-md text-on-surface-variant mt-1">
                                Your legal team will schedule sessions here as your case progresses.
                            </p>
                        </div>
                    ) : (
                        upcoming.map((ev, idx) => {
                            const video = isVideo(ev);
                            const isNext = idx === 0;
                            return (
                                <div
                                    key={ev.id}
                                    className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-lg"
                                >
                                    <div className="flex items-center gap-3 mb-3">
                                        <span
                                            className={
                                                isNext
                                                    ? "px-3 py-1 rounded-full bg-secondary-container text-on-secondary-container font-label-md text-label-md"
                                                    : "px-3 py-1 rounded-full bg-surface-container-high text-on-surface-variant font-label-md text-label-md"
                                            }
                                        >
                                            {isNext ? "Next Meeting" : "Upcoming"}
                                        </span>
                                        <span className="font-label-md text-label-md text-on-surface-variant">
                                            {label(ev.appointment_type) || "Consultation"}
                                        </span>
                                    </div>

                                    <h2 className="font-headline-lg text-headline-lg text-primary mb-stack-md">
                                        {ev.title}
                                    </h2>

                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-stack-md mb-stack-md">
                                        <div>
                                            <p className="font-label-md text-label-md text-on-surface-variant mb-1">
                                                Date
                                            </p>
                                            <p className="font-body-md text-body-md text-primary">
                                                {fmtDate(ev.scheduled_at)}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="font-label-md text-label-md text-on-surface-variant mb-1">
                                                Time
                                            </p>
                                            <p className="font-body-md text-body-md text-primary">
                                                {fmtTimeRange(ev.scheduled_at, ev.duration_minutes)}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="font-label-md text-label-md text-on-surface-variant mb-1">
                                                {video ? "Format" : "Location"}
                                            </p>
                                            <p className="font-body-md text-body-md text-primary">
                                                {ev.location || (video ? "Secure Video Conference" : "—")}
                                            </p>
                                        </div>
                                        <div>
                                            <p className="font-label-md text-label-md text-on-surface-variant mb-1">
                                                Attorney
                                            </p>
                                            <p className="font-body-md text-body-md text-primary">
                                                {ev.lawyer_name || "Your legal team"}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="flex flex-wrap gap-3 pt-stack-md border-t border-outline-variant">
                                        {video ? (
                                            <button
                                                type="button"
                                                className="bg-primary text-on-primary py-3 px-6 rounded font-label-md text-label-md hover:opacity-90 transition-opacity"
                                            >
                                                Join Video Call
                                            </button>
                                        ) : null}
                                        <button
                                            type="button"
                                            onClick={() => void handleCancel(ev.id)}
                                            disabled={cancelingId === ev.id}
                                            className="border border-outline-variant text-primary py-3 px-6 rounded font-label-md text-label-md hover:bg-surface-container-low transition-colors disabled:opacity-50"
                                        >
                                            {cancelingId === ev.id ? "Cancelling…" : "Cancel"}
                                        </button>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>

                {/* Sidebar */}
                <div className="lg:col-span-4 space-y-stack-md">
                    <div className="bg-surface-container-low border border-outline-variant rounded-xl p-stack-lg">
                        <h2 className="font-headline-md text-headline-md text-primary mb-stack-md">
                            Schedule at a Glance
                        </h2>
                        <div className="bg-surface-container rounded-lg p-stack-lg text-center">
                            <div className="font-display-lg text-display-lg text-primary leading-none">
                                {confirmedThisMonth}
                            </div>
                            <p className="font-label-md text-label-md text-on-surface-variant mt-2">
                                Confirmed meeting{confirmedThisMonth === 1 ? "" : "s"} this month
                            </p>
                        </div>
                    </div>

                    <div className="bg-primary-container rounded-xl p-stack-lg">
                        <span className="material-symbols-outlined text-on-primary mb-2">info</span>
                        <h3 className="font-headline-md text-headline-md text-on-primary mb-2">
                            Preparing for Meetings
                        </h3>
                        <p className="font-body-md text-body-md text-on-primary opacity-80">
                            Please ensure all requested documents are uploaded to your Documents area at least
                            24 hours before scheduled strategy sessions.
                        </p>
                    </div>

                    {past.length > 0 ? (
                        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-lg">
                            <p className="font-label-md text-label-md text-on-surface-variant uppercase tracking-widest mb-stack-md">
                                Past Appointments
                            </p>
                            <div className="divide-y divide-outline-variant">
                                {past.slice(0, 5).map((ev) => (
                                    <div key={ev.id} className="py-3 flex justify-between items-center">
                                        <span className="font-body-md text-body-md text-primary">
                                            {ev.title}
                                        </span>
                                        <span className="font-label-md text-label-md text-on-surface-variant">
                                            {fmtShortDate(ev.scheduled_at)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>
        </main>
    );
}
