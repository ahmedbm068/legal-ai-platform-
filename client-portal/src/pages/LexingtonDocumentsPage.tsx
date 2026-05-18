import { useMemo, useRef, useState } from "react";
import { usePortal } from "../context/PortalContext";
import { formatBytes, formatDate, label } from "../portalPresentation";
import type { ClientPortalDocument } from "../types";

// Map a document's processing status to one of the three pill buckets + a badge style.
type Bucket = "completed" | "review" | "signature";

function bucketOf(status: string): Bucket {
    const s = (status || "").toLowerCase();
    if (["completed", "processed", "signed", "approved", "ready"].includes(s)) return "completed";
    if (["awaiting_signature", "needs_signature", "signature_required"].includes(s)) return "signature";
    return "review";
}

const BADGE: Record<Bucket, { className: string; icon: string; text: (raw: string) => string }> = {
    completed: {
        className: "bg-secondary-container text-on-secondary-container",
        icon: "check_circle",
        text: (raw) => label(raw) || "Completed",
    },
    review: {
        className: "bg-tertiary-fixed text-on-tertiary-fixed",
        icon: "visibility",
        text: () => "For Review",
    },
    signature: {
        className: "bg-error-container text-on-error-container",
        icon: "ink_pen",
        text: () => "Awaiting Signature",
    },
};

function fileIcon(fileType: string): string {
    return (fileType || "").toLowerCase().includes("pdf") ? "picture_as_pdf" : "description";
}

