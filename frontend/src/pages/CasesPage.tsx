import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { saveEditorDraftSeed } from "../editorDraftSeed";

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

function statusTone(value: string | null | undefined) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === "closed" || normalized === "archived") return "settled";
    if (normalized === "in_progress") return "active";
    return "open";
}

function clientInitials(value: string) {
    const parts = value.trim().split(/\s+/).filter(Boolean);
    const initials = parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
    return initials || "CL";
}

function tabClassName(active: boolean) {
    return active ? "shell-tab active" : "shell-tab";
}

export default function CasesPage() {
    const navigate = useNavigate();
    const params = useParams();

    const {
        cases,
        clients,
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
    const [portfolioQuery, setPortfolioQuery] = useState("");

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
    const [focusedClientId, setFocusedClientId] = useState<number | null>(null);

    const clientPortfolios = useMemo(() => {
        const clientById = new Map(clients.map((client) => [client.id, client]));
        const grouped = new Map<number, typeof cases>();

        clients.forEach((client) => {
            grouped.set(client.id, []);
        });

        cases.forEach((caseItem) => {
            const rows = grouped.get(caseItem.client_id) || [];
            rows.push(caseItem);
            grouped.set(caseItem.client_id, rows);
        });

        return Array.from(grouped.entries())
            .map(([clientId, clientCases]) => {
                const client = clientById.get(clientId);
                const sortedCases = [...clientCases].sort((left, right) => right.id - left.id);
                const openCases = sortedCases.filter((item) => item.status !== "closed" && item.status !== "archived").length;
                const inProgressCases = sortedCases.filter((item) => item.status === "in_progress").length;
                const latestCase = sortedCases[0] || null;
                const health = inProgressCases > 0 ? "active" : openCases > 0 ? "open" : sortedCases.length > 0 ? "settled" : "quiet";

                return {
                    clientId,
                    client,
                    cases: sortedCases,
                    openCases,
                    inProgressCases,
                    latestCase,
                    health,
                    displayName: client?.name || `${t("client", "Client")} #${clientId}`,
                    subtitle: client?.email || client?.phone || client?.address || t("noContactInfo", "No contact info yet"),
                };
            })
            .sort((left, right) => {
                const leftActive = left.clientId === activeCase?.client_id ? 1 : 0;
                const rightActive = right.clientId === activeCase?.client_id ? 1 : 0;
                if (leftActive !== rightActive) return rightActive - leftActive;
                return right.cases.length - left.cases.length || left.displayName.localeCompare(right.displayName);
            });
    }, [activeCase?.client_id, cases, clients, t]);

    const visibleClientPortfolios = useMemo(() => {
        const query = portfolioQuery.trim().toLowerCase();
        if (!query) return clientPortfolios;

        return clientPortfolios.filter((portfolio) => {
            const searchText = [
                portfolio.displayName,
                portfolio.subtitle,
                portfolio.latestCase?.title,
                ...portfolio.cases.map((item) => `${item.id} ${item.title} ${item.status} ${item.jurisdiction_country}`),
            ].join(" ").toLowerCase();
            return searchText.includes(query);
        });
    }, [clientPortfolios, portfolioQuery]);

    const portfolioTotals = useMemo(() => ({
        totalCases: cases.length,
        activeCases: cases.filter((item) => item.status === "in_progress").length,
        clientsWithOpenCases: clientPortfolios.filter((portfolio) => portfolio.openCases > 0).length,
    }), [cases, clientPortfolios]);

    const activeClientId = activeCase?.client_id ?? focusedClientId ?? clientPortfolios[0]?.clientId ?? null;
    const activePortfolio = useMemo(
        () => clientPortfolios.find((portfolio) => portfolio.clientId === activeClientId) || null,
        [activeClientId, clientPortfolios]
    );
    const activeClient = activePortfolio?.client || null;

    useEffect(() => {
        if (activeCase?.client_id && activeCase.client_id !== focusedClientId) {
            setFocusedClientId(activeCase.client_id);
            return;
        }

        if (!focusedClientId && clientPortfolios[0]) {
            setFocusedClientId(clientPortfolios[0].clientId);
        }
    }, [activeCase?.client_id, clientPortfolios, focusedClientId]);

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
        const selectedCase = cases.find((item) => item.id === caseId);
        if (selectedCase) {
            setFocusedClientId(selectedCase.client_id);
        }
        setSelectedCaseId(caseId);
        navigate(`/cases/${caseId}/${activeTab}`);
    }

    function handleClientSelect(clientId: number) {
        setFocusedClientId(clientId);
        const firstCase = clientPortfolios.find((portfolio) => portfolio.clientId === clientId)?.cases[0];
        if (firstCase) {
            setSelectedCaseId(firstCase.id);
            navigate(`/cases/${firstCase.id}/${activeTab}`);
        }
    }

    function handleTabSelect(tab: CaseTab) {
        if (!activeCaseId) return;
        navigate(`/cases/${activeCaseId}/${tab}`);
    }

    function handleGenerateCaseDocument() {
        if (!activeCase) return;
        saveEditorDraftSeed({
            source: "case",
            caseId: activeCase.id,
            caseTitle: activeCase.title,
            createdAt: new Date().toISOString(),
        });
    }

    return (
        <section className="shell-page">
            <header className="shell-page-header">
                <p className="shell-page-kicker">{t("casesKicker", "Cases")}</p>
                <h2>{t("casesTitle", "Client portfolios with case intelligence")}</h2>
                <p>{t("casesSubtitle", "Each client opens as a matter portfolio: cases, status, documents, timeline, assistant, and tasks.")}</p>
            </header>

            <div className="shell-grid shell-grid-2 case-portfolio-layout">
                <article className="shell-card">
                    <div className="case-portfolio-head">
                        <div>
                            <h3>{t("clientPortfolios", "Client portfolios")}</h3>
                            <p>{t("clientPortfoliosHint", "Pick a client, then open the exact matter you want.")}</p>
                        </div>
                        <div className="portfolio-total">
                            <strong>{clientPortfolios.length}</strong>
                            <span>{t("clients", "clients")}</span>
                        </div>
                    </div>

                    <div className="portfolio-metrics" aria-label={t("portfolioMetrics", "Portfolio metrics")}>
                        <span><strong>{portfolioTotals.totalCases}</strong>{t("totalCases", " total cases")}</span>
                        <span><strong>{portfolioTotals.clientsWithOpenCases}</strong>{t("clientsWithOpenCases", " clients active")}</span>
                        <span><strong>{portfolioTotals.activeCases}</strong>{t("inProgressCases", " in progress")}</span>
                    </div>

                    <label className="portfolio-search">
                        <span>{t("findClientOrMatter", "Find client or matter")}</span>
                        <input
                            type="search"
                            value={portfolioQuery}
                            onChange={(event) => setPortfolioQuery(event.target.value)}
                            placeholder={t("clientSearchPlaceholder", "Search by client, case, status...")}
                        />
                    </label>

                    {workspaceLoading ? <p>{t("loadingCases", "Loading your cases...")}</p> : null}
                    {workspaceError ? <p className="shell-error-text">{workspaceError}</p> : null}
                    <ul className="client-portfolio-list">
                        {visibleClientPortfolios.map((portfolio) => {
                            const isActiveClient = activeClientId === portfolio.clientId;
                            return (
                                <li key={portfolio.clientId}>
                                    <button
                                        className={`client-portfolio-row ${isActiveClient ? "active" : ""}`}
                                        onClick={() => handleClientSelect(portfolio.clientId)}
                                        type="button"
                                    >
                                        <span className="client-row-top">
                                            <span className="client-identity">
                                                <span className="client-avatar" aria-hidden="true">{clientInitials(portfolio.displayName)}</span>
                                                <strong>{portfolio.displayName}</strong>
                                            </span>
                                            <em className={`portfolio-health ${portfolio.health}`}>
                                                {portfolio.openCases} / {portfolio.cases.length} {t("openShort", "open")}
                                            </em>
                                        </span>
                                        <span>{portfolio.subtitle}</span>
                                        <p>
                                            {portfolio.latestCase
                                                ? `${t("latestMatter", "Latest")}: ${portfolio.latestCase.title}`
                                                : t("noCasesYet", "No cases yet")}
                                        </p>
                                    </button>

                                    {isActiveClient ? (
                                        <div className="client-case-stack" aria-label={t("clientCases", "Client cases")}>
                                            {portfolio.cases.map((item) => (
                                                <button
                                                    key={item.id}
                                                    className={`client-case-pill ${statusTone(item.status)} ${activeCaseId === item.id ? "active" : ""}`}
                                                    onClick={() => handleCaseSelect(item.id)}
                                                    type="button"
                                                >
                                                    <span>{t("caseLabel", "Case")} #{item.id}</span>
                                                    <strong>{item.title}</strong>
                                                    <em>{normalizeLabel(item.status, t("unknown", "Unknown"))}</em>
                                                </button>
                                            ))}
                                            {!portfolio.cases.length ? (
                                                <p className="client-case-empty">{t("clientHasNoCases", "No cases created for this client yet.")}</p>
                                            ) : null}
                                        </div>
                                    ) : null}
                                </li>
                            );
                        })}
                        {!visibleClientPortfolios.length ? (
                            <li className="portfolio-empty-state">
                                <strong>{t("noPortfolioMatches", "No matching client portfolio")}</strong>
                                <span>{t("noPortfolioMatchesHint", "Try another client name, case title, or status.")}</span>
                            </li>
                        ) : null}
                    </ul>
                </article>

                <article className="shell-card">
                    <div className="case-detail-heading">
                        <div>
                            <p className="shell-page-kicker">{activeClient ? t("clientDossier", "Client dossier") : t("caseDetailTabs", "Case detail tabs")}</p>
                            <h3>{activeClient?.name || t("caseDetailTabs", "Case detail tabs")}</h3>
                            {activePortfolio ? (
                                <p>
                                    {activePortfolio.cases.length} {t("matterCount", "matter(s)")}
                                    {" | "}
                                    {activePortfolio.openCases} {t("openMatterCount", "open")}
                                    {activeClient?.email ? ` | ${activeClient.email}` : ""}
                                </p>
                            ) : null}
                        </div>
                    </div>

                    {activePortfolio ? (
                        <div className="client-dossier-strip">
                            <div>
                                <span>{t("portfolioHealth", "Portfolio health")}</span>
                                <strong>{normalizeLabel(activePortfolio.health, t("unknown", "Unknown"))}</strong>
                            </div>
                            <div>
                                <span>{t("contact", "Contact")}</span>
                                <strong>{activeClient?.phone || activeClient?.email || t("missing", "Missing")}</strong>
                            </div>
                            <div>
                                <span>{t("lastMatter", "Last matter")}</span>
                                <strong>{activePortfolio.latestCase?.title || t("none", "None")}</strong>
                            </div>
                        </div>
                    ) : null}

                    <div className="shell-tabs" role="tablist" aria-label={t("caseTabsAria", "Case detail tabs")}>
                        {tabs.map((tab) => (
                            <button
                                key={tab.id}
                                className={tabClassName(activeTab === tab.id)}
                                disabled={!activeCaseId}
                                onClick={() => handleTabSelect(tab.id)}
                                aria-selected={activeTab === tab.id}
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
                                        <div className="case-overview-hero">
                                            <div>
                                                <p className="shell-page-kicker">{t("selectedMatter", "Selected matter")}</p>
                                                <h4>{activeCase.title}</h4>
                                                <p>{activeCase.description || t("noCaseDescription", "No case description yet.")}</p>
                                            </div>
                                            <div className="case-overview-actions">
                                                <span className={`case-status-pill ${statusTone(activeCase.status)}`}>{normalizeLabel(activeCase.status, t("unknown", "Unknown"))}</span>
                                                <Link
                                                    className="shell-inline-link case-generate-document-link"
                                                    onClick={handleGenerateCaseDocument}
                                                    to={`/editor/${activeCase.id}`}
                                                >
                                                    {t("generateDocument", "Generate document")}
                                                </Link>
                                            </div>
                                        </div>
                                        <div className="case-metric-grid">
                                            <p><strong>{t("jurisdiction", "Jurisdiction")}</strong><span>{normalizeLabel(activeCase.jurisdiction_country, t("unknown", "Unknown"))}</span></p>
                                            <p><strong>{t("client", "Client")}</strong><span>{activeClient?.name || `${t("clientId", "Client ID")} ${activeCase.client_id}`}</span></p>
                                            <p><strong>{t("created", "Created")}</strong><span>{formatDate(activeCase.created_at, locale, t("noDate", "No date"))}</span></p>
                                            <p><strong>{t("clientMatters", "Client matters")}</strong><span>{activePortfolio?.cases.length || 1}</span></p>
                                        </div>
                                    </div>
                                ) : null}

                                {activeTab === "documents" ? (
                                    <div className="shell-detail-block">
                                        <p><strong>{documents.length}</strong> {t("documentsLoadedForCase", "document(s) loaded for this case.")}</p>
                                        <p><strong>{imageBatches.length}</strong> {t("imageBatchesTracked", "image batch(es) tracked.")}</p>
                                        <div className="case-action-row">
                                            <Link className="shell-inline-link" to={`/documents/${activeCase.id}`}>
                                                {t("openDedicatedDocumentsPage", "Open dedicated Documents page")}
                                            </Link>
                                            <Link className="shell-inline-link" to={`/assistant/${activeCase.id}`}>
                                                {t("askAboutDocuments", "Ask assistant about these documents")}
                                            </Link>
                                        </div>
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
                                        <div className="assistant-launch-card">
                                            <div>
                                                <strong>{t("assistantLaunchTitle", "Launch matter assistant")}</strong>
                                                <span>{t("assistantLaunchSubtitle", "Uses this case context, documents, timeline, and client history.")}</span>
                                            </div>
                                            <Link className="shell-inline-link" to={`/assistant/${activeCase.id}`}>
                                                {t("openAssistantForCase", "Open Assistant")}
                                            </Link>
                                        </div>
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
                            <div className="client-no-matter-state">
                                <strong>{activeClient ? t("clientSelectedNoCase", "Client selected, no matter yet") : t("selectCaseForTabs", "Select a case to open tabbed case details.")}</strong>
                                <p>
                                    {activeClient
                                        ? t("clientSelectedNoCaseHint", "Create the first case for this client from the classic workspace or intake flow.")
                                        : t("selectCaseForTabsHint", "Choose a client portfolio on the left to inspect its matters.")}
                                </p>
                            </div>
                        )}
                    </div>
                </article>
            </div>
        </section>
    );
}
