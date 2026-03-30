import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./lib/api";
import type {
  AgentWorkflowResponse,
  ArtifactContext,
  ArtifactVersion,
  CaseItem,
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
const UI_LANGUAGE_STORAGE_KEY = "legal-ai-platform-ui-language";
const SIDEBAR_COLLAPSED_STORAGE_KEY = "legal-ai-platform-sidebar-collapsed";
const CHAT_THREADS_STORAGE_KEY = "legal-ai-platform-chat-threads-v3";
const CASE_REFERENCE_PATTERN = /\bcase\s*#?\s*(\d+)\b/i;

type UiLanguage = "en" | "de" | "ar";

interface ChatThread {
  id: string;
  title: string;
  caseId: number | null;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

const UI_STRINGS: Record<UiLanguage, Record<string, string>> = {
  en: {
    appTitle: "Legal Copilot",
    newChat: "New chat",
    searchChats: "Search chats",
    chatHistory: "Chat history",
    noHistory: "No chats yet",
    askCopilot: "Ask copilot",
    processing: "Thinking...",
    placeholder: "Ask anything about your case, document, risks, deadlines, or drafting.",
    features: "Features",
    uploadPdf: "Upload document",
    uploadAudio: "Upload audio",
    recordVoice: "Record voice",
    stopRecording: "Stop recording",
    runWorkflow: "Run workflow",
    createCase: "Create case",
    createClient: "Create client",
    drafts: "Versioned drafts",
    refreshVersions: "Refresh versions",
    reviseWithAgent: "Revise with agent",
    saveVersion: "Save version",
    smartTranslation: "Smart translation",
  },
  de: {
    appTitle: "Legaler Copilot",
    newChat: "Neuer Chat",
    searchChats: "Chats suchen",
    chatHistory: "Chatverlauf",
    noHistory: "Noch keine Chats",
    askCopilot: "Copilot fragen",
    processing: "Denke nach...",
    placeholder: "Frage alles zu Fall, Dokument, Risiken, Fristen oder Entwürfen.",
    features: "Funktionen",
    uploadPdf: "Dokument hochladen",
    uploadAudio: "Audio hochladen",
    recordVoice: "Sprache aufnehmen",
    stopRecording: "Aufnahme stoppen",
    runWorkflow: "Workflow starten",
    createCase: "Fall erstellen",
    createClient: "Mandant erstellen",
    drafts: "Versionierte Entwürfe",
    refreshVersions: "Versionen aktualisieren",
    reviseWithAgent: "Mit Agent überarbeiten",
    saveVersion: "Version speichern",
    smartTranslation: "Semantische Übersetzung",
  },
  ar: {
    appTitle: "المساعد القانوني",
    newChat: "محادثة جديدة",
    searchChats: "ابحث في المحادثات",
    chatHistory: "سجل المحادثات",
    noHistory: "لا توجد محادثات بعد",
    askCopilot: "اسأل المساعد",
    processing: "جاري التفكير...",
    placeholder: "اسأل عن القضية أو المستند أو المخاطر أو المواعيد أو الصياغة.",
    features: "الميزات",
    uploadPdf: "رفع مستند",
    uploadAudio: "رفع صوت",
    recordVoice: "تسجيل صوت",
    stopRecording: "إيقاف التسجيل",
    runWorkflow: "تشغيل سير العمل",
    createCase: "إنشاء قضية",
    createClient: "إنشاء عميل",
    drafts: "المسودات بالإصدارات",
    refreshVersions: "تحديث الإصدارات",
    reviseWithAgent: "تحسين عبر الوكيل",
    saveVersion: "حفظ إصدار",
    smartTranslation: "ترجمة دلالية ذكية",
  },
};

const UI_BASE_COPY: Record<string, string> = {
  ...UI_STRINGS.en,
  cases: "Cases",
  documents: "Documents",
  voiceIntake: "Voice and intake",
  evidence: "Evidence",
  webResearch: "Web research",
  workflowMode: "Workflow mode",
  modeAgent: "Mode agent",
  soon: "Soon",
  on: "On",
  off: "Off",
  retrieval: "Retrieval",
  logout: "Logout",
  noClient: "No client",
  selectCaseFromSidebar: "Select a case from the sidebar",
  alwaysReady: "Always ready to support legal work.",
  noJurisdiction: "No jurisdiction",
  webSources: "web sources",
  loadingWorkspace: "Loading workspace...",
  workflowReady: "Workflow ready",
  focusedDocument: "Focused document",
  documentIntelligence: "Document intelligence",
  consultation: "Consultation",
  createIntakeRequest: "Create intake request",
  buildingIntake: "Building...",
  constitutionSource: "Constitution source",
  uploading: "Uploading...",
  running: "Running...",
  refreshing: "Refreshing...",
  noSummaryYet: "No summary available yet.",
  improvingPromptPlaceholder: "Tell the agent what to improve.",
  selectClient: "Select client",
  clientName: "Client name",
  caseTitle: "Case title",
  caseDescription: "Case description",
  phone: "Phone",
  address: "Address",
  status: "Status",
  jurisdiction: "Jurisdiction",
  tune: "Tune",
  transcribe: "Transcription",
  chooseClient: "Choose client",
  chooseCase: "Choose case",
  enterWorkspace: "Enter workspace",
  preparingWorkspace: "Preparing workspace...",
  noClientsAvailable: "No clients found. Create clients from the clients page first.",
  noCasesAvailable: "No cases found for this client. Create cases from the cases page first.",
  selectCaseToStart: "Select a case to start your copilot workspace.",
  workspaceSelection: "Workspace Selection",
  loginEyebrow: "Case-Centric Legal AI",
  loginTitle: "Grounded legal workspaces for cases, documents, and evidence-driven AI.",
  loginSubtitle: "Sign in to your legal workspace and run case-aware AI workflows.",
  lightMode: "Light mode",
  darkMode: "Dark mode",
  login: "Login",
  register: "Register",
  fullName: "Full name",
  firmName: "Tenant / firm name",
  role: "Role",
  lawyer: "Lawyer",
  assistant: "Assistant",
  admin: "Admin",
  email: "Email",
  password: "Password",
  working: "Working...",
  createAccount: "Create account",
  optimizePrompt: "Optimize prompt",
  optimizingPrompt: "Optimizing...",
  languageEnglish: "English",
  languageGerman: "Deutsch",
  languageArabic: "Arabic",
  collapseSidebar: "Collapse sidebar",
  expandSidebar: "Expand sidebar",
  noDate: "No date",
  you: "You",
};

const STATIC_UI_COPY: Record<UiLanguage, Record<string, string>> = {
  en: { ...UI_BASE_COPY },
  de: {
    ...UI_BASE_COPY,
    appTitle: "Legal Copilot",
    newChat: "Neuer Chat",
    searchChats: "Chats suchen",
    chatHistory: "Chatverlauf",
    noHistory: "Noch keine Chats",
    askCopilot: "Copilot fragen",
    processing: "Denke nach...",
    placeholder: "Frage etwas zu Fall, Dokument, Risiken, Fristen oder Entwurf.",
    features: "Funktionen",
    uploadPdf: "Dokument hochladen",
    uploadAudio: "Audio hochladen",
    recordVoice: "Sprache aufnehmen",
    stopRecording: "Aufnahme stoppen",
    runWorkflow: "Workflow ausfuehren",
    drafts: "Versionierte Entwuerfe",
    refreshVersions: "Versionen neu laden",
    reviseWithAgent: "Mit Agent ueberarbeiten",
    saveVersion: "Version speichern",
    smartTranslation: "Semantische Uebersetzung",
    cases: "Faelle",
    documents: "Dokumente",
    voiceIntake: "Sprache und Intake",
    evidence: "Belege",
    webResearch: "Web-Recherche",
    workflowMode: "Workflow-Modus",
    modeAgent: "Agent-Modus",
    soon: "Bald",
    on: "An",
    off: "Aus",
    retrieval: "Abruf",
    logout: "Abmelden",
    noClient: "Kein Mandant",
    selectCaseFromSidebar: "Waehle einen Fall in der Seitenleiste",
    alwaysReady: "Bereit fuer deine juristische Arbeit.",
    noJurisdiction: "Keine Zustaendigkeit",
    webSources: "Webquellen",
    loadingWorkspace: "Workspace wird geladen...",
    workflowReady: "Workflow bereit",
    focusedDocument: "Fokussiertes Dokument",
    documentIntelligence: "Dokumentanalyse",
    consultation: "Beratung",
    createIntakeRequest: "Intake-Anfrage erstellen",
    buildingIntake: "Wird erstellt...",
    constitutionSource: "Verfassungsquelle",
    uploading: "Wird hochgeladen...",
    running: "Laeuft...",
    refreshing: "Wird aktualisiert...",
    noSummaryYet: "Noch keine Zusammenfassung verfuegbar.",
    improvingPromptPlaceholder: "Sag dem Agenten, was verbessert werden soll.",
    selectClient: "Mandant waehlen",
    clientName: "Mandantenname",
    caseTitle: "Falltitel",
    caseDescription: "Fallbeschreibung",
    phone: "Telefon",
    address: "Adresse",
    status: "Status",
    jurisdiction: "Zustaendigkeit",
    transcribe: "Transkription",
    chooseClient: "Mandant waehlen",
    chooseCase: "Fall waehlen",
    enterWorkspace: "Workspace betreten",
    preparingWorkspace: "Workspace wird vorbereitet...",
    noClientsAvailable: "Keine Mandanten gefunden. Erstelle Mandanten zuerst auf der Mandanten-Seite.",
    noCasesAvailable: "Keine Faelle fuer diesen Mandanten. Erstelle Faelle zuerst auf der Faelle-Seite.",
    selectCaseToStart: "Waehle einen Fall, um den Copilot-Workspace zu starten.",
    workspaceSelection: "Workspace-Auswahl",
    loginEyebrow: "Fallzentrierte Legal AI",
    loginTitle: "Fundierte juristische Workspaces fuer Faelle, Dokumente und beweisbasierte KI.",
    loginSubtitle: "Melde dich an und arbeite mit fallbezogenen KI-Workflows.",
    lightMode: "Heller Modus",
    darkMode: "Dunkler Modus",
    login: "Anmelden",
    register: "Registrieren",
    fullName: "Vollstaendiger Name",
    firmName: "Kanzlei / Mandant",
    role: "Rolle",
    lawyer: "Anwalt",
    assistant: "Assistent",
    admin: "Admin",
    email: "E-Mail",
    password: "Passwort",
    working: "Bitte warten...",
    createAccount: "Konto erstellen",
    optimizePrompt: "Prompt optimieren",
    optimizingPrompt: "Wird optimiert...",
    languageEnglish: "Englisch",
    languageGerman: "Deutsch",
    languageArabic: "Arabisch",
    collapseSidebar: "Seitenleiste einklappen",
    expandSidebar: "Seitenleiste ausklappen",
    noDate: "Kein Datum",
    you: "Du",
  },
  ar: {
    ...UI_BASE_COPY,
    appTitle: "المساعد القانوني",
    newChat: "محادثة جديدة",
    searchChats: "ابحث في المحادثات",
    chatHistory: "سجل المحادثات",
    noHistory: "لا توجد محادثات بعد",
    askCopilot: "اسأل المساعد",
    processing: "جاري التفكير...",
    placeholder: "اسأل عن القضية أو المستند أو المخاطر أو المواعيد أو الصياغة.",
    features: "الميزات",
    uploadPdf: "رفع مستند",
    uploadAudio: "رفع صوت",
    recordVoice: "تسجيل صوت",
    stopRecording: "إيقاف التسجيل",
    runWorkflow: "تشغيل سير العمل",
    drafts: "المسودات بالإصدارات",
    refreshVersions: "تحديث الإصدارات",
    reviseWithAgent: "تحسين عبر الوكيل",
    saveVersion: "حفظ الإصدار",
    smartTranslation: "ترجمة دلالية ذكية",
    cases: "القضايا",
    documents: "المستندات",
    voiceIntake: "الصوت والاستقبال",
    evidence: "الأدلة",
    webResearch: "بحث الويب",
    workflowMode: "وضع سير العمل",
    modeAgent: "وضع الوكيل",
    soon: "قريبًا",
    on: "تشغيل",
    off: "إيقاف",
    retrieval: "الاسترجاع",
    logout: "تسجيل الخروج",
    noClient: "لا يوجد عميل",
    selectCaseFromSidebar: "اختر قضية من الشريط الجانبي",
    alwaysReady: "جاهز دائمًا لدعم العمل القانوني.",
    noJurisdiction: "لا توجد ولاية قضائية",
    webSources: "مصادر ويب",
    loadingWorkspace: "جاري تحميل مساحة العمل...",
    workflowReady: "سير العمل جاهز",
    focusedDocument: "المستند المحدد",
    documentIntelligence: "ذكاء المستند",
    consultation: "الاستشارة",
    createIntakeRequest: "إنشاء طلب استقبال",
    buildingIntake: "جاري الإنشاء...",
    constitutionSource: "مصدر الدستور",
    uploading: "جاري الرفع...",
    running: "جاري التشغيل...",
    refreshing: "جاري التحديث...",
    noSummaryYet: "لا يوجد ملخص حتى الآن.",
    improvingPromptPlaceholder: "أخبر الوكيل بما تريد تحسينه.",
    selectClient: "اختر العميل",
    clientName: "اسم العميل",
    caseTitle: "عنوان القضية",
    caseDescription: "وصف القضية",
    phone: "الهاتف",
    address: "العنوان",
    status: "الحالة",
    jurisdiction: "الولاية القضائية",
    transcribe: "التفريغ الصوتي",
    chooseClient: "اختر العميل",
    chooseCase: "اختر القضية",
    enterWorkspace: "دخول مساحة العمل",
    preparingWorkspace: "جاري تجهيز مساحة العمل...",
    noClientsAvailable: "لا يوجد عملاء. أنشئ العملاء أولًا من صفحة العملاء.",
    noCasesAvailable: "لا توجد قضايا لهذا العميل. أنشئ القضايا أولًا من صفحة القضايا.",
    selectCaseToStart: "اختر قضية لبدء مساحة عمل المساعد.",
    workspaceSelection: "اختيار مساحة العمل",
    loginEyebrow: "ذكاء قانوني متمحور حول القضية",
    loginTitle: "مساحات عمل قانونية مدعومة بالأدلة للقضايا والمستندات والذكاء الاصطناعي.",
    loginSubtitle: "سجّل الدخول وشغّل سير عمل ذكاء اصطناعي مرتبطًا بالقضية.",
    lightMode: "الوضع الفاتح",
    darkMode: "الوضع الداكن",
    login: "تسجيل الدخول",
    register: "إنشاء حساب",
    fullName: "الاسم الكامل",
    firmName: "المكتب / المؤسسة",
    role: "الدور",
    lawyer: "محامٍ",
    assistant: "مساعد",
    admin: "مشرف",
    email: "البريد الإلكتروني",
    password: "كلمة المرور",
    working: "جاري العمل...",
    createAccount: "إنشاء حساب",
    optimizePrompt: "تحسين الطلب",
    optimizingPrompt: "جارٍ التحسين...",
    languageEnglish: "الإنجليزية",
    languageGerman: "الألمانية",
    languageArabic: "العربية",
    collapseSidebar: "طي الشريط الجانبي",
    expandSidebar: "إظهار الشريط الجانبي",
    noDate: "بدون تاريخ",
    you: "أنت",
  },
};
function nowIso() {
  return new Date().toISOString();
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

function normalizeForSearch(value: string) {
  return value.toLowerCase().replace(/\s+/g, " ").trim();
}

function deriveThreadTitle(messages: ChatMessage[], fallback = "New chat") {
  const firstUser = messages.find((item) => item.role === "user");
  if (!firstUser?.content) return fallback;
  const compact = firstUser.content.replace(/\s+/g, " ").trim();
  return compact.length > 48 ? `${compact.slice(0, 48)}...` : compact;
}

function looksLikeHtml(value?: string | null) {
  if (!value) return false;
  const normalized = value.trim().toLowerCase();
  return normalized.startsWith("<!doctype html") || normalized.startsWith("<html");
}

function getRecordingTranscriptDisplay(recording: VoiceRecording) {
  if (recording.transcription_status === "failed") {
    return (
      recording.transcription_error ||
      (looksLikeHtml(recording.transcript_text)
        ? "Transcription failed because provider returned HTML instead of transcript text."
        : "Transcription failed.")
    );
  }
  if (recording.transcript_text && !looksLikeHtml(recording.transcript_text)) return recording.transcript_text;
  if (recording.transcription_error) return recording.transcription_error;
  return "Transcript not available yet.";
}

function getPreferredRecordingMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg", "audio/mp4"];
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return "";
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function getAudioExtension(mimeType: string) {
  const normalized = mimeType.split(";")[0].trim().toLowerCase();
  if (normalized.includes("wav")) return "wav";
  if (normalized.includes("ogg")) return "ogg";
  if (normalized.includes("mp4") || normalized.includes("m4a")) return "mp4";
  if (normalized.includes("mpeg") || normalized.includes("mp3")) return "mp3";
  return "webm";
}

function encodeWavFromAudioBuffer(audioBuffer: AudioBuffer) {
  const channelCount = Math.min(audioBuffer.numberOfChannels, 2);
  const length = audioBuffer.length;
  const interleaved = new Float32Array(length * channelCount);
  for (let sampleIndex = 0; sampleIndex < length; sampleIndex += 1) {
    for (let channelIndex = 0; channelIndex < channelCount; channelIndex += 1) {
      interleaved[sampleIndex * channelCount + channelIndex] = audioBuffer.getChannelData(channelIndex)[sampleIndex];
    }
  }

  const bytesPerSample = 2;
  const blockAlign = channelCount * bytesPerSample;
  const buffer = new ArrayBuffer(44 + interleaved.length * bytesPerSample);
  const view = new DataView(buffer);
  const writeString = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) view.setUint8(offset + index, value.charCodeAt(index));
  };

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
    return new File([wavBlob], `${normalizedName}.wav`, { type: "audio/wav", lastModified: Date.now() });
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
      ? `Workspace ready for "${caseTitle}". Ask for summaries, risks, timelines, or draft updates.`
      : "Select a case to start. I can summarize cases, inspect documents, surface risks, and draft client updates.",
  };
}

