import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { usePortal } from "../context/PortalContext";
import { formatDate, label, riskFromCase, tone } from "../portalPresentation";

export default function PortalCasesPage() {
    const { dashboard, selectedCaseId, setSelectedCaseId } = usePortal();
    const [searchParams] = useSearchParams();
    const [searchQuery, setSearchQuery] = useState(searchParams.get("q") ?? "");

    const sortedCases = useMemo(() => {
        if (!dashboard) return [];
        return [...dashboard.cases].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    }, [dashboard]);

    const visibleCases = useMemo(() => {
        const q = searchQuery.trim().toLowerCase();
        if (!q) return sortedCases;
        return sortedCases.filter(
            (c) =>
                c.title.toLowerCase().includes(q) ||
                (c.description ?? "").toLowerCase().includes(q) ||
                label(c.status).toLowerCase().includes(q)
        );
    }, [searchQuery, sortedCases]);

    const selectedCase = useMemo(
        () => sortedCases.find((c) => c.id === selectedCaseId) ?? null,
        [sortedCases, selectedCaseId]
    );

    const caseDocuments = useMemo(() => {
        if (!dashboard || !selectedCase) return [];
        return dashboard.documents
            .filter((d) => d.case_id === selectedCase.id)
            .sort((a, b) => b.upload_timestamp.localeCompare(a.upload_timestamp));
    }, [dashboard, selectedCase]);

    if (!dashboard) {
        return (
            <div className="card">
                <p>Loading cases…</p>
            </div>
        );
    }

    return (
        <div className="view-panel">
            <div className="view-header">
                <h2>Case Intelligence</h2>
                <p>Status, risk level, and evidence overview for your active matters.</p>
            </div>

            <div className="search-row">
                <input
                    placeholder="Search cases…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                />
            </div>

            <div className="cases-layout">
                <aside className="case-list">
                    {visibleCases.length === 0 ? (
                        <p className="muted">No cases found.</p>
                    ) : (
                        visibleCases.map((c) => {
                            const risk = riskFromCase(c);
                            return (
                                <button
                                    key={c.id}
                                    className={`case-row${c.id === selectedCaseId ? " active" : ""}`}
                                    onClick={() => setSelectedCaseId(c.id)}
                                    type="button"
                                >
                                    <div className="case-row-head">
                                        <strong>{c.title}</strong>
                                        <span className={`risk-badge ${risk.tone}`}>{risk.label} risk</span>
                                    </div>
                                    <div className="case-row-meta">
                                        <span className={`status-badge ${tone(c.status)}`}>{label(c.status)}</span>
                                        <span className="muted">{formatDate(c.updated_at)}</span>
                                    </div>
                                </button>
                            );
                        })
                    )}
                </aside>

                {selectedCase ? (
                    <div className="card case-detail">
                        <h3>{selectedCase.title}</h3>
                        <div className="case-meta-grid">
                            <span>Status</span>
                            <span className={`status-badge ${tone(selectedCase.status)}`}>{label(selectedCase.status)}</span>
                            <span>Jurisdiction</span>
                            <span>{label(selectedCase.jurisdiction_country)}</span>
                            <span>Lawyer</span>
                            <span>{selectedCase.lawyer_name ?? "—"}</span>
                            <span>Opened</span>
                            <span>{formatDate(selectedCase.created_at)}</span>
                            <span>Last update</span>
                            <span>{formatDate(selectedCase.updated_at)}</span>
                        </div>

                        {selectedCase.description ? (
                            <p className="case-description">{selectedCase.description}</p>
                        ) : null}

                        {selectedCase.next_recommended_step ? (
                            <div className="next-step-card">
                                <strong>Next recommended step</strong>
                                <p>{selectedCase.next_recommended_step}</p>
                            </div>
                        ) : null}

                        {caseDocuments.length > 0 ? (
                            <div>
                                <h4>Documents ({caseDocuments.length})</h4>
                                <ul className="doc-list">
                                    {caseDocuments.map((doc) => (
                                        <li key={doc.id} className="doc-row">
                                            <span className="doc-name">{doc.filename}</span>
                                            <span className={`status-badge ${tone(doc.processing_status)}`}>
                                                {label(doc.processing_status)}
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ) : (
                            <p className="muted">No documents uploaded for this case yet.</p>
                        )}
                    </div>
                ) : (
                    <div className="card case-detail">
                        <p className="muted">Select a case to view details.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
