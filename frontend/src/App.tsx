import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./lib/api";
import type {
  AgentWorkflowResponse,
  CaseItem,
  CaseStatus,
  ChatMessage,
  Client,
  ConsultationRequest,
  DocumentItem,
  FullDocumentAnalysis,
  ProviderStatusResponse,
  SourceItem,
  User,
  VoiceRecording,
} from "./types";

const TOKEN_STORAGE_KEY = "legal-ai-platform-token";
const THEME_STORAGE_KEY = "legal-ai-platform-theme";
const caseStatuses: CaseStatus[] = ["open", "in_progress", "closed", "archived"];
const CASE_REFERENCE_PATTERN = /\bcase\s*#?\s*(\d+)\b/i;

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

function looksLikeHtml(value?: string | null) {
  if (!value) {
    return false;
  }

  const normalized = value.trim().toLowerCase();
  return normalized.startsWith("<!doctype html") || normalized.startsWith("<html");
}

function getRecordingTranscriptDisplay(recording: VoiceRecording) {
  if (recording.transcription_status === "failed") {
    return (
      recording.transcription_error ||
      (looksLikeHtml(recording.transcript_text)
        ? "Transcription failed because the provider returned an HTML error page instead of text."
        : "Transcription failed.")
    );
  }

  if (recording.transcript_text && !looksLikeHtml(recording.transcript_text)) {
    return recording.transcript_text;
  }

  if (recording.transcription_error) {
    return recording.transcription_error;
  }

  return "Transcript not available yet.";
}

function getPreferredRecordingMimeType() {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
  ];

  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return "";
  }

  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function getAudioExtension(mimeType: string) {
  const normalized = mimeType.split(";")[0].trim().toLowerCase();

  if (normalized.includes("wav")) {
    return "wav";
  }
  if (normalized.includes("ogg")) {
    return "ogg";
  }
  if (normalized.includes("mp4") || normalized.includes("m4a")) {
    return "mp4";
  }
  if (normalized.includes("mpeg") || normalized.includes("mp3")) {
    return "mp3";
  }

  return "webm";
}

