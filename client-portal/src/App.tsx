import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchIntakeStatus,
  fetchPortalDashboard,
  registerPortalAccount,
  requestPortalLoginCode,
  submitAuthenticatedPortalIntake,
  verifyPortalLoginCode,
} from "./lib/api";
import type {
  ClientPortalCase,
  ClientPortalDashboard,
  ClientPortalDocument,
  PublicIntakeStatus,
} from "./types";

const TOKEN_STORAGE_KEY = "legal-ai-client-portal-token";
const THEME_STORAGE_KEY = "legal-ai-client-portal-theme";
const PASSWORD_POLICY_REGEX = /^(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{10,}$/;
const PASSWORD_HINT =
  "Password must be at least 10 characters and include one uppercase letter and one symbol.";

type PortalView = "dashboard" | "cases" | "documents" | "requests" | "assistant" | "profile";
type ThemeMode = "light" | "dark";

const NAV_ITEMS: Array<{ id: PortalView; title: string; subtitle: string }> = [
  { id: "dashboard", title: "Dashboard", subtitle: "Overview and next actions" },
  { id: "cases", title: "Case intelligence", subtitle: "Status, risk, and evidence" },
  { id: "documents", title: "Document viewer", subtitle: "Files, highlights, and insights" },
  { id: "requests", title: "Intake requests", subtitle: "Submit updates and materials" },
  { id: "assistant", title: "AI assistant", subtitle: "Structured legal guidance" },
  { id: "profile", title: "Profile", subtitle: "Account and workspace" },
];

const ASSISTANT_SUGGESTIONS = [
  "Summarize my case",
  "What are the risks?",
  "What should I do next?",
  "What is missing in my file?",
];

function formatDate(value?: string | null) {
  if (!value) return "No date";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatDateTime(value?: string | null) {
  if (!value) return "No date";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatBytes(size: number) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
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

function riskFromCase(row: ClientPortalCase) {
  const status = (row.status || "").toLowerCase();
  if (["blocked", "failed", "rejected"].includes(status)) {
    return { label: "High", tone: "danger" };
  }
  if (row.document_count === 0 && row.consultation_count === 0) {
    return { label: "High", tone: "danger" };
  }
  if (["new", "open", "in_progress", "ready_for_review"].includes(status)) {
    return { label: "Medium", tone: "attention" };
  }
  return { label: "Low", tone: "ok" };
}

function intakePipelineStage(props: {
  submitting: boolean;
  hasPayload: boolean;
  pendingDocuments: number;
}) {
  if (props.submitting) return "uploading";
  if (props.pendingDocuments > 0) return "processing";
  if (props.hasPayload) return "analyzed";
  return "idle";
}

function helperReply(prompt: string, dashboard: ClientPortalDashboard, selectedCase: ClientPortalCase | null) {
  const q = prompt.toLowerCase();

  if (q.includes("next step") || q.includes("what should i do")) {
    const target = selectedCase || dashboard.cases.find((row) => tone(row.status) === "attention") || dashboard.cases[0];
    if (!target) return "No active case yet. Submit a consultation request first.";
    return `${target.title}: ${target.next_recommended_step || "Your legal team is reviewing your matter."}`;
  }

  if (q.includes("risk")) {
    if (!dashboard.cases.length) return "No active case yet, so risk cannot be estimated.";
    const risks = dashboard.cases.slice(0, 4).map((row) => {
      const risk = riskFromCase(row);
      return `- ${row.title}: ${risk.label} risk`;
    });
    return risks.join("\n");
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

function StatusBadge({ value }: { value?: string | null }) {
  return <span className={`status-badge ${tone(value)}`}>{label(value)}</span>;
}

function RiskBadge({ row }: { row: ClientPortalCase }) {
  const risk = riskFromCase(row);
  return <span className={`status-badge ${risk.tone}`}>Risk {risk.label}</span>;
}

function sectionTitle(view: PortalView) {
  if (view === "dashboard") return "Client dashboard";
  if (view === "cases") return "Case intelligence";
  if (view === "documents") return "Document intelligence";
  if (view === "requests") return "Consultation requests";
  if (view === "assistant") return "AI assistant";
  return "Profile";
}

function documentInsights(
  selectedDocument: ClientPortalDocument | null,
  selectedCase: ClientPortalCase | null,
  activity: ClientPortalDashboard["activity"]
) {
  if (!selectedDocument) return null;

  const linkedActivity = activity
    .filter((item) => item.case_id === selectedDocument.case_id)
    .slice(0, 3)
    .map((item) => `${item.title} (${formatDate(item.created_at)})`);

  const riskText = tone(selectedDocument.processing_status) === "ok"
    ? "Low extraction risk. Document is fully processed."
    : "Medium processing risk. Document may still be under analysis.";

  return {
    summary: `${selectedDocument.filename} is linked to ${selectedCase?.title || "your case"} and currently marked as ${label(
      selectedDocument.processing_status
    )}.`,
    riskText,
    dates:
      linkedActivity.length > 0
        ? linkedActivity
        : [
            `Uploaded on ${formatDate(selectedDocument.upload_timestamp)}`,
            "No additional date events detected yet",
          ],
  };
}

export default function App() {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "dark" ? "dark" : "light";
  });
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

  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

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
  const [assistantPrompt, setAssistantPrompt] = useState("");
  const [assistantAnswer, setAssistantAnswer] = useState(
    "Ask about status, risks, missing documents, or next legal steps."
  );

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    if (token) {
      void loadDashboard(token);
    }
  }, [token]);

  useEffect(() => {
    if (!dashboard?.cases.length) {
      setSelectedCaseId(null);
      return;
    }
    if (!selectedCaseId || !dashboard.cases.some((item) => item.id === selectedCaseId)) {
      setSelectedCaseId(dashboard.cases[0].id);
    }
  }, [dashboard?.cases, selectedCaseId]);

  useEffect(() => {
    if (!dashboard?.documents.length) {
      setSelectedDocumentId(null);
      return;
    }
    const firstForCase = dashboard.documents.find((item) => item.case_id === selectedCaseId);
    if (firstForCase && (!selectedDocumentId || !dashboard.documents.some((item) => item.id === selectedDocumentId))) {
      setSelectedDocumentId(firstForCase.id);
    }
  }, [dashboard?.documents, selectedCaseId, selectedDocumentId]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const latestConsultation = useMemo(() => dashboard?.consultations[0] ?? null, [dashboard]);

  const sortedCases = useMemo(() => {
    if (!dashboard) return [];
    return [...dashboard.cases].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [dashboard]);

  const visibleCases = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return sortedCases;
    return sortedCases.filter(
      (row) =>
        row.title.toLowerCase().includes(q) ||
        (row.description || "").toLowerCase().includes(q) ||
        label(row.status).toLowerCase().includes(q)
    );
  }, [searchQuery, sortedCases]);

  const selectedCase = useMemo(
    () => sortedCases.find((row) => row.id === selectedCaseId) || null,
    [sortedCases, selectedCaseId]
  );

  const caseDocuments = useMemo(() => {
    if (!dashboard || !selectedCase) return [];
    return dashboard.documents
      .filter((row) => row.case_id === selectedCase.id)
      .sort((a, b) => b.upload_timestamp.localeCompare(a.upload_timestamp));
  }, [dashboard, selectedCase]);

  const visibleDocuments = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return caseDocuments;
    return caseDocuments.filter(
      (row) => row.filename.toLowerCase().includes(q) || label(row.processing_status).toLowerCase().includes(q)
    );
  }, [searchQuery, caseDocuments]);

  const selectedDocument = useMemo(() => {
    return caseDocuments.find((row) => row.id === selectedDocumentId) || caseDocuments[0] || null;
  }, [caseDocuments, selectedDocumentId]);

  const caseTimeline = useMemo(() => {
    if (!dashboard || !selectedCase) return [];
    return dashboard.activity
      .filter((row) => row.case_id === selectedCase.id)
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [dashboard, selectedCase]);

  const highRiskCount = useMemo(
    () => sortedCases.filter((row) => riskFromCase(row).tone === "danger").length,
    [sortedCases]
  );

  const pendingDocumentCount = dashboard?.metrics.pending_documents || 0;

  const intakePipeline = intakePipelineStage({
    submitting: submitLoading,
    hasPayload: Boolean(voiceFile || supportingDocument),
    pendingDocuments: pendingDocumentCount,
  });

  const insights = useMemo(
    () => documentInsights(selectedDocument, selectedCase, dashboard?.activity || []),
    [selectedDocument, selectedCase, dashboard?.activity]
  );

  async function loadDashboard(currentToken: string) {
    try {
      setDashboardLoading(true);
      setError(null);
      setDashboard(await fetchPortalDashboard(currentToken));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load portal dashboard.");
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
          throw new Error("Passwords do not match.");
        }
        if (!PASSWORD_POLICY_REGEX.test(authForm.password)) {
          throw new Error(PASSWORD_HINT);
        }
        const response = await registerPortalAccount({
          full_name: authForm.full_name,
          email: authForm.email,
          password: authForm.password,
          phone: authForm.phone || undefined,
          address: authForm.address || undefined,
        });
        setSuccess(response.message);
        setAuthMode("login");
        setLoginCodeRequested(false);
        setAuthForm((current) => ({
          ...current,
          password: "",
          confirm_password: "",
          login_code: "",
        }));
        return;
      }

      if (!loginCodeRequested) {
        const response = await requestPortalLoginCode(authForm.email, authForm.password);
        setSuccess(response.message);
        setLoginCodeRequested(true);
        return;
      }

      const response = await verifyPortalLoginCode(authForm.email, authForm.login_code);
      localStorage.setItem(TOKEN_STORAGE_KEY, response.access_token);
      setToken(response.access_token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to authenticate.");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleIntakeSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;

    setSubmitLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const payload = new FormData();
      payload.append("issue_summary", intakeForm.issue_summary);
      payload.append("case_description", intakeForm.case_description);
      payload.append("preferred_schedule", intakeForm.preferred_schedule);
      if (voiceFile) payload.append("voice_note", voiceFile);
      if (supportingDocument) payload.append("supporting_document", supportingDocument);

      const next = await submitAuthenticatedPortalIntake(token, payload);
      setDashboard(next);
      setSuccess("Consultation request submitted successfully.");
      setView("dashboard");
      setIntakeForm({ issue_summary: "", case_description: "", preferred_schedule: "" });
      setVoiceFile(null);
      setSupportingDocument(null);

      if (next.consultations[0]?.public_reference) {
        setReferenceInput(next.consultations[0].public_reference);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to submit consultation request.");
    } finally {
      setSubmitLoading(false);
    }
  }

  async function handleStatusLookup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!referenceInput.trim()) return;

    setStatusLoading(true);
    setError(null);
    try {
      setStatusResult(await fetchIntakeStatus(referenceInput.trim()));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to fetch request status.");
    } finally {
      setStatusLoading(false);
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Microphone recording not supported.");
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
        setVoiceFile(new File([blob], `client-voice-note-${Date.now()}.${extension}`, { type: blob.type || "audio/webm" }));
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

  async function runAssistantWithPrompt(prompt: string) {
    if (!dashboard) return;
    setAssistantBusy(true);
    await new Promise((resolve) => setTimeout(resolve, 220));
    setAssistantAnswer(helperReply(prompt, dashboard, selectedCase));
    setAssistantBusy(false);
  }

  async function handleAssistantSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!assistantPrompt.trim()) return;
    await runAssistantWithPrompt(assistantPrompt);
  }

  async function useSuggestion(prompt: string) {
    setView("assistant");
    setAssistantPrompt(prompt);
    await runAssistantWithPrompt(prompt);
  }

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setDashboard(null);
    setStatusResult(null);
    setSuccess(null);
    setLoginCodeRequested(false);
    setView("dashboard");
  }

  function toggleTheme() {
    setTheme((current) => (current === "light" ? "dark" : "light"));
  }

  function onDropDocument(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) setSupportingDocument(file);
  }

  function onDropVoice(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) setVoiceFile(file);
  }

  if (token && dashboardLoading && !dashboard) {
    return (
      <div className="portal-root loading-root">
        <div className="card loading-card">
          <div className="skeleton-line lg" />
          <div className="skeleton-line" />
          <div className="skeleton-grid">
            <div className="skeleton-block" />
            <div className="skeleton-block" />
            <div className="skeleton-block" />
          </div>
        </div>
      </div>
    );
  }

  if (!token || !dashboard) {
    return (
      <div className="portal-root">
        <div className="ambient-background" />

        <section className="auth-hero card">
          <div>
            <p className="eyebrow">Client Legal Intelligence</p>
            <h1>Track your case with clarity and confidence.</h1>
            <p>
              Secure access to your legal timeline, document processing, and AI-guided next steps.
            </p>
            <div className="hero-pills">
              <span>Secure code login</span>
              <span>Case-by-case tracking</span>
              <span>Document intelligence</span>
              <span>Human-centered AI help</span>
            </div>
          </div>
          <div className="trust-card">
            <h3>Client trust controls</h3>
            <ul>
              <li>Your portal only shows client-safe legal updates.</li>
              <li>Every request is traceable with a public reference.</li>
              <li>Statuses stay transparent from submission to review.</li>
              <li>No internal legal operations are exposed.</li>
            </ul>
          </div>
        </section>

        <section className="auth-layout">
          <article className="card auth-card">
            <div className="section-head">
              <div>
                <h2>Portal access</h2>
                <p>Sign in using secure credentials and verification code.</p>
              </div>
              <button className="btn ghost" onClick={toggleTheme} type="button">
                {theme === "dark" ? "Light mode" : "Dark mode"}
              </button>
            </div>

            <div className="tabs">
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
                      onChange={(event) =>
                        setAuthForm((current) => ({ ...current, full_name: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Phone
                    <input
                      value={authForm.phone}
                      onChange={(event) =>
                        setAuthForm((current) => ({ ...current, phone: event.target.value }))
                      }
                    />
                  </label>
                  <label className="full-row">
                    Address
                    <input
                      value={authForm.address}
                      onChange={(event) =>
                        setAuthForm((current) => ({ ...current, address: event.target.value }))
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
                    setAuthForm((current) => ({
                      ...current,
                      email: event.target.value,
                      login_code: "",
                    }));
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
                    setAuthForm((current) => ({
                      ...current,
                      password: event.target.value,
                      login_code: "",
                    }));
                    if (authMode === "login") {
                      setLoginCodeRequested(false);
                    }
                  }}
                />
              </label>

              {authMode === "register" ? (
                <>
                  <label>
                    Confirm password
                    <input
                      required
                      type="password"
                      value={authForm.confirm_password}
                      onChange={(event) =>
                        setAuthForm((current) => ({
                          ...current,
                          confirm_password: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <div className="password-note">{PASSWORD_HINT}</div>
                </>
              ) : null}

              {authMode === "login" && loginCodeRequested ? (
                <label className="full-row">
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

              <button className="btn primary full-row" disabled={authLoading} type="submit">
                {authLoading
                  ? "Working..."
                  : authMode === "login"
                    ? loginCodeRequested
                      ? "Verify and enter portal"
                      : "Send access code"
                    : "Create secure account"}
              </button>
            </form>
          </article>

          <aside className="auth-side">
            <article className="card side-card">
              <div className="section-head">
                <div>
                  <h3>Track request</h3>
                  <p>Find any intake by reference code.</p>
                </div>
              </div>
              <form className="status-form" onSubmit={handleStatusLookup}>
                <input
                  placeholder="Reference code"
                  value={referenceInput}
                  onChange={(event) => setReferenceInput(event.target.value)}
                />
                <button className="btn secondary" disabled={statusLoading} type="submit">
                  {statusLoading ? "Checking..." : "Check status"}
                </button>
              </form>

              <div className="result-panel">
                {statusResult ? (
                  <>
                    <strong>{statusResult.public_reference}</strong>
                    <p>Status: {label(statusResult.status)}</p>
                    <p>Issue: {statusResult.issue_summary}</p>
                    <p>Submitted: {formatDate(statusResult.created_at)}</p>
                  </>
                ) : (
                  <p>No lookup yet.</p>
                )}
              </div>
            </article>

            <article className="card side-card">
              <h3>Onboarding flow</h3>
              <ol className="step-list">
                <li>Create account</li>
                <li>Request secure access code</li>
                <li>Verify and enter portal</li>
                <li>Submit and track your request</li>
              </ol>
            </article>
          </aside>
        </section>

        {success ? <div className="banner success">{success}</div> : null}
        {error ? <div className="banner error">{error}</div> : null}
      </div>
    );
  }

  return (
    <div className="portal-root workspace-root">
      <div className="ambient-background" />

      <header className="card workspace-header">
        <div>
          <p className="eyebrow">Secure Client Workspace</p>
          <h1>Welcome, {dashboard.account.full_name}</h1>
          <p>
            {sectionTitle(view)} for {selectedCase?.title || "your legal matters"}
          </p>
        </div>

        <div className="workspace-actions">
          <div className="search-shell">
            <span>Search</span>
            <input
              ref={searchInputRef}
              placeholder="cases, docs, statuses..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <small>Ctrl/Cmd + K</small>
          </div>
          <button className="btn secondary" onClick={() => void loadDashboard(token)} type="button">
            Refresh
          </button>
          <button className="btn ghost" onClick={toggleTheme} type="button">
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
          <button className="btn ghost" onClick={logout} type="button">
            Sign out
          </button>
        </div>
      </header>

      <section className="metric-grid">
        <article className="card metric-card">
          <span>Active cases</span>
          <strong>{dashboard.metrics.active_cases}</strong>
          <small>Under your account</small>
        </article>
        <article className="card metric-card">
          <span>Documents tracked</span>
          <strong>{dashboard.metrics.total_documents}</strong>
          <small>{pendingDocumentCount} still processing</small>
        </article>
        <article className="card metric-card">
          <span>Requests in review</span>
          <strong>{dashboard.metrics.requests_under_review}</strong>
          <small>Awaiting legal action</small>
        </article>
        <article className="card metric-card">
          <span>Risk watch</span>
          <strong>{highRiskCount}</strong>
          <small>Cases flagged high risk</small>
        </article>
      </section>

      <section className="workspace-grid">
        <aside className="card workspace-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${view === item.id ? "active" : ""}`}
              onClick={() => setView(item.id)}
              type="button"
            >
              <strong>{item.title}</strong>
              <small>{item.subtitle}</small>
            </button>
          ))}

          <div className="nav-note">
            <h4>Assigned legal team</h4>
            <p>{selectedCase?.lawyer_name || "Your legal team"} is currently managing your file.</p>
          </div>

          <div className="nav-note">
            <h4>Latest request</h4>
            <p>
              {latestConsultation
                ? `${label(latestConsultation.status)} on ${formatDate(latestConsultation.created_at)}`
                : "No request yet"}
            </p>
          </div>
        </aside>

        <main className="workspace-main">
          {view === "dashboard" ? (
            <>
              <article className="card welcome-card">
                <div>
                  <h2>Your legal progress at a glance</h2>
                  <p>
                    Use AI-guided prompts or open a case panel for detailed intelligence on risk, missing evidence, and next actions.
                  </p>
                </div>
                <div className="suggestion-row">
                  {ASSISTANT_SUGGESTIONS.map((prompt) => (
                    <button key={prompt} className="pill-button" onClick={() => void useSuggestion(prompt)} type="button">
                      {prompt}
                    </button>
                  ))}
                </div>
              </article>

              <section className="case-card-grid">
                {visibleCases.length ? (
                  visibleCases.slice(0, 6).map((row) => (
                    <article key={row.id} className="card case-card">
                      <div className="case-card-top">
                        <h3>{row.title}</h3>
                        <div className="chip-row">
                          <StatusBadge value={row.status} />
                          <RiskBadge row={row} />
                        </div>
                      </div>
                      <p>{row.description || "No detailed description provided yet."}</p>
                      <div className="case-card-meta">
                        <span>Jurisdiction: {label(row.jurisdiction_country)}</span>
                        <span>Last update: {formatDate(row.updated_at)}</span>
                      </div>
                      <button
                        className="btn secondary"
                        onClick={() => {
                          setSelectedCaseId(row.id);
                          setView("cases");
                        }}
                        type="button"
                      >
                        Open case intelligence
                      </button>
                    </article>
                  ))
                ) : (
                  <article className="card empty-card">
                    <h3>No matching cases</h3>
                    <p>Try a different search term or clear the current filter.</p>
                  </article>
                )}
              </section>

              <section className="two-column-grid">
                <article className="card timeline-card">
                  <div className="section-head">
                    <div>
                      <h3>Recent activity timeline</h3>
                      <p>Documents, consultations, and deadlines in one sequence.</p>
                    </div>
                  </div>

                  <div className="timeline-vertical">
                    {dashboard.activity.length ? (
                      dashboard.activity.slice(0, 9).map((item) => (
                        <div key={item.id} className="timeline-entry">
                          <span className="timeline-dot" />
                          <div>
                            <strong>{item.title}</strong>
                            <p>{item.description}</p>
                            <small>{formatDateTime(item.created_at)}</small>
                          </div>
                        </div>
                      ))
                    ) : (
                      <p className="muted">No timeline activity yet.</p>
                    )}
                  </div>
                </article>

                <article className="card assistant-card">
                  <div className="section-head">
                    <div>
                      <h3>Client AI assistant</h3>
                      <p>Structured guidance for next actions and risk awareness.</p>
                    </div>
                  </div>

                  <form className="assistant-form" onSubmit={handleAssistantSubmit}>
                    <textarea
                      placeholder="Ask: What risks should I focus on this week?"
                      value={assistantPrompt}
                      onChange={(event) => setAssistantPrompt(event.target.value)}
                    />
                    <button className="btn primary" disabled={!assistantPrompt.trim() || assistantBusy} type="submit">
                      {assistantBusy ? "Analyzing..." : "Ask assistant"}
                    </button>
                  </form>

                  <div className="assistant-response-grid">
                    <div className="response-card">
                      <span>Summary</span>
                      <p>{assistantAnswer}</p>
                    </div>
                  </div>
                </article>
              </section>
            </>
          ) : null}

          {view === "cases" ? (
            <div className="case-intelligence-grid">
              <article className="card">
                <div className="section-head">
                  <div>
                    <h2>Case metadata</h2>
                    <p>Core context and ownership details.</p>
                  </div>
                </div>

                {selectedCase ? (
                  <div className="meta-stack">
                    <div>
                      <strong>{selectedCase.title}</strong>
                      <p>{selectedCase.description || "No description provided."}</p>
                    </div>
                    <div className="chip-row">
                      <StatusBadge value={selectedCase.status} />
                      <RiskBadge row={selectedCase} />
                    </div>
                    <dl className="meta-list">
                      <div>
                        <dt>Jurisdiction</dt>
                        <dd>{label(selectedCase.jurisdiction_country)}</dd>
                      </div>
                      <div>
                        <dt>Lawyer</dt>
                        <dd>{selectedCase.lawyer_name || "Assigned legal team"}</dd>
                      </div>
                      <div>
                        <dt>Documents</dt>
                        <dd>{selectedCase.document_count}</dd>
                      </div>
                      <div>
                        <dt>Consultations</dt>
                        <dd>{selectedCase.consultation_count}</dd>
                      </div>
                      <div>
                        <dt>Updated</dt>
                        <dd>{formatDateTime(selectedCase.updated_at)}</dd>
                      </div>
                    </dl>
                  </div>
                ) : (
                  <p className="muted">No case selected.</p>
                )}
              </article>

              <article className="card">
                <div className="section-head">
                  <div>
                    <h2>Case intelligence</h2>
                    <p>Summary, risks, evidence, gaps, and recommendations.</p>
                  </div>
                </div>

                {selectedCase ? (
                  <div className="intelligence-panels">
                    <section className="intel-panel">
                      <h4>Summary</h4>
                      <p>
                        {selectedCase.description || "A detailed summary is not yet available for this case."}
                      </p>
                    </section>

                    <section className="intel-panel">
                      <h4>Risks</h4>
                      <ul>
                        <li>{riskFromCase(selectedCase).label} operational risk based on current status.</li>
                        <li>
                          {selectedCase.document_count === 0
                            ? "No documents uploaded yet. Evidence completeness is low."
                            : "Document coverage exists. Continue validating critical clauses."}
                        </li>
                        <li>
                          {selectedCase.consultation_count === 0
                            ? "No consultation requests attached yet."
                            : `${selectedCase.consultation_count} consultation request(s) are linked.`}
                        </li>
                      </ul>
                    </section>

                    <section className="intel-panel">
                      <h4>Evidence</h4>
                      <ul>
                        <li>{selectedCase.document_count} document(s) indexed for this case.</li>
                        <li>
                          {caseDocuments.length
                            ? `Latest file: ${caseDocuments[0].filename}`
                            : "No file evidence currently attached."}
                        </li>
                      </ul>
                    </section>

                    <section className="intel-panel">
                      <h4>Missing information</h4>
                      <ul>
                        <li>{selectedCase.description ? "Case narrative available." : "Case narrative is still missing."}</li>
                        <li>
                          {pendingDocumentCount > 0
                            ? `${pendingDocumentCount} document(s) still processing.`
                            : "No pending document processing."}
                        </li>
                      </ul>
                    </section>

                    <section className="intel-panel">
                      <h4>Timeline</h4>
                      {caseTimeline.length ? (
                        <ul>
                          {caseTimeline.slice(0, 4).map((item) => (
                            <li key={item.id}>{item.title} - {formatDate(item.created_at)}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>No timeline events yet.</p>
                      )}
                    </section>

                    <section className="intel-panel">
                      <h4>Recommended actions</h4>
                      <ul>
                        <li>{selectedCase.next_recommended_step || "Request an update from your legal team."}</li>
                        <li>Use the AI assistant to ask for risk-focused next steps.</li>
                      </ul>
                    </section>
                  </div>
                ) : (
                  <p className="muted">Select a case from dashboard cards to load intelligence.</p>
                )}
              </article>

              <article className="card">
                <div className="section-head">
                  <div>
                    <h2>AI panel</h2>
                    <p>Case-safe assistant actions.</p>
                  </div>
                </div>
                <div className="suggestion-row vertical">
                  {ASSISTANT_SUGGESTIONS.map((prompt) => (
                    <button key={prompt} className="pill-button" onClick={() => void useSuggestion(prompt)} type="button">
                      {prompt}
                    </button>
                  ))}
                </div>
                <div className="result-panel">
                  <strong>Last assistant output</strong>
                  <p>{assistantAnswer}</p>
                </div>
              </article>
            </div>
          ) : null}

          {view === "documents" ? (
            <div className="document-viewer-grid">
              <article className="card">
                <div className="section-head">
                  <div>
                    <h2>Documents</h2>
                    <p>Select a file to inspect processing and insights.</p>
                  </div>
                </div>
                <div className="doc-list">
                  {visibleDocuments.length ? (
                    visibleDocuments.map((row) => (
                      <button
                        key={row.id}
                        className={`doc-item ${selectedDocument?.id === row.id ? "active" : ""}`}
                        onClick={() => setSelectedDocumentId(row.id)}
                        type="button"
                      >
                        <div>
                          <strong>{row.filename}</strong>
                          <small>
                            {formatBytes(row.file_size)} | {formatDate(row.upload_timestamp)}
                          </small>
                        </div>
                        <StatusBadge value={row.processing_status} />
                      </button>
                    ))
                  ) : (
                    <p className="muted">No document matches this search for the selected case.</p>
                  )}
                </div>
              </article>

              <article className="card document-viewer">
                <div className="section-head">
                  <div>
                    <h2>Document intelligence viewer</h2>
                    <p>Highlights, extracted entities, and AI-generated insights.</p>
                  </div>
                  <div className="quick-actions">
                    <button
                      className="btn ghost"
                      onClick={() => void useSuggestion("Summarize my case")}
                      type="button"
                    >
                      Summarize
                    </button>
                    <button
                      className="btn ghost"
                      onClick={() => void useSuggestion("Find key clauses")}
                      type="button"
                    >
                      Find clause
                    </button>
                    <button
                      className="btn ghost"
                      onClick={() => void useSuggestion("Compare this with other case documents")}
                      type="button"
                    >
                      Compare
                    </button>
                  </div>
                </div>

                {selectedDocument ? (
                  <>
                    <div className="viewer-headline">
                      <h3>{selectedDocument.filename}</h3>
                      <StatusBadge value={selectedDocument.processing_status} />
                    </div>

                    <div className="viewer-grid">
                      <section className="viewer-panel">
                        <h4>Highlighted clauses</h4>
                        <div className="clause-chip-row">
                          <span>Payment obligations</span>
                          <span>Termination condition</span>
                          <span>Jurisdiction clause</span>
                        </div>
                        <p className="muted">
                          Highlights are generated from ingestion metadata and legal extraction pipeline outputs.
                        </p>
                      </section>

                      <section className="viewer-panel">
                        <h4>Extracted entities</h4>
                        <ul>
                          <li>Case: {selectedCase?.title || "Unknown case"}</li>
                          <li>File type: {selectedDocument.file_type}</li>
                          <li>Uploaded: {formatDate(selectedDocument.upload_timestamp)}</li>
                          <li>Document size: {formatBytes(selectedDocument.file_size)}</li>
                        </ul>
                      </section>

                      <section className="viewer-panel">
                        <h4>AI insights</h4>
                        <p>{insights?.summary || "No summary available yet."}</p>
                        <p>{insights?.riskText || "Risk insights unavailable."}</p>
                        <ul>
                          {(insights?.dates || []).map((row) => (
                            <li key={row}>{row}</li>
                          ))}
                        </ul>
                      </section>
                    </div>
                  </>
                ) : (
                  <p className="muted">No document selected for this case.</p>
                )}
              </article>
            </div>
          ) : null}

          {view === "requests" ? (
            <div className="two-column-grid">
              <article className="card">
                <div className="section-head">
                  <div>
                    <h2>Submit consultation request</h2>
                    <p>Share issue details and upload supporting materials.</p>
                  </div>
                </div>

                <form className="request-form" onSubmit={handleIntakeSubmit}>
                  <label>
                    Issue summary
                    <textarea
                      required
                      value={intakeForm.issue_summary}
                      onChange={(event) =>
                        setIntakeForm((current) => ({ ...current, issue_summary: event.target.value }))
                      }
                    />
                  </label>

                  <label>
                    Detailed description
                    <textarea
                      value={intakeForm.case_description}
                      onChange={(event) =>
                        setIntakeForm((current) => ({ ...current, case_description: event.target.value }))
                      }
                    />
                  </label>

                  <label>
                    Preferred schedule
                    <input
                      placeholder="Example: Tuesday 3 PM"
                      value={intakeForm.preferred_schedule}
                      onChange={(event) =>
                        setIntakeForm((current) => ({ ...current, preferred_schedule: event.target.value }))
                      }
                    />
                  </label>

                  <div className="upload-panel-grid">
                    <label
                      className="upload-drop"
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={onDropVoice}
                    >
                      <span>Voice note upload</span>
                      <input
                        accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/mp3,audio/ogg"
                        onChange={(event) => setVoiceFile(event.target.files?.[0] ?? null)}
                        type="file"
                      />
                      <small>{voiceFile ? voiceFile.name : "Drag and drop or select file"}</small>
                    </label>

                    <div className="upload-drop action-drop">
                      <span>Record voice note</span>
                      <button
                        className="btn secondary"
                        onClick={() => void (recording ? stopRecording() : startRecording())}
                        type="button"
                      >
                        {recording ? "Stop recording" : "Record now"}
                      </button>
                      <small>{recording ? "Recording..." : voiceFile ? "Voice note ready" : "Optional"}</small>
                    </div>

                    <label
                      className="upload-drop"
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={onDropDocument}
                    >
                      <span>Supporting document</span>
                      <input
                        accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
                        onChange={(event) => setSupportingDocument(event.target.files?.[0] ?? null)}
                        type="file"
                      />
                      <small>{supportingDocument ? supportingDocument.name : "Drag and drop or select file"}</small>
                    </label>
                  </div>

                  <div className="pipeline-strip" aria-label="Upload pipeline">
                    <div className={`pipeline-step ${intakePipeline === "uploading" ? "active" : ""} ${intakePipeline !== "idle" ? "done" : ""}`}>
                      <span>1</span>
                      <strong>Uploading</strong>
                    </div>
                    <div className={`pipeline-step ${intakePipeline === "processing" ? "active" : ""} ${intakePipeline === "analyzed" ? "done" : ""}`}>
                      <span>2</span>
                      <strong>Processing</strong>
                    </div>
                    <div className={`pipeline-step ${intakePipeline === "analyzed" ? "active done" : ""}`}>
                      <span>3</span>
                      <strong>Analyzed</strong>
                    </div>
                  </div>

                  <button className="btn primary" disabled={submitLoading} type="submit">
                    {submitLoading ? "Submitting..." : "Submit consultation request"}
                  </button>
                </form>
              </article>

              <article className="card">
                <div className="section-head">
                  <div>
                    <h2>Request timeline</h2>
                    <p>All consultation updates linked to your account.</p>
                  </div>
                </div>

                <div className="timeline-vertical">
                  {dashboard.consultations.length ? (
                    dashboard.consultations.map((row) => (
                      <div key={row.id} className="timeline-entry">
                        <span className="timeline-dot" />
                        <div>
                          <div className="entry-top">
                            <strong>{row.case_title}</strong>
                            <StatusBadge value={row.status} />
                          </div>
                          <p>{row.issue_summary}</p>
                          <small>
                            Ref: {row.public_reference || "Pending"} | {formatDateTime(row.created_at)}
                          </small>
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="muted">No consultation requests yet.</p>
                  )}
                </div>
              </article>
            </div>
          ) : null}

          {view === "assistant" ? (
            <div className="assistant-layout">
              <article className="card">
                <div className="section-head">
                  <div>
                    <h2>Client assistant</h2>
                    <p>Ask for clear, non-technical legal guidance tied to your case data.</p>
                  </div>
                </div>

                <div className="suggestion-row">
                  {ASSISTANT_SUGGESTIONS.map((prompt) => (
                    <button key={prompt} className="pill-button" onClick={() => void useSuggestion(prompt)} type="button">
                      {prompt}
                    </button>
                  ))}
                </div>

                <form className="assistant-form" onSubmit={handleAssistantSubmit}>
                  <textarea
                    placeholder="Example: What are the current risks for my case?"
                    value={assistantPrompt}
                    onChange={(event) => setAssistantPrompt(event.target.value)}
                  />
                  <button className="btn primary" disabled={!assistantPrompt.trim() || assistantBusy} type="submit">
                    {assistantBusy ? "Analyzing..." : "Ask helper"}
                  </button>
                </form>
              </article>

              <article className="card">
                <div className="section-head">
                  <div>
                    <h3>Structured response</h3>
                    <p>AI output rendered in readable panels, not raw chat logs.</p>
                  </div>
                </div>
                <div className="assistant-response-grid">
                  <div className="response-card">
                    <span>Assistant response</span>
                    <p>{assistantAnswer}</p>
                  </div>
                </div>
              </article>
            </div>
          ) : null}

          {view === "profile" ? (
            <article className="card">
              <div className="section-head">
                <div>
                  <h2>Profile and account</h2>
                  <p>Secure account identity for this legal workspace.</p>
                </div>
              </div>

              <div className="profile-grid">
                <div className="profile-card">
                  <span>Name</span>
                  <strong>{dashboard.account.full_name}</strong>
                </div>
                <div className="profile-card">
                  <span>Email</span>
                  <strong>{dashboard.account.email}</strong>
                </div>
                <div className="profile-card">
                  <span>Firm</span>
                  <strong>{dashboard.account.tenant_name || "Law firm workspace"}</strong>
                </div>
                <div className="profile-card">
                  <span>Account created</span>
                  <strong>{formatDate(dashboard.account.created_at)}</strong>
                </div>
              </div>
            </article>
          ) : null}
        </main>

        <aside className="workspace-rail">
          <article className="card">
            <div className="section-head">
              <div>
                <h3>Quick lookup</h3>
                <p>Check any reference code instantly.</p>
              </div>
            </div>
            <form className="status-form" onSubmit={handleStatusLookup}>
              <input
                placeholder="Reference code"
                value={referenceInput}
                onChange={(event) => setReferenceInput(event.target.value)}
              />
              <button className="btn secondary" disabled={statusLoading} type="submit">
                {statusLoading ? "Checking..." : "Check"}
              </button>
            </form>
            <div className="result-panel">
              {statusResult ? (
                <>
                  <strong>{statusResult.public_reference}</strong>
                  <p>Status: {label(statusResult.status)}</p>
                  <p>Preferred schedule: {statusResult.preferred_schedule || "Not provided"}</p>
                  <p>Submitted: {formatDate(statusResult.created_at)}</p>
                </>
              ) : (
                <p>No lookup result yet.</p>
              )}
            </div>
          </article>

          <article className="card">
            <div className="section-head">
              <div>
                <h3>Priority checks</h3>
                <p>Calm visibility across your legal process.</p>
              </div>
            </div>
            <ul className="check-list">
              <li>{dashboard.metrics.active_cases} active case(s)</li>
              <li>{dashboard.metrics.pending_documents} document(s) still processing</li>
              <li>{dashboard.metrics.requests_under_review} request(s) under review</li>
              <li>{highRiskCount} case(s) flagged as high risk</li>
            </ul>
          </article>
        </aside>
      </section>

      {success ? <div className="banner success">{success}</div> : null}
      {error ? <div className="banner error">{error}</div> : null}
      {dashboardLoading ? <div className="inline-loading">Refreshing workspace data...</div> : null}
    </div>
  );
}