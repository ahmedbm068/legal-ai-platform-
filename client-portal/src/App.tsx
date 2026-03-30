import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchIntakeStatus,
  fetchPortalDashboard,
  registerPortalAccount,
  requestPortalLoginCode,
  submitAuthenticatedPortalIntake,
  verifyPortalLoginCode,
} from "./lib/api";
import type { ClientPortalDashboard, PublicIntakeStatus } from "./types";

const TOKEN_STORAGE_KEY = "legal-ai-client-portal-token";
const PASSWORD_POLICY_REGEX = /^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{10,}$/;
const PASSWORD_HINT =
  "Password must be at least 10 characters and include one uppercase letter and one symbol.";
type PortalView = "dashboard" | "cases" | "documents" | "requests" | "assistant" | "profile";

function formatDate(value?: string | null) {
  if (!value) return "No date";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}
function formatBytes(size: number) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`;
}
function label(value?: string | null) {
  const normalized = (value || "").toLowerCase().trim();
  if (!normalized) return "Unknown";
  return normalized.replace(/_/g, " ").replace(/\b\w/g, (x) => x.toUpperCase());
}
function tone(value?: string | null) {
  const normalized = (value || "").toLowerCase().trim();
  if (["completed", "approved", "closed", "resolved"].includes(normalized)) return "ok";
  if (["failed", "rejected", "blocked"].includes(normalized)) return "danger";
  if (["processing", "submitted", "new", "ready_for_review", "in_progress", "open"].includes(normalized)) return "attention";
  return "neutral";
}

function helperReply(prompt: string, dashboard: ClientPortalDashboard) {
  const q = prompt.toLowerCase();
  if (q.includes("next step") || q.includes("what should i do")) {
    const target = dashboard.cases.find((row) => tone(row.status) === "attention") || dashboard.cases[0];
    if (!target) return "No active case yet. Submit a consultation request first.";
    return `${target.title}: ${target.next_recommended_step || "Your legal team is reviewing your matter."}`;
  }
  if (q.includes("status") || q.includes("progress")) {
    if (!dashboard.cases.length) return "No case is active yet.";
    return dashboard.cases.slice(0, 4).map((row) => `- ${row.title}: ${label(row.status)}`).join("\n");
  }
  if (q.includes("document") || q.includes("missing")) {
    const pending = dashboard.documents.filter((row) => tone(row.processing_status) !== "ok");
    if (!pending.length) return "All uploaded documents are processed.";
    return pending.slice(0, 5).map((row) => `- ${row.filename}: ${label(row.processing_status)}`).join("\n");
  }
  return `Workspace summary: ${dashboard.metrics.active_cases} active case(s), ${dashboard.metrics.total_documents} document(s), ${dashboard.metrics.requests_under_review} request(s) under review.`;
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [dashboard, setDashboard] = useState<ClientPortalDashboard | null>(null);
  const [view, setView] = useState<PortalView>("dashboard");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authLoading, setAuthLoading] = useState(false);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loginCodeRequested, setLoginCodeRequested] = useState(false);
  const [authForm, setAuthForm] = useState({ full_name: "", email: "", password: "", confirm_password: "", login_code: "", phone: "", address: "" });
  const [intakeForm, setIntakeForm] = useState({ issue_summary: "", case_description: "", preferred_schedule: "" });
  const [referenceInput, setReferenceInput] = useState("");
  const [statusResult, setStatusResult] = useState<PublicIntakeStatus | null>(null);
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const [supportingDocument, setSupportingDocument] = useState<File | null>(null);
  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [assistantAnswer, setAssistantAnswer] = useState("Ask about status, missing documents, or next legal steps.");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);

  useEffect(() => { if (token) void loadDashboard(token); }, [token]);
  const latestConsultation = useMemo(() => dashboard?.consultations[0] ?? null, [dashboard]);

  async function loadDashboard(currentToken: string) {
    try {
      setDashboardLoading(true); setError(null);
      setDashboard(await fetchPortalDashboard(currentToken));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load portal dashboard.");
      localStorage.removeItem(TOKEN_STORAGE_KEY); setToken(null); setDashboard(null);
    } finally { setDashboardLoading(false); }
  }
  async function handleAuthSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setAuthLoading(true); setError(null); setSuccess(null);
    try {
      if (authMode === "register") {
        if (authForm.password !== authForm.confirm_password) throw new Error("Passwords do not match.");
        if (!PASSWORD_POLICY_REGEX.test(authForm.password)) throw new Error(PASSWORD_HINT);
        const response = await registerPortalAccount({ full_name: authForm.full_name, email: authForm.email, password: authForm.password, phone: authForm.phone || undefined, address: authForm.address || undefined });
        setSuccess(response.message); setAuthMode("login"); setLoginCodeRequested(false);
        setAuthForm((x) => ({ ...x, password: "", confirm_password: "", login_code: "" })); return;
      }
      if (!loginCodeRequested) {
        const response = await requestPortalLoginCode(authForm.email, authForm.password);
        setSuccess(response.message); setLoginCodeRequested(true); return;
      }
      const response = await verifyPortalLoginCode(authForm.email, authForm.login_code);
      localStorage.setItem(TOKEN_STORAGE_KEY, response.access_token); setToken(response.access_token);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to authenticate."); }
    finally { setAuthLoading(false); }
  }
  async function handleIntakeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token) return;
    setSubmitLoading(true); setError(null); setSuccess(null);
    try {
      const payload = new FormData();
      payload.append("issue_summary", intakeForm.issue_summary);
      payload.append("case_description", intakeForm.case_description);
      payload.append("preferred_schedule", intakeForm.preferred_schedule);
      if (voiceFile) payload.append("voice_note", voiceFile);
      if (supportingDocument) payload.append("supporting_document", supportingDocument);
      const next = await submitAuthenticatedPortalIntake(token, payload);
      setDashboard(next); setSuccess("Consultation request submitted successfully."); setView("dashboard");
      setIntakeForm({ issue_summary: "", case_description: "", preferred_schedule: "" }); setVoiceFile(null); setSupportingDocument(null);
      if (next.consultations[0]?.public_reference) setReferenceInput(next.consultations[0].public_reference);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to submit consultation request."); }
    finally { setSubmitLoading(false); }
  }
  async function handleStatusLookup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!referenceInput.trim()) return;
    setStatusLoading(true); setError(null);
    try { setStatusResult(await fetchIntakeStatus(referenceInput.trim())); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to fetch request status."); }
    finally { setStatusLoading(false); }
  }
  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) { setError("Microphone recording not supported."); return; }
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream); mediaRecorderRef.current = recorder; mediaChunksRef.current = [];
      recorder.ondataavailable = (event) => { if (event.data.size > 0) mediaChunksRef.current.push(event.data); };
      recorder.onstop = () => {
        const blob = new Blob(mediaChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const extension = blob.type.includes("wav") ? "wav" : blob.type.includes("ogg") ? "ogg" : "webm";
        setVoiceFile(new File([blob], `client-voice-note-${Date.now()}.${extension}`, { type: blob.type || "audio/webm" }));
        stream.getTracks().forEach((track) => track.stop()); mediaRecorderRef.current = null; mediaChunksRef.current = []; setRecording(false);
      };
      recorder.start(); setRecording(true);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to start recording."); }
  }
  function stopRecording() { if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") mediaRecorderRef.current.stop(); }
  async function handleAssistantSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!dashboard || !assistantPrompt.trim()) return;
    setAssistantBusy(true); await new Promise((r) => setTimeout(r, 250));
    setAssistantAnswer(helperReply(assistantPrompt, dashboard)); setAssistantBusy(false);
  }
  function logout() { localStorage.removeItem(TOKEN_STORAGE_KEY); setToken(null); setDashboard(null); setStatusResult(null); setSuccess(null); setLoginCodeRequested(false); setView("dashboard"); }

  if (token && dashboardLoading && !dashboard) return <div className="portal-shell loading-shell"><div className="loading-card"><h2>Loading your secure workspace...</h2><p>Preparing your case and document timeline.</p></div></div>;

  if (!token || !dashboard) {
    return (
      <div className="portal-shell">
        <section className="portal-hero">
          <div><div className="eyebrow">Client legal portal</div><h1>Track your case confidently.</h1><p>Secure access for requests, documents, and legal updates.</p><div className="hero-badges"><span>Secure sign in</span><span>Case progress</span><span>Document updates</span><span>Client-safe AI helper</span></div></div>
          <div className="hero-trust-card"><h3>Client trust controls</h3><ul><li>Private account access only.</li><li>Reference-based tracking.</li><li>Clear case and document statuses.</li><li>No internal legal tooling exposure.</li></ul></div>
        </section>
        <section className="portal-auth-layout">
          <div className="glass-card">
            <div className="card-header"><div><h2>Portal access</h2><p>Sign in with secure verification code.</p></div></div>
            <div className="auth-tabs">
              <button className={authMode === "login" ? "active" : ""} onClick={() => { setAuthMode("login"); setLoginCodeRequested(false); }} type="button">Sign in</button>
              <button className={authMode === "register" ? "active" : ""} onClick={() => { setAuthMode("register"); setLoginCodeRequested(false); }} type="button">Create account</button>
            </div>
            <form className="form-grid" onSubmit={handleAuthSubmit}>
              {authMode === "register" ? <><label>Full name<input required value={authForm.full_name} onChange={(e) => setAuthForm((x) => ({ ...x, full_name: e.target.value }))} /></label><label>Phone<input value={authForm.phone} onChange={(e) => setAuthForm((x) => ({ ...x, phone: e.target.value }))} /></label><label className="full-span">Address<input value={authForm.address} onChange={(e) => setAuthForm((x) => ({ ...x, address: e.target.value }))} /></label><label>Confirm password<input required type="password" value={authForm.confirm_password} onChange={(e) => setAuthForm((x) => ({ ...x, confirm_password: e.target.value }))} /></label></> : null}
              <label>Email<input required type="email" value={authForm.email} onChange={(e) => { setAuthForm((x) => ({ ...x, email: e.target.value, login_code: "" })); if (authMode === "login") setLoginCodeRequested(false); }} /></label>
              <label>Password<input required type="password" value={authForm.password} onChange={(e) => { setAuthForm((x) => ({ ...x, password: e.target.value, login_code: "" })); if (authMode === "login") setLoginCodeRequested(false); }} /></label>
              {authMode === "register" ? <div className="password-hint full-span">{PASSWORD_HINT}</div> : null}
              {authMode === "login" && loginCodeRequested ? <label className="full-span">Six-digit access code<input required inputMode="numeric" maxLength={6} placeholder="Enter the code sent to your email" value={authForm.login_code} onChange={(e) => setAuthForm((x) => ({ ...x, login_code: e.target.value.replace(/\D/g, "").slice(0, 6) }))} /></label> : null}
              <button className="primary-button full-span" disabled={authLoading} type="submit">{authLoading ? "Working..." : authMode === "login" ? (loginCodeRequested ? "Verify and enter portal" : "Send access code") : "Create secure account"}</button>
            </form>
          </div>
          <div className="stack-layout">
            <div className="glass-card"><div className="card-header"><div><h2>Track request</h2><p>Search by reference.</p></div></div><form className="status-form" onSubmit={handleStatusLookup}><input placeholder="Reference code" value={referenceInput} onChange={(e) => setReferenceInput(e.target.value)} /><button className="secondary-button" disabled={statusLoading} type="submit">{statusLoading ? "Checking..." : "Check status"}</button></form>{statusResult ? <div className="result-box"><strong>{statusResult.public_reference}</strong><p>Status: {label(statusResult.status)}</p><p>Issue: {statusResult.issue_summary}</p><p>Submitted: {formatDate(statusResult.created_at)}</p></div> : <div className="result-box empty-state">No lookup yet.</div>}</div>
            <div className="glass-card"><div className="card-header"><div><h2>Onboarding steps</h2><p>Simple and clear.</p></div></div><ol className="steps-list"><li>Create account</li><li>Verify login code</li><li>Submit request and files</li><li>Track legal updates</li></ol></div>
          </div>
        </section>
        {success ? <div className="success-banner">{success}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}
      </div>
    );
  }

  return (
    <div className="portal-shell portal-workspace">
      <header className="portal-topbar glass-card"><div><div className="eyebrow">Secure client workspace</div><h1>Welcome, {dashboard.account.full_name}</h1><p>View case progress, track documents, and stay aligned with your legal team.</p></div><div className="topbar-actions"><button className="secondary-button" onClick={() => void loadDashboard(token)} type="button">Refresh</button><button className="ghost-button" onClick={logout} type="button">Sign out</button></div></header>
      <section className="metrics-grid"><article className="metric-card"><span>Active cases</span><strong>{dashboard.metrics.active_cases}</strong></article><article className="metric-card"><span>Documents tracked</span><strong>{dashboard.metrics.total_documents}</strong></article><article className="metric-card"><span>Under review</span><strong>{dashboard.metrics.requests_under_review}</strong></article><article className="metric-card"><span>Latest request</span><strong>{latestConsultation ? label(latestConsultation.status) : "No request yet"}</strong></article></section>
      <section className="workspace-layout">
        <aside className="workspace-nav glass-card">{(["dashboard","cases","documents","requests","assistant","profile"] as PortalView[]).map((id) => <button key={id} className={`nav-button ${view === id ? "active" : ""}`} onClick={() => setView(id)} type="button"><strong>{id === "dashboard" ? "Dashboard" : id === "cases" ? "My cases" : id === "documents" ? "My documents" : id === "requests" ? "Consultation requests" : id === "assistant" ? "Case helper" : "Profile"}</strong><small>{id === "dashboard" ? "Overview and next steps" : id === "cases" ? "Status and assigned lawyer" : id === "documents" ? "Files and processing state" : id === "requests" ? "Submit and track requests" : id === "assistant" ? "Client-safe AI guidance" : "Account details"}</small></button>)}
          <div className="workspace-note"><h4>Assigned legal team</h4><p>{dashboard.cases[0]?.lawyer_name || "Your legal team"} is managing your current matters.</p></div>
        </aside>
        <main className="workspace-content">
          {view === "dashboard" ? <div className="content-grid two-columns"><article className="glass-card"><div className="card-header"><div><h2>Case progress</h2><p>Current status and recommended action.</p></div></div>{dashboard.cases.length ? <div className="stack-layout">{dashboard.cases.slice(0, 5).map((row) => <div key={row.id} className="list-row"><div><strong>{row.title}</strong><small>Lawyer: {row.lawyer_name || "Assigned legal team"} | Last update {formatDate(row.updated_at)}</small><p>{row.next_recommended_step || "Your legal team is reviewing your matter."}</p></div><span className={`status-chip ${tone(row.status)}`}>{label(row.status)}</span></div>)}</div> : <div className="empty-state">No case opened yet from this account.</div>}</article><article className="glass-card"><div className="card-header"><div><h2>Recent activity</h2><p>Traceable workflow updates.</p></div></div>{dashboard.activity.length ? <div className="timeline-list">{dashboard.activity.slice(0, 8).map((row) => <div key={row.id} className="timeline-item"><strong>{row.title}</strong><p>{row.description}</p><small>{formatDate(row.created_at)}</small></div>)}</div> : <div className="empty-state">No activity yet.</div>}</article></div> : null}
          {view === "cases" ? <article className="glass-card"><div className="card-header"><div><h2>My cases</h2><p>Visibility across case status and ownership.</p></div></div>{dashboard.cases.length ? <div className="table-wrap"><table><thead><tr><th>Case</th><th>Status</th><th>Jurisdiction</th><th>Lawyer</th><th>Documents</th><th>Updated</th></tr></thead><tbody>{dashboard.cases.map((row) => <tr key={row.id}><td><strong>{row.title}</strong><p>{row.description || "No description provided."}</p></td><td><span className={`status-chip ${tone(row.status)}`}>{label(row.status)}</span></td><td>{label(row.jurisdiction_country)}</td><td>{row.lawyer_name || "Assigned legal team"}</td><td>{row.document_count}</td><td>{formatDate(row.updated_at)}</td></tr>)}</tbody></table></div> : <div className="empty-state">No cases available yet.</div>}</article> : null}
          {view === "documents" ? <article className="glass-card"><div className="card-header"><div><h2>My documents</h2><p>Processing state for uploaded files.</p></div></div>{dashboard.documents.length ? <div className="stack-layout">{dashboard.documents.map((row) => <div key={row.id} className="list-row"><div><strong>{row.filename}</strong><small>Case: {row.case_title} | {formatBytes(row.file_size)} | {formatDate(row.upload_timestamp)}</small></div><span className={`status-chip ${tone(row.processing_status)}`}>{label(row.processing_status)}</span></div>)}</div> : <div className="empty-state">No documents uploaded yet.</div>}</article> : null}
          {view === "requests" ? <div className="content-grid two-columns"><article className="glass-card"><div className="card-header"><div><h2>Submit consultation request</h2><p>Share your issue summary and supporting material.</p></div></div><form className="form-grid single-column" onSubmit={handleIntakeSubmit}><label>Issue summary<textarea required value={intakeForm.issue_summary} onChange={(e) => setIntakeForm((x) => ({ ...x, issue_summary: e.target.value }))} /></label><label>Detailed description<textarea value={intakeForm.case_description} onChange={(e) => setIntakeForm((x) => ({ ...x, case_description: e.target.value }))} /></label><label>Preferred schedule<input placeholder="Example: Tuesday 3 PM" value={intakeForm.preferred_schedule} onChange={(e) => setIntakeForm((x) => ({ ...x, preferred_schedule: e.target.value }))} /></label><div className="upload-grid"><label className="upload-box"><span>Voice note upload</span><input accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/mp3,audio/ogg" onChange={(e) => setVoiceFile(e.target.files?.[0] ?? null)} type="file" /><small>{voiceFile ? voiceFile.name : "Optional"}</small></label><div className="upload-box"><span>Record voice note</span><button className="secondary-button" onClick={() => void (recording ? stopRecording() : startRecording())} type="button">{recording ? "Stop recording" : "Record now"}</button><small>{recording ? "Recording..." : voiceFile ? "Audio attached" : "Optional"}</small></div><label className="upload-box"><span>Supporting document</span><input accept=".pdf,.doc,.docx,.png,.jpg,.jpeg" onChange={(e) => setSupportingDocument(e.target.files?.[0] ?? null)} type="file" /><small>{supportingDocument ? supportingDocument.name : "Optional"}</small></label></div><button className="primary-button" disabled={submitLoading} type="submit">{submitLoading ? "Submitting..." : "Submit consultation request"}</button></form></article><article className="glass-card"><div className="card-header"><div><h2>Request history</h2><p>Recent requests linked to your account.</p></div></div>{dashboard.consultations.length ? <div className="stack-layout">{dashboard.consultations.map((row) => <div key={row.id} className="list-row"><div><strong>{row.case_title}</strong><small>Ref: {row.public_reference || "Pending"} | {formatDate(row.created_at)}</small><p>{row.issue_summary}</p></div><span className={`status-chip ${tone(row.status)}`}>{label(row.status)}</span></div>)}</div> : <div className="empty-state">No consultation requests yet.</div>}</article></div> : null}
          {view === "assistant" ? <article className="glass-card"><div className="card-header"><div><h2>Client case helper</h2><p>Client-safe guidance for status and next steps.</p></div></div><form className="assistant-form" onSubmit={handleAssistantSubmit}><textarea placeholder="Example: What is the next step for my case?" value={assistantPrompt} onChange={(e) => setAssistantPrompt(e.target.value)} /><button className="primary-button" disabled={!assistantPrompt.trim() || assistantBusy} type="submit">{assistantBusy ? "Analyzing..." : "Ask helper"}</button></form><div className="result-box assistant-answer"><strong>Assistant response</strong><p>{assistantAnswer}</p></div></article> : null}
          {view === "profile" ? <article className="glass-card"><div className="card-header"><div><h2>Profile and account</h2><p>Secure account details for this law firm portal.</p></div></div><div className="profile-grid"><div className="profile-card"><span>Name</span><strong>{dashboard.account.full_name}</strong></div><div className="profile-card"><span>Email</span><strong>{dashboard.account.email}</strong></div><div className="profile-card"><span>Firm</span><strong>{dashboard.account.tenant_name || "Law firm workspace"}</strong></div><div className="profile-card"><span>Created</span><strong>{formatDate(dashboard.account.created_at)}</strong></div></div></article> : null}
        </main>
        <aside className="workspace-rail"><article className="glass-card"><div className="card-header"><div><h2>Quick status lookup</h2><p>Track by reference code.</p></div></div><form className="status-form" onSubmit={handleStatusLookup}><input placeholder="Reference code" value={referenceInput} onChange={(e) => setReferenceInput(e.target.value)} /><button className="secondary-button" disabled={statusLoading} type="submit">{statusLoading ? "Checking..." : "Check"}</button></form>{statusResult ? <div className="result-box"><strong>{statusResult.public_reference}</strong><p>Status: {label(statusResult.status)}</p><p>Preferred schedule: {statusResult.preferred_schedule || "Not provided"}</p><p>Submitted: {formatDate(statusResult.created_at)}</p></div> : <div className="result-box empty-state">No lookup result yet.</div>}</article><article className="glass-card"><div className="card-header"><div><h2>Priority checks</h2><p>Client-facing legal workflow indicators.</p></div></div><ul className="checks-list"><li>{dashboard.metrics.active_cases} active case(s)</li><li>{dashboard.metrics.pending_documents} document(s) processing</li><li>{dashboard.metrics.requests_under_review} request(s) under review</li></ul></article></aside>
      </section>
      {success ? <div className="success-banner">{success}</div> : null}
      {error ? <div className="error-banner">{error}</div> : null}
    </div>
  );
}