function inferAgentFromIntent(intent?: string) {
  if (!intent) return "Copilot Core";
  if (intent === "optimize_prompt") return "Prompt Optimizer Agent";
  if (intent === "build_timeline_case") return "Timeline Agent";
  if (intent === "review_booking_case") return "Booking Agent";
  if (intent === "compare_case_documents") return "Document Comparison Agent";
  if (intent === "draft_client_email_case") return "Drafting Agent";
  if (intent === "list_deadlines_case" || intent === "analyze_risks_case" || intent === "summarize_case" || intent === "summarize_and_analyze_risks_case") return "Case Reasoning Agent";
  if (intent === "summarize_document") return "Summarization Agent";
  if (intent.startsWith("ask_") || intent.startsWith("summarize_")) return "RAG + External Research";
  return "Copilot Core";
}

function extractSourceUrl(source: SourceItem) {
  const match = source.snippet.match(/https?:\/\/[^\s)]+/i);
  return match ? match[0] : null;
}

function extractReferencedCaseId(value: string) {
  const match = value.match(CASE_REFERENCE_PATTERN);
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isInteger(parsed) ? parsed : null;
}

function formatJurisdictionCountry(country?: string | null) {
  if (!country) return "Tunisia";
  if (country === "germany") return "Germany";
  return "Tunisia";
}