export default function LexingtonDocumentsPage() {
    const { dashboard, selectedCaseId, uploadCaseMaterials, uploadLoading, account } = usePortal();
    const [activeFilter, setActiveFilter] = useState<Bucket | null>(null);
    const fileInputRef = useRef<HTMLInputElement | null>(null);

    const documents = dashboard?.documents ?? [];

    const counts = useMemo(() => {
        const c = { completed: 0, review: 0, signature: 0 };
        for (const d of documents) c[bucketOf(d.processing_status)] += 1;
        return c;
    }, [documents]);

    const visible = useMemo(() => {
        const sorted = [...documents].sort((a, b) =>
            b.upload_timestamp.localeCompare(a.upload_timestamp)
        );
        if (!activeFilter) return sorted;
        return sorted.filter((d) => bucketOf(d.processing_status) === activeFilter);
    }, [documents, activeFilter]);

    function uploadedBy(doc: ClientPortalDocument): string {
        const owningCase = dashboard?.cases.find((c) => c.id === doc.case_id);
        if (owningCase?.lawyer_name) return owningCase.lawyer_name;
        return account?.full_name ? "You" : "—";
    }

    function triggerUpload() {
        fileInputRef.current?.click();
    }

    async function onFilesPicked(e: React.ChangeEvent<HTMLInputElement>) {
        const files = e.target.files;
        const targetCaseId = selectedCaseId ?? dashboard?.cases[0]?.id ?? null;
        if (!files || files.length === 0 || targetCaseId == null) {
            e.target.value = "";
            return;
        }
        const formData = new FormData();
        Array.from(files).forEach((f) => formData.append("files", f));
        await uploadCaseMaterials(targetCaseId, formData);
        e.target.value = "";
    }

    if (!dashboard) {
        return (
            <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
                <div className="bg-surface-container-lowest p-stack-lg border border-outline-variant rounded-lg">
                    <p className="font-body-md text-body-md text-on-surface-variant">Loading documents…</p>
                </div>
            </main>
        );
    }

    const pills: Array<{ key: Bucket; label: string; icon: string; count: number }> = [
        { key: "completed", label: "Completed", icon: "check_circle", count: counts.completed },
        { key: "review", label: "Pending Review", icon: "pending", count: counts.review },
        { key: "signature", label: "Awaiting Signature", icon: "history_edu", count: counts.signature },
    ];

    return (
        <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
            {/* Action Header */}
            <section className="flex flex-col md:flex-row md:items-end justify-between gap-stack-md mb-stack-lg">
                <div>
                    <h1 className="font-headline-lg text-headline-lg text-primary mb-2">Documents</h1>
                    <p className="font-body-md text-body-md text-on-surface-variant">
                        Manage your legal filings and case-related paperwork in one secure location.
                    </p>
                </div>
                <button
                    type="button"
                    onClick={triggerUpload}
                    disabled={uploadLoading || dashboard.cases.length === 0}
                    className="flex items-center justify-center gap-3 bg-primary text-on-primary px-8 py-4 rounded-lg font-label-md text-label-md transition-opacity active:opacity-80 disabled:opacity-50"
                >
                    <span className="material-symbols-outlined">upload_file</span>
                    {uploadLoading ? "Uploading…" : "Upload Document"}
                </button>
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={onFilesPicked}
                />
            </section>

            {/* Status Pills (clickable filters) */}
            <div className="flex flex-wrap gap-4 mb-stack-lg">
                {pills.map((p) => {
                    const active = activeFilter === p.key;
                    return (
                        <button
                            key={p.key}
                            type="button"
                            onClick={() => setActiveFilter(active ? null : p.key)}
                            className={
                                active
                                    ? "flex items-center gap-2 px-4 py-2 bg-secondary-container text-on-secondary-container rounded-full font-label-md text-label-md ring-2 ring-secondary"
                                    : p.key === "completed"
                                      ? "flex items-center gap-2 px-4 py-2 bg-secondary-container text-on-secondary-container rounded-full font-label-md text-label-md"
                                      : "flex items-center gap-2 px-4 py-2 bg-surface-container-high text-on-surface-variant rounded-full font-label-md text-label-md border border-outline-variant"
                            }
                        >
                            <span
                                className="material-symbols-outlined text-[18px]"
                                style={p.key === "completed" ? { fontVariationSettings: "'FILL' 1" } : undefined}
                            >
                                {p.icon}
                            </span>
                            {p.label}: {p.count}
                        </button>
                    );
                })}
            </div>

            {/* Documents Table */}
            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden shadow-[0px_16px_16px_rgba(1,32,19,0.04)]">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-surface-container-low border-b border-outline-variant">
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Name</th>
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Uploaded By</th>
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Date</th>
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Status</th>
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-outline-variant">
                            {visible.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="px-8 py-12 text-center font-body-md text-on-surface-variant">
                                        {documents.length === 0
                                            ? "No documents yet. Use “Upload Document” to add your first file."
                                            : "No documents match this filter."}
                                    </td>
                                </tr>
                            ) : (
                                visible.map((doc) => {
                                    const bucket = bucketOf(doc.processing_status);
                                    const badge = BADGE[bucket];
                                    return (
                                        <tr key={doc.id} className="hover:bg-surface-container-low transition-colors duration-200">
                                            <td className="px-8 py-8">
                                                <div className="flex items-center gap-4">
                                                    <span className="material-symbols-outlined text-primary">
                                                        {fileIcon(doc.file_type)}
                                                    </span>
                                                    <div className="flex flex-col">
                                                        <span className="font-headline-md text-body-md text-primary">
                                                            {doc.filename}
                                                        </span>
                                                        <span className="font-label-md text-label-md text-on-surface-variant">
                                                            {doc.case_title} · {formatBytes(doc.file_size)}
                                                        </span>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="px-8 py-8 font-body-md text-on-surface">{uploadedBy(doc)}</td>
                                            <td className="px-8 py-8 font-body-md text-on-surface-variant">
                                                {formatDate(doc.upload_timestamp)}
                                            </td>
                                            <td className="px-8 py-8">
                                                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full font-label-md text-[12px] ${badge.className}`}>
                                                    <span className="material-symbols-outlined text-[14px]">{badge.icon}</span>
                                                    {badge.text(doc.processing_status)}
                                                </span>
                                            </td>
                                            <td className="px-8 py-8 text-right">
                                                <button
                                                    type="button"
                                                    className="text-on-surface-variant hover:text-primary transition-colors"
                                                    title="More actions"
                                                >
                                                    <span className="material-symbols-outlined">more_vert</span>
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Featured Resource Bento */}
            <section className="mt-stack-lg grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-2 relative h-64 rounded-xl overflow-hidden border border-outline-variant bg-primary-container flex flex-col justify-end p-8">
                    <span className="text-on-primary opacity-70 font-label-md text-label-md uppercase mb-2">
                        Legal Guide
                    </span>
                    <h3 className="text-on-primary font-headline-md text-headline-md leading-tight">
                        How to Review Your Financial Disclosure Documents
                    </h3>
                </div>
                <div className="bg-surface-container-high p-8 rounded-xl flex flex-col justify-center border border-outline-variant">
                    <div className="w-12 h-12 bg-primary text-on-primary rounded-lg flex items-center justify-center mb-4">
                        <span className="material-symbols-outlined">security</span>
                    </div>
                    <h3 className="font-headline-md text-headline-md text-primary mb-2">Encrypted Storage</h3>
                    <p className="font-body-md text-on-surface-variant">
                        All documents are secured with enterprise-grade AES-256 encryption and multi-factor
                        authentication.
                    </p>
                    <a className="mt-4 font-label-md text-label-md text-primary underline" href="#">
                        Security Policy
                    </a>
                </div>
            </section>
        </main>
    );
}
