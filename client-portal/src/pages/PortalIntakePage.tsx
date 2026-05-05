import { type FormEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { usePortal } from "../context/PortalContext";
import { formatDate, label, tone } from "../portalPresentation";
import { fetchIntakeStatus } from "../lib/api";
import type { PublicIntakeStatus } from "../types";

export default function PortalIntakePage() {
    const { dashboard, selectedCaseId, submitIntake, submitLoading, submitError, submitMessage, clearSubmitMessages, uploadCaseMaterials, uploadLoading } = usePortal();
    const navigate = useNavigate();

    // New consultation form
    const [issueSummary, setIssueSummary] = useState("");
    const [caseDescription, setCaseDescription] = useState("");
    const [preferredSchedule, setPreferredSchedule] = useState("");
    const [voiceFile, setVoiceFile] = useState<File | null>(null);
    const [supportingDoc, setSupportingDoc] = useState<File | null>(null);

    // Case upload form
    const [caseVoiceFile, setCaseVoiceFile] = useState<File | null>(null);
    const [caseDocFile, setCaseDocFile] = useState<File | null>(null);
    const [uploadCaseId, setUploadCaseId] = useState<number | null>(selectedCaseId);

    // Public status check (no auth)
    const [referenceInput, setReferenceInput] = useState("");
    const [statusLoading, setStatusLoading] = useState(false);
    const [statusResult, setStatusResult] = useState<PublicIntakeStatus | null>(null);
    const [statusError, setStatusError] = useState<string | null>(null);

    const intakeFormRef = useRef<HTMLFormElement | null>(null);
    const uploadFormRef = useRef<HTMLFormElement | null>(null);

    async function handleIntakeSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        clearSubmitMessages();
        const fd = new FormData();
        fd.append("issue_summary", issueSummary);
        fd.append("case_description", caseDescription);
        fd.append("preferred_schedule", preferredSchedule);
        if (voiceFile) fd.append("voice_note", voiceFile);
        if (supportingDoc) fd.append("supporting_document", supportingDoc);
        const ok = await submitIntake(fd);
        if (ok) {
            setIssueSummary("");
            setCaseDescription("");
            setPreferredSchedule("");
            setVoiceFile(null);
            setSupportingDoc(null);
            intakeFormRef.current?.reset();
            navigate("/dashboard");
        }
    }

    async function handleUploadSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!uploadCaseId) return;
        clearSubmitMessages();
        const fd = new FormData();
        if (caseVoiceFile) fd.append("voice_note", caseVoiceFile);
        if (caseDocFile) fd.append("supporting_document", caseDocFile);
        const ok = await uploadCaseMaterials(uploadCaseId, fd);
        if (ok) {
            setCaseVoiceFile(null);
            setCaseDocFile(null);
            uploadFormRef.current?.reset();
        }
    }

    async function handleStatusCheck(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!referenceInput.trim()) return;
        setStatusLoading(true);
        setStatusError(null);
        setStatusResult(null);
        try {
            const result = await fetchIntakeStatus(referenceInput.trim());
            setStatusResult(result);
        } catch (caught) {
            setStatusError(caught instanceof Error ? caught.message : "Unable to fetch status.");
        } finally {
            setStatusLoading(false);
        }
    }

    const cases = dashboard?.cases ?? [];

    return (
        <div className="view-panel">
            <div className="view-header">
                <h2>Intake Requests</h2>
                <p>Submit a new consultation, upload materials for an existing case, or check a request status.</p>
            </div>

            {submitError ? <p className="error-msg">{submitError}</p> : null}
            {submitMessage ? <p className="success-msg">{submitMessage}</p> : null}

            <div className="intake-grid">
                {/* New consultation */}
                <div className="card">
                    <h3>New consultation request</h3>
                    <form ref={intakeFormRef} onSubmit={(e) => void handleIntakeSubmit(e)}>
                        <label>
                            <span>Issue summary *</span>
                            <textarea
                                required
                                value={issueSummary}
                                onChange={(e) => setIssueSummary(e.target.value)}
                                rows={3}
                                placeholder="Briefly describe the legal issue you need help with…"
                            />
                        </label>
                        <label>
                            <span>Case description</span>
                            <textarea
                                value={caseDescription}
                                onChange={(e) => setCaseDescription(e.target.value)}
                                rows={3}
                                placeholder="Additional context or details…"
                            />
                        </label>
                        <label>
                            <span>Preferred schedule</span>
                            <input
                                type="text"
                                value={preferredSchedule}
                                onChange={(e) => setPreferredSchedule(e.target.value)}
                                placeholder="e.g. Weekday mornings"
                            />
                        </label>
                        <label>
                            <span>Voice note (optional)</span>
                            <input
                                type="file"
                                accept="audio/*"
                                onChange={(e) => setVoiceFile(e.target.files?.[0] ?? null)}
                            />
                        </label>
                        <label>
                            <span>Supporting document (optional)</span>
                            <input
                                type="file"
                                accept=".pdf,.doc,.docx,.txt"
                                onChange={(e) => setSupportingDoc(e.target.files?.[0] ?? null)}
                            />
                        </label>
                        <button className="btn primary" disabled={submitLoading || !issueSummary.trim()} type="submit">
                            {submitLoading ? "Submitting…" : "Submit request"}
                        </button>
                    </form>
                </div>

                {/* Upload to existing case */}
                {cases.length > 0 ? (
                    <div className="card">
                        <h3>Upload materials to a case</h3>
                        <form ref={uploadFormRef} onSubmit={(e) => void handleUploadSubmit(e)}>
                            <label>
                                <span>Target case</span>
                                <select
                                    value={uploadCaseId ?? ""}
                                    onChange={(e) => setUploadCaseId(Number(e.target.value))}
                                    required
                                >
                                    <option value="">Select a case…</option>
                                    {cases.map((c) => (
                                        <option key={c.id} value={c.id}>{c.title}</option>
                                    ))}
                                </select>
                            </label>
                            <label>
                                <span>Voice note (optional)</span>
                                <input
                                    type="file"
                                    accept="audio/*"
                                    onChange={(e) => setCaseVoiceFile(e.target.files?.[0] ?? null)}
                                />
                            </label>
                            <label>
                                <span>Document (optional)</span>
                                <input
                                    type="file"
                                    accept=".pdf,.doc,.docx,.txt"
                                    onChange={(e) => setCaseDocFile(e.target.files?.[0] ?? null)}
                                />
                            </label>
                            <button
                                className="btn secondary"
                                disabled={uploadLoading || (!caseVoiceFile && !caseDocFile)}
                                type="submit"
                            >
                                {uploadLoading ? "Uploading…" : "Upload files"}
                            </button>
                        </form>
                    </div>
                ) : null}

                {/* Status check */}
                <div className="card">
                    <h3>Check intake status</h3>
                    <form onSubmit={(e) => void handleStatusCheck(e)}>
                        <label>
                            <span>Public reference number</span>
                            <input
                                required
                                type="text"
                                value={referenceInput}
                                onChange={(e) => setReferenceInput(e.target.value)}
                                placeholder="REF-XXXXXX"
                            />
                        </label>
                        <button className="btn secondary" disabled={statusLoading} type="submit">
                            {statusLoading ? "Checking…" : "Check status"}
                        </button>
                    </form>

                    {statusError ? <p className="error-msg">{statusError}</p> : null}
                    {statusResult ? (
                        <div className="status-result">
                            <p><strong>Reference:</strong> {statusResult.public_reference}</p>
                            <p>
                                <strong>Status:</strong>{" "}
                                <span className={`status-badge ${tone(statusResult.status)}`}>
                                    {label(statusResult.status)}
                                </span>
                            </p>
                            {statusResult.issue_summary ? <p className="muted">{statusResult.issue_summary}</p> : null}
                            <p><strong>Filed:</strong> {formatDate(statusResult.created_at)}</p>
                        </div>
                    ) : null}
                </div>
            </div>

            {/* Existing consultation list */}
            {dashboard?.consultations && dashboard.consultations.length > 0 ? (
                <div className="card">
                    <h3>Your consultation history</h3>
                    <ul className="consultation-list">
                        {dashboard.consultations.map((req) => (
                            <li key={req.id} className="consultation-row">
                                <span className="ref-label">{req.public_reference ?? "—"}</span>
                                <span className="issue-text">{req.issue_summary}</span>
                                <span className={`status-badge ${tone(req.status)}`}>{label(req.status)}</span>
                                <span className="muted">{formatDate(req.created_at)}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            ) : null}
        </div>
    );
}