function encodeWavFromAudioBuffer(audioBuffer: AudioBuffer) {
  const channelCount = Math.min(audioBuffer.numberOfChannels, 2);
  const length = audioBuffer.length;
  const interleaved = new Float32Array(length * channelCount);

  for (let sampleIndex = 0; sampleIndex < length; sampleIndex += 1) {
    for (let channelIndex = 0; channelIndex < channelCount; channelIndex += 1) {
      interleaved[sampleIndex * channelCount + channelIndex] =
        audioBuffer.getChannelData(channelIndex)[sampleIndex];
    }
  }

  const bytesPerSample = 2;
  const blockAlign = channelCount * bytesPerSample;
  const buffer = new ArrayBuffer(44 + interleaved.length * bytesPerSample);
  const view = new DataView(buffer);

  function writeString(offset: number, value: string) {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  }

  writeString(0, "RIFF");
  view.setUint32(4, 36 + interleaved.length * bytesPerSample, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channelCount, true);
  view.setUint32(24, audioBuffer.sampleRate, true);
  view.setUint32(28, audioBuffer.sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, interleaved.length * bytesPerSample, true);

  let offset = 44;
  for (let index = 0; index < interleaved.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, interleaved[index]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

async function normalizeAudioFileToWav(file: File) {
  const context = new AudioContext();

  try {
    const arrayBuffer = await file.arrayBuffer();
    const audioBuffer = await context.decodeAudioData(arrayBuffer.slice(0));
    const wavBlob = encodeWavFromAudioBuffer(audioBuffer);
    const normalizedName = file.name.replace(/\.[^.]+$/, "") || `voice-note-${Date.now()}`;

    return new File([wavBlob], `${normalizedName}.wav`, {
      type: "audio/wav",
      lastModified: Date.now(),
    });
  } finally {
    await context.close();
  }
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

function inferAgentFromIntent(intent?: string) {
  if (!intent) {
    return "Copilot Core";
  }

  if (intent === "optimize_prompt") {
    return "Prompt Optimizer Agent";
  }
  if (intent === "build_timeline_case") {
    return "Timeline Agent";
  }
  if (intent === "review_booking_case") {
    return "Booking Agent";
  }
  if (intent === "compare_case_documents") {
    return "Document Comparison Agent";
  }
  if (intent === "draft_client_email_case") {
    return "Drafting Agent";
  }
  if (intent === "list_deadlines_case" || intent === "analyze_risks_case" || intent === "summarize_case") {
    return "Case Reasoning Agent";
  }
  if (intent === "summarize_document") {
    return "Summarization Agent";
  }
  if (intent.startsWith("ask_") || intent.startsWith("summarize_")) {
    return "RAG + External Research";
  }

  return "Copilot Core";
}

function extractSourceUrl(source: SourceItem) {
  const match = source.snippet.match(/https?:\/\/[^\s)]+/i);
  return match ? match[0] : null;
}

function extractReferencedCaseId(value: string) {
  const match = value.match(CASE_REFERENCE_PATTERN);
  if (!match) {
    return null;
  }
  const parsed = Number(match[1]);
  return Number.isInteger(parsed) ? parsed : null;
}

export default function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") {
      return stored;
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
  });
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [voiceRecordings, setVoiceRecordings] = useState<VoiceRecording[]>([]);
  const [consultationRequests, setConsultationRequests] = useState<ConsultationRequest[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [selectedRecordingId, setSelectedRecordingId] = useState<number | null>(null);
  const [selectedDocumentAnalysis, setSelectedDocumentAnalysis] = useState<FullDocumentAnalysis | null>(null);
  const [agentWorkflow, setAgentWorkflow] = useState<AgentWorkflowResponse | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([buildWelcomeMessage()]);
  const [activeSources, setActiveSources] = useState<SourceItem[]>([]);
  const [workflowObjective, setWorkflowObjective] = useState("");
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
  const [voiceUploading, setVoiceUploading] = useState(false);
  const [intakeBuilding, setIntakeBuilding] = useState(false);
  const [recordingAudio, setRecordingAudio] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [activeWorkspaceSection, setActiveWorkspaceSection] = useState<
    "workflow" | "intake" | "intelligence" | "evidence"
  >("workflow");
  const [useExternalResearch, setUseExternalResearch] = useState(true);
  const [retrievalDepth, setRetrievalDepth] = useState(5);
  const [providerStatus, setProviderStatus] = useState<ProviderStatusResponse | null>(null);
  const [providerLoading, setProviderLoading] = useState(false);
  const [llmSmokeOutput, setLlmSmokeOutput] = useState<string | null>(null);
  const [llmSmokeLoading, setLlmSmokeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);

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

  const selectedRecording = useMemo(
    () => voiceRecordings.find((item) => item.id === selectedRecordingId) ?? null,
    [voiceRecordings, selectedRecordingId]
  );

  const selectedConsultationRequest = useMemo(() => {
    if (!selectedRecordingId) {
      return consultationRequests[0] ?? null;
    }

    return (
      consultationRequests.find((item) => item.voice_recording_id === selectedRecordingId) ??
      consultationRequests[0] ??
      null
    );
  }, [consultationRequests, selectedRecordingId]);

  const selectedDocument = useMemo(
    () => documents.find((item) => item.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId]
  );

  const latestAssistantMessage = useMemo(
    () => [...chatMessages].reverse().find((item) => item.role === "assistant") ?? null,
    [chatMessages]
  );

  const activeIntent = latestAssistantMessage?.meta?.parsedIntent ?? null;
  const activeAgentName = inferAgentFromIntent(activeIntent ?? undefined);

  const externalResearchCount = useMemo(
    () => activeSources.filter((source) => source.document_id === null && Boolean(extractSourceUrl(source))).length,
    [activeSources]
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    if (!token) {
      return;
    }

    void bootstrapWorkspace(token);
  }, [token]);

  useEffect(() => {
    if (!token) {
      return;
    }

    void refreshProviderStatus(token);
  }, [token]);

  async function refreshProviderStatus(currentToken: string) {
    try {
      setProviderLoading(true);
      const status = await api.providerStatus(currentToken);
      setProviderStatus(status);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Unable to fetch provider status.";
      setProviderStatus(null);
      setError(message);
    } finally {
      setProviderLoading(false);
    }
  }

  async function runLlmSmokeTest() {
    if (!token) {
      return;
    }

    try {
      setLlmSmokeLoading(true);
      setError(null);
      const result = await api.testLlm(token, "Reply with OK and model family.");
      if (result.ok) {
        setLlmSmokeOutput(result.output || `OK from ${result.provider_name} (${result.model})`);
      } else {
        setLlmSmokeOutput(`Test failed: ${result.error || "Unknown provider error."}`);
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "LLM health check failed.";
      setLlmSmokeOutput(`Test failed: ${message}`);
      setError(message);
    } finally {
      setLlmSmokeLoading(false);
    }
  }

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
    setSelectedRecordingId(null);
    setConsultationRequests([]);
    setActiveSources([]);
    setAgentWorkflow(null);
    setChatMessages([buildWelcomeMessage(targetCase?.title)]);

    const [docs, recordings, requests] = await Promise.all([
      api.listCaseDocuments(currentToken, caseId),
      api.listVoiceRecordings(currentToken, caseId),
      api.listConsultationRequests(currentToken, caseId),
    ]);

    setDocuments(docs);
    setVoiceRecordings(recordings);
    setConsultationRequests(requests);

    if (recordings.length > 0) {
      setSelectedRecordingId(recordings[0].id);
    }

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

  async function submitCopilotPrompt() {
    if (!token || !chatInput.trim()) {
      return;
    }

    const input = chatInput.trim();
    const hasExplicitTarget = /\bcase\s*#?\s*\d+\b|\bdocument\s*#?\s*\d+\b/i.test(input);
    const scopedMessage = hasExplicitTarget || !selectedCaseId ? input : `${input} for case #${selectedCaseId}`;

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
      setError(null);
      const referencedCaseId = extractReferencedCaseId(scopedMessage);
      if (referencedCaseId && !cases.some((item) => item.id === referencedCaseId)) {
        const suggestion = selectedCaseId
          ? `Try running the same prompt with case #${selectedCaseId}.`
          : "Select a case from the sidebar first, then retry.";
        const validationMessage = `Case #${referencedCaseId} is not available in your workspace. ${suggestion}`;

        setChatMessages((current) => [
          ...current,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            timestamp: nowIso(),
            content: validationMessage,
            meta: {
              parsedIntent: "validation_error",
              confidence: "high",
              fallbackReason: "Invalid case id in prompt",
              sources: [],
            },
          },
        ]);
        setError(validationMessage);
        return;
      }

      const response = await api.copilot(token, scopedMessage, {
        topK: retrievalDepth,
        useExternalResearch,
      });

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
      setActiveWorkspaceSection("evidence");

      const topSource = response.sources[0];
      if (topSource?.document_id) {
        await selectDocument(token, topSource.document_id);
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Copilot request failed.";
      setError(message);
      setChatMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          timestamp: nowIso(),
          content: `I could not answer this request: ${message}${selectedCaseId ? `\n\nTip: try with case #${selectedCaseId} selected.` : ""}`,
          meta: {
            parsedIntent: "request_error",
            confidence: "low",
            fallbackReason: message,
            sources: [],
          },
        },
      ]);
    } finally {
      setCopilotLoading(false);
    }
  }

  async function handleChatSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitCopilotPrompt();
  }

  function handleChatInputKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      void submitCopilotPrompt();
    }
  }

  async function runAgentWorkflow() {
    if (!token || !selectedCaseId) {
      return;
    }

    try {
      setWorkflowLoading(true);
      setError(null);
      const response = await api.runAgentWorkflow(
        token,
        selectedCaseId,
        workflowObjective.trim() || undefined,
        retrievalDepth
      );
      setAgentWorkflow(response);
      setActiveSources(response.sources);
      setActiveWorkspaceSection("workflow");

      setChatMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          timestamp: nowIso(),
          content: response.verified_summary,
          meta: {
            parsedIntent: "agent_workflow",
            confidence: "high",
            fallbackReason: null,
            sources: response.sources,
          },
        },
      ]);

      const topSource = response.sources[0];
      if (topSource?.document_id) {
        await selectDocument(token, topSource.document_id);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to run the agent workflow.");
    } finally {
      setWorkflowLoading(false);
    }
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    if (!token) {
      return;
    }

    if (!selectedCaseId) {
      setError("Select a case first before uploading documents.");
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

  async function uploadVoiceFile(file: File) {
    if (!token) {
      return;
    }

    if (!selectedCaseId) {
      setError("Select a case first before uploading voice notes.");
      return;
    }

    setVoiceUploading(true);
    setError(null);

    try {
      const normalizedFile = await normalizeAudioFileToWav(file);
      const uploadResult = await api.uploadVoiceRecording(token, selectedCaseId, normalizedFile);
      const nextRecordings = [uploadResult.recording, ...voiceRecordings];
      setVoiceRecordings(nextRecordings);
      setSelectedRecordingId(uploadResult.recording.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Voice upload failed.");
    } finally {
      setVoiceUploading(false);
    }
  }

  async function buildConsultationFromSelectedRecording() {
    if (!token || !selectedRecordingId) {
      return;
    }

    setIntakeBuilding(true);
    setError(null);

    try {
      const response = await api.createConsultationFromRecording(token, selectedRecordingId);
      setConsultationRequests((current) => {
        const remaining = current.filter((item) => item.id !== response.consultation_request.id);
        return [response.consultation_request, ...remaining];
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to build consultation request.");
    } finally {
      setIntakeBuilding(false);
    }
  }

  async function handleVoiceUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    await uploadVoiceFile(file);
    event.target.value = "";
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser does not support microphone recording.");
      return;
    }

    if (!selectedCaseId) {
      setError("Select a case first before recording voice notes.");
      return;
    }

    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = getPreferredRecordingMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      mediaChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          mediaChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const resolvedMimeType = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(mediaChunksRef.current, { type: resolvedMimeType });
        const extension = getAudioExtension(blob.type || resolvedMimeType);
        const file = new File([blob], `voice-note-${Date.now()}.${extension}`, {
          type: blob.type || resolvedMimeType,
        });

        stream.getTracks().forEach((track) => track.stop());
        mediaRecorderRef.current = null;
        mediaChunksRef.current = [];
        setRecordingAudio(false);

        await uploadVoiceFile(file);
      };

      recorder.start();
      setRecordingAudio(true);
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
    setUser(null);
    setCases([]);
    setClients([]);
    setDocuments([]);
    setVoiceRecordings([]);
    setConsultationRequests([]);
    setSelectedCaseId(null);
    setSelectedDocumentId(null);
    setSelectedRecordingId(null);
    setSelectedDocumentAnalysis(null);
    setChatMessages([buildWelcomeMessage()]);
    setActiveSources([]);
    setProviderStatus(null);
    setLlmSmokeOutput(null);
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
            <div className="theme-row">
              <button
                className="ghost-button theme-toggle"
                onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
                type="button"
              >
                {theme === "dark" ? "Light mode" : "Dark mode"}
              </button>
            </div>

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
            <div className="eyebrow">Arbi Mostaissier</div>
            <h2>Case intelligence desk</h2>
          </div>
        </div>

        <div className="panel compact">
          <div className="panel-header">
            <div>
              <h3>{user.name}</h3>
              <span>
                {user.role} | internal legal workspace
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

        <div className="panel quick-ingest-panel">
          <div className="panel-header">
            <div>
              <h3>Quick uploads</h3>
              <span>{selectedCaseId ? `Attached to case #${selectedCaseId}` : "Select a case first"}</span>
            </div>
          </div>

          <div className="quick-ingest-actions">
            <label className="upload-button">
              {uploading ? "Uploading PDF..." : "Upload PDF"}
              <input accept="application/pdf" onChange={handleUpload} type="file" />
            </label>

            <label className="upload-button">
              {voiceUploading ? "Uploading audio..." : "Upload audio"}
              <input
                accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/mp3,audio/ogg"
                onChange={handleVoiceUpload}
                type="file"
              />
            </label>

            <button
              className="secondary-button"
              onClick={() => void (recordingAudio ? stopRecording() : startRecording())}
              type="button"
            >
              {recordingAudio ? "Stop recording" : "Record voice note"}
            </button>
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
        <section className="panel workspace-nav">
          <div className="workspace-nav-row">
            <div>
              <div className="eyebrow">AI runtime and orchestration controls</div>
              <h3>Copilot command bridge</h3>
              <p>
                Backend-aware command surface for Groq + retrieval + specialized legal agents.
              </p>
            </div>

            <div className="workspace-nav-controls">
              <button
                className="secondary-button theme-toggle"
                onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
                type="button"
              >
                {theme === "dark" ? "Light mode" : "Dark mode"}
              </button>

              <label className="toggle-control">
                <input
                  checked={useExternalResearch}
                  onChange={(event) => setUseExternalResearch(event.target.checked)}
                  type="checkbox"
                />
                External research
              </label>

              <label className="range-control">
                Retrieval depth
                <input
                  max={10}
                  min={3}
                  onChange={(event) => setRetrievalDepth(Number(event.target.value))}
                  type="range"
                  value={retrievalDepth}
                />
                <span>{retrievalDepth}</span>
              </label>

              <button
                className="secondary-button"
                disabled={providerLoading}
                onClick={() => token && void refreshProviderStatus(token)}
                type="button"
              >
                {providerLoading ? "Refreshing..." : "Refresh provider"}
              </button>

              <button
                className="secondary-button"
                disabled={llmSmokeLoading}
                onClick={() => void runLlmSmokeTest()}
                type="button"
              >
                {llmSmokeLoading ? "Testing..." : "Run LLM test"}
              </button>
            </div>
          </div>

          <div className="workspace-status-row">
            <div className="meta-card">
              <span>Provider</span>
              <strong>{providerStatus?.provider_name || "Unknown"}</strong>
            </div>
            <div className="meta-card">
              <span>Model</span>
              <strong>{providerStatus?.model || "Not configured"}</strong>
            </div>
            <div className="meta-card">
              <span>Summary model</span>
              <strong>{providerStatus?.summary_model || "Not configured"}</strong>
            </div>
            <div className="meta-card">
              <span>API key</span>
              <strong>{providerStatus?.key_present ? "Present" : "Missing"}</strong>
            </div>
            <div className="meta-card">
              <span>External references</span>
              <strong>{externalResearchCount}</strong>
            </div>
          </div>

          {llmSmokeOutput ? <div className="loading-bar">{llmSmokeOutput}</div> : null}
        </section>

        <section className="workspace-header">
          <div>
            <div className="eyebrow">Choose a matter and work from one command surface</div>
            <h1>{selectedCase?.title || "Select a case"}</h1>
            <p>
              {selectedCase?.description ||
                "Open a matter, then ask for summaries, risks, comparisons, timelines, or a client-ready draft."}
            </p>
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
            <div className="meta-card">
              <span>Voice notes</span>
              <strong>{voiceRecordings.length}</strong>
            </div>
            <div className="meta-card">
              <span>Focus file</span>
              <strong>{selectedDocument?.filename || "No document selected"}</strong>
            </div>
          </div>

          <div className="workspace-tabs">
            <button
              className={`tab-button ${activeWorkspaceSection === "workflow" ? "active" : ""}`}
              onClick={() => setActiveWorkspaceSection("workflow")}
              type="button"
            >
              Workflow
            </button>
            <button
              className={`tab-button ${activeWorkspaceSection === "intake" ? "active" : ""}`}
              onClick={() => setActiveWorkspaceSection("intake")}
              type="button"
            >
              Intake
            </button>
            <button
              className={`tab-button ${activeWorkspaceSection === "intelligence" ? "active" : ""}`}
              onClick={() => setActiveWorkspaceSection("intelligence")}
              type="button"
            >
              Intelligence
            </button>
            <button
              className={`tab-button ${activeWorkspaceSection === "evidence" ? "active" : ""}`}
              onClick={() => setActiveWorkspaceSection("evidence")}
              type="button"
            >
              Evidence
            </button>
          </div>
        </section>

        {error ? <div className="error-banner">{error}</div> : null}

        <section className="workspace-grid">
          <div className="column column-main">
            <div className="panel chat-panel">
              <div className="panel-header">
                <div>
                  <h3>Legal copilot</h3>
                  <span>Case-aware command center with evidence grounding</span>
                </div>
              </div>

              <div className="hero-actions context-chip-row">
                <button className="context-pill active" type="button">
                  {selectedCase ? selectedCase.title : "No case selected"}
                </button>
                <button className="context-pill" type="button">
                  {selectedClient ? selectedClient.name : "Client matter pending"}
                </button>
                <button className="context-pill" type="button">
                  {documents.length} documents
                </button>
                <button className="context-pill" type="button">
                  {voiceRecordings.length} voice notes
                </button>
                <button className="context-pill" type="button">
                  {activeSources.length} cited sources
                </button>
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
                <button
                  className="prompt-chip"
                  onClick={() =>
                    setChatInput(
                      selectedDocumentId
                        ? `Summarize document #${selectedDocumentId}`
                        : selectedCaseId
                          ? `Summarize case #${selectedCaseId}`
                          : "Summarize the selected document"
                    )
                  }
                  type="button"
                >
                  Summarize file
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setChatInput(selectedCaseId ? `Build timeline for case #${selectedCaseId}` : "Build timeline")}
                  type="button"
                >
                  Build timeline
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setChatInput(selectedCaseId ? `Review booking for case #${selectedCaseId}` : "Review booking")}
                  type="button"
                >
                  Booking review
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => setChatInput(selectedCaseId ? `Draft client email for case #${selectedCaseId}` : "Draft client email")}
                  type="button"
                >
                  Draft email
                </button>
                <button
                  className="prompt-chip"
                  onClick={() =>
                    setChatInput(
                      chatInput.trim()
                        ? `Optimize prompt: ${chatInput.trim()}`
                        : selectedCaseId
                          ? `Optimize prompt: Analyze risks for case #${selectedCaseId}`
                          : "Optimize prompt: Analyze litigation risks and next legal steps"
                    )
                  }
                  type="button"
                >
                  Optimize prompt
                </button>
              </div>

              <div className="agent-strip">
                <div className="agent-badge active">
                  <span>Primary agent</span>
                  <strong>{activeAgentName}</strong>
                </div>
                <div className="agent-badge">
                  <span>Detected intent</span>
                  <strong>{activeIntent || "none"}</strong>
                </div>
                <div className="agent-badge">
                  <span>Confidence</span>
                  <strong>{latestAssistantMessage?.meta?.confidence || "n/a"}</strong>
                </div>
                <div className="agent-badge">
                  <span>Fallback</span>
                  <strong>{latestAssistantMessage?.meta?.fallbackReason ? "yes" : "no"}</strong>
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
                          <span>Agent: {inferAgentFromIntent(message.meta.parsedIntent)}</span>
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

              <div className="composer-hint">
                Scope: {selectedCaseId ? `case #${selectedCaseId}` : "global"} | Retrieval depth: {retrievalDepth} |
                External research: {useExternalResearch ? "on" : "off"} | Tip: Ctrl/Cmd + Enter to send
              </div>
              {error ? <div className="error-banner inline-error">{error}</div> : null}

              <form className="chat-composer" onSubmit={handleChatSubmit}>
                <textarea
                  onKeyDown={handleChatInputKeyDown}
                  placeholder="Ask anything. Examples: 'Summarize case #1', 'Build timeline for case #1', 'Optimize prompt: draft a client update'."
                  value={chatInput}
                  onChange={(event) => {
                    if (error) {
                      setError(null);
                    }
                    setChatInput(event.target.value);
                  }}
                />
                <div className="command-actions">
                  <button
                    className="secondary-button"
                    disabled={!selectedCaseId || workflowLoading}
                    onClick={() => void runAgentWorkflow()}
                    type="button"
                  >
                    {workflowLoading ? "Running workflow..." : "Deep workflow"}
                  </button>
                  <button className="primary-button" disabled={copilotLoading || !selectedCaseId} type="submit">
                    Ask copilot
                  </button>
                </div>
              </form>
            </div>

            {activeWorkspaceSection === "workflow" ? (
              <div className="panel workflow-panel">
              <div className="panel-header">
                <div>
                  <h3>Agent workflow</h3>
                  <span>End-to-end orchestration across reasoning, verification, and drafting</span>
                </div>
              </div>

              <div className="workflow-objective">
                <textarea
                  onChange={(event) => setWorkflowObjective(event.target.value)}
                  placeholder="Optional workflow objective. Example: prepare negotiation strategy and client email for case hearing."
                  value={workflowObjective}
                />
                <button
                  className="secondary-button"
                  disabled={!selectedCaseId || workflowLoading}
                  onClick={() => void runAgentWorkflow()}
                  type="button"
                >
                  {workflowLoading ? "Running..." : "Run full workflow"}
                </button>
              </div>

              {agentWorkflow ? (
                  <div className="analysis-stack">
                    <div className="analysis-block">
                      <h4>Objective</h4>
                      <p>{agentWorkflow.objective}</p>
                    </div>

                    <div className="analysis-block">
                      <h4>Verified summary</h4>
                      <p>{agentWorkflow.verified_summary}</p>
                    </div>

                    <div className="analysis-block">
                      <h4>Client email draft</h4>
                      <p>{agentWorkflow.client_email}</p>
                    </div>

                    <div className="analysis-block">
                      <h4>Agent stages</h4>
                      <div className="workflow-stage-list">
                        {Object.entries(agentWorkflow.stages).map(([stageKey, stage]) => (
                          <div key={stageKey} className="workflow-stage-card">
                            <div className="workflow-stage-topline">
                              <strong>{stage.agent_name}</strong>
                              <span>{stage.success ? "ok" : "needs review"}</span>
                            </div>
                            {stage.warnings.length > 0 ? <p>Warnings: {stage.warnings.join(" | ")}</p> : null}
                            {stage.error ? <p>Error: {stage.error}</p> : null}
                            {stage.trace.length > 0 ? (
                              <div className="workflow-trace">
                                {stage.trace.map((item, index) => (
                                  <span key={`${stageKey}-${index}`}>{item}</span>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="empty-state">
                    Run the agent workflow to generate a verified case brief, inspect stage traces, and draft a client update.
                  </div>
                )}
              </div>
            ) : null}
          </div>

          <div className="column column-side">
            {activeWorkspaceSection === "workflow" ? (
              <div className="panel">
                <div className="empty-state">
                  Workflow details are shown below the copilot. Switch tabs to open intake, intelligence, or evidence tools.
                </div>
              </div>
            ) : null}

            <div className={`panel side-panel ${activeWorkspaceSection === "intake" ? "active" : "hidden"}`}>
              <div className="panel-header">
                <div>
                  <h3>Voice intake</h3>
                  <span>Case-linked recordings and transcripts</span>
                </div>
                <div className="voice-actions">
                  <button
                    className="secondary-button"
                    onClick={() => void (recordingAudio ? stopRecording() : startRecording())}
                    type="button"
                  >
                    {recordingAudio ? "Stop recording" : "Record"}
                  </button>
                  <label className="upload-button">
                    {voiceUploading ? "Uploading..." : "Upload audio"}
                    <input
                      accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/mp3,audio/ogg"
                      onChange={handleVoiceUpload}
                      type="file"
                    />
                  </label>
                </div>
              </div>

              <div className="voice-recording-list">
                {voiceRecordings.length > 0 ? (
                  voiceRecordings.map((recording) => (
                    <button
                      key={recording.id}
                      className={`document-card ${selectedRecordingId === recording.id ? "selected" : ""}`}
                      onClick={() => setSelectedRecordingId(recording.id)}
                      type="button"
                    >
                      <div className="document-topline">
                        <strong>{recording.filename}</strong>
                        <span>{formatBytes(recording.file_size)}</span>
                      </div>
                      <small>{recording.transcription_status}</small>
                      <small>{formatDate(recording.created_at)}</small>
                    </button>
                  ))
                ) : (
                  <div className="empty-state">
                    No voice intake yet. Record or upload audio to attach a transcript to this case.
                  </div>
                )}
              </div>

              {selectedRecording ? (
                <div className="analysis-block">
                  <h4>Transcript</h4>
                  <p>{getRecordingTranscriptDisplay(selectedRecording)}</p>
                  <div className="voice-actions inline-actions">
                    <button
                      className="secondary-button"
                      disabled={
                        intakeBuilding ||
                        selectedRecording.transcription_status !== "completed" ||
                        !selectedRecording.transcript_text
                      }
                      onClick={() => void buildConsultationFromSelectedRecording()}
                      type="button"
                    >
                      {intakeBuilding ? "Building intake..." : "Create intake request"}
                    </button>
                  </div>
                </div>
              ) : null}
            </div>

            <div className={`panel evidence-panel side-panel ${activeWorkspaceSection === "intake" ? "active" : "hidden"}`}>
              <div className="panel-header">
                <div>
                  <h3>Consultation intake</h3>
                  <span>Transcript-to-booking workflow</span>
                </div>
              </div>

              {selectedConsultationRequest ? (
                <div className="analysis-stack">
                  <div className="metric-grid">
                    <div className="metric-card">
                      <span>Status</span>
                      <strong>{selectedConsultationRequest.status}</strong>
                    </div>
                    <div className="metric-card">
                      <span>Booking</span>
                      <strong>{selectedConsultationRequest.booking_intent}</strong>
                    </div>
                    <div className="metric-card">
                      <span>Urgency</span>
                      <strong>{selectedConsultationRequest.urgency_level}</strong>
                    </div>
                  </div>

                  <div className="analysis-block">
                    <h4>Client details</h4>
                    <p>
                      {selectedConsultationRequest.client_name || "Unknown client"}
                      {selectedConsultationRequest.client_phone ? ` | ${selectedConsultationRequest.client_phone}` : ""}
                      {selectedConsultationRequest.client_email ? ` | ${selectedConsultationRequest.client_email}` : ""}
                    </p>
                  </div>

                  <div className="analysis-block">
                    <h4>Issue summary</h4>
                    <p>{selectedConsultationRequest.issue_summary}</p>
                  </div>

                  <div className="analysis-block">
                    <h4>Case description</h4>
                    <p>{selectedConsultationRequest.extracted_case_description || "No extracted description available."}</p>
                  </div>

                  <div className="analysis-block">
                    <h4>Booking details</h4>
                    <p>
                      Preferred schedule: {selectedConsultationRequest.preferred_schedule || "Not detected"}
                      <br />
                      Legal area: {selectedConsultationRequest.legal_area || "Not detected"}
                    </p>
                  </div>

                  <div className="analysis-block">
                    <h4>Intake notes</h4>
                    <p>{selectedConsultationRequest.intake_notes || "No additional intake notes."}</p>
                  </div>
                </div>
              ) : (
                <div className="empty-state">
                  Select a completed voice transcript and generate an intake request to extract booking and case details.
                </div>
              )}
            </div>

            <div className={`panel side-panel ${activeWorkspaceSection === "intelligence" ? "active" : "hidden"}`}>
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

            <div className={`panel evidence-panel side-panel ${activeWorkspaceSection === "intelligence" ? "active" : "hidden"}`}>
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

            <div className={`panel evidence-panel side-panel ${activeWorkspaceSection === "evidence" ? "active" : "hidden"}`}>
              <div className="panel-header">
                <div>
                  <h3>Evidence trail</h3>
                  <span>Sources returned by the copilot</span>
                </div>
              </div>

              {activeSources.length > 0 ? (
                <div className="source-list">
                  {activeSources.map((source, index) => (
                    <article key={`${source.document_id ?? "external"}-${index}`} className="source-card">
                      <strong>{source.filename}</strong>
                      <span>
                        {source.document_id
                          ? source.chunk_index !== null
                            ? `Document chunk ${source.chunk_index}`
                            : "Document source"
                          : "External research source"}{" "}
                        | score {source.score.toFixed(2)}
                      </span>
                      <p>{source.snippet}</p>
                      <div className="source-actions">
                        {source.document_id ? (
                          <button
                            className="secondary-button"
                            onClick={() => token && void selectDocument(token, source.document_id as number)}
                            type="button"
                          >
                            Open document
                          </button>
                        ) : null}
                        {extractSourceUrl(source) ? (
                          <a className="ghost-link" href={extractSourceUrl(source) || "#"} rel="noreferrer" target="_blank">
                            Open web source
                          </a>
                        ) : null}
                      </div>
                    </article>
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
