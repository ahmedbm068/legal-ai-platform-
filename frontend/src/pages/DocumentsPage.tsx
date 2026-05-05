import { useEffect, useMemo, useRef, useState, useCallback, type ChangeEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useRoutedWorkspace } from "../context/RoutedWorkspaceContext";
import { workspaceApi } from "../workspaceApi";

type QueueItem = {
    id: string;
    sourceId: number;
    fileType: "pdf" | "voice" | "image";
    filename: string;
    createdAt: string;
    status: string;
    attention: string;
    generatedDocumentId?: number | null;
};

type PreviewFile = {
    id: string;
    title: string;
    url: string;
    kind: "pdf" | "image" | "audio" | "other";
};

type PreviewState = {
    title: string;
    files: PreviewFile[];
    activeIndex: number;
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

function statusTone(status: string) {
    const normalized = status.toLowerCase();
    if (normalized === "processed" || normalized === "completed") return "ready";
    if (normalized === "queued" || normalized === "processing" || normalized === "transcribing") return "pending";
    return "warning";
}

function fileTypeLabel(type: QueueItem["fileType"], t: ReturnType<typeof useRoutedWorkspace>["t"]) {
    if (type === "pdf") return t("fileTypePdf", "PDF");
    if (type === "voice") return t("fileTypeVoice", "VOICE");
    return t("fileTypeImage", "IMAGE");
}

function previewKind(blob: Blob, filename: string): PreviewFile["kind"] {
    const mimeType = blob.type.toLowerCase();
    const loweredName = filename.toLowerCase();
    if (mimeType.includes("pdf") || loweredName.endsWith(".pdf")) return "pdf";
    if (mimeType.startsWith("image/")) return "image";
    if (mimeType.startsWith("audio/")) return "audio";
    return "other";
}

function OpenIcon() {
    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="M11 4h5v5" />
            <path d="m9 11 7-7" />
            <path d="M15 11v4.5H4.5V5H9" />
        </svg>
    );
}

function GenerateIcon() {
    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="M10 2.5 11.4 7l4.1 1.4-4.1 1.4L10 14.3 8.6 9.8 4.5 8.4 8.6 7 10 2.5Z" />
            <path d="M15.3 12.2 16 14l1.7.7-1.7.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8Z" />
        </svg>
    );
}

function ArchiveIcon() {
    return (
        <svg aria-hidden="true" viewBox="0 0 20 20">
            <path d="M4 6.5h12" />
            <path d="M6 6.5v9h8v-9" />
            <path d="M8 6.5V4h4v2.5" />
            <path d="M8.2 10h3.6" />
        </svg>
    );
}

