import { useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import type {
  CaseItem,
  CaseStatus,
  ChatMessage,
  Client,
  DocumentItem,
  FullDocumentAnalysis,
  SourceItem,
  User,
} from "./types";

const TOKEN_STORAGE_KEY = "legal-ai-platform-token";
const caseStatuses: CaseStatus[] = ["open", "in_progress", "closed", "archived"];

function nowIso() {
  return new Date().toISOString();
}

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

function formatBytes(size: number) {
  if (!size) {
    return "0 B";
  }

  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let index = 0;

  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }

  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`;
}

function buildWelcomeMessage(caseTitle?: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    timestamp: nowIso(),
    content: caseTitle
      ? `Workspace ready for "${caseTitle}". Ask for a case summary, deadlines, risks, or contradictions across uploaded evidence.`
      : "Select a case to start a grounded legal conversation. I can summarize cases, inspect documents, surface risks, and show evidence snippets.",
  };
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [selectedDocumentAnalysis, setSelectedDocumentAnalysis] = useState<FullDocumentAnalysis | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([buildWelcomeMessage()]);
  const [activeSources, setActiveSources] = useState<SourceItem[]>([]);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authForm, setAuthForm] = useState({
    name: "",
    email: "",
    password: "",
    tenant_name: "",
    role: "lawyer",
  });
  const [clientForm, setClientForm] = useState({
    name: "",
    email: "",
    phone: "",
    address: "",
  });
  const [caseForm, setCaseForm] = useState({
    title: "",
    description: "",
    status: "open" as CaseStatus,
    client_id: "",
  });
  const [chatInput, setChatInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedCase = useMemo(
    () => cases.find((item) => item.id === selectedCaseId) ?? null,
    [cases, selectedCaseId]
  );

  const selectedClient = useMemo(() => {
    if (!selectedCase) {
      return null;
    }
    return clients.find((item) => item.id === selectedCase.client_id) ?? null;
  }, [clients, selectedCase]);

  useEffect(() => {
    if (!token) {
      return;
    }

    void bootstrapWorkspace(token);
  }, [token]);

  async function bootstrapWorkspace(currentToken: string) {
    try {
      setWorkspaceLoading(true);
      setError(null);

      const [me, caseList, clientList] = await Promise.all([
        api.me(currentToken),
        api.listCases(currentToken),
        api.listClients(currentToken),
      ]);

      setUser(me);
      setCases(caseList);
      setClients(clientList);

      if (caseList.length > 0) {
        const firstCaseId = selectedCaseId && caseList.some((item) => item.id === selectedCaseId)
          ? selectedCaseId
          : caseList[0].id;
        await selectCase(currentToken, firstCaseId, caseList);
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Unable to initialize workspace.";
      setError(message);
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setToken(null);
    } finally {
      setWorkspaceLoading(false);
    }
  }

  async function selectCase(currentToken: string, caseId: number, availableCases = cases) {
    const targetCase = availableCases.find((item) => item.id === caseId) ?? null;

    setSelectedCaseId(caseId);
    setSelectedDocumentAnalysis(null);
    setSelectedDocumentId(null);
    setActiveSources([]);
    setChatMessages([buildWelcomeMessage(targetCase?.title)]);

    const docs = await api.listCaseDocuments(currentToken, caseId);
    setDocuments(docs);

    if (docs.length > 0) {
      await selectDocument(currentToken, docs[0].id, docs);
    }
  }

  async function selectDocument(
    currentToken: string,
    documentId: number,
    availableDocuments = documents
  ) {
    setSelectedDocumentId(documentId);
    const exists = availableDocuments.some((item) => item.id === documentId);

    if (!exists) {
      setSelectedDocumentAnalysis(null);
      return;
    }

    try {
      const analysis = await api.getDocumentAnalysis(currentToken, documentId);
      setSelectedDocumentAnalysis(analysis);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load document analysis.");
      setSelectedDocumentAnalysis(null);
    }
  }

  async function handleAuthSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthLoading(true);
    setError(null);

    try {
      if (authMode === "register") {
        await api.register(authForm);
      }

      const loginResponse = await api.login(authForm.email, authForm.password);
      localStorage.setItem(TOKEN_STORAGE_KEY, loginResponse.access_token);
      setToken(loginResponse.access_token);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed.");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleClientCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      return;
    }

    try {
      const createdClient = await api.createClient(token, clientForm);
      setClients((current) => [createdClient, ...current]);
      setClientForm({ name: "", email: "", phone: "", address: "" });
      setCaseForm((current) => ({ ...current, client_id: String(createdClient.id) }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create client.");
    }
  }

  async function handleCaseCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !caseForm.client_id) {
      return;
    }

    try {
      const createdCase = await api.createCase(token, {
        title: caseForm.title,
        description: caseForm.description,
        status: caseForm.status,
        client_id: Number(caseForm.client_id),
      });

      const nextCases = [createdCase, ...cases];
      setCases(nextCases);
      setCaseForm((current) => ({ ...current, title: "", description: "" }));
      await selectCase(token, createdCase.id, nextCases);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create case.");
    }
  }

  async function handleChatSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !chatInput.trim()) {
      return;
    }

    const input = chatInput.trim();
    setChatMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        timestamp: nowIso(),
        content: input,
      },
    ]);
    setChatInput("");
    setCopilotLoading(true);

    try {
      const scopedMessage = selectedCaseId ? `${input} for case #${selectedCaseId}` : input;
      const response = await api.copilot(token, scopedMessage);

      setChatMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          timestamp: nowIso(),
          content: response.answer,
          meta: {
            parsedIntent: response.parsed_intent,
            confidence: response.confidence,
            fallbackReason: response.fallback_reason,
            sources: response.sources,
          },
        },
      ]);
      setActiveSources(response.sources);

      const topSource = response.sources[0];
      if (topSource?.document_id) {
        await selectDocument(token, topSource.document_id);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Copilot request failed.");
    } finally {
      setCopilotLoading(false);
    }
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    if (!token || !selectedCaseId) {
      return;
    }

    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const uploadResult = await api.uploadDocument(token, selectedCaseId, file);
      const nextDocuments = [uploadResult.document, ...documents];
      setDocuments(nextDocuments);
      await selectDocument(token, uploadResult.document.id, nextDocuments);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setCases([]);
    setClients([]);
    setDocuments([]);
    setSelectedCaseId(null);
    setSelectedDocumentId(null);
    setSelectedDocumentAnalysis(null);
    setChatMessages([buildWelcomeMessage()]);
    setActiveSources([]);
  }

  if (!token || !user) {
    return (
      <div className="auth-shell">
        <div className="auth-panel">
          <div className="auth-hero">
            <div className="eyebrow">Case-Centric Legal AI</div>
            <h1>Grounded legal workspaces for cases, documents, and evidence-driven AI.</h1>
            <p>
              This frontend is shaped around your platform architecture: legal case management, document
              intelligence, and a copilot that stays tied to retrieved evidence.
            </p>
          </div>

          <div className="auth-card">
            <div className="auth-tabs">
              <button className={authMode === "login" ? "active" : ""} onClick={() => setAuthMode("login")} type="button">
                Login
              </button>
              <button
                className={authMode === "register" ? "active" : ""}
                onClick={() => setAuthMode("register")}
                type="button"
              >
                Register
              </button>
            </div>

            <form className="auth-form" onSubmit={handleAuthSubmit}>
              {authMode === "register" ? (
                <>
                  <label>
                    Full name
                    <input
                      value={authForm.name}
                      onChange={(event) => setAuthForm((current) => ({ ...current, name: event.target.value }))}
                      required
                    />
                  </label>
                  <label>
                    Tenant / firm name
                    <input
                      value={authForm.tenant_name}
                      onChange={(event) =>
                        setAuthForm((current) => ({ ...current, tenant_name: event.target.value }))
                      }
                      required
                    />
                  </label>
                  <label>
                    Role
                    <select
                      value={authForm.role}
                      onChange={(event) => setAuthForm((current) => ({ ...current, role: event.target.value }))}
                    >
                      <option value="lawyer">Lawyer</option>
                      <option value="assistant">Assistant</option>
                      <option value="admin">Admin</option>
                    </select>
                  </label>
                </>
              ) : null}

              <label>
                Email
                <input
                  type="email"
                  value={authForm.email}
                  onChange={(event) => setAuthForm((current) => ({ ...current, email: event.target.value }))}
                  required
                />
              </label>

              <label>
                Password
                <input
                  type="password"
                  value={authForm.password}
                  onChange={(event) => setAuthForm((current) => ({ ...current, password: event.target.value }))}
                  required
                />
              </label>

              <button className="primary-button" disabled={authLoading} type="submit">
                {authLoading ? "Working..." : authMode === "login" ? "Enter workspace" : "Create account"}
              </button>
            </form>

            {error ? <div className="error-banner">{error}</div> : null}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">LA</div>
          <div>
            <div className="eyebrow">Legal AI Workspace</div>
            <h2>Case-centric copilot</h2>
          </div>
        </div>

        <div className="panel compact">
          <div className="panel-header">
            <div>
              <h3>{user.name}</h3>
              <span>
                {user.role} | tenant #{user.tenant_id}
              </span>
            </div>
            <button className="ghost-button" onClick={logout} type="button">
              Logout
            </button>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div>
              <h3>Cases</h3>
              <span>{cases.length} active workspaces</span>
            </div>
          </div>
          <div className="case-list">
            {cases.map((item) => (
              <button
                key={item.id}
                className={`case-card ${selectedCaseId === item.id ? "selected" : ""}`}
                onClick={() => token && void selectCase(token, item.id)}
                type="button"
              >
                <span className="case-status">{item.status.replace("_", " ")}</span>
                <strong>{item.title}</strong>
                <small>{item.description || "No description provided."}</small>
              </button>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div>
              <h3>New client</h3>
              <span>Quick intake</span>
            </div>
          </div>
          <form className="stack-form" onSubmit={handleClientCreate}>
            <input
              placeholder="Client name"
              required
              value={clientForm.name}
              onChange={(event) => setClientForm((current) => ({ ...current, name: event.target.value }))}
            />
            <input
              placeholder="Email"
              value={clientForm.email}
              onChange={(event) => setClientForm((current) => ({ ...current, email: event.target.value }))}
            />
            <input
              placeholder="Phone"
              value={clientForm.phone}
              onChange={(event) => setClientForm((current) => ({ ...current, phone: event.target.value }))}
            />
            <input
              placeholder="Address"
              value={clientForm.address}
              onChange={(event) => setClientForm((current) => ({ ...current, address: event.target.value }))}
            />
            <button className="secondary-button" type="submit">
              Create client
            </button>
          </form>
        </div>

        <div className="panel">
          <div className="panel-header">
            <div>
              <h3>New case</h3>
              <span>Launch a workspace</span>
            </div>
          </div>
          <form className="stack-form" onSubmit={handleCaseCreate}>
            <input
              placeholder="Case title"
              required
              value={caseForm.title}
              onChange={(event) => setCaseForm((current) => ({ ...current, title: event.target.value }))}
            />
            <textarea
              placeholder="Short case description"
              value={caseForm.description}
              onChange={(event) => setCaseForm((current) => ({ ...current, description: event.target.value }))}
            />
            <select
              value={caseForm.client_id}
              onChange={(event) => setCaseForm((current) => ({ ...current, client_id: event.target.value }))}
              required
            >
              <option value="">Select client</option>
              {clients.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            <select
              value={caseForm.status}
              onChange={(event) =>
                setCaseForm((current) => ({ ...current, status: event.target.value as CaseStatus }))
              }
            >
              {caseStatuses.map((status) => (
                <option key={status} value={status}>
                  {status.replace("_", " ")}
                </option>
              ))}
            </select>
            <button className="secondary-button" type="submit">
              Create case
            </button>
          </form>
        </div>
      </aside>

      <main className="workspace">
        <section className="workspace-header">
          <div>
            <div className="eyebrow">Case workspace</div>
            <h1>{selectedCase?.title || "Select a case"}</h1>
            <p>{selectedCase?.description || "Use the left panel to open a case and start grounded legal work."}</p>
          </div>
          <div className="workspace-meta">
            <div className="meta-card">
              <span>Status</span>
              <strong>{selectedCase?.status.replace("_", " ") || "n/a"}</strong>
            </div>
            <div className="meta-card">
              <span>Client</span>
              <strong>{selectedClient?.name || "n/a"}</strong>
            </div>
            <div className="meta-card">
              <span>Documents</span>
              <strong>{documents.length}</strong>
            </div>
          </div>
        </section>

        {error ? <div className="error-banner">{error}</div> : null}

        <section className="workspace-grid">
          <div className="column column-main">
            <div className="panel hero-panel">
              <div className="panel-header">
                <div>
                  <h3>Case command center</h3>
                  <span>Summaries, grounded chat, and evidence review</span>
                </div>
              </div>

              <div className="hero-actions">
                <button
                  className="prompt-chip"
                  onClick={() => setChatInput(selectedCaseId ? `Summarize case #${selectedCaseId}` : "Summarize case")}
                  type="button"
                >
                  Summarize case
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setChatInput(selectedCaseId ? `List deadlines for case #${selectedCaseId}` : "List deadlines")}
                  type="button"
                >
                  Deadlines
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setChatInput(selectedCaseId ? `Analyze risks for case #${selectedCaseId}` : "Analyze risks")}
                  type="button"
                >
                  Risks
                </button>
                <button
                  className="prompt-chip"
                  onClick={() =>
                    setChatInput(
                      selectedCaseId ? `Compare documents in case #${selectedCaseId}` : "Compare the current case documents"
                    )
                  }
                  type="button"
                >
                  Compare docs
                </button>
              </div>
            </div>

            <div className="panel chat-panel">
              <div className="panel-header">
                <div>
                  <h3>Legal copilot</h3>
                  <span>Case-aware chat with evidence grounding</span>
                </div>
              </div>

              <div className="message-stream">
                {chatMessages.map((message) => (
                  <article key={message.id} className={`message ${message.role}`}>
                    <div className="message-avatar">{message.role === "assistant" ? "AI" : "You"}</div>
                    <div className="message-card">
                      <p>{message.content}</p>
                      {message.meta ? (
                        <div className="message-meta">
                          <span>Intent: {message.meta.parsedIntent || "n/a"}</span>
                          <span>Confidence: {message.meta.confidence || "n/a"}</span>
                          {message.meta.fallbackReason ? <span>Fallback: {message.meta.fallbackReason}</span> : null}
                        </div>
                      ) : null}
                    </div>
                  </article>
                ))}
                {copilotLoading ? <div className="loading-bar">Consulting the case copilot...</div> : null}
              </div>

              <form className="chat-composer" onSubmit={handleChatSubmit}>
                <textarea
                  placeholder="Ask grounded questions about this case, its deadlines, contradictions, or documents..."
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                />
                <button className="primary-button" disabled={copilotLoading || !selectedCaseId} type="submit">
                  Send
                </button>
              </form>
            </div>
          </div>

          <div className="column column-side">
            <div className="panel">
              <div className="panel-header">
                <div>
                  <h3>Documents</h3>
                  <span>AI-processed case materials</span>
                </div>
                <label className="upload-button">
                  {uploading ? "Uploading..." : "Upload PDF"}
                  <input accept="application/pdf" onChange={handleUpload} type="file" />
                </label>
              </div>

              <div className="document-list">
                {documents.map((document) => (
                  <button
                    key={document.id}
                    className={`document-card ${selectedDocumentId === document.id ? "selected" : ""}`}
                    onClick={() => token && void selectDocument(token, document.id)}
                    type="button"
                  >
                    <div className="document-topline">
                      <strong>{document.filename}</strong>
                      <span>{formatBytes(document.file_size)}</span>
                    </div>
                    <small>{document.processing_status}</small>
                    <small>{formatDate(document.upload_timestamp)}</small>
                  </button>
                ))}
              </div>
            </div>

            <div className="panel evidence-panel">
              <div className="panel-header">
                <div>
                  <h3>Document intelligence</h3>
                  <span>Structured extraction and summary</span>
                </div>
              </div>

              {workspaceLoading ? (
                <div className="loading-bar">Loading workspace...</div>
              ) : selectedDocumentAnalysis ? (
                <div className="analysis-stack">
                  <div className="metric-grid">
                    <div className="metric-card">
                      <span>Type</span>
                      <strong>{selectedDocumentAnalysis.document_type || "Unknown"}</strong>
                    </div>
                    <div className="metric-card">
                      <span>Entities</span>
                      <strong>{selectedDocumentAnalysis.entity_count}</strong>
                    </div>
                    <div className="metric-card">
                      <span>Summary</span>
                      <strong>{selectedDocumentAnalysis.summary_status}</strong>
                    </div>
                  </div>

                  <div className="analysis-block">
                    <h4>Short summary</h4>
                    <p>{selectedDocumentAnalysis.summary_short || "No summary generated yet."}</p>
                  </div>

                  <div className="analysis-block">
                    <h4>Entities</h4>
                    <div className="tag-cloud">
                      {selectedDocumentAnalysis.entities.slice(0, 12).map((entity, index) => (
                        <span key={`${entity.label}-${index}`} className="tag">
                          {entity.label}: {entity.value}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="analysis-block">
                    <h4>Redacted preview</h4>
                    <p>{selectedDocumentAnalysis.redacted_preview || "No preview available."}</p>
                  </div>
                </div>
              ) : (
                <div className="empty-state">Pick a document to inspect summaries, entities, and redacted previews.</div>
              )}
            </div>

            <div className="panel evidence-panel">
              <div className="panel-header">
                <div>
                  <h3>Evidence trail</h3>
                  <span>Sources returned by the copilot</span>
                </div>
              </div>

              {activeSources.length > 0 ? (
                <div className="source-list">
                  {activeSources.map((source, index) => (
                    <button
                      key={`${source.document_id}-${index}`}
                      className="source-card"
                      onClick={() => token && void selectDocument(token, source.document_id)}
                      type="button"
                    >
                      <strong>{source.filename}</strong>
                      <span>
                        {source.chunk_index !== null ? `Chunk ${source.chunk_index}` : "Document source"} | score {source.score.toFixed(2)}
                      </span>
                      <p>{source.snippet}</p>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state">Ask the copilot a question and its evidence snippets will appear here.</div>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
