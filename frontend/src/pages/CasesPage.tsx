import { useEffect, useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";

type CaseTab = "overview" | "documents" | "timeline" | "assistant" | "tasks";

const VALID_TABS = new Set<CaseTab>(["overview", "documents", "timeline", "assistant", "tasks"]);

function parseCaseId(value?: string) {
    const parsed = Number(value);
    if (!value || Number.isNaN(parsed) || parsed <= 0) {
        return null;
    }
    return parsed;
}

function formatDate(value: string | null | undefined, locale: string, noDateLabel: string) {
    if (!value) return noDateLabel;
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

function tabClassName(active: boolean) {
    return active ? "shell-tab active" : "shell-tab";
}

export default function CasesPage() {
    const navigate = useNavigate();
    const params = useParams();

    const {
        cases,
        workspaceLoading,
        workspaceError,
        selectedCaseId,
        setSelectedCaseId,
        caseContextLoading,
        caseContextError,
        documents,
        calendarAppointments,
        consultations,
        imageBatches,
        locale,
        t,
    } = useRoutedWorkspace();

    const tabs: Array<{ id: CaseTab; label: string }> = [
        { id: "overview", label: t("tabOverview", "Overview") },
        { id: "documents", label: t("tabDocuments", "Documents") },
        { id: "timeline", label: t("tabTimeline", "Timeline") },
        { id: "assistant", label: t("tabAssistant", "Assistant") },
        { id: "tasks", label: t("tabTasks", "Tasks") },
    ];

    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);
    const activeCaseId = routeCaseId ?? selectedCaseId;
    const rawTab = params.tab;
    const activeTab: CaseTab = (rawTab && VALID_TABS.has(rawTab as CaseTab) ? rawTab : "overview") as CaseTab;

    useEffect(() => {
        if (routeCaseId && routeCaseId !== selectedCaseId) {
            setSelectedCaseId(routeCaseId);
        }
    }, [routeCaseId, selectedCaseId, setSelectedCaseId]);

    useEffect(() => {
        if (routeCaseId && rawTab && !VALID_TABS.has(rawTab as CaseTab)) {
            navigate(`/cases/${routeCaseId}/overview`, { replace: true });
        }
    }, [navigate, rawTab, routeCaseId]);

    const activeCase = useMemo(
        () => (activeCaseId ? cases.find((item) => item.id === activeCaseId) || null : null),
        [activeCaseId, cases]
    );

    const timelineItems = useMemo(() => {
        const appointmentRows = calendarAppointments.map((item) => ({
            id: `appointment-${item.id}`,
            date: item.scheduled_at,
            title: item.title,
            subtitle: normalizeLabel(item.status, t("unknown", "Unknown")),
        }));

        const consultationRows = consultations.map((item) => ({
            id: `consultation-${item.id}`,
            date: item.created_at,
            title: t("consultationRequest", "Consultation request"),
            subtitle: normalizeLabel(item.urgency_level, t("unknown", "Unknown")),
        }));

        return [...appointmentRows, ...consultationRows]
            .sort((left, right) => left.date.localeCompare(right.date))
            .slice(0, 8);
    }, [calendarAppointments, consultations, t]);

    function handleCaseSelect(caseId: number) {
        setSelectedCaseId(caseId);
        navigate(`/cases/${caseId}/${activeTab}`);
    }

    function handleTabSelect(tab: CaseTab) {
        if (!activeCaseId) return;
        navigate(`/cases/${activeCaseId}/${tab}`);
    }

    return (
        <section className="shell-page">
            <header className="shell-page-header">
                <p className="shell-page-kicker">{t("casesKicker", "Cases")}</p>
                <h2>{t("casesTitle", "List first, then tabbed case details")}</h2>
                <p>{t("casesSubtitle", "Tabs: Overview, Documents, Timeline, Assistant, Tasks.")}</p>
            </header>

            <div className="shell-grid shell-grid-2">
                <article className="shell-card">
                    <h3>{t("caseList", "Case list")}</h3>
                    {workspaceLoading ? <p>{t("loadingCases", "Loading your cases...")}</p> : null}
                    {workspaceError ? <p className="shell-error-text">{workspaceError}</p> : null}
                    <ul className="shell-list shell-tight-list">
                        {cases.map((item) => (
                            <li key={item.id}>
                                <button
                                    className={`shell-case-row ${activeCaseId === item.id ? "active" : ""}`}
                                    onClick={() => handleCaseSelect(item.id)}
                                    type="button"
                                >
                                    <strong>{t("caseLabel", "Case")} #{item.id}</strong>
                                    <span>{item.title}</span>
                                    <p>{normalizeLabel(item.status, t("unknown", "Unknown"))}</p>
                                </button>
                            </li>
                        ))}
                    </ul>
                </article>

                <article className="shell-card">
                    <h3>{t("caseDetailTabs", "Case detail tabs")}</h3>
                    <div className="shell-tabs" role="tablist" aria-label={t("caseTabsAria", "Case detail tabs")}>
                        {tabs.map((tab) => (
                            <button
                                key={tab.id}
                                className={tabClassName(activeTab === tab.id)}
                                onClick={() => handleTabSelect(tab.id)}
                                role="tab"
                                type="button"
                            >
                                {tab.label}
                            </button>
                        ))}
                    </div>
                    <div className="shell-tab-panel">
                        {activeCase ? (
                            <>
                                {caseContextLoading ? <p>{t("loadingCaseContext", "Loading selected case context...")}</p> : null}
                                {caseContextError ? <p className="shell-error-text">{caseContextError}</p> : null}

                                {activeTab === "overview" ? (
                                    <div className="shell-detail-block">
                                        <p><strong>{activeCase.title}</strong></p>
                                        <p>{t("status", "Status")}: {normalizeLabel(activeCase.status, t("unknown", "Unknown"))}</p>
                                        <p>{t("jurisdiction", "Jurisdiction")}: {normalizeLabel(activeCase.jurisdiction_country, t("unknown", "Unknown"))}</p>
                                        <p>{t("clientId", "Client ID")}: {activeCase.client_id}</p>
                                    </div>
                                ) : null}

                                {activeTab === "documents" ? (
                                    <div className="shell-detail-block">
                                        <p><strong>{documents.length}</strong> {t("documentsLoadedForCase", "document(s) loaded for this case.")}</p>
                                        <p><strong>{imageBatches.length}</strong> {t("imageBatchesTracked", "image batch(es) tracked.")}</p>
                                        <Link className="shell-inline-link" to={`/documents/${activeCase.id}`}>
                                            {t("openDedicatedDocumentsPage", "Open dedicated Documents page")}
                                        </Link>
                                    </div>
                                ) : null}

                                {activeTab === "timeline" ? (
                                    <ul className="shell-list shell-tight-list">
                                        {timelineItems.length ? timelineItems.map((item) => (
                                            <li key={item.id}>
                                                <strong>{item.title}</strong>
                                                <span>{formatDate(item.date, locale, t("noDate", "No date"))}</span>
                                                <p>{item.subtitle}</p>
                                            </li>
                                        )) : <li>{t("noTimelineEvents", "No timeline events yet.")}</li>}
                                    </ul>
                                ) : null}

                                {activeTab === "assistant" ? (
                                    <div className="shell-detail-block">
                                        <p>{t("openCaseAssistantNotice", "Open case-scoped assistant chat for this matter.")}</p>
                                        <Link className="shell-inline-link" to={`/assistant/${activeCase.id}`}>
                                            {t("openAssistantForCase", "Open Assistant for this case")}
                                        </Link>
                                    </div>
                                ) : null}

                                {activeTab === "tasks" ? (
                                    <div className="shell-detail-block">
                                        <p>{t("pendingUploads", "Pending uploads")}: {documents.filter((item) => item.processing_status !== "completed").length}</p>
                                        <p>{t("upcomingAppointments", "Upcoming appointments")}: {calendarAppointments.length}</p>
                                        <p>{t("consultationRequests", "Consultation requests")}: {consultations.length}</p>
                                    </div>
                                ) : null}
                            </>
                        ) : (
                            <p>{t("selectCaseForTabs", "Select a case to open tabbed case details.")}</p>
                        )}
                    </div>
                </article>
            </div>
        </section>
    );
}
