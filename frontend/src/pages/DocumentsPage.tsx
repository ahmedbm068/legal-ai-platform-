import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";

type QueueItem = {
    id: string;
    fileType: "pdf" | "voice" | "image";
    filename: string;
    createdAt: string;
    status: string;
    attention: string;
};

type GlobalSummaryState = {
    caseCount: number;
    totalDocuments: number;
    pendingDocuments: number;
    pendingRecordings: number;
    pendingImageBatches: number;
};

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

function documentAttention(status: string, readyLabel: string, pendingLabel: string, processingError?: string | null) {
    if (processingError?.trim()) {
        return processingError;
    }
    if (status === "completed") {
        return readyLabel;
    }
    return pendingLabel;
}

function recordingAttention(status: string, readyLabel: string, pendingLabel: string, error?: string | null) {
    if (error?.trim()) {
        return error;
    }
    if (status === "completed") {
        return readyLabel;
    }
    return pendingLabel;
}

function batchAttention(
    status: string,
    completedWithDocPrefix: string,
    completedLabel: string,
    pendingLabel: string,
    generatedDocumentId?: number | null,
    processingError?: string | null
) {
    if (processingError?.trim()) {
        return processingError;
    }
    if (status === "completed" && generatedDocumentId) {
        return `${completedWithDocPrefix} #${generatedDocumentId}.`;
    }
    if (status === "completed") {
        return completedLabel;
    }
    return pendingLabel;
}

function statusClassName(status: string) {
    const normalized = status.toLowerCase();
    if (normalized === "processed") return "shell-status ok";
    if (normalized === "completed") return "shell-status ok";
    if (normalized === "queued") return "shell-status pending";
    if (normalized === "processing") return "shell-status pending";
    if (normalized === "transcribing") return "shell-status pending";
    return "shell-status warning";
}

