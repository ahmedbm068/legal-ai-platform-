import { useRef, useState } from "react";
import { fetchIntakeStatus, submitIntake } from "./lib/api";
import type { PublicIntakeResponse, PublicIntakeStatus } from "./types";

function formatDate(value?: string | null) {
  if (!value) {
    return "No date";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export default function App() {
  const [form, setForm] = useState({
    tenant_name: "",
    client_name: "",
    client_email: "",
    client_phone: "",
    client_address: "",
    issue_summary: "",
    case_description: "",
    preferred_schedule: "",
  });
  const [referenceInput, setReferenceInput] = useState("");
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [supportingDocument, setSupportingDocument] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [recording, setRecording] = useState(false);
  const [submitResult, setSubmitResult] = useState<PublicIntakeResponse | null>(null);
  const [statusResult, setStatusResult] = useState<PublicIntakeStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSubmitResult(null);

    try {
      const payload = new FormData();
      Object.entries(form).forEach(([key, value]) => payload.append(key, value));
      if (voiceFile) {
        payload.append("voice_note", voiceFile);
      }
      if (supportingDocument) {
        payload.append("supporting_document", supportingDocument);
      }

      const result = await submitIntake(payload);
      setSubmitResult(result);
      setReferenceInput(result.public_reference);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to submit intake request.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStatusLookup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!referenceInput.trim()) {
      return;
    }

    setStatusLoading(true);
    setError(null);

    try {
      const result = await fetchIntakeStatus(referenceInput.trim());
      setStatusResult(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to fetch intake status.");
    } finally {
      setStatusLoading(false);
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser does not support microphone recording.");
      return;
    }

    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      mediaChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          mediaChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(mediaChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const extension = blob.type.includes("wav") ? "wav" : blob.type.includes("ogg") ? "ogg" : "webm";
        const file = new File([blob], `client-voice-note-${Date.now()}.${extension}`, {
          type: blob.type || "audio/webm",
        });

        setVoiceFile(file);
        stream.getTracks().forEach((track) => track.stop());
        mediaRecorderRef.current = null;
        mediaChunksRef.current = [];
        setRecording(false);
      };

      recorder.start();
      setRecording(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to start recording.");
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
  }

  return (
    <div className="portal-shell">
      <section className="hero">
        <div className="eyebrow">Client Intake Portal</div>
        <h1>Request a legal consultation without touching the internal AI workspace.</h1>
        <p>
          This portal is separate from the internal legal dashboard. Clients can describe their issue,
          upload documents, send a voice note, and receive a reference for follow-up.
        </p>
      </section>

      <section className="portal-grid">
        <div className="card">
          <div className="card-header">
            <div>
              <h2>New consultation request</h2>
              <span>Safe public intake only</span>
            </div>
          </div>

          <form className="form-grid" onSubmit={handleSubmit}>
            <label>
              Law firm / tenant name
              <input
                required
                value={form.tenant_name}
                onChange={(event) => setForm((current) => ({ ...current, tenant_name: event.target.value }))}
              />
            </label>
            <label>
              Full name
              <input
                required
                value={form.client_name}
                onChange={(event) => setForm((current) => ({ ...current, client_name: event.target.value }))}
              />
            </label>
            <label>
              Email
              <input
                type="email"
                value={form.client_email}
                onChange={(event) => setForm((current) => ({ ...current, client_email: event.target.value }))}
              />
            </label>
            <label>
              Phone
              <input
                value={form.client_phone}
                onChange={(event) => setForm((current) => ({ ...current, client_phone: event.target.value }))}
              />
            </label>
            <label className="full-span">
              Address
              <input
                value={form.client_address}
                onChange={(event) => setForm((current) => ({ ...current, client_address: event.target.value }))}
              />
            </label>
            <label className="full-span">
              Short issue summary
              <textarea
                required
                value={form.issue_summary}
                onChange={(event) => setForm((current) => ({ ...current, issue_summary: event.target.value }))}
              />
            </label>
            <label className="full-span">
              Detailed case description
              <textarea
                value={form.case_description}
                onChange={(event) => setForm((current) => ({ ...current, case_description: event.target.value }))}
              />
            </label>
            <label className="full-span">
              Preferred schedule
              <input
                placeholder="Example: next Tuesday at 3 PM"
                value={form.preferred_schedule}
                onChange={(event) => setForm((current) => ({ ...current, preferred_schedule: event.target.value }))}
              />
            </label>

            <div className="upload-row full-span">
              <label className="upload-box">
                <span>Upload voice note</span>
                <input
                  accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/mp3,audio/ogg"
                  onChange={(event) => setVoiceFile(event.target.files?.[0] ?? null)}
                  type="file"
                />
                <small>{voiceFile ? voiceFile.name : "Optional"}</small>
              </label>

              <div className="record-box">
                <span>Or record audio</span>
                <button
                  className="secondary-button"
                  onClick={() => void (recording ? stopRecording() : startRecording())}
                  type="button"
                >
                  {recording ? "Stop recording" : "Record voice note"}
                </button>
                <small>{recording ? "Recording in progress..." : voiceFile ? "Audio attached" : "Optional"}</small>
              </div>

              <label className="upload-box">
                <span>Upload supporting document</span>
                <input
                  accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
                  onChange={(event) => setSupportingDocument(event.target.files?.[0] ?? null)}
                  type="file"
                />
                <small>{supportingDocument ? supportingDocument.name : "Optional"}</small>
              </label>
            </div>

            <button className="primary-button full-span" disabled={submitting} type="submit">
              {submitting ? "Submitting..." : "Submit consultation request"}
            </button>
          </form>
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-header">
              <div>
                <h2>Track request</h2>
                <span>Safe status lookup by reference</span>
              </div>
            </div>

            <form className="status-form" onSubmit={handleStatusLookup}>
              <input
                placeholder="Enter intake reference"
                value={referenceInput}
                onChange={(event) => setReferenceInput(event.target.value)}
              />
              <button className="secondary-button" disabled={statusLoading} type="submit">
                {statusLoading ? "Checking..." : "Check status"}
              </button>
            </form>

            {statusResult ? (
              <div className="result-box">
                <strong>{statusResult.public_reference}</strong>
                <p>Status: {statusResult.status}</p>
                <p>Client: {statusResult.client_name || "Unknown"}</p>
                <p>Issue: {statusResult.issue_summary}</p>
                <p>Preferred schedule: {statusResult.preferred_schedule || "Not provided"}</p>
                <p>Submitted: {formatDate(statusResult.created_at)}</p>
              </div>
            ) : null}
          </div>

          <div className="card">
            <div className="card-header">
              <div>
                <h2>What this portal does</h2>
                <span>And what it does not do</span>
              </div>
            </div>
            <ul className="safe-list">
              <li>Submit a consultation request</li>
              <li>Upload documents and voice notes</li>
              <li>Share scheduling preferences</li>
              <li>Receive a public reference for follow-up</li>
              <li>No access to internal AI agents, prompts, or case workspace tools</li>
            </ul>
          </div>

          {submitResult ? (
            <div className="card success-card">
              <div className="card-header">
                <div>
                  <h2>Request submitted</h2>
                  <span>Save this reference</span>
                </div>
              </div>
              <div className="result-box">
                <strong>{submitResult.public_reference}</strong>
                <p>{submitResult.message}</p>
                <p>Client: {submitResult.client_name}</p>
                <p>Status: {submitResult.status}</p>
              </div>
            </div>
          ) : null}

          {error ? <div className="error-banner">{error}</div> : null}
        </div>
      </section>
    </div>
  );
}
