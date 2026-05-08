import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { saveEditorDraftSeed } from "../editorDraftSeed";
import IntelligencePanel from "../components/IntelligencePanel";
import SuccessionCalculatorModal from "../components/SuccessionCalculatorModal";
import type { CaseReviewTable, CaseWorkflowCatalog, CaseWorkflowPreview, CaseWorkspaceSnapshot, DraftOutline } from "../types";
import { workspaceApi } from "../workspaceApi";

type CaseTab = "overview" | "workspace" | "documents" | "review" | "workflows" | "drafting" | "timeline" | "assistant" | "tasks" | "calendar";

const VALID_TABS = new Set<CaseTab>(["overview", "workspace", "documents", "review", "workflows", "drafting", "timeline", "assistant", "tasks", "calendar"]);

const DRAFT_INTENTS = [
    { id: "draft_client_email_case", label: "Client update email" },
    { id: "draft_internal_email_case", label: "Internal team email" },
    { id: "draft_partner_strategy_note_case", label: "Partner strategy memo" },
    { id: "draft_negotiation_strategy", label: "Negotiation strategy" },
    { id: "draft_contract_redline_case", label: "Contract redline pack" },
];

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

function compactText(value: unknown, fallback = "None"): string {
    if (Array.isArray(value)) {
        return value.length ? value.map((item) => compactText(item, "")).filter(Boolean).join(", ") : fallback;
    }
    if (typeof value === "string") {
        return value.trim() || fallback;
    }
    if (typeof value === "number" || typeof value === "boolean") {
        return String(value);
    }
    if (value && typeof value === "object") {
        const record = value as Record<string, unknown>;
        return compactText(record.title || record.label || record.name || record.summary || JSON.stringify(record), fallback);
    }
    return fallback;
}