export default function DocumentsPage() {
    const params = useParams();
    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);

    const {
        selectedCaseId,
        setSelectedCaseId,
        selectedCase,
        cases,
        documents,
        recordings,
        imageBatches,
        caseContextLoading,
        caseContextError,
        workspaceError,
        uploadPdf,
        uploadAudio,
        uploadImageBatch,
        uploadingPdf,
        uploadingAudio,
        uploadingImages,
        loadGlobalDocumentsSummary,
        locale,
        t,
    } = useRoutedWorkspace();

    const pdfInputRef = useRef<HTMLInputElement | null>(null);
    const audioInputRef = useRef<HTMLInputElement | null>(null);
    const imageInputRef = useRef<HTMLInputElement | null>(null);

    const [globalSummary, setGlobalSummary] = useState<GlobalSummaryState | null>(null);
    const [summaryLoading, setSummaryLoading] = useState(false);
    const [summaryError, setSummaryError] = useState<string | null>(null);

    const activeCaseId = routeCaseId ?? selectedCaseId;

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

        setSummaryLoading(true);
        setSummaryError(null);
        void loadGlobalDocumentsSummary()
            .then((summary) => {
                if (!cancelled) {
                    setGlobalSummary(summary);
                }
            })
            .catch((caught) => {
                if (!cancelled) {
                    const message = caught instanceof Error ? caught.message : t("documentSummaryFailed", "Unable to load document summary.");
                    setSummaryError(message);
                }
            })
            .finally(() => {
                if (!cancelled) {
                    setSummaryLoading(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, [activeCaseId, loadGlobalDocumentsSummary, t]);

    const queueItems = useMemo<QueueItem[]>(() => {
        if (!activeCaseId) return [];

        const documentRows = documents.map((item) => ({
            id: `doc-${item.id}`,
            fileType: "pdf" as const,
            filename: item.filename,
            createdAt: item.upload_timestamp,
            status: item.processing_status,
            attention: documentAttention(
                item.processing_status,
                t("readyForDrafting", "Ready for drafting and legal extraction."),
                t("stillProcessing", "Still processing. Keep this item in the review queue."),
                item.processing_error
            ),
        }));

        const recordingRows = recordings.map((item) => ({
            id: `voice-${item.id}`,
            fileType: "voice" as const,
            filename: item.filename,
            createdAt: item.created_at,
            status: item.transcription_status,
            attention: recordingAttention(
                item.transcription_status,
                t("transcriptReady", "Transcript is ready for case reasoning."),
                t("transcriptionPending", "Transcription is pending before legal summary is reliable."),
                item.transcription_error
            ),
        }));

        const imageRows = imageBatches.map((item) => ({
            id: `image-${item.id}`,
            fileType: "image" as const,
            filename: item.title,
            createdAt: item.created_at,
            status: item.status,
            attention: batchAttention(
                item.status,
                t("completedWithGeneratedDoc", "Completed with generated document"),
                t("completedValidateExtraction", "Completed. Validate extraction quality and evidence review signals."),
                t("imageBatchProcessing", "Image batch processing is still running."),
                item.generated_document_id,
                item.processing_error
            ),
        }));

        return [...documentRows, ...recordingRows, ...imageRows].sort((left, right) =>
            right.createdAt.localeCompare(left.createdAt)
        );
    }, [activeCaseId, documents, imageBatches, recordings, t]);

    async function onPdfSelected(event: ChangeEvent<HTMLInputElement>) {
        if (!activeCaseId) return;
        const file = event.target.files?.[0];
        if (!file) return;
        await uploadPdf(activeCaseId, file);
        event.target.value = "";
    }

    async function onAudioSelected(event: ChangeEvent<HTMLInputElement>) {
        if (!activeCaseId) return;
        const file = event.target.files?.[0];
        if (!file) return;
        await uploadAudio(activeCaseId, file);
        event.target.value = "";
    }

    async function onImagesSelected(event: ChangeEvent<HTMLInputElement>) {
        if (!activeCaseId) return;
        const files = Array.from(event.target.files || []);
        if (!files.length) return;
        await uploadImageBatch(activeCaseId, files);
        event.target.value = "";
    }

    return (
        <section className="shell-page">
            <header className="shell-page-header">
                <p className="shell-page-kicker">{t("documentsKicker", "Documents")}</p>
                <h2>{t("documentsTitle", "Dedicated upload and review queue")}</h2>
                <p>{t("documentsSubtitle", "Processing status and what-needs-attention are visible in one place.")}</p>
            </header>

            {!activeCaseId ? (
                <>
                    <article className="shell-card">
                        <h3>{t("noCaseSelectedSummary", "No case selected")}</h3>
                        <p>
                            {t("documentsSummaryIntro", "This view shows dashboard-style document queue summaries across your workspace. Select a case in Cases to open full upload and review controls.")}
                            <Link className="shell-inline-link" to="/cases"> {t("navCasesLabel", "Cases")}</Link>
                        </p>
                    </article>

                    {summaryLoading ? <p>{t("loadingGlobalDocumentSummary", "Loading global document summary...")}</p> : null}
                    {summaryError ? <p className="shell-error-text">{summaryError}</p> : null}

                    {globalSummary ? (
                        <div className="shell-grid shell-grid-2">
                            <article className="shell-card">
                                <h3>{t("coverage", "Coverage")}</h3>
                                <p>{t("casesInWorkspace", "Cases in workspace")}: {globalSummary.caseCount || cases.length}</p>
                                <p>{t("totalDocuments", "Total documents")}: {globalSummary.totalDocuments}</p>
                            </article>
                            <article className="shell-card">
                                <h3>{t("pendingWork", "Pending work")}</h3>
                                <p>{t("pendingDocuments", "Pending documents")}: {globalSummary.pendingDocuments}</p>
                                <p>{t("pendingRecordings", "Pending recordings")}: {globalSummary.pendingRecordings}</p>
                                <p>{t("pendingImageBatches", "Pending image batches")}: {globalSummary.pendingImageBatches}</p>
                            </article>
                        </div>
                    ) : null}
                </>
            ) : (
                <>
                    {workspaceError ? <p className="shell-error-text">{workspaceError}</p> : null}
                    {caseContextError ? <p className="shell-error-text">{caseContextError}</p> : null}

                    <article className="shell-card">
                        <h3>{t("uploadActions", "Upload actions")}</h3>
                        <p>
                            {t("caseLabel", "Case")}: <strong>{selectedCase?.title || `#${activeCaseId}`}</strong>
                        </p>
                        <div className="shell-action-row">
                            <button
                                disabled={uploadingPdf || caseContextLoading}
                                onClick={() => pdfInputRef.current?.click()}
                                type="button"
                            >
                                {uploadingPdf ? t("uploadingPdf", "Uploading PDF...") : t("uploadPdf", "Upload PDF")}
                            </button>
                            <button
                                disabled={uploadingAudio || caseContextLoading}
                                onClick={() => audioInputRef.current?.click()}
                                type="button"
                            >
                                {uploadingAudio ? t("uploadingVoice", "Uploading voice...") : t("uploadVoiceFile", "Upload voice file")}
                            </button>
                            <button
                                disabled={uploadingImages || caseContextLoading}
                                onClick={() => imageInputRef.current?.click()}
                                type="button"
                            >
                                {uploadingImages ? t("uploadingBatch", "Uploading batch...") : t("uploadScannedBatch", "Upload scanned batch")}
                            </button>
                        </div>
                    </article>

                    <article className="shell-card">
                        <h3>{t("reviewQueue", "Review queue")}</h3>
                        {caseContextLoading ? <p>{t("refreshingCaseQueue", "Refreshing case queue...")}</p> : null}
                        <table className="shell-table">
                            <thead>
                                <tr>
                                    <th>{t("tableId", "ID")}</th>
                                    <th>{t("tableFile", "File")}</th>
                                    <th>{t("tableType", "Type")}</th>
                                    <th>{t("status", "Status")}</th>
                                    <th>{t("needsAttention", "Needs attention")}</th>
                                    <th>{t("updated", "Updated")}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {queueItems.length ? queueItems.map((item) => (
                                    <tr key={item.id}>
                                        <td>{item.id}</td>
                                        <td>{item.filename}</td>
                                        <td>
                                            {item.fileType === "pdf"
                                                ? t("fileTypePdf", "PDF")
                                                : item.fileType === "voice"
                                                    ? t("fileTypeVoice", "VOICE")
                                                    : t("fileTypeImage", "IMAGE")}
                                        </td>
                                        <td>
                                            <span className={statusClassName(item.status)}>{item.status}</span>
                                        </td>
                                        <td>{item.attention}</td>
                                        <td>{formatDate(item.createdAt, locale)}</td>
                                    </tr>
                                )) : (
                                    <tr>
                                        <td colSpan={6}>{t("noUploadItemsForCase", "No upload items found for this case.")}</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </article>
                </>
            )}

            <input
                accept=".pdf,application/pdf"
                onChange={onPdfSelected}
                ref={pdfInputRef}
                style={{ display: "none" }}
                type="file"
            />
            <input
                accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/mp3,audio/ogg,audio/m4a,audio/x-m4a"
                onChange={onAudioSelected}
                ref={audioInputRef}
                style={{ display: "none" }}
                type="file"
            />
            <input
                accept="image/*,.pdf,application/pdf"
                multiple
                onChange={onImagesSelected}
                ref={imageInputRef}
                style={{ display: "none" }}
                type="file"
            />
        </section>
    );
}
