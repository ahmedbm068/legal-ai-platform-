import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import type { CalendarAppointment } from "../types";

function parseCaseId(value?: string) {
    const parsed = Number(value);
    if (!value || Number.isNaN(parsed) || parsed <= 0) {
        return null;
    }
    return parsed;
}

function formatDate(value: string, locale: string) {
    return new Intl.DateTimeFormat(locale, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(new Date(value));
}

function normalizeLabel(value: string | null | undefined, unknownLabel: string) {
    const normalized = String(value || "").trim().replace(/_/g, " ");
    if (!normalized) return unknownLabel;
    return normalized.charAt(0).toUpperCase() + normalized.slice(1);
}

function buildDateReason(
    appointment: CalendarAppointment,
    consultationSummaryById: Map<number, string>,
    derivedPrefix: string,
    generatedPrefix: string,
    fallbackReason: string
) {
    if (appointment.ai_recommendation?.trim()) {
        return appointment.ai_recommendation;
    }
    if (appointment.description?.trim()) {
        return appointment.description;
    }
    if (appointment.consultation_request_id && consultationSummaryById.has(appointment.consultation_request_id)) {
        return `${derivedPrefix}: ${consultationSummaryById.get(appointment.consultation_request_id)}`;
    }
    if (appointment.ai_source?.trim()) {
        return `${generatedPrefix} ${appointment.ai_source.replace(/_/g, " ")}.`;
    }
    if (appointment.notes?.trim()) {
        return appointment.notes;
    }
    return fallbackReason;
}

export default function CalendarPage() {
    const params = useParams();
    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);

    const {
        selectedCaseId,
        setSelectedCaseId,
        selectedCase,
        calendarAppointments,
        consultations,
        caseContextLoading,
        caseContextError,
        loadGlobalCalendarSummary,
        locale,
        t,
    } = useRoutedWorkspace();

    const activeCaseId = routeCaseId ?? selectedCaseId;
    const [globalSummaryLoading, setGlobalSummaryLoading] = useState(false);
    const [globalSummaryError, setGlobalSummaryError] = useState<string | null>(null);
    const [globalSummary, setGlobalSummary] = useState<{
        totalAppointments: number;
        upcomingAppointments: number;
        aiSuggestedAppointments: number;
        nextItems: CalendarAppointment[];
    } | null>(null);

    useEffect(() => {
        if (routeCaseId && routeCaseId !== selectedCaseId) {
            setSelectedCaseId(routeCaseId);
        }
    }, [routeCaseId, selectedCaseId, setSelectedCaseId]);

    useEffect(() => {
        let cancelled = false;
        if (activeCaseId) {
            setGlobalSummary(null);
            return;
        }

        setGlobalSummaryLoading(true);
        setGlobalSummaryError(null);
        void loadGlobalCalendarSummary()
            .then((summary) => {
                if (!cancelled) {
                    setGlobalSummary(summary);
                }
            })
            .catch((caught) => {
                if (!cancelled) {
                    const message = caught instanceof Error ? caught.message : t("calendarSummaryFailed", "Unable to load calendar summary.");
                    setGlobalSummaryError(message);
                }
            })
            .finally(() => {
                if (!cancelled) {
                    setGlobalSummaryLoading(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, [activeCaseId, loadGlobalCalendarSummary, t]);

    const consultationSummaryById = useMemo(() => {
        const map = new Map<number, string>();
        consultations.forEach((item) => {
            const summary = item.issue_summary || item.extracted_case_description || item.booking_intent || t("consultationRequest", "Consultation request");
            map.set(item.id, summary.slice(0, 140));
        });
        return map;
    }, [consultations, t]);

    const sortedCaseAppointments = useMemo(
        () => calendarAppointments.slice().sort((left, right) => left.scheduled_at.localeCompare(right.scheduled_at)),
        [calendarAppointments]
    );

    return (
        <section className="shell-page">
            <header className="shell-page-header">
                <p className="shell-page-kicker">{t("calendarKicker", "Calendar")}</p>
                <h2>{t("calendarTitle", "Deadlines and appointments with legal context")}</h2>
                <p>{t("calendarSubtitle", "Each event highlights why the date matters for case execution.")}</p>
            </header>

            {!activeCaseId ? (
                <>
                    <article className="shell-card">
                        <h3>{t("noCaseSelectedSummary", "No case selected")}</h3>
                        <p>
                            {t("calendarSummaryIntro", "This page is showing dashboard-style calendar summaries across your workspace. Select a case in Cases for detailed case-specific planning.")}
                            <Link className="shell-inline-link" to="/cases"> {t("navCasesLabel", "Cases")}</Link>
                        </p>
                    </article>

                    {globalSummaryLoading ? <p>{t("loadingGlobalCalendarSummary", "Loading global calendar summary...")}</p> : null}
                    {globalSummaryError ? <p className="shell-error-text">{globalSummaryError}</p> : null}

                    {globalSummary ? (
                        <>
                            <div className="shell-grid shell-grid-2">
                                <article className="shell-card">
                                    <h3>{t("coverage", "Coverage")}</h3>
                                    <p>{t("totalAppointments", "Total appointments")}: {globalSummary.totalAppointments}</p>
                                    <p>{t("upcomingAppointments", "Upcoming appointments")}: {globalSummary.upcomingAppointments}</p>
                                    <p>{t("aiSuggested", "AI suggested")}: {globalSummary.aiSuggestedAppointments}</p>
                                </article>
                                <article className="shell-card">
                                    <h3>{t("nextDeadlines", "Next deadlines")}</h3>
                                    <ul className="shell-list shell-tight-list">
                                        {globalSummary.nextItems.length ? globalSummary.nextItems.map((item) => (
                                            <li key={item.id}>
                                                <strong>{item.title}</strong>
                                                <span>{formatDate(item.scheduled_at, locale)}</span>
                                                <p>{normalizeLabel(item.status, t("unknown", "Unknown"))}</p>
                                            </li>
                                        )) : <li>{t("noUpcomingAppointments", "No upcoming appointments found.")}</li>}
                                    </ul>
                                </article>
                            </div>
                        </>
                    ) : null}
                </>
            ) : (
                <article className="shell-card">
                    <h3>{t("upcoming", "Upcoming")}</h3>
                    <p>
                        {t("caseLabel", "Case")}: <strong>{selectedCase?.title || `#${activeCaseId}`}</strong>
                    </p>
                    {caseContextLoading ? <p>{t("loadingCaseCalendarContext", "Loading case calendar context...")}</p> : null}
                    {caseContextError ? <p className="shell-error-text">{caseContextError}</p> : null}
                    <ul className="shell-list">
                        {sortedCaseAppointments.length ? sortedCaseAppointments.map((event) => (
                            <li key={event.id}>
                                <strong>{event.title}</strong>
                                <span>{formatDate(event.scheduled_at, locale)}</span>
                                <p>{buildDateReason(
                                    event,
                                    consultationSummaryById,
                                    t("derivedFromConsultation", "Derived from consultation"),
                                    t("generatedFrom", "Generated from"),
                                    t("scheduledTouchpoint", "Scheduled legal touchpoint to keep case execution and deadlines aligned.")
                                )}</p>
                            </li>
                        )) : <li>{t("noAppointmentsForCase", "No appointments scheduled for this case yet.")}</li>}
                    </ul>
                </article>
            )}
        </section>
    );
}