type ComposerMenuIcon = "agent" | "web" | "document" | "audio" | "record" | "workflow";

function MenuIcon({ icon }: { icon: ComposerMenuIcon }) {
  const shared = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "menu-item-icon",
    "aria-hidden": true,
  };

  if (icon === "agent") {
    return (
      <svg {...shared}>
        <path d="M12 3l1.9 4.2L18 9l-4.1 1.8L12 15l-1.9-4.2L6 9l4.1-1.8L12 3z" />
        <circle cx="18.5" cy="5.5" r="1.5" />
      </svg>
    );
  }
  if (icon === "web") {
    return (
      <svg {...shared}>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a15 15 0 010 18M12 3a15 15 0 000 18" />
      </svg>
    );
  }
  if (icon === "document") {
    return (
      <svg {...shared}>
        <path d="M14 2H7a2 2 0 00-2 2v16a2 2 0 002 2h10a2 2 0 002-2V7z" />
        <path d="M14 2v5h5M9 13h6M9 17h6" />
      </svg>
    );
  }
  if (icon === "audio") {
    return (
      <svg {...shared}>
        <path d="M11 5L6 9v6l5 4V5zM15 9.5a4 4 0 010 5M17.7 7a7.5 7.5 0 010 10" />
      </svg>
    );
  }
  if (icon === "record") {
    return (
      <svg {...shared}>
        <rect x="8" y="3.5" width="8" height="12" rx="4" />
        <path d="M5 11.5a7 7 0 0014 0M12 18.5V21" />
      </svg>
    );
  }
  return (
    <svg {...shared}>
      <path d="M4 12h16M12 4v16" />
      <circle cx="12" cy="12" r="9" />
    </svg>
  );
}

type SidebarIconName = "toggle" | "chat" | "history" | "cases" | "features" | "document" | "audio" | "evidence";

function SidebarIcon({ icon }: { icon: SidebarIconName }) {
  const shared = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "sidebar-icon",
    "aria-hidden": true,
  };

  if (icon === "toggle") {
    return (
      <svg {...shared}>
        <path d="M9 4h11M9 12h11M9 20h11" />
        <path d="M4 4v16" />
      </svg>
    );
  }
  if (icon === "chat") {
    return (
      <svg {...shared}>
        <path d="M21 12a8 8 0 01-8 8H6l-3 2 1-4A8 8 0 1112 4h1a8 8 0 018 8z" />
      </svg>
    );
  }
  if (icon === "history") {
    return (
      <svg {...shared}>
        <path d="M3 12a9 9 0 109-9" />
        <path d="M3 4v4h4M12 7v5l3 2" />
      </svg>
    );
  }
  if (icon === "cases") {
    return (
      <svg {...shared}>
        <path d="M4 6h16v12H4z" />
        <path d="M9 6V4h6v2M8 11h8M8 15h5" />
      </svg>
    );
  }
  if (icon === "features") {
    return (
      <svg {...shared}>
        <path d="M12 3l2.6 5.2L20 9l-4 3.9L17 20l-5-2.8L7 20l1-7.1L4 9l5.4-.8L12 3z" />
      </svg>
    );
  }
  if (icon === "document") {
    return (
      <svg {...shared}>
        <path d="M14 2H7a2 2 0 00-2 2v16a2 2 0 002 2h10a2 2 0 002-2V7z" />
        <path d="M14 2v5h5M9 13h6M9 17h6" />
      </svg>
    );
  }
  if (icon === "audio") {
    return (
      <svg {...shared}>
        <path d="M11 5L6 9v6l5 4V5zM15 9.5a4 4 0 010 5M17.7 7a7.5 7.5 0 010 10" />
      </svg>
    );
  }
  return (
    <svg {...shared}>
      <path d="M4 12h16" />
      <path d="M12 4v16" />
      <circle cx="12" cy="12" r="9" />
    </svg>
  );
}

