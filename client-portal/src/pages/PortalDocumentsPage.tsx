import { useMemo, useState } from "react";
import { usePortal } from "../context/PortalContext";
import { formatBytes, formatDate, label, tone } from "../portalPresentation";

export default function PortalDocumentsPage() {
    const { dashboard, selectedCaseId, setSelectedCaseId } = usePortal();
    const [searchQuery, setSearchQuery] = useState("");

    const allDocuments = dashboard?.documents ?? [];
    const cases = dashboard?.cases ?? [];

    const visibleDocuments = useMemo(() => {
        const docs = selectedCaseId
            ? allDocuments.filter((d) => d.case_id === selectedCaseId)
            : allDocuments;
        const q = searchQuery.trim().toLowerCase();
        if (!q) return docs;
        return docs.filter(
            (d) =>
                d.filename.toLowerCase().includes(q) ||
                d.case_title.toLowerCase().includes(q) ||
                label(d.processing_status).toLowerCase().includes(q)
        );
    }, [allDocuments, selectedCaseId, searchQuery]);

    if (!dashboard) {
        return (
            <div className="card">
                <p>Loading documents…</p>
            </div>
        );
    }

    return (
        <div className="view-panel">
            <div className="view-header">
                <h2>Document Viewer</h2>
                <p>Files, highlights, and processing status for your matters.</p>
            </div>

            <div className="filter-row">
                <select
                    value={selectedCaseId ?? ""}
                    onChange={(e) => setSelectedCaseId(e.target.value ? Number(e.target.value) : null)}
                >
                    <option value="">All cases</option>
                    {cases.map((c) => (
                        <option key={c.id} value={c.id}>{c.title}</option>
                    ))}
                </select>
                <input
                    placeholder="Search documents…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                />
            </div>

            {visibleDocuments.length === 0 ? (
                <div className="card">
                    <p className="muted">No documents match your filter.</p>
                </div>
            ) : (
                <ul className="doc-full-list">
                    {visibleDocuments.map((doc) => (
                        <li key={doc.id} className="card doc-full-row">
                            <div className="doc-info">
                                <strong>{doc.filename}</strong>
                                <span className="muted">{doc.case_title}</span>
                            </div>
                            <div className="doc-meta">
                                <span>{doc.file_type.toUpperCase()}</span>
                                <span>{formatBytes(doc.file_size)}</span>
                                <span className={`status-badge ${tone(doc.processing_status)}`}>
                                    {label(doc.processing_status)}
                                </span>
                                <span className="muted">{formatDate(doc.upload_timestamp)}</span>
                            </div>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