function firstRecordDate(value: Record<string, unknown>) {
    return compactText(value.date || value.created_at || value.timestamp || value.start_datetime, "No date");
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
        recordings,
        calendarAppointments,
        consultations,
        imageBatches,
        locale,
        language,
        t,
        token,
    } = useRoutedWorkspace();

    const tabs: Array<{ id: CaseTab; label: string }> = [
        { id: "overview", label: t("tabOverview", "Overview") },
        { id: "workspace", label: t("tabWorkspace", "Workspace v2") },
        { id: "documents", label: t("tabDocuments", "Documents") },
        { id: "review", label: t("tabReviewTable", "Review Table") },
        { id: "workflows", label: t("tabWorkflows", "Workflows") },
        { id: "drafting", label: t("tabDrafting", "Drafting v2") },
        { id: "timeline", label: t("tabTimeline", "Timeline") },
        { id: "calendar", label: t("tabCalendar", "Calendar") },
        { id: "assistant", label: t("tabAssistant", "Assistant") },
        { id: "tasks", label: t("tabTasks", "Tasks") },
    ];

    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);
    const activeCaseId = routeCaseId ?? selectedCaseId;
    const rawTab = params.tab;
    const activeTab: CaseTab = (rawTab && VALID_TABS.has(rawTab as CaseTab) ? rawTab : "overview") as CaseTab;
    const [portfolioQuery, setPortfolioQuery] = useState("");
    const [workspaceSnapshot, setWorkspaceSnapshot] = useState<CaseWorkspaceSnapshot | null>(null);
    const [workspaceSnapshotLoading, setWorkspaceSnapshotLoading] = useState(false);
    const [workspaceSnapshotError, setWorkspaceSnapshotError] = useState<string | null>(null);
    const [reviewTable, setReviewTable] = useState<CaseReviewTable | null>(null);
    const [reviewTableLoading, setReviewTableLoading] = useState(false);
    const [reviewTableError, setReviewTableError] = useState<string | null>(null);
    const [workflowCatalog, setWorkflowCatalog] = useState<CaseWorkflowCatalog | null>(null);
    const [workflowPreview, setWorkflowPreview] = useState<CaseWorkflowPreview | null>(null);
    const [successionModalOpen, setSuccessionModalOpen] = useState(false);
    const [workflowLoading, setWorkflowLoading] = useState(false);
    const [workflowError, setWorkflowError] = useState<string | null>(null);
    const [draftIntent, setDraftIntent] = useState(DRAFT_INTENTS[0].id);
    const [draftObjective, setDraftObjective] = useState("");
    const [draftOutline, setDraftOutline] = useState<DraftOutline | null>(null);
    const [draftBody, setDraftBody] = useState("");
    const [draftingLoading, setDraftingLoading] = useState(false);
    const [draftingError, setDraftingError] = useState<string | null>(null);
    const [draftingNotice, setDraftingNotice] = useState<string | null>(null);

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

    const workflowAvailabilityById = useMemo(() => {
        return new Map((workflowCatalog?.availability || []).map((item) => [item.blueprint_id, item]));
    }, [workflowCatalog]);

    const citationSources = useMemo(() => {
        return documents.map((document, index) => ({
            source_label: `Source ${index + 1}: ${document.filename}`,
            filename: document.filename,
            document_id: document.id,
            case_id: document.case_id,
            snippet: document.extracted_text?.slice(0, 240) || document.filename,
            score: 1,
        }));
    }, [documents]);

    useEffect(() => {
        if (!token || !activeCaseId || activeTab !== "workspace") return;

        let cancelled = false;
        setWorkspaceSnapshotLoading(true);
        setWorkspaceSnapshotError(null);
        workspaceApi.getCaseWorkspaceSnapshot(token, activeCaseId)
            .then((payload) => {
                if (!cancelled) setWorkspaceSnapshot(payload);
            })
            .catch((caught) => {
                if (!cancelled) setWorkspaceSnapshotError(caught instanceof Error ? caught.message : "Unable to load workspace snapshot.");
            })
            .finally(() => {
                if (!cancelled) setWorkspaceSnapshotLoading(false);
            });

        return () => {
            cancelled = true;
        };
    }, [activeCaseId, activeTab, token]);

    useEffect(() => {
        if (!token || !activeCaseId || activeTab !== "review") return;

        let cancelled = false;
        setReviewTableLoading(true);
        setReviewTableError(null);
        workspaceApi.getCaseReviewTable(token, activeCaseId)
            .then((payload) => {
                if (!cancelled) setReviewTable(payload);
            })
            .catch((caught) => {
                if (!cancelled) setReviewTableError(caught instanceof Error ? caught.message : "Unable to load review table.");
            })
            .finally(() => {
                if (!cancelled) setReviewTableLoading(false);
            });

        return () => {
            cancelled = true;
        };
    }, [activeCaseId, activeTab, token]);

    useEffect(() => {
        if (!token || !activeCaseId || activeTab !== "workflows") return;

        let cancelled = false;
        setWorkflowLoading(true);
        setWorkflowError(null);
        workspaceApi.listCaseWorkflows(token, activeCaseId)
            .then(async (payload) => {
                if (cancelled) return;
                setWorkflowCatalog(payload);
                const firstAvailable = payload.availability.find((item) => item.status === "available")?.blueprint_id;
                const firstBlueprint = firstAvailable || payload.blueprints[0]?.id;
                if (firstBlueprint) {
                    const preview = await workspaceApi.previewCaseWorkflow(token, activeCaseId, firstBlueprint);
                    if (!cancelled) setWorkflowPreview(preview);
                }
            })
            .catch((caught) => {
                if (!cancelled) setWorkflowError(caught instanceof Error ? caught.message : "Unable to load workflow catalog.");
            })
            .finally(() => {
                if (!cancelled) setWorkflowLoading(false);
            });

        return () => {
            cancelled = true;
        };
    }, [activeCaseId, activeTab, token]);

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
        if (tab === "calendar") {
            navigate(`/cases/${activeCaseId}/calendar`);
            return;
        }
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

    async function handleWorkflowPreview(blueprintId: string) {
        if (!token || !activeCaseId) return;
        setWorkflowLoading(true);
        setWorkflowError(null);
        try {
            setWorkflowPreview(await workspaceApi.previewCaseWorkflow(token, activeCaseId, blueprintId));
        } catch (caught) {
            setWorkflowError(caught instanceof Error ? caught.message : "Unable to preview workflow.");
        } finally {
            setWorkflowLoading(false);
        }
    }

    async function handleGenerateOutline() {
        if (!token || !activeCase) return;
        setDraftingLoading(true);
        setDraftingError(null);
        setDraftingNotice(null);
        try {
            const outline = await workspaceApi.createDraftOutline(token, {
                intent: draftIntent,
                objective: draftObjective || activeCase.title,
                caseId: activeCase.id,
                jurisdiction: activeCase.jurisdiction_country,
            });
            setDraftOutline(outline);
            const seededBody = [
                outline.title,
                "",
                ...outline.sections.map((section, index) => (
                    `${index + 1}. ${section.heading}\n${section.purpose}${section.suggested_citations.length ? " [cite:source:1]" : ""}`
                )),
            ].join("\n\n");
            setDraftBody(seededBody);
            setDraftingNotice("Outline generated. Review the structure, then resolve citation markers or open it in the editor.");
        } catch (caught) {
            setDraftingError(caught instanceof Error ? caught.message : "Unable to generate draft outline.");
        } finally {
            setDraftingLoading(false);
        }
    }

    async function handleResolveDraftMarkers() {
        if (!token) return;
        setDraftingLoading(true);
        setDraftingError(null);
        setDraftingNotice(null);
        try {
            const result = await workspaceApi.resolveDraftCitationMarkers(token, {
                body: draftBody,
                sources: citationSources,
                citations: [],
            });
            setDraftBody(result.body);
            setDraftingNotice(result.reason);
        } catch (caught) {
            setDraftingError(caught instanceof Error ? caught.message : "Unable to resolve citation markers.");
        } finally {
            setDraftingLoading(false);
        }
    }

    function handleOpenDraftInEditor() {
        if (!activeCase) return;
        saveEditorDraftSeed({
            source: "assistant",
            caseId: activeCase.id,
            caseTitle: activeCase.title,
            prompt: draftObjective || draftOutline?.title || "Draft from outline",
            answer: draftBody || draftOutline?.sections.map((section) => `${section.heading}\n${section.purpose}`).join("\n\n") || "",
            sources: citationSources.map((source, index) => ({
                chunk_id: null,
                document_id: Number(source.document_id) || null,
                case_id: activeCase.id,
                filename: String(source.filename),
                chunk_index: index,
                score: 1,
                snippet: String(source.snippet || source.filename),
            })),
            citations: citationSources.map((source) => ({
                label: String(source.source_label),
                document_id: Number(source.document_id) || null,
                case_id: activeCase.id,
                snippet: String(source.snippet || source.filename),
            })),
            createdAt: new Date().toISOString(),
        });
        navigate(`/editor/${activeCase.id}`);
    }

    function launchWorkflowInAssistant() {
        if (!activeCase || !workflowPreview?.blueprint) return;
        const prompt = `Run or prepare the ${workflowPreview.blueprint.title} workflow for case #${activeCase.id}. Include expected outputs, missing prerequisites, and the next lawyer action.`;
        navigate(`/assistant/${activeCase.id}?q=${encodeURIComponent(prompt)}`);
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
                                        <IntelligencePanel
                                            language={(language as "en" | "de" | "ar") ?? "en"}
                                            caseItem={activeCase}
                                            client={activeClient}
                                            documents={documents}
                                            consultations={consultations}
                                            recordings={recordings}
                                            analysis={null}
                                            latestAssistantMessage={null}
                                            onLaunchAction={(prompt) => navigate(`/assistant/${activeCase.id}?q=${encodeURIComponent(prompt)}`)}
                                        />
                                    </div>
                                ) : null}

                                {activeTab === "workspace" ? (
                                    <div className="shell-detail-block lawyer-feature-surface">
                                        <div className="case-overview-hero">
                                            <div>
                                                <p className="shell-page-kicker">Workspace v2</p>
                                                <h4>One-call matter snapshot</h4>
                                                <p>Shows the aggregate backend workspace endpoint: case context, timeline, risks, memory, and available Big Agents.</p>
                                            </div>
                                            <Link className="shell-inline-link" to={`/assistant/${activeCase.id}`}>
                                                Ask with this context
                                            </Link>
                                        </div>
                                        {workspaceSnapshotLoading ? <p>Loading workspace snapshot...</p> : null}
                                        {workspaceSnapshotError ? <p className="shell-error-text">{workspaceSnapshotError}</p> : null}
                                        {workspaceSnapshot ? (
                                            <>
                                                <div className="case-metric-grid">
                                                    <p><strong>Scope</strong><span>{workspaceSnapshot.scope}</span></p>
                                                    <p><strong>Timeline events</strong><span>{workspaceSnapshot.timeline.length}</span></p>
                                                    <p><strong>Risk signals</strong><span>{workspaceSnapshot.risk_signals.length}</span></p>
                                                    <p><strong>Big Agents</strong><span>{workspaceSnapshot.big_agents.length}</span></p>
                                                </div>
                                                <div className="lawyer-feature-grid">
                                                    <section className="lawyer-feature-card">
                                                        <h5>Risk Signals</h5>
                                                        <ul className="shell-list shell-tight-list">
                                                            {workspaceSnapshot.risk_signals.length ? workspaceSnapshot.risk_signals.slice(0, 5).map((signal, index) => (
                                                                <li key={`risk-${index}`}>{compactText(signal)}</li>
                                                            )) : <li>No risk signals surfaced yet.</li>}
                                                        </ul>
                                                    </section>
                                                    <section className="lawyer-feature-card">
                                                        <h5>Memory</h5>
                                                        <div className="feature-key-value-list">
                                                            {Object.entries(workspaceSnapshot.memory).length ? Object.entries(workspaceSnapshot.memory).slice(0, 6).map(([key, value]) => (
                                                                <p key={key}><strong>{normalizeLabel(key, key)}</strong><span>{compactText(value)}</span></p>
                                                            )) : <p>No memory snapshot yet.</p>}
                                                        </div>
                                                    </section>
                                                </div>
                                                <section className="lawyer-feature-card">
                                                    <h5>Big Agent Catalog Visible To Lawyer</h5>
                                                    <div className="agent-chip-grid">
                                                        {workspaceSnapshot.big_agents.map((agent) => (
                                                            <article key={agent.name} className="agent-chip-card">
                                                                <strong>{normalizeLabel(agent.name, agent.name)}</strong>
                                                                <span>{agent.tier}</span>
                                                                <p>{agent.description}</p>
                                                                <small>{agent.mini_agents_used.slice(0, 4).join(", ")}</small>
                                                            </article>
                                                        ))}
                                                    </div>
                                                </section>
                                                <section className="lawyer-feature-card">
                                                    <h5>Workspace Timeline</h5>
                                                    <ul className="shell-list shell-tight-list">
                                                        {workspaceSnapshot.timeline.length ? workspaceSnapshot.timeline.slice(0, 8).map((event, index) => (
                                                            <li key={`workspace-event-${index}`}>
                                                                <strong>{compactText(event.title || event.label || event.type, "Event")}</strong>
                                                                <span>{firstRecordDate(event)}</span>
                                                                <p>{compactText(event.summary || event.description || event.subtitle, "No detail")}</p>
                                                            </li>
                                                        )) : <li>No workspace timeline events yet.</li>}
                                                    </ul>
                                                </section>
                                            </>
                                        ) : null}
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

                                {activeTab === "review" ? (
                                    <div className="shell-detail-block lawyer-feature-surface">
                                        <div className="case-overview-hero">
                                            <div>
                                                <p className="shell-page-kicker">Review Table v2</p>
                                                <h4>Vault-style document matrix</h4>
                                                <p>Every uploaded document is projected against lawyer questions: type, parties, dates, risks, and missing evidence.</p>
                                            </div>
                                            <span className="case-status-pill active">
                                                Coverage {reviewTable ? `${Math.round(reviewTable.coverage * 100)}%` : "--"}
                                            </span>
                                        </div>
                                        {reviewTableLoading ? <p>Loading review table...</p> : null}
                                        {reviewTableError ? <p className="shell-error-text">{reviewTableError}</p> : null}
                                        {reviewTable ? (
                                            <div className="review-table-wrap">
                                                <table className="lawyer-review-table">
                                                    <thead>
                                                        <tr>
                                                            <th>Document</th>
                                                            {reviewTable.questions.map((question) => (
                                                                <th key={question.id}>{question.label}</th>
                                                            ))}
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {reviewTable.rows.length ? reviewTable.rows.map((row) => (
                                                            <tr key={`${row.document_id}-${row.filename}`}>
                                                                <td>
                                                                    <strong>{row.filename}</strong>
                                                                    <span>{row.document_type || "Unknown type"}</span>
                                                                </td>
                                                                {reviewTable.questions.map((question) => {
                                                                    const cell = row.cells.find((item) => item.question_id === question.id);
                                                                    return (
                                                                        <td key={`${row.document_id}-${question.id}`} className={`evidence-${cell?.evidence_strength || "none"}`}>
                                                                            {cell && !cell.is_empty ? cell.values.slice(0, 3).map((value) => <p key={value}>{value}</p>) : <em>Missing</em>}
                                                                        </td>
                                                                    );
                                                                })}
                                                            </tr>
                                                        )) : (
                                                            <tr>
                                                                <td colSpan={reviewTable.questions.length + 1}>No documents available for review yet.</td>
                                                            </tr>
                                                        )}
                                                    </tbody>
                                                </table>
                                            </div>
                                        ) : null}
                                    </div>
                                ) : null}

                                {activeTab === "workflows" ? (
                                    <div className="shell-detail-block lawyer-feature-surface">
                                        <div className="case-overview-hero">
                                            <div>
                                                <p className="shell-page-kicker">Workflow Blueprints</p>
                                                <h4>Case-aware legal workflows</h4>
                                                <p>Lawyers can see which multi-step workflows are available, what each will produce, and why a workflow is blocked.</p>
                                            </div>
                                            <button className="shell-inline-link as-button" disabled={!workflowPreview} onClick={launchWorkflowInAssistant} type="button">
                                                Open in Assistant
                                            </button>
                                        </div>
                                        {workflowLoading ? <p>Loading workflows...</p> : null}
                                        {workflowError ? <p className="shell-error-text">{workflowError}</p> : null}
                                        {workflowCatalog ? (
                                            <div className="workflow-blueprint-layout">
                                                <div className="workflow-blueprint-list">
                                                    {workflowCatalog.blueprints.map((blueprint) => {
                                                        const availability = workflowAvailabilityById.get(blueprint.id);
                                                        return (
                                                            <button
                                                                key={blueprint.id}
                                                                className={`workflow-blueprint-card ${workflowPreview?.blueprint.id === blueprint.id ? "active" : ""}`}
                                                                onClick={() => {
                                                                    if (blueprint.id === "succession_entitlement_analysis") {
                                                                        setSuccessionModalOpen(true);
                                                                        return;
                                                                    }
                                                                    void handleWorkflowPreview(blueprint.id);
                                                                }}
                                                                type="button"
                                                            >
                                                                <strong>{blueprint.title}</strong>
                                                                <span className={`case-status-pill ${availability?.status === "available" ? "active" : "open"}`}>
                                                                    {availability?.status || "unknown"}
                                                                </span>
                                                                <small>{blueprint.harvey_equivalent || blueprint.executor}</small>
                                                                <p>{blueprint.description}</p>
                                                                {availability?.missing_prerequisites.length ? (
                                                                    <em>Missing: {availability.missing_prerequisites.join(", ")}</em>
                                                                ) : null}
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                                {workflowPreview ? (
                                                    <article className="workflow-preview-panel">
                                                        <h5>{workflowPreview.blueprint.title}</h5>
                                                        <p>{workflowPreview.blueprint.description}</p>
                                                        <div className="case-metric-grid compact">
                                                            <p><strong>Runtime</strong><span>{workflowPreview.blueprint.estimated_runtime_seconds}s</span></p>
                                                            <p><strong>Executor</strong><span>{workflowPreview.blueprint.executor}</span></p>
                                                            <p><strong>Status</strong><span>{workflowPreview.availability.status}</span></p>
                                                            <p><strong>Outputs</strong><span>{workflowPreview.blueprint.output_keys.length}</span></p>
                                                        </div>
                                                        <ol className="workflow-step-list">
                                                            {workflowPreview.blueprint.steps.map((step) => (
                                                                <li key={`${workflowPreview.blueprint.id}-${step.name}`}>
                                                                    <strong>{step.name}</strong>
                                                                    <span>{step.agent}</span>
                                                                    <p>{step.description}</p>
                                                                </li>
                                                            ))}
                                                        </ol>
                                                    </article>
                                                ) : null}
                                            </div>
                                        ) : null}
                                    </div>
                                ) : null}

                                {activeTab === "drafting" ? (
                                    <div className="shell-detail-block lawyer-feature-surface">
                                        <div className="case-overview-hero">
                                            <div>
                                                <p className="shell-page-kicker">Drafting v2</p>
                                                <h4>Outline-first drafting with citation markers</h4>
                                                <p>Generate a deterministic outline, review it, resolve citation markers, then open the draft in the legal editor.</p>
                                            </div>
                                            <button className="shell-inline-link as-button" disabled={!draftBody.trim()} onClick={handleOpenDraftInEditor} type="button">
                                                Open in Editor
                                            </button>
                                        </div>
                                        <div className="drafting-control-grid">
                                            <label>
                                                <span>Draft type</span>
                                                <select value={draftIntent} onChange={(event) => setDraftIntent(event.target.value)}>
                                                    {DRAFT_INTENTS.map((intent) => (
                                                        <option key={intent.id} value={intent.id}>{intent.label}</option>
                                                    ))}
                                                </select>
                                            </label>
                                            <label>
                                                <span>Objective</span>
                                                <input
                                                    value={draftObjective}
                                                    onChange={(event) => setDraftObjective(event.target.value)}
                                                    placeholder={`Draft for ${activeCase.title}`}
                                                />
                                            </label>
                                            <button className="shell-inline-link as-button primary-action" disabled={draftingLoading} onClick={() => void handleGenerateOutline()} type="button">
                                                Generate Outline
                                            </button>
                                        </div>
                                        {draftingError ? <p className="shell-error-text">{draftingError}</p> : null}
                                        {draftingNotice ? <p className="shell-success-text">{draftingNotice}</p> : null}
                                        {draftOutline ? (
                                            <div className="lawyer-feature-grid">
                                                <section className="lawyer-feature-card">
                                                    <h5>{draftOutline.title}</h5>
                                                    <p><strong>Tone:</strong> {draftOutline.tone}</p>
                                                    <p><strong>Audience:</strong> {draftOutline.audience}</p>
                                                    <ul className="shell-list shell-tight-list">
                                                        {draftOutline.sections.map((section) => (
                                                            <li key={section.heading}>
                                                                <strong>{section.heading}</strong>
                                                                <p>{section.purpose}</p>
                                                                {section.suggested_citations.length ? <span>Suggested citations: {section.suggested_citations.join(", ")}</span> : null}
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </section>
                                                <section className="lawyer-feature-card">
                                                    <h5>Case hints</h5>
                                                    <ul className="shell-list shell-tight-list">
                                                        {draftOutline.case_hints.length ? draftOutline.case_hints.map((hint) => <li key={hint}>{hint}</li>) : <li>No case hints yet.</li>}
                                                    </ul>
                                                </section>
                                            </div>
                                        ) : null}
                                        <label className="draft-body-editor">
                                            <span>Draft body / citation marker sandbox</span>
                                            <textarea value={draftBody} onChange={(event) => setDraftBody(event.target.value)} placeholder="Generate an outline, or type [cite:source:1] to test citation marker resolution." />
                                        </label>
                                        <div className="case-action-row">
                                            <button className="shell-inline-link as-button" disabled={!draftBody.trim() || !citationSources.length || draftingLoading} onClick={() => void handleResolveDraftMarkers()} type="button">
                                                Resolve citation markers
                                            </button>
                                            <span>{citationSources.length} document source(s) available for citation.</span>
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

                                {activeTab === "calendar" ? (
                                    <div className="shell-detail-block">
                                        <p>{t("caseCalendarNotice", "Open the matter calendar for hearings, deadlines, extracted document dates, reminders, and review status.")}</p>
                                        <Link className="shell-inline-link" to={`/cases/${activeCase.id}/calendar`}>
                                            {t("openCaseCalendar", "Open case calendar")}
                                        </Link>
                                    </div>
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
            {successionModalOpen && token ? (
                <SuccessionCalculatorModal
                    token={token}
                    language={language}
                    onClose={() => setSuccessionModalOpen(false)}
                />
            ) : null}
        </section>
    );
}
