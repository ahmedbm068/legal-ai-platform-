import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchIntakeStatus,
  fetchPortalDashboard,
  registerPortalAccount,
  requestPortalLoginCode,
  submitAuthenticatedPortalIntake,
  verifyPortalLoginCode,
} from "./lib/api";
import type { ClientPortalConsultation, ClientPortalDashboard, PublicIntakeStatus } from "./types";

const TOKEN_STORAGE_KEY = "legal-ai-client-portal-token";
const PASSWORD_HINT =
  "Password must be at least 10 characters and include one uppercase letter and one symbol.";
const PASSWORD_POLICY_REGEX = /^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{10,}$/;

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
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [dashboard, setDashboard] = useState<ClientPortalDashboard | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authLoading, setAuthLoading] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loginCodeRequested, setLoginCodeRequested] = useState(false);

  const [authForm, setAuthForm] = useState({
    full_name: "",
    email: "",
    password: "",
    confirm_password: "",
    login_code: "",
    phone: "",
    address: "",
  });
  const [intakeForm, setIntakeForm] = useState({
    issue_summary: "",
    case_description: "",
    preferred_schedule: "",
  });
  const [referenceInput, setReferenceInput] = useState("");
  const [statusResult, setStatusResult] = useState<PublicIntakeStatus | null>(null);
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [supportingDocument, setSupportingDocument] = useState<File | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    if (!token) {
      return;
    }

    void loadDashboard(token);
  }, [token]);

  const latestConsultation = useMemo<ClientPortalConsultation | null>(() => {
    return dashboard?.consultations[0] ?? null;
  }, [dashboard]);

  async function loadDashboard(currentToken: string) {
    try {
      setDashboardLoading(true);
      setError(null);
      const nextDashboard = await fetchPortalDashboard(currentToken);
      setDashboard(nextDashboard);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Unable to load portal dashboard.";
      setError(message);
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setToken(null);
      setDashboard(null);
    } finally {
      setDashboardLoading(false);
    }
  }

  async function handleAuthSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthLoading(true);
    setError(null);
    setSuccess(null);

    try {
      if (authMode === "register") {
        if (authForm.password !== authForm.confirm_password) {
          throw new Error("Please confirm the same password in both password fields.");
        }

        if (!PASSWORD_POLICY_REGEX.test(authForm.password)) {
          throw new Error(PASSWORD_HINT);
        }

        const registerResponse = await registerPortalAccount({
              full_name: authForm.full_name,
              email: authForm.email,
              password: authForm.password,
              phone: authForm.phone || undefined,
              address: authForm.address || undefined,
            });

        setSuccess(registerResponse.message);
        setAuthMode("login");
        setLoginCodeRequested(false);
        setAuthForm((current) => ({
          ...current,
          password: "",
          confirm_password: "",
          login_code: "",
        }));
      } else if (!loginCodeRequested) {
        const loginResponse = await requestPortalLoginCode(authForm.email, authForm.password);
        setSuccess(loginResponse.message);
        setLoginCodeRequested(true);
      } else {
        const verifyResponse = await verifyPortalLoginCode(authForm.email, authForm.login_code);
        localStorage.setItem(TOKEN_STORAGE_KEY, verifyResponse.access_token);
        setToken(verifyResponse.access_token);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to authenticate.");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleIntakeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }

    setSubmitLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const payload = new FormData();
      payload.append("issue_summary", intakeForm.issue_summary);
      payload.append("case_description", intakeForm.case_description);
      payload.append("preferred_schedule", intakeForm.preferred_schedule);
      if (voiceFile) {
        payload.append("voice_note", voiceFile);
      }
      if (supportingDocument) {
        payload.append("supporting_document", supportingDocument);
      }

      const nextDashboard = await submitAuthenticatedPortalIntake(token, payload);
      setDashboard(nextDashboard);
      setSuccess("Consultation request submitted successfully.");
      setIntakeForm({ issue_summary: "", case_description: "", preferred_schedule: "" });
      setVoiceFile(null);
      setSupportingDocument(null);
      if (nextDashboard.consultations[0]?.public_reference) {
        setReferenceInput(nextDashboard.consultations[0].public_reference);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to submit consultation request.");
    } finally {
      setSubmitLoading(false);
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
      setError(caught instanceof Error ? caught.message : "Unable to fetch request status.");
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

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setDashboard(null);
    setStatusResult(null);
    setSuccess(null);
    setLoginCodeRequested(false);
  }

  if (!token || !dashboard) {
    return (
      <div className="portal-shell">
        <section className="hero hero-split">
          <div>
            <div className="eyebrow">Client Legal Portal</div>
            <h1>Secure client access for consultation requests, updates, and follow-up.</h1>
            <p>
              This portal is dedicated to your law firm. Clients can securely sign in, submit consultation
              requests, upload voice notes and supporting files, and track request status without touching
              internal AI tools.
            </p>
          </div>
          <div className="hero-points">
            <span>Secure sign in</span>
            <span>Private dashboard</span>
            <span>Voice + document intake</span>
            <span>Reference-based tracking</span>
          </div>
        </section>

        <section className="portal-grid auth-grid">
          <div className="card auth-card">
            <div className="card-header">
              <div>
                <h2>Portal access</h2>
                <span>Professional client account flow</span>
              </div>
            </div>

            <div className="auth-tabs">
              <button
                className={authMode === "login" ? "active" : ""}
                onClick={() => {
                  setAuthMode("login");
                  setLoginCodeRequested(false);
                }}
                type="button"
              >
                Sign in
              </button>
              <button
                className={authMode === "register" ? "active" : ""}
                onClick={() => {
                  setAuthMode("register");
                  setLoginCodeRequested(false);
                }}
                type="button"
              >
                Create account
              </button>
            </div>

            <form className="form-grid" onSubmit={handleAuthSubmit}>
              {authMode === "register" ? (
                <>
                  <label>
                    Full name
                    <input
                      required
                      value={authForm.full_name}
                      onChange={(event) => setAuthForm((current) => ({ ...current, full_name: event.target.value }))}
                    />
                  </label>
                  <label>
                    Phone
                    <input
                      value={authForm.phone}
                      onChange={(event) => setAuthForm((current) => ({ ...current, phone: event.target.value }))}
                    />
                  </label>
                  <label>
                    Address
                    <input
                      value={authForm.address}
                      onChange={(event) => setAuthForm((current) => ({ ...current, address: event.target.value }))}
                    />
                  </label>
                  <label>
                    Confirm password
                    <input
                      required
                      type="password"
                      value={authForm.confirm_password}
                      onChange={(event) =>
                        setAuthForm((current) => ({ ...current, confirm_password: event.target.value }))
                      }
                    />
                  </label>
                </>
              ) : null}

              <label>
                Email
                <input
                  required
                  type="email"
                  value={authForm.email}
                  onChange={(event) => {
                    const nextEmail = event.target.value;
                    setAuthForm((current) => ({ ...current, email: nextEmail, login_code: "" }));
                    if (authMode === "login") {
                      setLoginCodeRequested(false);
                    }
                  }}
                />
              </label>
              <label>
                Password
                <input
                  required
                  type="password"
                  value={authForm.password}
                  onChange={(event) => {
                    const nextPassword = event.target.value;
                    setAuthForm((current) => ({ ...current, password: nextPassword, login_code: "" }));
                    if (authMode === "login") {
                      setLoginCodeRequested(false);
                    }
                  }}
                />
              </label>

              {authMode === "register" ? <div className="password-hint full-span">{PASSWORD_HINT}</div> : null}

              {authMode === "login" && loginCodeRequested ? (
                <label className="full-span">
                  Six-digit access code
                  <input
                    required
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="Enter the code sent to your email"
                    value={authForm.login_code}
                    onChange={(event) =>
                      setAuthForm((current) => ({
                        ...current,
                        login_code: event.target.value.replace(/\D/g, "").slice(0, 6),
                      }))
                    }
                  />
                </label>
              ) : null}

              <button className="primary-button full-span" disabled={authLoading} type="submit">
                {authLoading
                  ? "Working..."
                  : authMode === "login"
                    ? loginCodeRequested
                      ? "Verify code and enter portal"
                      : "Send access code"
                    : "Create secure account"}
              </button>
            </form>
          </div>

          <div className="stack">
            <div className="card">
              <div className="card-header">
                <div>
                  <h2>Track a request</h2>
                  <span>Status lookup by reference</span>
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
                  <h2>Portal standards</h2>
                  <span>Client-safe by design</span>
                </div>
              </div>
              <ul className="safe-list">
                <li>Secure client-only access</li>
                <li>Private dashboard for submissions and references</li>
                <li>Voice note and supporting file upload</li>
                <li>No access to internal agents, prompts, or legal workspace tools</li>
              </ul>
            </div>

            {success ? <div className="success-banner">{success}</div> : null}
            {error ? <div className="error-banner">{error}</div> : null}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="portal-shell">
      <section className="hero hero-dashboard">
        <div>
          <div className="eyebrow">Secure Client Workspace</div>
          <h1>Welcome back, {dashboard.account.full_name}.</h1>
          <p>
            Submit new consultation requests, attach supporting materials, and track your recent requests in a
            clean professional portal dedicated to your law firm and kept separate from the internal legal AI workspace.
          </p>
        </div>
        <div className="dashboard-summary">
          <div className="summary-card">
            <span>Requests</span>
            <strong>{dashboard.consultations.length}</strong>
          </div>
          <div className="summary-card">
            <span>Latest status</span>
            <strong>{latestConsultation?.status || "No requests yet"}</strong>
          </div>
          <button className="secondary-button" onClick={logout} type="button">
            Sign out
          </button>
        </div>
      </section>

      <section className="portal-grid dashboard-grid">
        <div className="card">
          <div className="card-header">
            <div>
              <h2>New consultation request</h2>
              <span>Private submission for your client account</span>
            </div>
          </div>

          <form className="form-grid" onSubmit={handleIntakeSubmit}>
            <label className="full-span">
              Short issue summary
              <textarea
                required
                value={intakeForm.issue_summary}
                onChange={(event) => setIntakeForm((current) => ({ ...current, issue_summary: event.target.value }))}
              />
            </label>
            <label className="full-span">
              Detailed case description
              <textarea
                value={intakeForm.case_description}
                onChange={(event) =>
                  setIntakeForm((current) => ({ ...current, case_description: event.target.value }))
                }
              />
            </label>
            <label className="full-span">
              Preferred schedule
              <input
                placeholder="Example: next Tuesday at 3 PM"
                value={intakeForm.preferred_schedule}
                onChange={(event) =>
                  setIntakeForm((current) => ({ ...current, preferred_schedule: event.target.value }))
                }
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

            <button className="primary-button full-span" disabled={submitLoading} type="submit">
              {submitLoading ? "Submitting..." : "Submit consultation request"}
            </button>
          </form>
        </div>

        <div className="stack">
          <div className="card">
            <div className="card-header">
              <div>
                <h2>Recent requests</h2>
                <span>Everything tied to your client account</span>
              </div>
            </div>

            {dashboardLoading ? (
              <div className="result-box">Loading dashboard...</div>
            ) : dashboard.consultations.length > 0 ? (
              <div className="request-list">
                {dashboard.consultations.map((item) => (
                  <div key={item.id} className="request-card">
                    <div className="request-topline">
                      <strong>{item.case_title}</strong>
                      <span>{item.status}</span>
                    </div>
                    <p>{item.issue_summary}</p>
                    <small>
                      Ref: {item.public_reference || "Pending"} | Preferred schedule:{" "}
                      {item.preferred_schedule || "Not provided"} | {formatDate(item.created_at)}
                    </small>
                  </div>
                ))}
              </div>
            ) : (
              <div className="result-box">No requests yet. Submit your first consultation request to begin.</div>
            )}
          </div>

          <div className="card">
            <div className="card-header">
              <div>
                <h2>Quick status lookup</h2>
                <span>Reference-based confirmation</span>
              </div>
            </div>

            <form className="status-form" onSubmit={handleStatusLookup}>
              <input
                placeholder="Enter request reference"
                value={referenceInput}
                onChange={(event) => setReferenceInput(event.target.value)}
              />
              <button className="secondary-button" disabled={statusLoading} type="submit">
                {statusLoading ? "Checking..." : "Check"}
              </button>
            </form>

            {statusResult ? (
              <div className="result-box">
                <strong>{statusResult.public_reference}</strong>
                <p>Status: {statusResult.status}</p>
                <p>Issue: {statusResult.issue_summary}</p>
                <p>Preferred schedule: {statusResult.preferred_schedule || "Not provided"}</p>
                <p>Submitted: {formatDate(statusResult.created_at)}</p>
              </div>
            ) : null}
          </div>

          {success ? <div className="success-banner">{success}</div> : null}
          {error ? <div className="error-banner">{error}</div> : null}
        </div>
      </section>
    </div>
  );
}