export default function DocumentsPage() {
    const params = useParams();
    const navigate = useNavigate();
    const routeCaseId = useMemo(() => parseCaseId(params.caseId), [params.caseId]);

    const {
        token,
        selectedCaseId,
        setSelectedCaseId,
        selectedCase,
        documents,
        recordings,
        imageBatches,
        caseContextLoading,
        caseContextError,
        workspaceError,
        uploadPdf,
        uploadAudio,
        uploadImageBatch,
        loadCaseContext,
        uploadingPdf,
        uploadingAudio,
        uploadingImages,
        locale,
        t,
    } = useRoutedWorkspace();

    const pdfInputRef = useRef<HTMLInputElement | null>(null);
    const audioInputRef = useRef<HTMLInputElement | null>(null);
    const imageInputRef = useRef<HTMLInputElement | null>(null);

    const [queueQuery, setQueueQuery] = useState("");
    const [queueStatusFilter, setQueueStatusFilter] = useState<"all" | "ready" | "pending" | "warning">("all");
    const [openingItemId, setOpeningItemId] = useState<string | null>(null);
    const [archivingItemId, setArchivingItemId] = useState<string | null>(null);
    const [openError, setOpenError] = useState<string | null>(null);
    const [preview, setPreview] = useState<PreviewState | null>(null);
    const [recording, setRecording] = useState(false);
    const [recordingError, setRecordingError] = useState<string | null>(null);
    const [showArchive, setShowArchive] = useState(false);
    const [archivedItems, setArchivedItems] = useState<QueueItem[]>([]);
    const [archivedLoading, setArchivedLoading] = useState(false);
    const [archivedError, setArchivedError] = useState<string | null>(null);
    const [restoringItemId, setRestoringItemId] = useState<string | null>(null);
    const previewRef = useRef<PreviewState | null>(null);
    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const mediaStreamRef = useRef<MediaStream | null>(null);
    const recordingChunksRef = useRef<BlobPart[]>([]);

    const activeCaseId = routeCaseId ?? selectedCaseId;

    const loadArchivedItems = useCallback(async () => {
        if (!token || !activeCaseId) return;
        setArchivedLoading(true);
        setArchivedError(null);
        try {
            const [docs, voices, batches] = await Promise.all([
                workspaceApi.listArchivedCaseDocuments(token, activeCaseId),
                workspaceApi.listArchivedCaseVoiceRecordings(token, activeCaseId),
                workspaceApi.listArchivedCaseImageBatches(token, activeCaseId),
            ]);
            const docRows: QueueItem[] = docs.map((d) => ({
                id: `doc-${d.id}`,
                sourceId: d.id,
                fileType: "pdf" as const,
                filename: d.filename,
                createdAt: d.upload_timestamp,
                status: d.processing_status ?? "archived",
                attention: t("archivedFile", "Archived"),
            }));
            const voiceRows: QueueItem[] = voices.map((v) => ({
                id: `voice-${v.id}`,
                sourceId: v.id,
                fileType: "voice" as const,
                filename: v.filename,
                createdAt: v.created_at,
                status: v.transcription_status ?? "archived",
                attention: t("archivedFile", "Archived"),
            }));
            const batchRows: QueueItem[] = batches.map((b) => ({
                id: `batch-${b.id}`,
                sourceId: b.id,
                fileType: "image" as const,
                filename: b.title ?? `Batch #${b.id}`,
                createdAt: b.created_at,
                status: b.status ?? "archived",
                attention: t("archivedFile", "Archived"),
                generatedDocumentId: b.generated_document_id ?? null,
            }));
            setArchivedItems([...docRows, ...voiceRows, ...batchRows].sort(
                (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
            ));
        } catch (err) {
            setArchivedError(err instanceof Error ? err.message : t("archiveLoadFailed", "Failed to load archived files."));
        } finally {
            setArchivedLoading(false);
        }
    }, [token, activeCaseId, t]);

    const toggleArchive = useCallback(() => {
        setShowArchive((prev) => {
            if (!prev) void loadArchivedItems();
            return !prev;
        });
    }, [loadArchivedItems]);

    const restoreItem = useCallback(async (item: QueueItem) => {
        if (!token) return;
        setRestoringItemId(item.id);
        try {
            if (item.fileType === "pdf") {
                await workspaceApi.unarchiveDocument(token, item.sourceId);
            } else if (item.fileType === "voice") {
                await workspaceApi.unarchiveVoiceRecording(token, item.sourceId);
            } else {
                await workspaceApi.unarchiveImageBatch(token, item.sourceId);
            }
            setArchivedItems((prev) => prev.filter((i) => i.id !== item.id));
        } catch {
            setArchivedError(t("restoreFailed", "Unable to restore item. Please try again."));
        } finally {
            setRestoringItemId(null);
        }
    }, [token]);

    useEffect(() => {
        if (routeCaseId && routeCaseId !== selectedCaseId) {
            setSelectedCaseId(routeCaseId);
        }
    }, [routeCaseId, selectedCaseId, setSelectedCaseId]);

    useEffect(() => {
        previewRef.current = preview;
    }, [preview]);

    useEffect(() => () => {
        previewRef.current?.files.forEach((file) => URL.revokeObjectURL(file.url));
        mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    }, []);

    const queueItems = useMemo<QueueItem[]>(() => {
        if (!activeCaseId) return [];

        const documentRows = documents.map((item) => ({
            id: `doc-${item.id}`,
            sourceId: item.id,
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
            sourceId: item.id,
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
            sourceId: item.id,
            fileType: "image" as const,
            filename: item.title,
            createdAt: item.created_at,
            generatedDocumentId: item.generated_document_id,
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

    const queueStats = useMemo(() => {
        const ready = queueItems.filter((item) => statusTone(item.status) === "ready").length;
        const pending = queueItems.filter((item) => statusTone(item.status) === "pending").length;
        const warning = queueItems.filter((item) => statusTone(item.status) === "warning").length;
        return {
            total: queueItems.length,
            ready,
            pending,
            warning,
            sources: new Set(queueItems.map((item) => item.fileType)).size,
        };
    }, [queueItems]);

    const visibleQueueItems = useMemo(() => {
        const query = queueQuery.trim().toLowerCase();
        return queueItems.filter((item) => {
            const tone = statusTone(item.status);
            const matchesStatus = queueStatusFilter === "all" || tone === queueStatusFilter;
            const matchesQuery = !query || [
                item.id,
                item.filename,
                item.fileType,
                item.status,
                item.attention,
            ].join(" ").toLowerCase().includes(query);
            return matchesStatus && matchesQuery;
        });
    }, [queueItems, queueQuery, queueStatusFilter]);

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

    function makePreviewFile(blob: Blob, filename: string, id = filename): PreviewFile {
        return {
            id,
            title: filename,
            url: URL.createObjectURL(blob),
            kind: previewKind(blob, filename),
        };
    }

    function showPreview(title: string, files: PreviewFile[]) {
        setPreview((current) => {
            current?.files.forEach((file) => URL.revokeObjectURL(file.url));
            return {
                title,
                files,
                activeIndex: 0,
            };
        });
    }

    function closePreview() {
        setPreview((current) => {
            current?.files.forEach((file) => URL.revokeObjectURL(file.url));
            return null;
        });
    }

    async function openQueueItem(item: QueueItem) {
        if (!token) return;
        setOpeningItemId(item.id);
        setOpenError(null);
        try {
            if (item.fileType === "pdf") {
                const blob = await workspaceApi.getDocumentFile(token, item.sourceId);
                showPreview(item.filename, [makePreviewFile(blob, item.filename, item.id)]);
                return;
            }

            if (item.fileType === "voice") {
                const blob = await workspaceApi.getVoiceRecordingFile(token, item.sourceId);
                showPreview(item.filename, [makePreviewFile(blob, item.filename, item.id)]);
                return;
            }

            const batch = await workspaceApi.getImageBatch(token, item.sourceId);
            if (batch.assets.length) {
                const assetBlobs = await Promise.all(
                    batch.assets.map(async (asset) => ({
                        asset,
                        blob: await workspaceApi.getImageAssetFile(token, asset.id),
                    }))
                );
                showPreview(
                    item.filename,
                    assetBlobs.map(({ asset, blob }) => makePreviewFile(blob, asset.filename, `asset-${asset.id}`))
                );
                return;
            }

            if (item.generatedDocumentId) {
                const blob = await workspaceApi.getDocumentFile(token, item.generatedDocumentId);
                showPreview(item.filename, [makePreviewFile(blob, item.filename, `generated-${item.generatedDocumentId}`)]);
                return;
            }

            setOpenError(t("noFilesAvailable", "No source files are available for this item yet."));
        } catch (caught) {
            setOpenError(caught instanceof Error ? caught.message : t("unableOpenFile", "Unable to open file."));
        } finally {
            setOpeningItemId(null);
        }
    }

    async function openGeneratedDocument(item: QueueItem) {
        if (!token || !item.generatedDocumentId) return;
        setOpeningItemId(`${item.id}-generated`);
        setOpenError(null);
        try {
            const blob = await workspaceApi.getDocumentFile(token, item.generatedDocumentId);
            showPreview(
                `${item.filename} - generated document`,
                [makePreviewFile(blob, `${item.filename}-generated-document`, `generated-${item.generatedDocumentId}`)]
            );
        } catch (caught) {
            setOpenError(caught instanceof Error ? caught.message : t("unableOpenFile", "Unable to open file."));
        } finally {
            setOpeningItemId(null);
        }
    }

    async function archiveQueueItem(item: QueueItem) {
        if (!token || !activeCaseId) return;
        const confirmed = window.confirm(t("archiveQueueItemConfirm", "Move this file to the archive? It will disappear from this case queue but the stored file will not be permanently deleted."));
        if (!confirmed) return;

        setArchivingItemId(item.id);
        setOpenError(null);
        try {
            if (item.fileType === "pdf") {
                await workspaceApi.archiveDocument(token, item.sourceId);
            } else if (item.fileType === "voice") {
                await workspaceApi.archiveVoiceRecording(token, item.sourceId);
            } else {
                await workspaceApi.archiveImageBatch(token, item.sourceId);
            }
            await loadCaseContext(activeCaseId);
        } catch (caught) {
            setOpenError(caught instanceof Error ? caught.message : t("archiveFailed", "Unable to move item to archive."));
        } finally {
            setArchivingItemId(null);
        }
    }

    async function startRecording() {
        if (!activeCaseId) return;
        if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
            setRecordingError(t("recordingUnsupported", "Audio recording is not supported in this browser."));
            return;
        }

        setRecordingError(null);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream);
            recordingChunksRef.current = [];
            mediaStreamRef.current = stream;
            mediaRecorderRef.current = recorder;

            recorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    recordingChunksRef.current.push(event.data);
                }
            };
            recorder.onstop = () => {
                const mimeType = recorder.mimeType || "audio/webm";
                const blob = new Blob(recordingChunksRef.current, { type: mimeType });
                const extension = mimeType.includes("mpeg") ? "mp3" : mimeType.includes("wav") ? "wav" : "webm";
                const file = new File([blob], `recorded-voice-${Date.now()}.${extension}`, { type: mimeType });
                stream.getTracks().forEach((track) => track.stop());
                mediaStreamRef.current = null;
                mediaRecorderRef.current = null;
                recordingChunksRef.current = [];
                setRecording(false);
                void uploadAudio(activeCaseId, file).catch((caught) => {
                    setRecordingError(caught instanceof Error ? caught.message : t("uploadRecordingFailed", "Unable to upload recording."));
                });
            };

            recorder.start();
            setRecording(true);
        } catch (caught) {
            setRecordingError(caught instanceof Error ? caught.message : t("microphoneUnavailable", "Unable to access microphone."));
        }
    }

    function stopRecording() {
        const recorder = mediaRecorderRef.current;
        if (recorder && recorder.state !== "inactive") {
            recorder.stop();
            return;
        }
        mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        setRecording(false);
    }

    const activePreviewFile = preview?.files[preview.activeIndex] || null;

    return (
        <section className="shell-page documents-page">
            <header className="shell-page-header documents-hero">
                <div>
                    <p className="shell-page-kicker">{t("documentsKicker", "Documents")}</p>
                    <h2>{t("documentsTitle", "Dedicated upload and review queue")}</h2>
                    <p>{t("documentsSubtitle", "Processing status and what-needs-attention are visible in one place.")}</p>
                </div>
                {activeCaseId ? (
                    <div className="documents-hero-side">
                        <div className="documents-hero-stats" aria-label={t("queueSummary", "Queue summary")}>
                            <span><strong>{queueStats.total}</strong>{t("queueItems", "items")}</span>
                            <span><strong>{queueStats.ready}</strong>{t("ready", "ready")}</span>
                            <span><strong>{queueStats.pending}</strong>{t("pending", "pending")}</span>
                        </div>
                        <button className="documents-change-case-button" onClick={() => navigate("/cases")} type="button">
                            {t("chooseAnotherCase", "Choose another case")}
                        </button>
                    </div>
                ) : null}
            </header>

            {!activeCaseId ? (
                <article className="shell-card documents-empty-hero">
                    <div>
                        <p className="shell-page-kicker">{t("caseRequired", "Case required")}</p>
                        <h3>{t("noCaseSelectedSummary", "No case selected")}</h3>
                        <p>
                            {t("documentsSelectCaseOnly", "The document queue only shows files for the selected case. Choose a case to review its evidence and uploads.")}
                        </p>
                    </div>
                    <button className="shell-action-link" onClick={() => navigate("/cases")} type="button">
                        {t("chooseCase", "Choose case")}
                    </button>
                </article>
            ) : (
                <>
                    {openError ? <p className="shell-error-text">{openError}</p> : null}
                    {workspaceError ? <p className="shell-error-text">{workspaceError}</p> : null}
                    {caseContextError ? <p className="shell-error-text">{caseContextError}</p> : null}

                    <article className="shell-card documents-upload-console">
                        <div className="documents-upload-head">
                            <div>
                                <p className="shell-page-kicker">{t("activeMatter", "Active matter")}</p>
                                <h3>{selectedCase?.title || `${t("caseLabel", "Case")} #${activeCaseId}`}</h3>
                                <p>{t("uploadActionsHint", "Add evidence to the matter, then track processing and review readiness below.")}</p>
                            </div>
                            <span className="documents-case-chip">{t("caseLabel", "Case")} #{activeCaseId}</span>
                        </div>
                        <div className="documents-upload-grid">
                            <button
                                className="documents-upload-button pdf"
                                disabled={uploadingPdf || caseContextLoading}
                                onClick={() => pdfInputRef.current?.click()}
                                type="button"
                            >
                                <span aria-hidden="true">PDF</span>
                                <strong>{uploadingPdf ? t("uploadingPdf", "Uploading PDF...") : t("uploadPdf", "Upload PDF")}</strong>
                                <small>{t("uploadPdfHint", "Contracts, letters, judgments, exhibits")}</small>
                            </button>
                            <div className="documents-upload-button voice documents-voice-card">
                                <span aria-hidden="true">REC</span>
                                <strong>{uploadingAudio ? t("uploadingVoice", "Uploading voice...") : t("voiceEvidence", "Voice evidence")}</strong>
                                <small>{t("uploadVoiceHint", "Calls, intakes, consultations")}</small>
                                <div className="documents-voice-actions">
                                    <button
                                        disabled={uploadingAudio || caseContextLoading}
                                        onClick={() => recording ? stopRecording() : void startRecording()}
                                        type="button"
                                    >
                                        {recording ? t("stopRecording", "Stop recording") : t("recordAudio", "Record audio")}
                                    </button>
                                    <button
                                        disabled={uploadingAudio || caseContextLoading || recording}
                                        onClick={() => audioInputRef.current?.click()}
                                        type="button"
                                    >
                                        {t("uploadFromPc", "Upload from PC")}
                                    </button>
                                </div>
                                {recordingError ? <small className="documents-recording-error">{recordingError}</small> : null}
                            </div>
                            <button
                                className="documents-upload-button image"
                                disabled={uploadingImages || caseContextLoading}
                                onClick={() => imageInputRef.current?.click()}
                                type="button"
                            >
                                <span aria-hidden="true">IMG</span>
                                <strong>{uploadingImages ? t("uploadingBatch", "Uploading batch...") : t("uploadScannedBatch", "Upload scanned batch")}</strong>
                                <small>{t("uploadImageHint", "Scans, photos, mixed evidence packets")}</small>
                            </button>
                        </div>
                    </article>

                    <div className="documents-summary-grid compact">
                        <article className="documents-stat-card">
                            <span>{t("queueItems", "Items")}</span>
                            <strong>{queueStats.total}</strong>
                        </article>
                        <article className="documents-stat-card ready">
                            <span>{t("readyForReview", "Ready")}</span>
                            <strong>{queueStats.ready}</strong>
                        </article>
                        <article className="documents-stat-card attention">
                            <span>{t("pending", "Pending")}</span>
                            <strong>{queueStats.pending}</strong>
                        </article>
                        <article className="documents-stat-card warning">
                            <span>{t("needsAttention", "Needs attention")}</span>
                            <strong>{queueStats.warning}</strong>
                        </article>
                    </div>

                    <article className="shell-card documents-queue-card">
                        <div className="documents-queue-head">
                            <div>
                                <p className="shell-page-kicker">{t("reviewQueue", "Review queue")}</p>
                                <h3>{t("evidenceProcessingQueue", "Evidence processing queue")}</h3>
                            </div>
                            <div className="documents-queue-tools">
                                <input
                                    aria-label={t("searchQueue", "Search queue")}
                                    onChange={(event) => setQueueQuery(event.target.value)}
                                    placeholder={t("searchQueuePlaceholder", "Search file, status, issue...")}
                                    type="search"
                                    value={queueQuery}
                                />
                                <select
                                    aria-label={t("filterByStatus", "Filter by status")}
                                    onChange={(event) => setQueueStatusFilter(event.target.value as typeof queueStatusFilter)}
                                    value={queueStatusFilter}
                                >
                                    <option value="all">{t("allStatuses", "All statuses")}</option>
                                    <option value="ready">{t("ready", "Ready")}</option>
                                    <option value="pending">{t("pending", "Pending")}</option>
                                    <option value="warning">{t("needsAttention", "Needs attention")}</option>
                                </select>
                                <button
                                    className={`documents-archive-toggle-btn${showArchive ? " active" : ""}`}
                                    onClick={toggleArchive}
                                    title={showArchive ? t("hideArchive", "Hide archive") : t("viewArchive", "View archived files")}
                                    type="button"
                                >
                                    <ArchiveIcon />
                                    {showArchive ? t("hideArchive", "Hide archive") : t("viewArchive", "Archive")}
                                </button>
                            </div>
                        </div>
                        {caseContextLoading ? <p>{t("refreshingCaseQueue", "Refreshing case queue...")}</p> : null}
                        <table className="shell-table documents-queue-table">
                            <thead>
                                <tr>
                                    <th>{t("tableFile", "File")}</th>
                                    <th>{t("tableType", "Type")}</th>
                                    <th>{t("status", "Status")}</th>
                                    <th>{t("needsAttention", "Needs attention")}</th>
                                    <th>{t("updated", "Updated")}</th>
                                    <th>{t("actions", "Actions")}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {visibleQueueItems.length ? visibleQueueItems.map((item) => (
                                    <tr className={`documents-queue-row ${statusTone(item.status)}`} key={item.id}>
                                        <td>
                                            <span className={`documents-file-icon ${item.fileType}`}>{fileTypeLabel(item.fileType, t).slice(0, 3)}</span>
                                            <span className="documents-file-main">
                                                <strong>{item.filename}</strong>
                                                <small>{item.id}</small>
                                            </span>
                                        </td>
                                        <td>
                                            <span className="documents-type-pill">{fileTypeLabel(item.fileType, t)}</span>
                                        </td>
                                        <td>
                                            <span className={statusClassName(item.status)}>{item.status}</span>
                                        </td>
                                        <td><span className="documents-attention-text">{item.attention}</span></td>
                                        <td><span className="documents-date">{formatDate(item.createdAt, locale)}</span></td>
                                        <td>
                                            <div className="documents-row-actions">
                                                <button
                                                    aria-label={t("openFile", "Open")}
                                                    className="documents-icon-button"
                                                    disabled={openingItemId === item.id}
                                                    onClick={() => void openQueueItem(item)}
                                                    title={t("openFile", "Open")}
                                                    type="button"
                                                >
                                                    <OpenIcon />
                                                </button>
                                                <button
                                                    aria-label={t("openGeneratedDocument", "Generated document")}
                                                    className="documents-icon-button"
                                                    disabled={!item.generatedDocumentId || openingItemId === `${item.id}-generated`}
                                                    onClick={() => void openGeneratedDocument(item)}
                                                    title={item.generatedDocumentId ? t("openGeneratedDocument", "Generated document") : t("noGeneratedDocument", "No generated document")}
                                                    type="button"
                                                >
                                                    <GenerateIcon />
                                                </button>
                                                <button
                                                    aria-label={t("archiveFile", "Move to archive")}
                                                    className="documents-icon-button danger"
                                                    disabled={archivingItemId === item.id}
                                                    onClick={() => void archiveQueueItem(item)}
                                                    title={t("archiveFile", "Move to archive")}
                                                    type="button"
                                                >
                                                    <ArchiveIcon />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                )) : (
                                    <tr>
                                        <td colSpan={6}>{queueItems.length ? t("noQueueMatches", "No queue items match the current filters.") : t("noUploadItemsForCase", "No upload items found for this case.")}</td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </article>
                    {showArchive ? (
                        <article className="shell-card documents-archive-card">
                            <div className="documents-queue-head">
                                <div>
                                    <p className="shell-page-kicker">{t("archive", "Archive")}</p>
                                    <h3>{t("archivedFiles", "Archived files")}</h3>
                                </div>
                                {archivedLoading ? null : (
                                    <button className="documents-archive-refresh-btn" onClick={() => void loadArchivedItems()} type="button">
                                        {t("refresh", "Refresh")}
                                    </button>
                                )}
                            </div>
                            {archivedLoading ? (
                                <p className="documents-archive-loading">{t("loadingArchive", "Loading archived files...")}</p>
                            ) : archivedError ? (
                                <p className="documents-archive-error">{archivedError}</p>
                            ) : (
                                <table className="shell-table documents-queue-table">
                                    <thead>
                                        <tr>
                                            <th>{t("tableFile", "File")}</th>
                                            <th>{t("tableType", "Type")}</th>
                                            <th>{t("status", "Status")}</th>
                                            <th>{t("updated", "Updated")}</th>
                                            <th>{t("actions", "Actions")}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {archivedItems.length ? archivedItems.map((item) => (
                                            <tr className="documents-queue-row archived" key={item.id}>
                                                <td>
                                                    <span className={`documents-file-icon ${item.fileType}`}>{fileTypeLabel(item.fileType, t).slice(0, 3)}</span>
                                                    <span className="documents-file-main">
                                                        <strong>{item.filename}</strong>
                                                        <small>{item.id}</small>
                                                    </span>
                                                </td>
                                                <td><span className="documents-type-pill">{fileTypeLabel(item.fileType, t)}</span></td>
                                                <td><span className="shell-status warning">{t("archived", "archived")}</span></td>
                                                <td><span className="documents-date">{formatDate(item.createdAt, locale)}</span></td>
                                                <td>
                                                    <div className="documents-row-actions">
                                                        <button
                                                            aria-label={t("openFile", "Open")}
                                                            className="documents-icon-button"
                                                            disabled={openingItemId === item.id}
                                                            onClick={() => void openQueueItem(item)}
                                                            title={t("openFile", "Open")}
                                                            type="button"
                                                        >
                                                            <OpenIcon />
                                                        </button>
                                                        <button
                                                            aria-label={t("restoreFile", "Restore")}
                                                            className="documents-restore-btn"
                                                            disabled={restoringItemId === item.id}
                                                            onClick={() => void restoreItem(item)}
                                                            title={t("restoreFileTitle", "Restore to active documents")}
                                                            type="button"
                                                        >
                                                            {restoringItemId === item.id
                                                                ? t("restoring", "Restoring…")
                                                                : t("restoreFile", "Restore")}
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        )) : (
                                            <tr>
                                                <td colSpan={5}>{t("noArchivedFiles", "No archived files found for this case.")}</td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            )}
                        </article>
                    ) : null}                </>
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
            {preview && activePreviewFile ? (
                <div
                    className="documents-preview-backdrop"
                    role="dialog"
                    aria-modal="true"
                    aria-label={preview.title}
                    onClick={closePreview}
                    onKeyDown={(e) => e.key === "Escape" && closePreview()}
                    tabIndex={-1}
                >
                    <div className="documents-preview-card" onClick={(e) => e.stopPropagation()}>
                        <header className="documents-preview-header">
                            <div className="documents-preview-header-left">
                                <span className="documents-preview-kind-badge">
                                    {activePreviewFile.kind === "image" ? "IMAGE" : activePreviewFile.kind === "audio" ? "AUDIO" : "PDF"}
                                </span>
                                <h3 className="documents-preview-title" title={preview.title}>{preview.title}</h3>
                            </div>
                            <div className="documents-preview-header-actions">
                                <a
                                    aria-label={t("openInNewTab", "Open in new tab")}
                                    className="documents-preview-action-btn"
                                    href={activePreviewFile.url}
                                    rel="noopener noreferrer"
                                    target="_blank"
                                    title={t("openInNewTab", "Open in new tab")}
                                >
                                    <svg aria-hidden="true" fill="none" height="16" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="16"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" x2="21" y1="14" y2="3" /></svg>
                                </a>
                                <button
                                    aria-label={t("close", "Close")}
                                    className="documents-preview-close-btn"
                                    onClick={closePreview}
                                    title={t("close", "Close")}
                                    type="button"
                                >
                                    <svg aria-hidden="true" fill="none" height="18" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" viewBox="0 0 24 24" width="18"><line x1="18" x2="6" y1="6" y2="18" /><line x1="6" x2="18" y1="6" y2="18" /></svg>
                                </button>
                            </div>
                        </header>
                        {preview.files.length > 1 ? (
                            <div className="documents-preview-tabs" role="tablist" aria-label={t("previewFiles", "Preview files")}>
                                {preview.files.map((file, index) => (
                                    <button
                                        className={index === preview.activeIndex ? "active" : ""}
                                        key={file.id}
                                        onClick={() => setPreview((current) => current ? { ...current, activeIndex: index } : current)}
                                        role="tab"
                                        type="button"
                                    >
                                        {index + 1}. {file.title}
                                    </button>
                                ))}
                            </div>
                        ) : null}
                        <div className="documents-preview-frame">
                            {activePreviewFile.kind === "image" ? (
                                <img alt={activePreviewFile.title} src={activePreviewFile.url} />
                            ) : activePreviewFile.kind === "audio" ? (
                                <div className="documents-preview-audio">
                                    <svg aria-hidden="true" className="documents-preview-audio-icon" fill="none" height="40" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" viewBox="0 0 24 24" width="40"><path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" /></svg>
                                    <strong>{activePreviewFile.title}</strong>
                                    <audio controls src={activePreviewFile.url} />
                                </div>
                            ) : (
                                <iframe src={`${activePreviewFile.url}#toolbar=0&navpanes=0&scrollbar=1&view=FitH`} title={activePreviewFile.title} />
                            )}
                        </div>
                    </div>
                </div>
            ) : null}
        </section>
    );
}