export default function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
  });
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>(() => {
    const stored = localStorage.getItem(UI_LANGUAGE_STORAGE_KEY);
    if (stored === "de" || stored === "ar" || stored === "en") return stored;
    return "en";
  });
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "1");
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

  const [chatThreads, setChatThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([buildWelcomeMessage()]);
  const [historyQuery, setHistoryQuery] = useState("");
  const [chatInput, setChatInput] = useState("");

  const [activeSources, setActiveSources] = useState<SourceItem[]>([]);
  const [useExternalResearch, setUseExternalResearch] = useState(false);
  const [workflowFromPrompt, setWorkflowFromPrompt] = useState(false);
  const [retrievalDepth, setRetrievalDepth] = useState(5);
  const [workflowObjective, setWorkflowObjective] = useState("");

  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authForm, setAuthForm] = useState({
    name: "",
    email: "",
    password: "",
    tenant_name: "",
    role: "lawyer",
  });
  const [workspaceEntered, setWorkspaceEntered] = useState(false);
  const [workspaceClientId, setWorkspaceClientId] = useState<number | null>(null);
  const [workspaceCaseId, setWorkspaceCaseId] = useState<number | null>(null);
  const [workspaceSelecting, setWorkspaceSelecting] = useState(false);

  const [uploading, setUploading] = useState(false);
  const [voiceUploading, setVoiceUploading] = useState(false);
  const [recordingAudio, setRecordingAudio] = useState(false);
  const [intakeBuilding, setIntakeBuilding] = useState(false);

  const [authLoading, setAuthLoading] = useState(false);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [showComposerMenu, setShowComposerMenu] = useState(false);
  const [agentModeEnabled, setAgentModeEnabled] = useState(false);
  const [optimizingPrompt, setOptimizingPrompt] = useState(false);
  const [semanticTranslationBusy, setSemanticTranslationBusy] = useState(false);

  const [providerStatus, setProviderStatus] = useState<ProviderStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [artifactContext, setArtifactContext] = useState<ArtifactContext | null>(null);
  const [artifactVersions, setArtifactVersions] = useState<ArtifactVersion[]>([]);
  const [artifactEditorContent, setArtifactEditorContent] = useState("");
  const [artifactInstruction, setArtifactInstruction] = useState("");
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactSaving, setArtifactSaving] = useState(false);
  const [translationCache, setTranslationCache] = useState<Record<string, string>>({});
  const [localizedUiCopy, setLocalizedUiCopy] = useState<Record<string, string>>(UI_BASE_COPY);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);
  const documentUploadInputRef = useRef<HTMLInputElement | null>(null);
  const audioUploadInputRef = useRef<HTMLInputElement | null>(null);
  const languageSwitchInitializedRef = useRef(false);

  const t = (key: string, fallback: string) => localizedUiCopy[key] || UI_BASE_COPY[key] || fallback;
  const dateLocale = uiLanguage === "de" ? "de-DE" : uiLanguage === "ar" ? "ar-TN" : "en-US";
  const formatUiDate = (value?: string | null) => {
    if (!value) return t("noDate", "No date");
    try {
      return new Intl.DateTimeFormat(dateLocale, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(new Date(value));
    } catch {
      return t("noDate", "No date");
    }
  };

  const selectedCase = useMemo(() => cases.find((item) => item.id === selectedCaseId) ?? null, [cases, selectedCaseId]);
  const selectedClient = useMemo(() => {
    if (!selectedCase) return null;
    return clients.find((item) => item.id === selectedCase.client_id) ?? null;
  }, [clients, selectedCase]);
  const casesForWorkspaceClient = useMemo(() => {
    if (!workspaceClientId) return [];
    return cases.filter((item) => item.client_id === workspaceClientId);
  }, [cases, workspaceClientId]);
  const selectedDocument = useMemo(() => documents.find((item) => item.id === selectedDocumentId) ?? null, [documents, selectedDocumentId]);
  const selectedRecording = useMemo(() => voiceRecordings.find((item) => item.id === selectedRecordingId) ?? null, [voiceRecordings, selectedRecordingId]);
  const selectedConsultationRequest = useMemo(() => {
    if (!selectedRecordingId) return consultationRequests[0] ?? null;
    return (
      consultationRequests.find((item) => item.voice_recording_id === selectedRecordingId) ??
      consultationRequests[0] ??
      null
    );
  }, [consultationRequests, selectedRecordingId]);
  const latestAssistantMessage = useMemo(() => [...chatMessages].reverse().find((item) => item.role === "assistant") ?? null, [chatMessages]);
  const activeAgentName = inferAgentFromIntent(latestAssistantMessage?.meta?.parsedIntent);
  const externalResearchCount = useMemo(
    () => activeSources.filter((source) => source.document_id === null && Boolean(extractSourceUrl(source))).length,
    [activeSources]
  );
  const filteredThreads = useMemo(() => {
    const needle = normalizeForSearch(historyQuery);
    if (!needle) return chatThreads;
    return chatThreads.filter((thread) => {
      if (normalizeForSearch(thread.title).includes(needle)) return true;
      return thread.messages.some((message) => normalizeForSearch(message.content).includes(needle));
    });
  }, [chatThreads, historyQuery]);
  const inConversationMode = useMemo(() => copilotLoading || chatMessages.some((item) => item.role === "user"), [chatMessages, copilotLoading]);
  const activeJurisdiction = useMemo(() => {
    const fromMessage = latestAssistantMessage?.meta?.jurisdiction;
    if (fromMessage) return fromMessage;
    if (!selectedCase) return null;
    return {
      country_code: selectedCase.jurisdiction_country,
      country_display_name: formatJurisdictionCountry(selectedCase.jurisdiction_country),
      constitutional_references: [],
      legal_guardrails: [],
      risk_focus_areas: [],
    };
  }, [latestAssistantMessage, selectedCase]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, uiLanguage);
    document.documentElement.setAttribute("dir", uiLanguage === "ar" ? "rtl" : "ltr");
  }, [uiLanguage]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (!languageSwitchInitializedRef.current) {
      languageSwitchInitializedRef.current = true;
      return;
    }
    if (!token || !selectedCaseId) return;
    startNewChat();
  }, [uiLanguage]);

  useEffect(() => {
    function hydrateUiCopy() {
      const staticFallback = STATIC_UI_COPY[uiLanguage] || UI_BASE_COPY;
      setLocalizedUiCopy(staticFallback);
    }

    hydrateUiCopy();
  }, [uiLanguage]);

  useEffect(() => {
    if (!token || uiLanguage === "en") return;

    const candidateTexts: string[] = [];
    const addCandidate = (text?: string | null) => {
      const cleaned = (text || "").trim();
      if (!cleaned) return;
      candidateTexts.push(cleaned.length > 900 ? `${cleaned.slice(0, 900)}...` : cleaned);
    };

    addCandidate(selectedCase?.title);
    addCandidate(selectedCase?.description);
    addCandidate(selectedDocumentAnalysis?.summary_short);
    addCandidate(selectedConsultationRequest?.issue_summary);
    addCandidate(selectedRecording?.transcript_text);
    addCandidate(error);
    activeSources.slice(0, 8).forEach((source) => addCandidate(source.snippet));
    chatMessages
      .filter((message) => message.role === "assistant")
      .slice(-6)
      .forEach((message) => addCandidate(message.content));

    if (candidateTexts.length === 0) return;
    const deduped = [...new Set(candidateTexts)].slice(0, 24);
    void translateSemantically(deduped, "legal_content");
  }, [
    activeSources,
    chatMessages,
    selectedCase?.description,
    selectedCase?.title,
    selectedConsultationRequest?.issue_summary,
    selectedDocumentAnalysis?.summary_short,
    selectedRecording?.transcript_text,
    error,
    token,
    uiLanguage,
  ]);

  useEffect(() => {
    if (!token) return;
    void bootstrapWorkspace(token);
  }, [token]);

  useEffect(() => {
    if (!token) return;
    void refreshProviderStatus(token);
  }, [token]);

  useEffect(() => {
    if (!user) {
      setChatThreads([]);
      setActiveThreadId(null);
      return;
    }
    try {
      const payload = JSON.parse(localStorage.getItem(CHAT_THREADS_STORAGE_KEY) || "{}") as Record<string, ChatThread[]>;
      const ownerKey = `${user.tenant_id}:${user.id}`;
      const rows = Array.isArray(payload[ownerKey]) ? payload[ownerKey] : [];
      setChatThreads(rows);
      if (rows.length > 0) {
        const latest = [...rows].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0];
        setActiveThreadId(latest.id);
        setChatMessages(latest.messages);
      }
    } catch {
      setChatThreads([]);
    }
  }, [user]);

  useEffect(() => {
    if (!user) return;
    const ownerKey = `${user.tenant_id}:${user.id}`;
    let payload: Record<string, ChatThread[]> = {};
    try {
      payload = JSON.parse(localStorage.getItem(CHAT_THREADS_STORAGE_KEY) || "{}") as Record<string, ChatThread[]>;
    } catch {
      payload = {};
    }
    payload[ownerKey] = chatThreads;
    localStorage.setItem(CHAT_THREADS_STORAGE_KEY, JSON.stringify(payload));
  }, [chatThreads, user]);

  useEffect(() => {
    if (!activeThreadId) return;
    setChatThreads((current) =>
      current.map((thread) =>
        thread.id === activeThreadId
          ? { ...thread, messages: chatMessages, title: deriveThreadTitle(chatMessages, thread.title), updatedAt: nowIso() }
          : thread
      )
    );
  }, [chatMessages, activeThreadId]);

  function createThread(options?: { caseId?: number | null; title?: string; messages?: ChatMessage[] }) {
    const thread: ChatThread = {
      id: crypto.randomUUID(),
      title: options?.title || t("newChat", "New chat"),
      caseId: options?.caseId ?? selectedCaseId ?? null,
      messages: options?.messages || [buildWelcomeMessage(selectedCase?.title)],
      createdAt: nowIso(),
      updatedAt: nowIso(),
    };
    setChatThreads((current) => [thread, ...current]);
    setActiveThreadId(thread.id);
    setChatMessages(thread.messages);
    return thread;
  }

  function openThread(threadId: string) {
    const thread = chatThreads.find((item) => item.id === threadId);
    if (!thread) return;
    setActiveThreadId(thread.id);
    setChatMessages(thread.messages);
    if (thread.caseId && token && thread.caseId !== selectedCaseId) {
      void selectCase(token, thread.caseId, undefined, true);
    }
  }

  function startNewChat() {
    createThread({
      caseId: selectedCaseId ?? null,
      title: t("newChat", "New chat"),
      messages: [buildWelcomeMessage(selectedCase?.title)],
    });
  }

  async function translateSemantically(texts: string[], domain: "legal_ui" | "legal_content" | "general" = "legal_content") {
    const cleaned = texts.map((text) => text.trim());
    if (uiLanguage === "en" || !token) return cleaned;

    const cacheSnapshot = { ...translationCache };
    const keys = cleaned.map((text) => `${uiLanguage}:${domain}:${text}`);
    const missing = keys.map((key, idx) => ({ key, idx })).filter((item) => !(item.key in cacheSnapshot));

    if (missing.length > 0) {
      try {
        setSemanticTranslationBusy(true);
        const response = await api.semanticTranslate(token, {
          texts: missing.map((row) => cleaned[row.idx]),
          target_language: uiLanguage,
          source_language: "auto",
          domain,
        });
        missing.forEach((row, index) => {
          cacheSnapshot[row.key] = response.translations[index] || cleaned[row.idx];
        });
        setTranslationCache((current) => ({ ...current, ...cacheSnapshot }));
      } catch {
        return cleaned;
      } finally {
        setSemanticTranslationBusy(false);
      }
    }

    return keys.map((key, idx) => cacheSnapshot[key] || cleaned[idx]);
  }

  function localizedText(value?: string | null, domain: "legal_ui" | "legal_content" | "general" = "legal_content") {
    if (!value) return "";
    const cleaned = value.trim();
    if (!cleaned || uiLanguage === "en") return cleaned;
    const key = `${uiLanguage}:${domain}:${cleaned}`;
    return translationCache[key] || cleaned;
  }

  async function refreshProviderStatus(currentToken: string) {
    try {
      const status = await api.providerStatus(currentToken);
      setProviderStatus(status);
    } catch {
      setProviderStatus(null);
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
      const preferredCase =
        (selectedCaseId && caseList.find((item) => item.id === selectedCaseId)) ||
        caseList[0] ||
        null;
      if (preferredCase) {
        setWorkspaceClientId(preferredCase.client_id);
        setWorkspaceCaseId(preferredCase.id);
      } else {
        setWorkspaceClientId(clientList[0]?.id ?? null);
        setWorkspaceCaseId(null);
      }
      setWorkspaceEntered(false);
      setDocuments([]);
      setVoiceRecordings([]);
      setConsultationRequests([]);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Unable to initialize workspace.";
      setError(message);
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setToken(null);
    } finally {
      setWorkspaceLoading(false);
    }
  }

  async function selectCase(
    currentToken: string,
    caseId: number,
    availableCases = cases,
    preserveCurrentThread = false
  ) {
    const targetCase = availableCases.find((item) => item.id === caseId) ?? null;
    setSelectedCaseId(caseId);
    setSelectedDocumentId(null);
    setSelectedRecordingId(null);
    setSelectedDocumentAnalysis(null);
    setActiveSources([]);
    setAgentWorkflow(null);
    clearArtifactWorkspace();

    if (!preserveCurrentThread) {
      const latestCaseThread = [...chatThreads]
        .filter((thread) => thread.caseId === caseId)
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0];
      if (latestCaseThread) {
        setActiveThreadId(latestCaseThread.id);
        setChatMessages(latestCaseThread.messages);
      } else {
        createThread({
          caseId,
          title: targetCase?.title || "New chat",
          messages: [buildWelcomeMessage(targetCase?.title)],
        });
      }
    }

    const [docs, recordings, requests] = await Promise.all([
      api.listCaseDocuments(currentToken, caseId),
      api.listVoiceRecordings(currentToken, caseId),
      api.listConsultationRequests(currentToken, caseId),
    ]);
    setDocuments(docs);
    setVoiceRecordings(recordings);
    setConsultationRequests(requests);

    if (recordings.length > 0) setSelectedRecordingId(recordings[0].id);
    if (docs.length > 0) await selectDocument(currentToken, docs[0].id, docs);
  }

  async function enterWorkspace() {
    if (!token) return;
    if (!workspaceCaseId) {
      setError("Select a case before entering the workspace.");
      return;
    }
    try {
      setWorkspaceSelecting(true);
      setError(null);
      await selectCase(token, workspaceCaseId, cases);
      setWorkspaceEntered(true);
    } finally {
      setWorkspaceSelecting(false);
    }
  }

  async function selectDocument(currentToken: string, documentId: number, availableDocuments = documents) {
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

  function clearArtifactWorkspace() {
    setArtifactContext(null);
    setArtifactVersions([]);
    setArtifactEditorContent("");
    setArtifactInstruction("");
  }

  function applyArtifactVersionState(payload: {
    artifact_type: "document_summary" | "case_email";
    case_id: number | null;
    document_id: number | null;
    selected_version_id: number | null;
    versions: ArtifactVersion[];
  }) {
    const selectedVersion =
      payload.versions.find((item) => item.id === payload.selected_version_id) ??
      payload.versions[payload.versions.length - 1] ??
      null;
    setArtifactContext({
      artifact_type: payload.artifact_type,
      case_id: payload.case_id,
      document_id: payload.document_id,
      selected_version_id: payload.selected_version_id,
      version_count: payload.versions.length,
      latest_version: selectedVersion,
    });
    setArtifactVersions(payload.versions);
    setArtifactEditorContent(selectedVersion?.content || "");
  }

  async function loadArtifactVersionsForContext(currentToken: string, context: ArtifactContext) {
    try {
      setArtifactLoading(true);
      const payload = await api.listArtifactVersions(currentToken, {
        artifactType: context.artifact_type,
        caseId: context.case_id,
        documentId: context.document_id,
      });
      applyArtifactVersionState(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load artifact versions.");
    } finally {
      setArtifactLoading(false);
    }
  }

  async function saveManualArtifactEdit() {
    if (!token || !artifactContext || !artifactEditorContent.trim()) return;
    try {
      setArtifactSaving(true);
      const response = await api.editArtifactVersion(token, {
        artifact_type: artifactContext.artifact_type,
        case_id: artifactContext.case_id,
        document_id: artifactContext.document_id,
        content: artifactEditorContent.trim(),
        edit_instruction: artifactInstruction.trim() || null,
        parent_version_id: artifactContext.selected_version_id,
      });
      applyArtifactVersionState(response);
      if (response.document_id) await selectDocument(token, response.document_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to save edited version.");
    } finally {
      setArtifactSaving(false);
    }
  }

  async function reviseArtifactWithAgent() {
    if (!token || !artifactContext || !artifactInstruction.trim()) return;
    try {
      setArtifactSaving(true);
      const response = await api.reviseArtifactVersionWithAgent(token, {
        artifact_type: artifactContext.artifact_type,
        case_id: artifactContext.case_id,
        document_id: artifactContext.document_id,
        instruction: artifactInstruction.trim(),
        base_version_id: artifactContext.selected_version_id,
      });
      applyArtifactVersionState(response);
      if (response.document_id) await selectDocument(token, response.document_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to revise version with AI.");
    } finally {
      setArtifactSaving(false);
    }
  }

  async function selectArtifactVersion(versionId: number) {
    if (!token || !artifactContext) return;
    try {
      setArtifactSaving(true);
      const response = await api.selectArtifactVersion(token, versionId);
      applyArtifactVersionState(response);
      if (response.document_id) await selectDocument(token, response.document_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to switch selected version.");
    } finally {
      setArtifactSaving(false);
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

  async function submitCopilotPrompt() {
    if (!token || !chatInput.trim()) return;
    if (!activeThreadId) {
      createThread({
        caseId: selectedCaseId ?? null,
        title: "New chat",
        messages: chatMessages.length > 0 ? chatMessages : [buildWelcomeMessage(selectedCase?.title)],
      });
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
    setShowComposerMenu(false);

    try {
      setError(null);
      const referencedCaseId = extractReferencedCaseId(scopedMessage);
      if (referencedCaseId && !cases.some((item) => item.id === referencedCaseId)) {
        const suggestion = selectedCaseId
          ? `Try running the same prompt with case #${selectedCaseId}.`
          : "Select a case from the sidebar first, then retry.";
        const validationMessage = `Case #${referencedCaseId} is not available in your workspace. ${suggestion}`;
        const [translatedValidation] = await translateSemantically([validationMessage], "general");
        setChatMessages((current) => [
          ...current,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            timestamp: nowIso(),
            content: translatedValidation,
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

      if (workflowFromPrompt) {
        if (!selectedCaseId) {
          setError("Select a case first to run workflow mode.");
          return;
        }
        await runAgentWorkflow(input);
        return;
      }

      const conversationHistory = chatMessages.slice(-18).map((item) => ({
        role: item.role,
        content: item.content,
        parsed_intent: item.meta?.parsedIntent,
        case_id: selectedCaseId ?? undefined,
        document_id: selectedDocumentId ?? undefined,
      }));

      const response = await api.copilot(token, scopedMessage, {
        topK: retrievalDepth,
        useExternalResearch,
        conversationHistory,
      });
      const [translatedAnswer] = await translateSemantically([response.answer], "legal_content");

      setChatMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          timestamp: nowIso(),
          content: translatedAnswer,
          meta: {
            parsedIntent: response.parsed_intent,
            confidence: response.confidence,
            fallbackReason: response.fallback_reason,
            sources: response.sources,
            artifact: response.artifact || null,
            jurisdiction: response.jurisdiction || null,
          },
        },
      ]);
      setActiveSources(response.sources);

      if (response.artifact) {
        setArtifactContext(response.artifact);
        await loadArtifactVersionsForContext(token, response.artifact);
      }

      const topSource = response.sources[0];
      if (topSource?.document_id) {
        await selectDocument(token, topSource.document_id);
      }
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Copilot request failed.";
      setError(message);
      const [translatedFailure] = await translateSemantically([`I could not answer this request: ${message}`], "general");
      setChatMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          timestamp: nowIso(),
          content: translatedFailure,
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

  async function optimizePromptInput() {
    if (!token || !chatInput.trim()) return;
    try {
      setOptimizingPrompt(true);
      setError(null);
      const basePrompt = chatInput.trim();
      const caseSuffix = selectedCaseId ? ` for case #${selectedCaseId}` : "";
      const response = await api.copilot(token, `Optimize prompt: ${basePrompt}${caseSuffix}`, {
        topK: retrievalDepth,
        useExternalResearch,
        conversationHistory: [],
      });
      if (response.parsed_intent !== "optimize_prompt") {
        throw new Error("Prompt optimizer mode was not applied.");
      }
      const normalizedAnswer = (response.answer || "").replace(/^\[intent=.*?\]\s*/i, "").trim();
      const extracted = normalizedAnswer.match(/optimized prompt:\s*(.+)$/im)?.[1]?.trim();
      const cleaned = (extracted || normalizedAnswer).split(/\n\s*notes\s*:/i)[0].trim();
      if (cleaned) setChatInput(cleaned);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to optimize prompt.");
    } finally {
      setOptimizingPrompt(false);
    }
  }

  async function runAgentWorkflow(objectiveOverride?: string) {
    if (!token || !selectedCaseId) return;
    const resolvedObjective = (objectiveOverride ?? workflowObjective).trim();
    try {
      setWorkflowLoading(true);
      setError(null);
      if (resolvedObjective) setWorkflowObjective(resolvedObjective);
      const response = await api.runAgentWorkflow(token, selectedCaseId, resolvedObjective || undefined, retrievalDepth);
      setAgentWorkflow(response);
      setActiveSources(response.sources);
      const [translatedSummary] = await translateSemantically([response.verified_summary], "legal_content");
      setChatMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          timestamp: nowIso(),
          content: translatedSummary,
          meta: {
            parsedIntent: "agent_workflow",
            confidence: "high",
            fallbackReason: null,
            sources: response.sources,
          },
        },
      ]);

      if (response.client_email?.trim()) {
        const context: ArtifactContext = {
          artifact_type: "case_email",
          case_id: selectedCaseId,
          document_id: null,
          selected_version_id: null,
          version_count: 0,
          latest_version: null,
        };
        setArtifactContext(context);
        await loadArtifactVersionsForContext(token, context);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to run workflow.");
    } finally {
      setWorkflowLoading(false);
    }
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    if (!token) return;
    if (!selectedCaseId) {
      setError("Select a case first before uploading documents.");
      return;
    }
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
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
    if (!token) return;
    if (!selectedCaseId) {
      setError("Select a case first before uploading voice notes.");
      return;
    }

    setVoiceUploading(true);
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

  async function handleVoiceUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    await uploadVoiceFile(file);
    event.target.value = "";
  }

  async function buildConsultationFromSelectedRecording() {
    if (!token || !selectedRecordingId) return;
    setIntakeBuilding(true);
    try {
      const response = await api.createConsultationFromRecording(token, selectedRecordingId);
      setConsultationRequests((current) => {
        const rest = current.filter((item) => item.id !== response.consultation_request.id);
        return [response.consultation_request, ...rest];
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to build intake.");
    } finally {
      setIntakeBuilding(false);
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("This browser does not support microphone recording.");
      return;
    }
    if (!selectedCaseId) {
      setError("Select a case first before recording.");
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
        if (event.data.size > 0) mediaChunksRef.current.push(event.data);
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

  async function handleChatSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitCopilotPrompt();
  }

  function handleChatInputKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitCopilotPrompt();
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
    setWorkspaceEntered(false);
    setWorkspaceClientId(null);
    setWorkspaceCaseId(null);
    setChatThreads([]);
    setActiveThreadId(null);
    setChatMessages([buildWelcomeMessage()]);
    setHistoryQuery("");
    setActiveSources([]);
    clearArtifactWorkspace();
    setProviderStatus(null);
    setAgentWorkflow(null);
  }

  if (!token || !user) {
    return (
      <div className="auth-shell">
        <div className="auth-panel">
          <div className="auth-hero">
            <div className="eyebrow">{t("loginEyebrow", "Case-Centric Legal AI")}</div>
            <h1>{t("loginTitle", "Grounded legal workspaces for cases, documents, and evidence-driven AI.")}</h1>
            <p>{t("loginSubtitle", "Sign in to your legal workspace and run case-aware AI workflows.")}</p>
          </div>

          <div className="auth-card">
            <div className="theme-row">
              <button
                className="ghost-button theme-toggle"
                onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
                type="button"
              >
                {theme === "dark" ? t("lightMode", "Light mode") : t("darkMode", "Dark mode")}
              </button>
            </div>

            <div className="auth-tabs">
              <button className={authMode === "login" ? "active" : ""} onClick={() => setAuthMode("login")} type="button">
                {t("login", "Login")}
              </button>
              <button className={authMode === "register" ? "active" : ""} onClick={() => setAuthMode("register")} type="button">
                {t("register", "Register")}
              </button>
            </div>

            <form className="auth-form" onSubmit={handleAuthSubmit}>
              {authMode === "register" ? (
                <>
                  <label>
                    {t("fullName", "Full name")}
                    <input
                      value={authForm.name}
                      onChange={(event) => setAuthForm((current) => ({ ...current, name: event.target.value }))}
                      required
                    />
                  </label>
                  <label>
                    {t("firmName", "Tenant / firm name")}
                    <input
                      value={authForm.tenant_name}
                      onChange={(event) => setAuthForm((current) => ({ ...current, tenant_name: event.target.value }))}
                      required
                    />
                  </label>
                  <label>
                    {t("role", "Role")}
                    <select
                      value={authForm.role}
                      onChange={(event) => setAuthForm((current) => ({ ...current, role: event.target.value }))}
                    >
                      <option value="lawyer">{t("lawyer", "Lawyer")}</option>
                      <option value="assistant">{t("assistant", "Assistant")}</option>
                      <option value="admin">{t("admin", "Admin")}</option>
                    </select>
                  </label>
                </>
              ) : null}

              <label>
                {t("email", "Email")}
                <input
                  type="email"
                  value={authForm.email}
                  onChange={(event) => setAuthForm((current) => ({ ...current, email: event.target.value }))}
                  required
                />
              </label>

              <label>
                {t("password", "Password")}
                <input
                  type="password"
                  value={authForm.password}
                  onChange={(event) => setAuthForm((current) => ({ ...current, password: event.target.value }))}
                  required
                />
              </label>

              <button className="primary-button" disabled={authLoading} type="submit">
                {authLoading ? t("working", "Working...") : authMode === "login" ? t("enterWorkspace", "Enter workspace") : t("createAccount", "Create account")}
              </button>
            </form>

            {error ? <div className="error-banner">{localizedText(error, "general")}</div> : null}
          </div>
        </div>
      </div>
    );
  }

  if (!workspaceEntered) {
    return (
      <div className={`workspace-entry-shell ${uiLanguage === "ar" ? "rtl-layout" : ""}`}>
        <div className="workspace-entry-card">
          <div className="workspace-entry-top">
            <div>
              <div className="eyebrow">{t("workspaceSelection", "Workspace Selection")}</div>
              <h1>{t("appTitle", "Legal Copilot")}</h1>
              <p>{t("selectCaseToStart", "Select a case to start your copilot workspace.")}</p>
            </div>
            <div className="workspace-entry-actions">
              <select value={uiLanguage} onChange={(event) => setUiLanguage(event.target.value as UiLanguage)}>
                <option value="en">{t("languageEnglish", "English")}</option>
                <option value="de">{t("languageGerman", "Deutsch")}</option>
                <option value="ar">{t("languageArabic", "Arabic")}</option>
              </select>
              <button className="secondary-button" onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} type="button">
                {theme === "dark" ? t("lightMode", "Light mode") : t("darkMode", "Dark mode")}
              </button>
              <button className="ghost-button" onClick={logout} type="button">
                {t("logout", "Logout")}
              </button>
            </div>
          </div>

          <div className="workspace-entry-grid">
            <label>
              {t("chooseClient", "Choose client")}
              <select
                value={workspaceClientId ?? ""}
                onChange={(event) => {
                  const nextClientId = event.target.value ? Number(event.target.value) : null;
                  setWorkspaceClientId(nextClientId);
                  const firstCase = cases.find((item) => item.client_id === nextClientId) || null;
                  setWorkspaceCaseId(firstCase?.id ?? null);
                }}
              >
                <option value="">{t("chooseClient", "Choose client")}</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              {t("chooseCase", "Choose case")}
              <select value={workspaceCaseId ?? ""} onChange={(event) => setWorkspaceCaseId(event.target.value ? Number(event.target.value) : null)}>
                <option value="">{t("chooseCase", "Choose case")}</option>
                {casesForWorkspaceClient.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {clients.length === 0 ? <div className="error-banner">{t("noClientsAvailable", "No clients found. Create clients from the clients page first.")}</div> : null}
          {clients.length > 0 && casesForWorkspaceClient.length === 0 ? (
            <div className="error-banner">{t("noCasesAvailable", "No cases found for this client. Create cases from the cases page first.")}</div>
          ) : null}

          <button className="primary-button workspace-entry-cta" disabled={!workspaceCaseId || workspaceSelecting} onClick={() => void enterWorkspace()} type="button">
            {workspaceSelecting ? t("preparingWorkspace", "Preparing workspace...") : t("enterWorkspace", "Enter workspace")}
          </button>
          {error ? <div className="error-banner">{localizedText(error, "general")}</div> : null}
        </div>
      </div>
    );
  }

  return (
    <div className={`chatgpt-shell ${uiLanguage === "ar" ? "rtl-layout" : ""} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className={`chatgpt-sidebar ${sidebarCollapsed ? "collapsed" : ""}`}>
        {sidebarCollapsed ? (
          <div className="icon-sidebar">
            <button
              className="icon-sidebar-button"
              onClick={() => setSidebarCollapsed(false)}
              title={t("expandSidebar", "Expand sidebar")}
              type="button"
            >
              <SidebarIcon icon="toggle" />
            </button>
            <div className="icon-sidebar-brand" title={t("appTitle", "Legal Copilot")}>
              LA
            </div>
            <button className="icon-sidebar-button" onClick={startNewChat} title={t("newChat", "New chat")} type="button">
              <SidebarIcon icon="chat" />
            </button>
            <button className="icon-sidebar-button" onClick={() => setSidebarCollapsed(false)} title={t("chatHistory", "Chat history")} type="button">
              <SidebarIcon icon="history" />
            </button>
            <button className="icon-sidebar-button" onClick={() => setSidebarCollapsed(false)} title={t("cases", "Cases")} type="button">
              <SidebarIcon icon="cases" />
            </button>
            <button className="icon-sidebar-button" onClick={() => setSidebarCollapsed(false)} title={t("features", "Features")} type="button">
              <SidebarIcon icon="features" />
            </button>
            <button className="icon-sidebar-button" onClick={() => documentUploadInputRef.current?.click()} title={t("uploadPdf", "Upload document")} type="button">
              <SidebarIcon icon="document" />
            </button>
            <button className="icon-sidebar-button" onClick={() => audioUploadInputRef.current?.click()} title={t("uploadAudio", "Upload audio")} type="button">
              <SidebarIcon icon="audio" />
            </button>
            <button
              className="icon-sidebar-button"
              onClick={() => void (recordingAudio ? stopRecording() : startRecording())}
              title={recordingAudio ? t("stopRecording", "Stop recording") : t("recordVoice", "Record voice")}
              type="button"
            >
              <SidebarIcon icon="audio" />
            </button>
            <button
              className="icon-sidebar-button"
              disabled={!selectedCaseId || workflowLoading}
              onClick={() => void runAgentWorkflow()}
              title={workflowLoading ? t("running", "Running...") : t("runWorkflow", "Run workflow")}
              type="button"
            >
              <SidebarIcon icon="features" />
            </button>
            <button
              className={`icon-sidebar-button ${useExternalResearch ? "active" : ""}`}
              onClick={() => setUseExternalResearch((current) => !current)}
              title={t("webResearch", "Web research")}
              type="button"
            >
              <SidebarIcon icon="evidence" />
            </button>
          </div>
        ) : (
          <>
        <div className="sidebar-brand">
          <div className="brand-mark">LA</div>
          <div>
            <strong>{t("appTitle", "Legal Copilot")}</strong>
            <small>{user.name}</small>
          </div>
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarCollapsed(true)}
            title={t("collapseSidebar", "Collapse sidebar")}
            type="button"
          >
            <SidebarIcon icon="toggle" />
          </button>
        </div>

        <button className="primary-button sidebar-new-chat" onClick={startNewChat} type="button">
          {t("newChat", "New chat")}
        </button>

        <input
          placeholder={t("searchChats", "Search chats")}
          value={historyQuery}
          onChange={(event) => setHistoryQuery(event.target.value)}
        />

        <div className="sidebar-section">
          <h4>{t("chatHistory", "Chat history")}</h4>
          <div className="history-list">
            {filteredThreads.length > 0 ? (
              filteredThreads.map((thread) => (
                <button
                  key={thread.id}
                  className={`history-item ${activeThreadId === thread.id ? "active" : ""}`}
                  onClick={() => openThread(thread.id)}
                  type="button"
                >
                  <strong>{thread.title}</strong>
                  <small>{formatUiDate(thread.updatedAt)}</small>
                </button>
              ))
            ) : (
              <small className="muted">{t("noHistory", "No chats yet")}</small>
            )}
          </div>
        </div>

        <details className="sidebar-section" open>
          <summary>{t("cases", "Cases")}</summary>
          <div className="case-list compact-list">
            {cases.map((item) => (
              <button
                key={item.id}
                className={`case-card ${selectedCaseId === item.id ? "selected" : ""}`}
                onClick={() => {
                  setWorkspaceClientId(item.client_id);
                  setWorkspaceCaseId(item.id);
                  token && void selectCase(token, item.id);
                }}
                type="button"
              >
                <strong>{item.title}</strong>
                <small>{formatJurisdictionCountry(item.jurisdiction_country)}</small>
              </button>
            ))}
          </div>
        </details>

        <details className="sidebar-section" open>
          <summary>{t("features", "Features")}</summary>
          <div className="quick-ingest-actions">
            <button className="secondary-button" onClick={() => documentUploadInputRef.current?.click()} type="button">
              {uploading ? t("uploading", "Uploading...") : t("uploadPdf", "Upload PDF")}
            </button>
            <button className="secondary-button" onClick={() => audioUploadInputRef.current?.click()} type="button">
              {voiceUploading ? t("uploading", "Uploading...") : t("uploadAudio", "Upload audio")}
            </button>
            <button className="secondary-button" onClick={() => void (recordingAudio ? stopRecording() : startRecording())} type="button">
              {recordingAudio ? t("stopRecording", "Stop recording") : t("recordVoice", "Record voice")}
            </button>
            <button className="secondary-button" disabled={!selectedCaseId || workflowLoading} onClick={() => void runAgentWorkflow()} type="button">
              {workflowLoading ? t("running", "Running...") : t("runWorkflow", "Run workflow")}
            </button>
            <label className="toggle-control">
              <input checked={useExternalResearch} onChange={(event) => setUseExternalResearch(event.target.checked)} type="checkbox" />
              {t("webResearch", "Web research")}
            </label>
          </div>
        </details>

        <details className="sidebar-section">
          <summary>{t("documents", "Documents")}</summary>
          <div className="document-list">
            {documents.map((document) => (
              <button
                key={document.id}
                className={`document-card ${selectedDocumentId === document.id ? "selected" : ""}`}
                onClick={() => token && void selectDocument(token, document.id)}
                type="button"
              >
                <strong>{document.filename}</strong>
                <small>
                  {formatBytes(document.file_size)} - {localizedText(document.processing_status, "general")}
                </small>
              </button>
            ))}
          </div>
          {selectedDocumentAnalysis ? (
            <div className="analysis-block">
              <h4>{t("documentIntelligence", "Document intelligence")}</h4>
              <p>{localizedText(selectedDocumentAnalysis.summary_short, "legal_content") || t("noSummaryYet", "No summary available yet.")}</p>
            </div>
          ) : null}
        </details>

        <details className="sidebar-section">
          <summary>{t("voiceIntake", "Voice and intake")}</summary>
          <div className="voice-recording-list">
            {voiceRecordings.map((recording) => (
              <button
                key={recording.id}
                className={`document-card ${selectedRecordingId === recording.id ? "selected" : ""}`}
                onClick={() => setSelectedRecordingId(recording.id)}
                type="button"
              >
                <strong>{recording.filename}</strong>
                <small>{localizedText(recording.transcription_status, "general")}</small>
              </button>
            ))}
          </div>
          {selectedRecording ? (
            <div className="analysis-block">
              <p>{localizedText(getRecordingTranscriptDisplay(selectedRecording), "legal_content")}</p>
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
                {intakeBuilding ? t("buildingIntake", "Building...") : t("createIntakeRequest", "Create intake request")}
              </button>
            </div>
          ) : null}
          {selectedConsultationRequest ? (
            <div className="analysis-block">
              <h4>{t("consultation", "Consultation")}</h4>
              <p>{localizedText(selectedConsultationRequest.issue_summary, "legal_content")}</p>
            </div>
          ) : null}
        </details>

        {artifactContext ? (
          <details className="sidebar-section" open>
            <summary>{t("drafts", "Versioned drafts")}</summary>
            <div className="artifact-toolbar">
              <button
                className="secondary-button"
                disabled={artifactLoading || !token || !artifactContext}
                onClick={() => token && artifactContext && void loadArtifactVersionsForContext(token, artifactContext)}
                type="button"
              >
                {artifactLoading ? "Refreshing..." : t("refreshVersions", "Refresh versions")}
              </button>
            </div>
            <textarea className="artifact-editor" value={artifactEditorContent} onChange={(event) => setArtifactEditorContent(event.target.value)} />
            <div className="artifact-actions">
              <input
                value={artifactInstruction}
                onChange={(event) => setArtifactInstruction(event.target.value)}
                placeholder={t("improvingPromptPlaceholder", "Tell the agent what to improve.")}
              />
              <button
                className="secondary-button"
                disabled={artifactSaving || !artifactInstruction.trim()}
                onClick={() => void reviseArtifactWithAgent()}
                type="button"
              >
                {t("reviseWithAgent", "Revise with agent")}
              </button>
              <button
                className="primary-button"
                disabled={artifactSaving || !artifactEditorContent.trim()}
                onClick={() => void saveManualArtifactEdit()}
                type="button"
              >
                {t("saveVersion", "Save version")}
              </button>
            </div>
            <div className="artifact-version-list">
              {artifactVersions.map((version) => (
                <button
                  key={version.id}
                  className={`artifact-version-card ${artifactContext.selected_version_id === version.id ? "selected" : ""}`}
                  onClick={() => void selectArtifactVersion(version.id)}
                  type="button"
                >
                  <strong>V{version.version_number}</strong>
                  <small>{version.source_kind.replace("_", " ")}</small>
                </button>
              ))}
            </div>
          </details>
        ) : null}

        <details className="sidebar-section">
          <summary>{t("evidence", "Evidence")}</summary>
          <div className="source-list">
            {activeSources.slice(0, 8).map((source, index) => (
              <article key={`${source.document_id ?? "external"}-${index}`} className="source-card">
                <strong>{source.filename}</strong>
                <p>{localizedText(source.snippet, "legal_content")}</p>
              </article>
            ))}
          </div>
          {activeJurisdiction?.constitutional_references?.length ? (
            <div className="source-actions">
              {activeJurisdiction.constitutional_references.map((url) => (
                <a key={url} className="ghost-link" href={url} rel="noreferrer" target="_blank">
                  {t("constitutionSource", "Constitution source")}
                </a>
              ))}
            </div>
          ) : null}
        </details>
          </>
        )}

        <input ref={documentUploadInputRef} type="file" accept="application/pdf" onChange={handleUpload} hidden />
        <input
          ref={audioUploadInputRef}
          type="file"
          accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/mp3,audio/ogg"
          onChange={handleVoiceUpload}
          hidden
        />
      </aside>

      <main className={`chatgpt-main ${inConversationMode ? "conversation-mode" : "home-mode"} ${copilotLoading ? "processing" : ""}`}>
        <header className="chatgpt-topbar">
          <div>
            <strong>{selectedCase?.title || t("appTitle", "Legal Copilot")}</strong>
            <small>
              {selectedCase
                ? `${selectedClient?.name || t("noClient", "No client")} - ${formatJurisdictionCountry(selectedCase.jurisdiction_country)}`
                : t("selectCaseFromSidebar", "Select a case from the sidebar")}
            </small>
          </div>
          <div className="topbar-actions">
            <button
              className="ghost-button sidebar-toggle-topbar"
              onClick={() => setSidebarCollapsed((current) => !current)}
              title={sidebarCollapsed ? t("expandSidebar", "Expand sidebar") : t("collapseSidebar", "Collapse sidebar")}
              type="button"
            >
              <SidebarIcon icon="toggle" />
            </button>
            <label className="range-control">
              {t("retrieval", "Retrieval")}
              <input type="range" min={3} max={10} value={retrievalDepth} onChange={(event) => setRetrievalDepth(Number(event.target.value))} />
              <span>{retrievalDepth}</span>
            </label>
            <select value={uiLanguage} onChange={(event) => setUiLanguage(event.target.value as UiLanguage)}>
              <option value="en">{t("languageEnglish", "English")}</option>
              <option value="de">{t("languageGerman", "Deutsch")}</option>
              <option value="ar">{t("languageArabic", "Arabic")}</option>
            </select>
            <button className="secondary-button" onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))} type="button">
              {theme === "dark" ? t("lightMode", "Light mode") : t("darkMode", "Dark mode")}
            </button>
            <button className="ghost-button" onClick={logout} type="button">
              {t("logout", "Logout")}
            </button>
          </div>
        </header>

        <section className="chatgpt-canvas">
          {inConversationMode ? (
            <div className="message-stream message-stream-chatgpt">
              {chatMessages.map((message) => (
                <article key={message.id} className={`message ${message.role}`}>
                  <div className="message-avatar">{message.role === "assistant" ? "AI" : t("you", "You")}</div>
                  <div className="message-card">
                    <p>{message.role === "assistant" ? localizedText(message.content, "legal_content") : message.content}</p>
                    {message.meta ? (
                      <div className="message-meta">
                        <span>{inferAgentFromIntent(message.meta.parsedIntent)}</span>
                        <span>{message.meta.confidence || "n/a"}</span>
                        {message.meta.fallbackReason ? <span>{message.meta.fallbackReason}</span> : null}
                      </div>
                    ) : null}
                  </div>
                </article>
              ))}
              {copilotLoading ? <div className="loading-bar">{t("processing", "Thinking...")}</div> : null}
            </div>
          ) : (
            <div className="chatgpt-home-hero">
              <h1>{t("askCopilot", "Ask copilot")}</h1>
              <p>{semanticTranslationBusy ? `${t("smartTranslation", "Smart translation")}...` : t("alwaysReady", "Always ready to support legal work.")}</p>
            </div>
          )}
        </section>

        <footer className={`chatgpt-composer-dock ${copilotLoading ? "loading" : ""}`}>
          {showComposerMenu ? (
            <div className="composer-plus-menu">
              <button className={`menu-item ${agentModeEnabled ? "active" : ""}`} onClick={() => setAgentModeEnabled((current) => !current)} type="button">
                <span className="menu-item-left">
                  <MenuIcon icon="agent" />
                  <span>{t("modeAgent", "Mode agent")}</span>
                </span>
                <span className="menu-item-badge">{t("soon", "Soon")}</span>
              </button>
              <button
                className={`menu-item ${useExternalResearch ? "active" : ""}`}
                onClick={() => {
                  setUseExternalResearch((current) => !current);
                  setShowComposerMenu(false);
                }}
                type="button"
              >
                <span className="menu-item-left">
                  <MenuIcon icon="web" />
                  <span>{t("webResearch", "Web research")}</span>
                </span>
                <span className="menu-item-badge">{useExternalResearch ? t("on", "On") : t("off", "Off")}</span>
              </button>
              <button
                className={`menu-item ${workflowFromPrompt ? "active" : ""}`}
                onClick={() => {
                  setWorkflowFromPrompt((current) => !current);
                  setShowComposerMenu(false);
                }}
                type="button"
              >
                <span className="menu-item-left">
                  <MenuIcon icon="workflow" />
                  <span>{t("runWorkflow", "Run workflow")}</span>
                </span>
                <span className="menu-item-badge">{workflowFromPrompt ? t("on", "On") : t("off", "Off")}</span>
              </button>
            </div>
          ) : null}

          <form className="chatgpt-composer" onSubmit={handleChatSubmit}>
            <button className="composer-plus-trigger" type="button" onClick={() => setShowComposerMenu((current) => !current)}>
              +
            </button>
            <div className="composer-input-column">
              {useExternalResearch || workflowFromPrompt ? (
                <div className="composer-chip-row">
                  {useExternalResearch ? (
                    <button className="composer-chip active" onClick={() => setUseExternalResearch(false)} type="button">
                      <MenuIcon icon="web" />
                      <span>{t("webResearch", "Web research")}</span>
                    </button>
                  ) : null}
                  {workflowFromPrompt ? (
                    <button className="composer-chip active" onClick={() => setWorkflowFromPrompt(false)} type="button">
                      <MenuIcon icon="workflow" />
                      <span>{t("workflowMode", "Workflow mode")}</span>
                    </button>
                  ) : null}
                </div>
              ) : null}
              <textarea
                onKeyDown={handleChatInputKeyDown}
                placeholder={t("placeholder", "Ask anything about your case, document, risks, deadlines, or drafting.")}
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
              />
            </div>
            <div className="composer-action-group">
              <button
                className="ghost-button composer-optimize"
                disabled={copilotLoading || optimizingPrompt || !chatInput.trim()}
                onClick={() => void optimizePromptInput()}
                title={t("optimizePrompt", "Optimize prompt")}
                type="button"
              >
                <MenuIcon icon="agent" />
              </button>
              <button className="primary-button composer-send" disabled={copilotLoading || optimizingPrompt || workflowLoading || !chatInput.trim()} type="submit">
                {t("askCopilot", "Ask copilot")}
              </button>
            </div>
          </form>

          {providerStatus ? (
            <div className="composer-status">
              {providerStatus.provider_name} - {providerStatus.model} - {activeAgentName} -{" "}
              {activeJurisdiction?.country_display_name || t("noJurisdiction", "No jurisdiction")} - {externalResearchCount} {t("webSources", "web sources")}
            </div>
          ) : null}
          {optimizingPrompt ? <div className="composer-status">{t("optimizingPrompt", "Optimizing...")}</div> : null}
          {agentModeEnabled ? <div className="composer-status">{t("modeAgent", "Mode agent")}: {t("soon", "Soon")}</div> : null}
          {workspaceLoading ? <div className="composer-status">{t("loadingWorkspace", "Loading workspace...")}</div> : null}
          {agentWorkflow ? <div className="composer-status">{t("workflowReady", "Workflow ready")}: {localizedText(agentWorkflow.objective, "general")}</div> : null}
          {selectedDocument ? <div className="composer-status">{t("focusedDocument", "Focused document")}: {selectedDocument.filename}</div> : null}
          {error ? <div className="error-banner inline-error">{localizedText(error, "general")}</div> : null}
        </footer>
      </main>
    </div>
  );
}
