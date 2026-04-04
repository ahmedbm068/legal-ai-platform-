
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { workspaceApi as api } from "./workspaceApi";
import ChatMessageBubble, { type MessageFeedbackState } from "./components/ChatMessageBubble";
import type {
  CaseItem,
  ChatMessage,
  Client,
  ConsultationRequest,
  DocumentItem,
  EvidenceAnalysisReview,
  FullDocumentAnalysis,
  ImageDocumentBatch,
  PromptLibraryEntry,
  ProviderStatusResponse,
  CaseReviewTable,
  User,
  VoiceRecording,
} from "./types";

// Optimization: lazy load right-side intelligence dashboard to reduce initial bundle and first paint cost.
const IntelligencePanel = lazy(() => import("./components/IntelligencePanel"));

const TOKEN_STORAGE_KEY = "legal-ai-platform-token";
const THEME_STORAGE_KEY = "legal-ai-platform-theme-v3";
const LANGUAGE_STORAGE_KEY = "legal-ai-platform-language-v2";
const LEGACY_CHAT_STORAGE_KEY = "legal-ai-platform-chat-map-v2";
const CHAT_STORAGE_KEY = "legal-ai-platform-chat-sessions-v3";
const IMAGE_BATCH_POLL_INTERVAL_MS = 4500;
const IMAGE_BATCH_POLL_MAX_CYCLES = 30;

type ThemeMode = "dark" | "light";
type UiLanguage = "en" | "de" | "ar";
type WorkspaceMode = "chat" | "agent" | "legal_search";
type ReasoningLevel = "low" | "medium" | "high";
type FeedbackValue = "up" | "down";

type BrowserSpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: {
    resultIndex: number;
    results: ArrayLike<ArrayLike<{ transcript?: string }> & { isFinal?: boolean }>;
  }) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

declare global {
  interface Window {
    SpeechRecognition?: new () => BrowserSpeechRecognition;
    webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
  }
}

interface AuthFormState {
  name: string;
  tenant: string;
  inviteToken: string;
  email: string;
  password: string;
  role: "admin" | "lawyer" | "assistant";
}

interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

interface StoredChatSessionsState {
  sessionsByCase: Record<number, ChatSession[]>;
  activeSessionIdByCase: Record<number, string>;
}

const REASONING_TOP_K: Record<ReasoningLevel, number> = {
  low: 3,
  medium: 6,
  high: 9,
};

const APP_TEXT: Record<UiLanguage, Record<string, string>> = {
  en: {
    noDate: "No date",
    modelLabel: "model",
    notAvailable: "N/A",
    caseIdLabel: "ID",
    providerUnavailable: "Provider unavailable",
    noCaseSelected: "No case selected",
    noCasesForClient: "No cases found for selected client.",
    noEvidenceYet: "No evidence uploaded yet.",
    loadingWorkspace: "Loading workspace context...",
    startQuestionTitle: "Start with a legal question",
    startQuestionBody: "Ask about risks, obligations, deadlines, contradictions, or draft a professional legal response.",
    focusedDocumentNone: "none",
    caseLabel: "Case",
    documentsLabel: "Documents",
    consultationsLabel: "Consultations",
    focusedDocumentLabel: "Focused document",
    attachPdf: "Attach PDF",
    attachVoice: "Attach voice file",
    recordFromMic: "Record from microphone",
    stopMicRecording: "Stop microphone recording",
    askPlaceholder: "Ask about your case, risks, deadlines, or draft something...",
    send: "Send",
    optimizePrompt: "Optimize",
    optimizingPrompt: "Optimizing...",
    voiceInput: "Voice input",
    stopVoiceInput: "Stop voice input",
    transcribingVoiceInput: "Transcribing...",
    liveVoiceInputNotice: "Live voice dictation is active.",
    liveVoiceFallbackNotice: "Live dictation is unavailable in this browser. Using slower transcription fallback.",
    promptOptimizedNotice: "Prompt optimized for clearer legal reasoning.",
    promptOptimizeFailed: "Unable to optimize the prompt.",
    voiceTranscriptFailed: "Unable to transcribe your voice input.",
    voiceTranscriptInserted: "Voice transcript added to the prompt.",
    stopCaseRecordingFirst: "Stop the case voice recording before starting prompt dictation.",
    legalSearchFootnote: "Legal Search Mode prioritizes jurisdiction-specific legal sources before fallback reasoning.",
    agentFootnote: "Agent Mode enables structured reasoning and legal workflow orchestration.",
    chatFootnote: "Chat Mode provides conversational legal support grounded in your case context.",
    modeChat: "Chat Mode",
    modeChatDesc: "Fast legal discussion",
    modeAgent: "Agent Mode",
    modeAgentDesc: "Step-by-step execution",
    modeLegalSearch: "Legal Search Mode",
    modeLegalSearchDesc: "Source-grounded legal answers",
    modeExternal: "External Mode",
    modeExternalDesc: "Web-enhanced legal research",
    plusModesTitle: "Modes",
    plusAttachmentsTitle: "Attachments",
    language: "Language",
    languageEnglish: "English",
    languageGerman: "German",
    languageArabic: "Arabic",
    reasoning: "Reasoning",
    reasoningLow: "Low",
    reasoningMedium: "Medium",
    reasoningHigh: "High",
    light: "Light",
    dark: "Dark",
    authKicker: "Next-Gen Legal AI Workspace",
    authTitle: "Calm. Intelligent. Powerful.",
    authSubtitle: "A premium legal copilot with case-grounded reasoning, structured insights, and evidence-aware drafting.",
    authPoint1: "AI-native legal chat",
    authPoint2: "Case intelligence dashboard",
    authPoint3: "Document + voice ingestion",
    signIn: "Sign in",
    createAccountTitle: "Create account",
    secureAccess: "Secure access to your legal workspace.",
    login: "Login",
    register: "Register",
    fullName: "Full name",
    tenant: "Tenant / Firm",
    role: "Role",
    lawyer: "Lawyer",
    assistant: "Assistant",
    admin: "Admin",
    email: "Email",
    password: "Password",
    working: "Working...",
    enterWorkspace: "Enter Workspace",
    createAccount: "Create Account",
    accountCreated: "Account created. Sign in to continue.",
    authFailed: "Authentication failed.",
    unableLoadWorkspace: "Unable to load workspace.",
    unableLoadCaseContext: "Unable to load case context.",
    uploadPdfOnly: "Only PDF files are allowed.",
    uploadPdfFailed: "Unable to upload PDF.",
    uploadAudioFailed: "Unable to upload audio.",
    uploadPdfSuccess: "PDF uploaded and queued for processing.",
    uploadAudioSuccess: "Voice file uploaded. Transcription is running.",
    micUnsupported: "Microphone recording is not supported in this browser.",
    micAccessFailed: "Unable to access microphone.",
    copilotFailed: "Copilot request failed.",
    copiedClipboard: "Copied to clipboard.",
    legalAiPlatform: "Legal AI Platform",
    premiumWorkspace: "Premium Copilot Workspace",
    matterNavigator: "Matter Navigator",
    client: "Client",
    evidenceFeed: "Evidence Feed",
    ingestion: "Ingestion",
    workspaceFacts: "Workspace Facts",
    logout: "Logout",
    uploadPdf: "Upload PDF",
    uploadingPdf: "Uploading PDF...",
    uploadAudioFile: "Upload audio file",
    uploadingAudio: "Uploading audio...",
    stopRecording: "Stop recording",
    recordVoice: "Record voice",
    lawyerId: "Lawyer ID",
    consultations: "Consultations",
    voiceNotes: "Voice notes",
    lastDocRefresh: "Last document refresh",
    workspaceTopDefault: "Select a case to start",
    copilotWorkspace: "Copilot Workspace",
    copilotWorkspaceDesc: "AI-grounded legal drafting and reasoning for active matter.",
    chatHistory: "Chat History",
    noHistory: "No messages yet for this case.",
    clearHistory: "Clear history",
    userLabel: "You",
    assistantLabel: "AI",
  },
  de: {
    noDate: "Kein Datum",
    modelLabel: "Modell",
    notAvailable: "k. A.",
    caseIdLabel: "ID",
    providerUnavailable: "Provider nicht verfuegbar",
    noCaseSelected: "Kein Fall ausgewaehlt",
    noCasesForClient: "Keine Faelle fuer den ausgewaehlten Mandanten gefunden.",
    noEvidenceYet: "Noch keine Beweise hochgeladen.",
    loadingWorkspace: "Workspace-Kontext wird geladen...",
    startQuestionTitle: "Beginne mit einer Rechtsfrage",
    startQuestionBody: "Frage zu Risiken, Pflichten, Fristen, Widerspruechen oder erstelle einen professionellen Rechtstext.",
    focusedDocumentNone: "keins",
    caseLabel: "Fall",
    documentsLabel: "Dokumente",
    consultationsLabel: "Beratungen",
    focusedDocumentLabel: "Fokussiertes Dokument",
    attachPdf: "PDF anhaengen",
    attachVoice: "Audio anhaengen",
    recordFromMic: "Mit Mikrofon aufnehmen",
    stopMicRecording: "Mikrofonaufnahme stoppen",
    askPlaceholder: "Frage zu Fall, Risiken, Fristen oder erstelle einen Entwurf...",
    send: "Senden",
    legalSearchFootnote: "Legal Search Mode priorisiert zustandigkeitsspezifische Rechtsquellen vor Fallback-Reasoning.",
    agentFootnote: "Agent Mode aktiviert strukturierte Reasoning- und Workflow-Ausfuehrung.",
    chatFootnote: "Chat Mode bietet konversationelle rechtliche Hilfe auf Basis deines Falls.",
    modeChat: "Chat-Modus",
    modeChatDesc: "Schnelle juristische Unterhaltung",
    modeAgent: "Agent-Modus",
    modeAgentDesc: "Schrittweise Ausfuehrung",
    modeLegalSearch: "Legal-Search-Modus",
    modeLegalSearchDesc: "Quellenbasierte Rechtsantworten",
    modeExternal: "Externer Modus",
    modeExternalDesc: "Web-gestuetzte Rechtsrecherche",
    plusModesTitle: "Modi",
    plusAttachmentsTitle: "Anhaenge",
    language: "Sprache",
    languageEnglish: "Englisch",
    languageGerman: "Deutsch",
    languageArabic: "Arabisch",
    reasoning: "Reasoning",
    reasoningLow: "Niedrig",
    reasoningMedium: "Mittel",
    reasoningHigh: "Hoch",
    light: "Hell",
    dark: "Dunkel",
    authKicker: "Next-Gen Legal AI Workspace",
    authTitle: "Ruhig. Intelligent. Stark.",
    authSubtitle: "Ein Premium-Copilot fuer juristische Arbeit mit fallbezogenem Reasoning und evidenzbasiertem Drafting.",
    authPoint1: "AI-native Rechts-Chat",
    authPoint2: "Fall-Intelligence-Dashboard",
    authPoint3: "Dokument- und Audio-Ingestion",
    signIn: "Anmelden",
    createAccountTitle: "Konto erstellen",
    secureAccess: "Sicherer Zugriff auf deinen Legal-Workspace.",
    login: "Login",
    register: "Registrieren",
    fullName: "Vollstaendiger Name",
    tenant: "Mandant / Kanzlei",
    role: "Rolle",
    lawyer: "Anwalt",
    assistant: "Assistent",
    admin: "Admin",
    email: "E-Mail",
    password: "Passwort",
    working: "Bitte warten...",
    enterWorkspace: "Workspace betreten",
    createAccount: "Konto erstellen",
    accountCreated: "Konto erstellt. Bitte anmelden.",
    authFailed: "Authentifizierung fehlgeschlagen.",
    unableLoadWorkspace: "Workspace konnte nicht geladen werden.",
    unableLoadCaseContext: "Fallkontext konnte nicht geladen werden.",
    uploadPdfOnly: "Nur PDF-Dateien sind erlaubt.",
    uploadPdfFailed: "PDF konnte nicht hochgeladen werden.",
    uploadAudioFailed: "Audio konnte nicht hochgeladen werden.",
    uploadPdfSuccess: "PDF hochgeladen und zur Verarbeitung vorgemerkt.",
    uploadAudioSuccess: "Audiodatei hochgeladen. Transkription laeuft.",
    micUnsupported: "Mikrofonaufnahme wird in diesem Browser nicht unterstuetzt.",
    micAccessFailed: "Mikrofonzugriff fehlgeschlagen.",
    copilotFailed: "Copilot-Anfrage fehlgeschlagen.",
    copiedClipboard: "In Zwischenablage kopiert.",
    legalAiPlatform: "Legal AI Platform",
    premiumWorkspace: "Premium Copilot Workspace",
    matterNavigator: "Fall-Navigator",
    client: "Mandant",
    evidenceFeed: "Evidenz-Feed",
    ingestion: "Ingestion",
    workspaceFacts: "Workspace-Fakten",
    logout: "Abmelden",
    uploadPdf: "PDF hochladen",
    uploadingPdf: "PDF wird hochgeladen...",
    uploadAudioFile: "Audiodatei hochladen",
    uploadingAudio: "Audio wird hochgeladen...",
    stopRecording: "Aufnahme stoppen",
    recordVoice: "Sprache aufnehmen",
    lawyerId: "Anwalt-ID",
    consultations: "Beratungen",
    voiceNotes: "Sprachnotizen",
    lastDocRefresh: "Letzte Dokumentaktualisierung",
    workspaceTopDefault: "Waehle einen Fall zum Start",
    copilotWorkspace: "Copilot-Workspace",
    copilotWorkspaceDesc: "AI-gestuetztes juristisches Drafting und Reasoning fuer den aktiven Fall.",
    chatHistory: "Chat-Verlauf",
    noHistory: "Noch keine Nachrichten fuer diesen Fall.",
    clearHistory: "Verlauf loeschen",
    userLabel: "Du",
    assistantLabel: "AI",
  },
  ar: {
    noDate: "لا يوجد تاريخ",
    modelLabel: "النموذج",
    notAvailable: "غير متاح",
    caseIdLabel: "المعرّف",
    providerUnavailable: "مزود الخدمة غير متاح",
    noCaseSelected: "لا توجد قضية محددة",
    noCasesForClient: "لا توجد قضايا للعميل المحدد.",
    noEvidenceYet: "لا توجد أدلة مرفوعة بعد.",
    loadingWorkspace: "جار تحميل سياق مساحة العمل...",
    startQuestionTitle: "ابدأ بسؤال قانوني",
    startQuestionBody: "اسأل عن المخاطر أو الالتزامات أو المواعيد أو التناقضات أو اطلب صياغة قانونية احترافية.",
    focusedDocumentNone: "لا يوجد",
    caseLabel: "القضية",
    documentsLabel: "المستندات",
    consultationsLabel: "الاستشارات",
    focusedDocumentLabel: "المستند المحدد",
    attachPdf: "إرفاق PDF",
    attachVoice: "إرفاق ملف صوتي",
    recordFromMic: "التسجيل من الميكروفون",
    stopMicRecording: "إيقاف تسجيل الميكروفون",
    askPlaceholder: "اسأل عن قضيتك أو المخاطر أو المواعيد أو اطلب صياغة...",
    send: "إرسال",
    legalSearchFootnote: "وضع البحث القانوني يعطي الأولوية للمصادر القانونية حسب الاختصاص قبل أي استدلال بديل.",
    agentFootnote: "وضع الوكيل يفعّل الاستدلال المنظم وتنفيذ سير العمل القانوني.",
    chatFootnote: "وضع المحادثة يوفّر دعماً قانونياً حوارياً مبنياً على سياق قضيتك.",
    modeChat: "وضع المحادثة",
    modeChatDesc: "مناقشة قانونية سريعة",
    modeAgent: "وضع الوكيل",
    modeAgentDesc: "تنفيذ خطوة بخطوة",
    modeLegalSearch: "وضع البحث القانوني",
    modeLegalSearchDesc: "إجابات قانونية مدعومة بالمصادر",
    modeExternal: "الوضع الخارجي",
    modeExternalDesc: "بحث قانوني مدعوم بالويب",
    plusModesTitle: "الأوضاع",
    plusAttachmentsTitle: "المرفقات",
    language: "اللغة",
    languageEnglish: "الإنجليزية",
    languageGerman: "الألمانية",
    languageArabic: "العربية",
    reasoning: "الاستدلال",
    reasoningLow: "منخفض",
    reasoningMedium: "متوسط",
    reasoningHigh: "عال",
    light: "فاتح",
    dark: "داكن",
    authKicker: "مساحة عمل قانونية ذكية",
    authTitle: "هادئ. ذكي. قوي.",
    authSubtitle: "مساعد قانوني مميز يعتمد على سياق القضية واستدلال منظم وصياغة مبنية على الأدلة.",
    authPoint1: "دردشة قانونية مدعومة بالذكاء الاصطناعي",
    authPoint2: "لوحة ذكاء القضية",
    authPoint3: "إدخال المستندات والصوت",
    signIn: "تسجيل الدخول",
    createAccountTitle: "إنشاء حساب",
    secureAccess: "وصول آمن إلى مساحة العمل القانونية.",
    login: "دخول",
    register: "تسجيل",
    fullName: "الاسم الكامل",
    tenant: "المؤسسة / المكتب",
    role: "الدور",
    lawyer: "محامٍ",
    assistant: "مساعد",
    admin: "مشرف",
    email: "البريد الإلكتروني",
    password: "كلمة المرور",
    working: "جارٍ العمل...",
    enterWorkspace: "دخول مساحة العمل",
    createAccount: "إنشاء حساب",
    accountCreated: "تم إنشاء الحساب. قم بتسجيل الدخول للمتابعة.",
    authFailed: "فشل تسجيل الدخول.",
    unableLoadWorkspace: "تعذر تحميل مساحة العمل.",
    unableLoadCaseContext: "تعذر تحميل سياق القضية.",
    uploadPdfOnly: "يسمح فقط بملفات PDF.",
    uploadPdfFailed: "تعذر رفع ملف PDF.",
    uploadAudioFailed: "تعذر رفع الملف الصوتي.",
    uploadPdfSuccess: "تم رفع ملف PDF وإرساله للمعالجة.",
    uploadAudioSuccess: "تم رفع الملف الصوتي. بدأت عملية التفريغ.",
    micUnsupported: "التسجيل عبر الميكروفون غير مدعوم في هذا المتصفح.",
    micAccessFailed: "تعذر الوصول إلى الميكروفون.",
    copilotFailed: "فشل طلب المساعد.",
    copiedClipboard: "تم النسخ إلى الحافظة.",
    legalAiPlatform: "منصة الذكاء القانوني",
    premiumWorkspace: "مساحة كوبايلوت الاحترافية",
    matterNavigator: "مستعرض القضايا",
    client: "العميل",
    evidenceFeed: "سجل الأدلة",
    ingestion: "الإدخال",
    workspaceFacts: "حقائق مساحة العمل",
    logout: "تسجيل الخروج",
    uploadPdf: "رفع PDF",
    uploadingPdf: "جار رفع PDF...",
    uploadAudioFile: "رفع ملف صوتي",
    uploadingAudio: "جار رفع الصوت...",
    stopRecording: "إيقاف التسجيل",
    recordVoice: "تسجيل صوت",
    lawyerId: "معرّف المحامي",
    consultations: "الاستشارات",
    voiceNotes: "ملاحظات صوتية",
    lastDocRefresh: "آخر تحديث للمستندات",
    workspaceTopDefault: "اختر قضية للبدء",
    copilotWorkspace: "مساحة عمل المساعد",
    copilotWorkspaceDesc: "صياغة قانونية واستدلال مدعوم بالذكاء الاصطناعي للقضية النشطة.",
    chatHistory: "سجل المحادثة",
    noHistory: "لا توجد رسائل بعد لهذه القضية.",
    clearHistory: "مسح السجل",
    userLabel: "أنت",
    assistantLabel: "ذكاء",
  },
};

function generateId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `m-${Date.now()}-${Math.round(Math.random() * 1_000_000)}`;
}

function compactDate(value: string | null | undefined, locale = "en-US", noDateLabel = "No date"): string {
  if (!value) return noDateLabel;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return noDateLabel;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

function compactDateTime(value: string | null | undefined, locale = "en-US", noDateLabel = "No date"): string {
  if (!value) return noDateLabel;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return noDateLabel;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function truncateText(value: string, max = 92): string {
  const cleaned = (value || "").replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max - 1)}...`;
}

function normalizeError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function normalizeStoredMessage(message: ChatMessage): ChatMessage {
  const rawAnswer = message.meta?.rawAnswer;
  if (message.role === "assistant" && typeof rawAnswer === "string" && rawAnswer && message.content !== rawAnswer) {
    return {
      ...message,
      content: rawAnswer,
    };
  }
  return message;
}

function buildChatSessionTitle(messages: ChatMessage[], fallback = "New chat"): string {
  const firstUserMessage = messages.find((message) => message.role === "user")?.content || "";
  return truncateText(firstUserMessage, 52) || fallback;
}

function normalizeStoredSession(rawSession: Partial<ChatSession> | null | undefined): ChatSession | null {
  if (!rawSession || !Array.isArray(rawSession.messages)) {
    return null;
  }

  const messages = rawSession.messages.map(normalizeStoredMessage);
  const createdAt = rawSession.createdAt || messages[0]?.timestamp || new Date().toISOString();
  const updatedAt = rawSession.updatedAt || messages[messages.length - 1]?.timestamp || createdAt;

  return {
    id: rawSession.id || generateId(),
    title: rawSession.title || buildChatSessionTitle(messages),
    createdAt,
    updatedAt,
    messages,
  };
}

function parseStoredChatState(): StoredChatSessionsState {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoredChatSessionsState>;
      const sessionsByCase: Record<number, ChatSession[]> = {};
      const activeSessionIdByCase: Record<number, string> = {};

      Object.entries(parsed.sessionsByCase || {}).forEach(([key, value]) => {
        const numeric = Number(key);
        if (Number.isNaN(numeric) || !Array.isArray(value)) return;
        const sessions = value
          .map((session) => normalizeStoredSession(session))
          .filter((session): session is ChatSession => Boolean(session));
        sessionsByCase[numeric] = sessions;
      });

      Object.entries(parsed.activeSessionIdByCase || {}).forEach(([key, value]) => {
        const numeric = Number(key);
        if (!Number.isNaN(numeric) && typeof value === "string" && value.trim()) {
          activeSessionIdByCase[numeric] = value;
        }
      });

      return { sessionsByCase, activeSessionIdByCase };
    }

    const legacyRaw = localStorage.getItem(LEGACY_CHAT_STORAGE_KEY);
    if (!legacyRaw) {
      return { sessionsByCase: {}, activeSessionIdByCase: {} };
    }

    const parsed = JSON.parse(legacyRaw) as Record<string, ChatMessage[]>;
    const sessionsByCase: Record<number, ChatSession[]> = {};
    const activeSessionIdByCase: Record<number, string> = {};

    Object.entries(parsed).forEach(([key, value]) => {
      const numeric = Number(key);
      if (!Number.isNaN(numeric) && Array.isArray(value)) {
        const messages = value.map(normalizeStoredMessage);
        const createdAt = messages[0]?.timestamp || new Date().toISOString();
        const updatedAt = messages[messages.length - 1]?.timestamp || createdAt;
        const sessionId = generateId();
        sessionsByCase[numeric] = [{
          id: sessionId,
          title: buildChatSessionTitle(messages),
          createdAt,
          updatedAt,
          messages,
        }];
        activeSessionIdByCase[numeric] = sessionId;
      }
    });

    return { sessionsByCase, activeSessionIdByCase };
  } catch {
    return { sessionsByCase: {}, activeSessionIdByCase: {} };
  }
}

function createMessage(role: "user" | "assistant", content: string, meta?: ChatMessage["meta"]): ChatMessage {
  return {
    id: generateId(),
    role,
    content,
    timestamp: new Date().toISOString(),
    meta,
  };
}

function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <span />
      <span />
      <span />
    </div>
  );
}

export default function App() {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "dark" ? "dark" : "light";
  });
  const [language, setLanguage] = useState<UiLanguage>(() => {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (stored === "de" || stored === "ar") return stored;
    return "en";
  });
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("chat");
  const [externalModeEnabled, setExternalModeEnabled] = useState(false);
  const [reasoningLevel, setReasoningLevel] = useState<ReasoningLevel>("medium");

  const [user, setUser] = useState<User | null>(null);
  const [providerStatus, setProviderStatus] = useState<ProviderStatusResponse | null>(null);
  const [clients, setClients] = useState<Client[]>([]);
  const [cases, setCases] = useState<CaseItem[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [recordings, setRecordings] = useState<VoiceRecording[]>([]);
  const [consultations, setConsultations] = useState<ConsultationRequest[]>([]);
  const [imageBatches, setImageBatches] = useState<ImageDocumentBatch[]>([]);
  const [evidenceReviews, setEvidenceReviews] = useState<EvidenceAnalysisReview[]>([]);
  const [promptLibraryEntries, setPromptLibraryEntries] = useState<PromptLibraryEntry[]>([]);
  const [caseReviewTable, setCaseReviewTable] = useState<CaseReviewTable | null>(null);
  const [selectedAnalysis, setSelectedAnalysis] = useState<FullDocumentAnalysis | null>(null);

  const [selectedClientId, setSelectedClientId] = useState<number | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);

  const [chatState, setChatState] = useState<StoredChatSessionsState>(() => parseStoredChatState());
  const [chatInput, setChatInput] = useState("");
  const [chatFeedback, setChatFeedback] = useState<Record<string, MessageFeedbackState>>({});

  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authBusy, setAuthBusy] = useState(false);
  const [authForm, setAuthForm] = useState<AuthFormState>({
    name: "",
    tenant: "",
    inviteToken: "",
    email: "",
    password: "",
    role: "lawyer",
  });

  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [caseContextLoading, setCaseContextLoading] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [uploadingAudio, setUploadingAudio] = useState(false);
  const [uploadingScannedPhotos, setUploadingScannedPhotos] = useState(false);
  const [runScannedAuthenticityCheck, setRunScannedAuthenticityCheck] = useState(false);
  const [recordingVoice, setRecordingVoice] = useState(false);
  const [composerRecording, setComposerRecording] = useState(false);
  const [composerTranscribing, setComposerTranscribing] = useState(false);
  const [optimizingPrompt, setOptimizingPrompt] = useState(false);
  const [savingPromptTemplate, setSavingPromptTemplate] = useState(false);
  const [promptLibraryDeleteId, setPromptLibraryDeleteId] = useState<number | null>(null);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [chatHistoryOpen, setChatHistoryOpen] = useState(false);
  const [reviewDecisionBusyId, setReviewDecisionBusyId] = useState<number | null>(null);

  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pdfInputRef = useRef<HTMLInputElement | null>(null);
  const audioInputRef = useRef<HTMLInputElement | null>(null);
  const scannedPhotoInputRef = useRef<HTMLInputElement | null>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaChunksRef = useRef<Blob[]>([]);
  const composerRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const composerDictationSeedRef = useRef("");
  const composerDictationFinalRef = useRef("");
  const composerRecorderRef = useRef<MediaRecorder | null>(null);
  const composerStreamRef = useRef<MediaStream | null>(null);
  const composerChunksRef = useRef<Blob[]>([]);
  const messageStreamRef = useRef<HTMLDivElement | null>(null);
  const messageEndRef = useRef<HTMLDivElement | null>(null);
  const messageAnimationTimeoutsRef = useRef<Record<string, number>>({});

  const t = useCallback(
    (key: string, fallback: string) => APP_TEXT[language]?.[key] || APP_TEXT.en[key] || fallback,
    [language]
  );
  const dateLocale = language === "de" ? "de-DE" : language === "ar" ? "ar-TN" : "en-US";
  const chatSessionsByCase = chatState.sessionsByCase;
  const activeSessionIdByCase = chatState.activeSessionIdByCase;

  const selectedCase = useMemo(
    () => cases.find((item) => item.id === selectedCaseId) || null,
    [cases, selectedCaseId]
  );
  const selectedClient = useMemo(() => {
    if (selectedCase) {
      return clients.find((item) => item.id === selectedCase.client_id) || null;
    }
    return clients.find((item) => item.id === selectedClientId) || null;
  }, [clients, selectedCase, selectedClientId]);
  const selectedDocument = useMemo(
    () => documents.find((item) => item.id === selectedDocumentId) || documents[0] || null,
    [documents, selectedDocumentId]
  );
  const activeSessions = useMemo(
    () => (selectedCaseId ? chatSessionsByCase[selectedCaseId] || [] : []),
    [chatSessionsByCase, selectedCaseId]
  );
  const activeChatSessionId = useMemo(() => {
    if (!selectedCaseId) return null;
    const explicit = activeSessionIdByCase[selectedCaseId];
    if (explicit && activeSessions.some((session) => session.id === explicit)) {
      return explicit;
    }
    return [...activeSessions]
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))[0]?.id ?? null;
  }, [activeSessionIdByCase, activeSessions, selectedCaseId]);
  const activeSession = useMemo(
    () => activeSessions.find((session) => session.id === activeChatSessionId) || null,
    [activeSessions, activeChatSessionId]
  );
  const activeMessages = activeSession?.messages || [];
  const latestMessageContent = activeMessages[activeMessages.length - 1]?.content || "";
  const historyPreview = useMemo(() => {
    return [...activeSessions]
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
      .slice(0, 12)
      .map((session) => ({
        id: session.id,
        title: session.title,
        content: truncateText(session.messages[session.messages.length - 1]?.content || "", 92),
        timestamp: session.updatedAt,
        promptCount: session.messages.filter((message) => message.role === "user").length,
      }));
  }, [activeSessions]);
  const latestAssistantMessage = useMemo(
    () => [...activeMessages].reverse().find((message) => message.role === "assistant") || null,
    [activeMessages]
  );
  const visionUnavailableReason = useMemo(() => {
    if (providerStatus?.vision_available) return null;
    return (
      providerStatus?.vision_reason_unavailable ||
      t("visionUnavailable", "Image analysis is unavailable right now.")
    );
  }, [providerStatus, t]);
  const visionFeaturesEnabled = Boolean(providerStatus?.vision_available);
  const visionUiDisabled = !visionFeaturesEnabled;
  const hasPendingImageBatch = useMemo(
    () => imageBatches.some((batch) => batch.status === "queued" || batch.status === "processing"),
    [imageBatches]
  );
  const filteredCases = useMemo(() => {
    if (!selectedClientId) return cases;
    return cases.filter((item) => item.client_id === selectedClientId);
  }, [cases, selectedClientId]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    document.documentElement.setAttribute("dir", language === "ar" ? "rtl" : "ltr");
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  }, [language]);

  useEffect(() => {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chatState));
  }, [chatState]);

  useEffect(
    () => () => {
      Object.values(messageAnimationTimeoutsRef.current).forEach((timeoutId) => {
        window.clearTimeout(timeoutId);
      });
      messageAnimationTimeoutsRef.current = {};
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      composerStreamRef.current?.getTracks().forEach((track) => track.stop());
      if (composerRecognitionRef.current) {
        try {
          composerRecognitionRef.current.abort();
        } catch {
          // Ignore cleanup errors from browser speech recognition.
        }
        composerRecognitionRef.current = null;
      }
    },
    []
  );

  useEffect(() => {
    const stream = messageStreamRef.current;
    if (!stream) return;

    const frame = window.requestAnimationFrame(() => {
      if (messageEndRef.current) {
        messageEndRef.current.scrollIntoView({ block: "end" });
        return;
      }
      stream.scrollTop = stream.scrollHeight;
    });

    return () => window.cancelAnimationFrame(frame);
  }, [activeMessages.length, latestMessageContent, selectedCaseId, copilotLoading]);

  useEffect(() => {
    if (copilotLoading || activeMessages.length > 0) {
      setChatHistoryOpen(true);
    }
  }, [copilotLoading, activeMessages.length]);

  useEffect(() => {
    if (notice || error) {
      const timeout = window.setTimeout(() => {
        setNotice(null);
        setError(null);
      }, 4200);
      return () => window.clearTimeout(timeout);
    }
    return undefined;
  }, [notice, error]);
  const bootstrapWorkspace = useCallback(
    async (activeToken: string) => {
      setWorkspaceLoading(true);
      setError(null);
      try {
        const [me, clientsRows, caseRows] = await Promise.all([
          api.me(activeToken),
          api.listClients(activeToken),
          api.listCases(activeToken),
        ]);
        setUser(me);
        setClients(clientsRows);
        setCases(caseRows);

        try {
          const provider = await api.providerStatus(activeToken);
          setProviderStatus(provider);
        } catch {
          setProviderStatus(null);
        }

        try {
          const promptLibraryRows = await api.listPromptLibrary(activeToken);
          setPromptLibraryEntries(promptLibraryRows);
        } catch {
          setPromptLibraryEntries([]);
        }

        setSelectedClientId((current) => {
          if (current && clientsRows.some((client) => client.id === current)) return current;
          return clientsRows[0]?.id ?? null;
        });
      } catch (caught) {
        setError(normalizeError(caught, t("unableLoadWorkspace", "Unable to load workspace.")));
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        setToken(null);
        setUser(null);
      } finally {
        setWorkspaceLoading(false);
      }
    },
    [t]
  );

  const loadCaseContext = useCallback(
    async (caseId: number) => {
      if (!token) return;
      setCaseContextLoading(true);
      try {
        const [docs, voiceRows, consultationRows, imageBatchRows, reviewRows, reviewTableRows] = await Promise.all([
          api.listCaseDocuments(token, caseId),
          api.listVoiceRecordings(token, caseId),
          api.listConsultationRequests(token, caseId),
          api.listCaseImageBatches(token, caseId),
          api.listEvidenceReviews(token, caseId),
          api.getCaseReviewTable(token, caseId),
        ]);
        setDocuments(docs);
        setRecordings(voiceRows);
        setConsultations(consultationRows);
        setImageBatches(imageBatchRows);
        setEvidenceReviews(reviewRows.reviews || []);
        setCaseReviewTable(reviewTableRows);
        setSelectedDocumentId((current) => {
          if (current && docs.some((document) => document.id === current)) return current;
          return docs[0]?.id ?? null;
        });
      } catch (caught) {
        setError(normalizeError(caught, t("unableLoadCaseContext", "Unable to load case context.")));
      } finally {
        setCaseContextLoading(false);
      }
    },
    [token, t]
  );

  useEffect(() => {
    if (token) {
      void bootstrapWorkspace(token);
    }
  }, [token, bootstrapWorkspace]);

  useEffect(() => {
    if (!filteredCases.length) {
      setSelectedCaseId(null);
      return;
    }
    setSelectedCaseId((current) => {
      if (current && filteredCases.some((item) => item.id === current)) return current;
      return filteredCases[0].id;
    });
  }, [filteredCases]);

  useEffect(() => {
    if (!selectedCaseId) {
      setDocuments([]);
      setRecordings([]);
      setConsultations([]);
      setImageBatches([]);
      setEvidenceReviews([]);
      setCaseReviewTable(null);
      setSelectedAnalysis(null);
      return;
    }
    void loadCaseContext(selectedCaseId);
  }, [selectedCaseId, loadCaseContext]);

  useEffect(() => {
    if (!token || !selectedCaseId || !hasPendingImageBatch) {
      return undefined;
    }

    let isCancelled = false;
    let timeoutId: number | undefined;
    let pollCycles = 0;

    const pollCaseContext = async () => {
      if (isCancelled) {
        return;
      }

      if (pollCycles >= IMAGE_BATCH_POLL_MAX_CYCLES) {
        setNotice(
          t(
            "imageBatchPollingPaused",
            "Automatic refresh paused because image processing is taking longer than expected. Refresh the case context manually."
          )
        );
        return;
      }

      pollCycles += 1;
      await loadCaseContext(selectedCaseId);

      if (isCancelled) {
        return;
      }

      timeoutId = window.setTimeout(() => {
        void pollCaseContext();
      }, IMAGE_BATCH_POLL_INTERVAL_MS);
    };

    timeoutId = window.setTimeout(() => {
      void pollCaseContext();
    }, IMAGE_BATCH_POLL_INTERVAL_MS);

    return () => {
      isCancelled = true;
      if (typeof timeoutId === "number") {
        window.clearTimeout(timeoutId);
      }
    };
  }, [token, selectedCaseId, hasPendingImageBatch, loadCaseContext, t]);

  useEffect(() => {
    if (!token || !selectedDocumentId) {
      setSelectedAnalysis(null);
      return;
    }
    let active = true;
    setAnalysisLoading(true);
    void api
      .getDocumentAnalysis(token, selectedDocumentId)
      .then((analysis) => {
        if (active) setSelectedAnalysis(analysis);
      })
      .catch(() => {
        if (active) setSelectedAnalysis(null);
      })
      .finally(() => {
        if (active) setAnalysisLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedDocumentId, token]);

  const createChatSession = useCallback((caseId: number, seedPrompt?: string) => {
    const now = new Date().toISOString();
    const sessionId = generateId();
    const session: ChatSession = {
      id: sessionId,
      title: truncateText((seedPrompt || "").trim(), 52) || t("newChat", "New chat"),
      createdAt: now,
      updatedAt: now,
      messages: [],
    };

    setChatState((current) => ({
      sessionsByCase: {
        ...current.sessionsByCase,
        [caseId]: [session, ...(current.sessionsByCase[caseId] || [])],
      },
      activeSessionIdByCase: {
        ...current.activeSessionIdByCase,
        [caseId]: sessionId,
      },
    }));

    return sessionId;
  }, [t]);

  const selectChatSession = useCallback((caseId: number, sessionId: string) => {
    setChatState((current) => ({
      sessionsByCase: current.sessionsByCase,
      activeSessionIdByCase: {
        ...current.activeSessionIdByCase,
        [caseId]: sessionId,
      },
    }));
  }, []);

  const appendMessage = useCallback((caseId: number, sessionId: string, message: ChatMessage) => {
    setChatState((current) => {
      const sessions = current.sessionsByCase[caseId] || [];
      const nextSessions = sessions.map((session) => {
        if (session.id !== sessionId) return session;
        const nextMessages = [...session.messages, message];
        return {
          ...session,
          title:
            session.messages.length === 0 && message.role === "user"
              ? truncateText(message.content, 52) || t("newChat", "New chat")
              : session.title,
          updatedAt: message.timestamp,
          messages: nextMessages,
        };
      });

      return {
        sessionsByCase: {
          ...current.sessionsByCase,
          [caseId]: nextSessions,
        },
        activeSessionIdByCase: {
          ...current.activeSessionIdByCase,
          [caseId]: sessionId,
        },
      };
    });
  }, [t]);

  const updateMessageContent = useCallback((caseId: number, sessionId: string, messageId: string, content: string) => {
    setChatState((current) => {
      const sessions = current.sessionsByCase[caseId] || [];
      return {
        sessionsByCase: {
          ...current.sessionsByCase,
          [caseId]: sessions.map((session) => (
            session.id === sessionId
              ? {
                ...session,
                messages: session.messages.map((message) => (
                  message.id === messageId
                    ? {
                      ...message,
                      content,
                    }
                    : message
                )),
              }
              : session
          )),
        },
        activeSessionIdByCase: current.activeSessionIdByCase,
      };
    });
  }, []);

  const animateAssistantMessage = useCallback((caseId: number, sessionId: string, message: ChatMessage) => {
    const fullContent = Array.from(message.content);
    const messageId = message.id;
    const existingTimeout = messageAnimationTimeoutsRef.current[messageId];
    if (existingTimeout) {
      window.clearTimeout(existingTimeout);
      delete messageAnimationTimeoutsRef.current[messageId];
    }

    appendMessage(caseId, sessionId, {
      ...message,
      content: "",
    });

    if (!fullContent.length) {
      return;
    }

    const chunkSize =
      fullContent.length > 1800 ? 20 :
        fullContent.length > 1000 ? 12 :
          fullContent.length > 500 ? 6 :
            3;
    const baseDelay =
      fullContent.length > 1800 ? 14 :
        fullContent.length > 1000 ? 18 :
          24;

    let cursor = 0;
    const tick = () => {
      cursor = Math.min(fullContent.length, cursor + chunkSize);
      updateMessageContent(caseId, sessionId, messageId, fullContent.slice(0, cursor).join(""));

      if (cursor >= fullContent.length) {
        delete messageAnimationTimeoutsRef.current[messageId];
        return;
      }

      const previousToken = fullContent[cursor - 1] || "";
      const delay =
        previousToken === "\n"
          ? baseDelay + 60
          : /[.!?]/.test(previousToken)
            ? baseDelay + 40
            : baseDelay;

      messageAnimationTimeoutsRef.current[messageId] = window.setTimeout(tick, delay);
    };

    messageAnimationTimeoutsRef.current[messageId] = window.setTimeout(tick, 110);
  }, [appendMessage, updateMessageContent]);

  const sendMessage = useCallback(
    async (promptText: string) => {
      if (!token || !selectedCaseId) return;
      const trimmed = promptText.trim();
      if (!trimmed) return;

      const outboundPrompt = trimmed;
      const sessionId = activeChatSessionId || createChatSession(selectedCaseId, outboundPrompt);
      const userMessage = createMessage("user", outboundPrompt);
      const caseMessages = activeSession?.messages || [];
      appendMessage(selectedCaseId, sessionId, userMessage);
      setChatInput("");
      setAttachmentMenuOpen(false);
      setCopilotLoading(true);
      setError(null);

      try {
        const response = await api.copilot(token, outboundPrompt, {
          topK: REASONING_TOP_K[reasoningLevel],
          useExternalResearch: externalModeEnabled || workspaceMode === "legal_search" || workspaceMode === "agent",
          mode: workspaceMode === "legal_search" ? "legal_search" : "default",
          legalSearchMultilingualOutput: workspaceMode === "legal_search",
          agentMode: workspaceMode === "agent",
          workspaceCaseId: selectedCaseId,
          workspaceDocumentId: selectedDocumentId,
          conversationHistory: [...caseMessages, userMessage]
            .slice(-12)
            .map((message) => ({
              role: message.role,
              content: message.content,
              parsed_intent: message.meta?.parsedIntent,
              case_id: selectedCaseId,
              document_id: selectedDocumentId,
            })),
        });

        const assistantMessage = createMessage("assistant", response.answer || response.message, {
          parsedIntent: response.parsed_intent,
          confidence: response.confidence,
          fallbackReason: response.fallback_reason,
          actionCategory: response.action_category,
          actionStatus: response.action_status,
          permissionDenied: response.permission_denied,
          steps: response.steps,
          structuredResult: response.structured_result,
          sources: response.sources,
          citations: response.citations,
          executionTrace: response.execution_trace,
          cache: response.cache,
          jobId: response.job_id,
          caseSnapshotVersion: response.case_snapshot_version,
          artifact: response.artifact,
          jurisdiction: response.jurisdiction,
          rawAnswer: response.answer,
        });

        animateAssistantMessage(selectedCaseId, sessionId, assistantMessage);
      } catch (caught) {
        setError(normalizeError(caught, t("copilotFailed", "Copilot request failed.")));
      } finally {
        setCopilotLoading(false);
      }
    },
    [
      token,
      selectedCaseId,
      activeChatSessionId,
      activeSession,
      appendMessage,
      animateAssistantMessage,
      createChatSession,
      reasoningLevel,
      workspaceMode,
      selectedDocumentId,
      externalModeEnabled,
      t,
    ]
  );
  const handleFeedback = useCallback(
    async (message: ChatMessage, value: FeedbackValue) => {
      if (!token || !selectedCaseId) return;
      const caseMessages = activeMessages;
      const messageIndex = caseMessages.findIndex((row) => row.id === message.id);
      if (messageIndex < 0) return;

      let promptText = "No prompt context";
      for (let index = messageIndex - 1; index >= 0; index -= 1) {
        if (caseMessages[index].role === "user") {
          promptText = caseMessages[index].content;
          break;
        }
      }

      setChatFeedback((current) => ({
        ...current,
        [message.id]: { value, status: "saving" },
      }));

      try {
        await api.createCopilotFeedback(token, {
          message_id: message.id,
          case_id: selectedCaseId,
          document_id: selectedDocumentId,
          prompt_text: promptText,
          response_text: message.content,
          parsed_intent: message.meta?.parsedIntent || null,
          confidence: message.meta?.confidence || null,
          feedback_value: value,
          source_count: message.meta?.sources?.length || 0,
          metadata: {
            mode: workspaceMode,
            action_category: message.meta?.actionCategory || null,
            action_status: message.meta?.actionStatus || null,
          },
        });
        setChatFeedback((current) => ({
          ...current,
          [message.id]: { value, status: "submitted" },
        }));
      } catch {
        setChatFeedback((current) => ({
          ...current,
          [message.id]: { value, status: "error" },
        }));
      }
    },
    [activeMessages, selectedCaseId, selectedDocumentId, token, workspaceMode]
  );

  const handleCopy = useCallback((message: ChatMessage) => {
    void navigator.clipboard.writeText(message.content);
    setNotice(t("copiedClipboard", "Copied to clipboard."));
  }, [t]);

  const handleRegenerate = useCallback(
    (message: ChatMessage) => {
      if (!selectedCaseId) return;
      const caseMessages = activeMessages;
      const index = caseMessages.findIndex((row) => row.id === message.id);
      if (index < 1) return;
      for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
        if (caseMessages[cursor].role === "user") {
          const prompt = caseMessages[cursor].content;
          void sendMessage(prompt);
          return;
        }
      }
    },
    [activeMessages, selectedCaseId, sendMessage]
  );

  const clearActiveCaseHistory = useCallback(() => {
    if (!selectedCaseId || !activeChatSessionId) return;
    setChatState((current) => {
      const nextSessions = (current.sessionsByCase[selectedCaseId] || []).filter((session) => session.id !== activeChatSessionId);
      const nextActiveId = nextSessions[0]?.id;
      const nextActiveSessionIdByCase = { ...current.activeSessionIdByCase };
      if (nextActiveId) {
        nextActiveSessionIdByCase[selectedCaseId] = nextActiveId;
      } else {
        delete nextActiveSessionIdByCase[selectedCaseId];
      }
      return {
        sessionsByCase: {
          ...current.sessionsByCase,
          [selectedCaseId]: nextSessions,
        },
        activeSessionIdByCase: nextActiveSessionIdByCase,
      };
    });
    setChatFeedback({});
    setNotice(`${t("chatHistory", "Chat History")}: ${t("clearHistory", "Clear history")}`);
  }, [activeChatSessionId, selectedCaseId, t]);

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (authMode === "register") {
        await api.register({
          name: authForm.name,
          email: authForm.email,
          password: authForm.password,
          tenant_name: authForm.tenant || undefined,
          invite_token: authForm.inviteToken || undefined,
          role: authForm.role,
        });
        setNotice(t("accountCreated", "Account created. Sign in to continue."));
        setAuthMode("login");
      } else {
        const auth = await api.login(authForm.email, authForm.password);
        localStorage.setItem(TOKEN_STORAGE_KEY, auth.access_token);
        setToken(auth.access_token);
      }
    } catch (caught) {
      setError(normalizeError(caught, t("authFailed", "Authentication failed.")));
    } finally {
      setAuthBusy(false);
    }
  }

  function logout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUser(null);
    setClients([]);
    setCases([]);
    setDocuments([]);
    setRecordings([]);
    setConsultations([]);
    setImageBatches([]);
    setEvidenceReviews([]);
    setPromptLibraryEntries([]);
    setCaseReviewTable(null);
    setSelectedCaseId(null);
    setSelectedClientId(null);
    setSelectedDocumentId(null);
    setSelectedAnalysis(null);
    setChatInput("");
    setExternalModeEnabled(false);
    setWorkspaceMode("chat");
  }

  function buildPromptTemplateTitle(prompt: string) {
    const clean = prompt.replace(/\s+/g, " ").trim();
    if (!clean) return "Saved prompt";
    return truncateText(clean, 48);
  }

  async function uploadPdfFile(file: File) {
    if (!token || !selectedCaseId) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError(t("uploadPdfOnly", "Only PDF files are allowed."));
      return;
    }
    setUploadingPdf(true);
    setError(null);
    try {
      const response = await api.uploadDocument(token, selectedCaseId, file);
      await loadCaseContext(selectedCaseId);
      setNotice(
        response.job?.id
          ? `${t("uploadPdfSuccess", "PDF uploaded and queued for processing.")} Job: ${response.job.id}`
          : t("uploadPdfSuccess", "PDF uploaded and queued for processing.")
      );
    } catch (caught) {
      setError(normalizeError(caught, t("uploadPdfFailed", "Unable to upload PDF.")));
    } finally {
      setUploadingPdf(false);
    }
  }

  async function uploadAudioFile(file: File) {
    if (!token || !selectedCaseId) return;
    setUploadingAudio(true);
    setError(null);
    try {
      const response = await api.uploadVoiceRecording(token, selectedCaseId, file);
      await loadCaseContext(selectedCaseId);
      setNotice(
        response.job?.id
          ? `${t("uploadAudioSuccess", "Voice file uploaded. Transcription is running.")} Job: ${response.job.id}`
          : t("uploadAudioSuccess", "Voice file uploaded. Transcription is running.")
      );
    } catch (caught) {
      setError(normalizeError(caught, t("uploadAudioFailed", "Unable to upload audio.")));
    } finally {
      setUploadingAudio(false);
    }
  }

  const focusComposer = useCallback(() => {
    window.requestAnimationFrame(() => {
      const textarea = composerTextareaRef.current;
      if (!textarea) return;
      textarea.focus();
      const length = textarea.value.length;
      textarea.setSelectionRange(length, length);
    });
  }, []);

  function onPdfFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void uploadPdfFile(file);
    event.target.value = "";
  }

  function onAudioFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void uploadAudioFile(file);
    event.target.value = "";
  }

  async function uploadScannedPhotoFiles(files: File[]) {
    if (!token || !selectedCaseId || !files.length) return;
    if (!providerStatus?.vision_available) {
      setError(
        providerStatus?.vision_reason_unavailable
        || t("visionUnavailable", "Image analysis is unavailable right now.")
      );
      return;
    }
    setUploadingScannedPhotos(true);
    setError(null);
    try {
      const response = await api.uploadImageBatch(token, selectedCaseId, files, {
        title: selectedCase ? `${selectedCase.title} - scanned photos` : "Scanned photos",
        generateDocument: true,
        runAuthenticityCheck: runScannedAuthenticityCheck,
      });
      await loadCaseContext(selectedCaseId);
      setNotice(
        response.job?.id
          ? `Scanned photos uploaded and queued for OCR${runScannedAuthenticityCheck ? " with authenticity screening" : ""}. Job: ${response.job.id}`
          : `Scanned photos uploaded and queued for OCR${runScannedAuthenticityCheck ? " with authenticity screening" : ""}.`
      );
    } catch (caught) {
      setError(normalizeError(caught, "Unable to upload scanned photos."));
    } finally {
      setUploadingScannedPhotos(false);
    }
  }

  function onScannedPhotosSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;
    void uploadScannedPhotoFiles(files);
  }

  function releaseComposerRecorder() {
    composerStreamRef.current?.getTracks().forEach((track) => track.stop());
    composerStreamRef.current = null;
    composerRecorderRef.current = null;
    composerChunksRef.current = [];
  }

  function releaseComposerRecognition() {
    if (composerRecognitionRef.current) {
      try {
        composerRecognitionRef.current.abort();
      } catch {
        // Ignore cleanup errors from browser speech recognition.
      }
    }
    composerRecognitionRef.current = null;
    composerDictationSeedRef.current = "";
    composerDictationFinalRef.current = "";
  }

  async function optimizePromptDraft() {
    if (!token) return;
    const trimmed = chatInput.trim();
    if (!trimmed) return;

    setOptimizingPrompt(true);
    setError(null);

    try {
      const response = await api.optimizePrompt(token, {
        prompt: trimmed,
        workspaceCaseId: selectedCaseId,
        workspaceDocumentId: selectedDocumentId,
      });
      setChatInput(response.optimized_prompt || trimmed);
      setNotice(t("promptOptimizedNotice", "Prompt optimized for clearer legal reasoning."));
      focusComposer();
    } catch (caught) {
      setError(normalizeError(caught, t("promptOptimizeFailed", "Unable to optimize the prompt.")));
    } finally {
      setOptimizingPrompt(false);
    }
  }

  async function saveCurrentPromptToLibrary() {
    if (!token) return;
    const trimmed = chatInput.trim();
    if (!trimmed) return;

    setSavingPromptTemplate(true);
    setError(null);

    try {
      const entry = await api.createPromptLibraryEntry(token, {
        title: buildPromptTemplateTitle(trimmed),
        prompt_text: trimmed,
        description: selectedCase ? `Saved from case #${selectedCase.id} (${selectedCase.title})` : null,
        category: workspaceMode === "legal_search" ? "research" : workspaceMode === "agent" ? "workflow" : "general",
        is_favorite: false,
      });
      setPromptLibraryEntries((current) => [entry, ...current.filter((item) => item.id !== entry.id)]);
      setNotice("Prompt saved to the library.");
    } catch (caught) {
      setError(normalizeError(caught, "Unable to save the prompt."));
    } finally {
      setSavingPromptTemplate(false);
    }
  }

  async function deletePromptLibraryEntry(entryId: number) {
    if (!token) return;
    setPromptLibraryDeleteId(entryId);
    setError(null);
    try {
      await api.deletePromptLibraryEntry(token, entryId);
      setPromptLibraryEntries((current) => current.filter((entry) => entry.id !== entryId));
      setNotice("Prompt removed from the library.");
    } catch (caught) {
      setError(normalizeError(caught, "Unable to remove the prompt."));
    } finally {
      setPromptLibraryDeleteId(null);
    }
  }

  function applyPromptLibraryEntry(entry: PromptLibraryEntry) {
    setChatInput(entry.prompt_text);
    setAttachmentMenuOpen(false);
    setNotice(`Loaded prompt: ${entry.title}`);
    focusComposer();
  }

  async function handleEvidenceReviewDecision(reviewId: number, decision: "approved" | "rejected") {
    if (!token || !selectedCaseId) return;
    setReviewDecisionBusyId(reviewId);
    setError(null);
    try {
      await api.decideEvidenceReview(token, reviewId, { decision });
      await loadCaseContext(selectedCaseId);
      setNotice(`Evidence review ${decision}.`);
    } catch (caught) {
      setError(normalizeError(caught, "Unable to update the evidence review."));
    } finally {
      setReviewDecisionBusyId(null);
    }
  }

  async function startComposerRecording() {
    if (recordingVoice) {
      setError(t("stopCaseRecordingFirst", "Stop the case voice recording before starting prompt dictation."));
      return;
    }

    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognitionCtor) {
      try {
        setError(null);
        composerDictationSeedRef.current = chatInput.trim() ? `${chatInput.trim()} ` : "";
        composerDictationFinalRef.current = "";

        const recognition = new SpeechRecognitionCtor();
        recognition.lang = language === "de" ? "de-DE" : language === "ar" ? "ar-TN" : "en-US";
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        recognition.onresult = (event) => {
          let finalTranscript = composerDictationFinalRef.current;
          let interimTranscript = "";

          for (let index = event.resultIndex; index < event.results.length; index += 1) {
            const result = event.results[index];
            const transcript = String(result?.[0]?.transcript || "").trim();
            if (!transcript) continue;

            if (result?.isFinal) {
              finalTranscript = `${finalTranscript}${transcript} `;
            } else {
              interimTranscript = `${interimTranscript}${transcript} `;
            }
          }

          composerDictationFinalRef.current = finalTranscript;
          const nextValue = `${composerDictationSeedRef.current}${finalTranscript}${interimTranscript}`
            .replace(/\s+/g, " ")
            .trim();
          setChatInput(nextValue);
        };

        recognition.onerror = (event) => {
          const errorCode = String(event?.error || "").trim().toLowerCase();
          setComposerRecording(false);
          composerRecognitionRef.current = null;

          if (errorCode && errorCode !== "aborted" && errorCode !== "no-speech") {
            setError(t("voiceTranscriptFailed", "Unable to transcribe your voice input."));
          }
        };

        recognition.onend = () => {
          setComposerRecording(false);
          composerRecognitionRef.current = null;
          composerDictationSeedRef.current = "";
          composerDictationFinalRef.current = "";
          focusComposer();
        };

        composerRecognitionRef.current = recognition;
        setComposerRecording(true);
        setNotice(t("liveVoiceInputNotice", "Live voice dictation is active."));
        recognition.start();
        focusComposer();
        return;
      } catch (caught) {
        releaseComposerRecognition();
        setComposerRecording(false);
        setError(normalizeError(caught, t("micAccessFailed", "Unable to access microphone.")));
        return;
      }
    }

    if (!token) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(t("micUnsupported", "Microphone recording is not supported in this browser."));
      return;
    }

    try {
      setError(null);
      setNotice(t("liveVoiceFallbackNotice", "Live dictation is unavailable in this browser. Using slower transcription fallback."));
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);

      composerRecorderRef.current = recorder;
      composerStreamRef.current = stream;
      composerChunksRef.current = [];
      setComposerRecording(true);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          composerChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const mimeType = recorder.mimeType || "audio/webm";
        const extension = mimeType.includes("wav") ? "wav" : mimeType.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(composerChunksRef.current, { type: mimeType });
        const file = new File([blob], `prompt-dictation-${Date.now()}.${extension}`, { type: mimeType });

        releaseComposerRecorder();
        setComposerRecording(false);
        setComposerTranscribing(true);

        void api.transcribeVoiceInput(token, file)
          .then((response) => {
            const transcript = response.transcript_text.trim();
            if (!response.success || !transcript) {
              throw new Error(response.error || t("voiceTranscriptFailed", "Unable to transcribe your voice input."));
            }

            setChatInput((current) => current.trim() ? `${current.trim()} ${transcript}` : transcript);
            setNotice(t("voiceTranscriptInserted", "Voice transcript added to the prompt."));
            focusComposer();
          })
          .catch((caught) => {
            setError(normalizeError(caught, t("voiceTranscriptFailed", "Unable to transcribe your voice input.")));
          })
          .finally(() => {
            setComposerTranscribing(false);
          });
      };

      recorder.start();
    } catch (caught) {
      releaseComposerRecorder();
      setComposerRecording(false);
      setComposerTranscribing(false);
      setError(normalizeError(caught, t("micAccessFailed", "Unable to access microphone.")));
    }
  }

  function stopComposerRecording() {
    if (composerRecognitionRef.current) {
      try {
        composerRecognitionRef.current.stop();
      } catch {
        releaseComposerRecognition();
        setComposerRecording(false);
      }
      return;
    }

    if (composerRecorderRef.current && composerRecorderRef.current.state !== "inactive") {
      composerRecorderRef.current.stop();
    }
  }

  async function startVoiceRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(t("micUnsupported", "Microphone recording is not supported in this browser."));
      return;
    }

    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);

      mediaRecorderRef.current = recorder;
      mediaStreamRef.current = stream;
      mediaChunksRef.current = [];
      setRecordingVoice(true);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          mediaChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const mimeType = recorder.mimeType || "audio/webm";
        const extension = mimeType.includes("wav") ? "wav" : mimeType.includes("ogg") ? "ogg" : "webm";
        const blob = new Blob(mediaChunksRef.current, { type: mimeType });
        const file = new File([blob], `recorded-voice-${Date.now()}.${extension}`, { type: mimeType });

        mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
        mediaStreamRef.current = null;
        mediaRecorderRef.current = null;
        mediaChunksRef.current = [];
        setRecordingVoice(false);
        void uploadAudioFile(file);
      };

      recorder.start();
    } catch (caught) {
      setRecordingVoice(false);
      setError(normalizeError(caught, t("micAccessFailed", "Unable to access microphone.")));
    }
  }

  function stopVoiceRecording() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage(chatInput);
    }
  }

  const topMetaLine = useMemo(() => {
    const provider = providerStatus
      ? `${providerStatus.provider_name} | ${providerStatus.model || t("modelLabel", "model")}`
      : t("providerUnavailable", "Provider unavailable");
    const caseLabel = selectedCase ? `${t("caseLabel", "Case")} #${selectedCase.id}` : t("noCaseSelected", "No case selected");
    return `${provider} | ${caseLabel}`;
  }, [providerStatus, selectedCase, t]);
  const roleLabel = useMemo(() => {
    if (!user?.role) return "Workspace view";
    return `${user.role.charAt(0).toUpperCase()}${user.role.slice(1)} view`;
  }, [user?.role]);
  const caseStatusLabel = useMemo(() => {
    if (!selectedCase) return "No active case";
    return `${selectedCase.jurisdiction_country} | ${selectedCase.status}`;
  }, [selectedCase]);
  const workspaceModules = useMemo(
    () => [
      { title: "Assistant", detail: `${activeMessages.filter((item) => item.role === "assistant").length} replies`, accent: "ai" },
      { title: "Vault", detail: `${documents.length} docs | ${imageBatches.length} batches`, accent: "neutral" },
      { title: "Review", detail: `${caseReviewTable?.row_count ?? 0} rows | ${evidenceReviews.length} reviews`, accent: "warning" },
      { title: "Workflows", detail: `${consultations.length} consultations | ${recordings.length} voice notes`, accent: "stable" },
      { title: "Library", detail: `${promptLibraryEntries.length} saved prompts`, accent: "neutral" },
    ],
    [activeMessages, documents.length, imageBatches.length, caseReviewTable?.row_count, evidenceReviews.length, consultations.length, recordings.length, promptLibraryEntries.length]
  );
  const workspaceSnapshot = useMemo(
    () => [
      { label: "Documents", value: String(documents.length), meta: selectedDocument ? `Focused: ${truncateText(selectedDocument.filename, 28)}` : "No focused document" },
      { label: "Open reviews", value: String(evidenceReviews.filter((review) => review.status === "ready_for_review").length), meta: `${imageBatches.length} scanned batch${imageBatches.length === 1 ? "" : "es"}` },
      { label: "Matter activity", value: String(consultations.length + recordings.length), meta: `${consultations.length} consultations | ${recordings.length} recordings` },
      { label: "Prompt assets", value: String(promptLibraryEntries.length), meta: `${historyPreview.length} active chat${historyPreview.length === 1 ? "" : "s"}` },
    ],
    [documents.length, selectedDocument, evidenceReviews, imageBatches.length, consultations.length, recordings.length, promptLibraryEntries.length, historyPreview.length]
  );
  const suggestedActions = useMemo(
    () => [
      selectedCase ? `Summarize case #${selectedCase.id}` : "Summarize this matter",
      "List the main legal risks",
      "Draft a client update email",
      "Show missing evidence and next steps",
    ],
    [selectedCase]
  );
  if (!token) {
    return (
      <div className="auth-shell">
        <section className="auth-hero">
          <p className="hero-kicker">{t("authKicker", "Next-Gen Legal AI Workspace")}</p>
          <h1>{t("authTitle", "Calm. Intelligent. Powerful.")}</h1>
          <p>
            {t("authSubtitle", "A premium legal copilot with case-grounded reasoning, structured insights, and evidence-aware drafting.")}
          </p>
          <div className="hero-points">
            <span>{t("authPoint1", "AI-native legal chat")}</span>
            <span>{t("authPoint2", "Case intelligence dashboard")}</span>
            <span>{t("authPoint3", "Document + voice ingestion")}</span>
          </div>
        </section>

        <section className="auth-panel">
          <header>
            <h2>{authMode === "login" ? t("signIn", "Sign in") : t("createAccountTitle", "Create account")}</h2>
            <p>{t("secureAccess", "Secure access to your legal workspace.")}</p>
          </header>

          <div className="auth-switch">
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
                    required
                    value={authForm.name}
                    onChange={(event) => setAuthForm((current) => ({ ...current, name: event.target.value }))}
                  />
                </label>
                <label>
                  {t("tenant", "Tenant / Firm")}
                  <input
                    placeholder="Required only for the first bootstrap admin"
                    value={authForm.tenant}
                    onChange={(event) => setAuthForm((current) => ({ ...current, tenant: event.target.value }))}
                  />
                </label>
                <label>
                  Invite token
                  <input
                    placeholder="Required for invited staff registration"
                    value={authForm.inviteToken}
                    onChange={(event) => setAuthForm((current) => ({ ...current, inviteToken: event.target.value }))}
                  />
                </label>
                <label>
                  {t("role", "Role")}
                  <select
                    value={authForm.role}
                    onChange={(event) =>
                      setAuthForm((current) => ({
                        ...current,
                        role: event.target.value as AuthFormState["role"],
                      }))
                    }
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
                required
                type="email"
                value={authForm.email}
                onChange={(event) => setAuthForm((current) => ({ ...current, email: event.target.value }))}
              />
            </label>

            <label>
              {t("password", "Password")}
              <input
                required
                type="password"
                value={authForm.password}
                onChange={(event) => setAuthForm((current) => ({ ...current, password: event.target.value }))}
              />
            </label>

            <button className="primary-button" disabled={authBusy} type="submit">
              {authBusy ? t("working", "Working...") : authMode === "login" ? t("enterWorkspace", "Enter Workspace") : t("createAccount", "Create Account")}
            </button>
          </form>

          {notice ? <p className="notice-banner">{notice}</p> : null}
          {error ? <p className="error-banner">{error}</p> : null}
        </section>
      </div>
    );
  }

  return (
    <div className="workspace-shell">
      <aside className="left-rail glass">
        <header className="left-brand">
          <div className="brand-mark">H</div>
          <div>
            <strong>Legal AI</strong>
            <small>{t("premiumWorkspace", "Legal Copilot Workspace")}</small>
          </div>
        </header>

        <section className="left-section">
          <h3>{t("matterNavigator", "Matter Navigator")}</h3>
          <label>
            {t("client", "Client")}
            <select
              value={selectedClientId ?? ""}
              onChange={(event) => setSelectedClientId(event.target.value ? Number(event.target.value) : null)}
            >
              {clients.map((client) => (
                <option key={client.id} value={client.id}>
                  {client.name}
                </option>
              ))}
            </select>
          </label>

          <div className="case-list">
            {filteredCases.length ? (
              filteredCases.map((item) => (
                <button
                  key={item.id}
                  className={`case-item ${selectedCaseId === item.id ? "active" : ""}`}
                  onClick={() => setSelectedCaseId(item.id)}
                  type="button"
                >
                  <strong>{item.title}</strong>
                  <small>
                    {t("caseLabel", "Case")} #{item.id} | {item.jurisdiction_country}
                  </small>
                </button>
              ))
            ) : (
              <p className="muted">{t("noCasesForClient", "No cases found for selected client.")}</p>
            )}
          </div>
        </section>

        <section className="left-section">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Modules</p>
              <h3>Workspace Map</h3>
            </div>
            <span className="section-count">{workspaceModules.length}</span>
          </div>
          <div className="module-nav">
            {workspaceModules.map((module) => (
              <article key={module.title} className={`module-nav-item ${module.accent}`}>
                <strong>{module.title}</strong>
                <small>{module.detail}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="left-section">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Matter</p>
              <h3>Case Navigation</h3>
            </div>
            <span className="section-count">{filteredCases.length}</span>
          </div>
          <div className="history-heading-row">
            <h3>{t("chatHistory", "Chat History")}</h3>
            <div className="history-actions">
              <button
                className="ghost-button history-action"
                disabled={!selectedCaseId}
                onClick={() => {
                  if (!selectedCaseId) return;
                  createChatSession(selectedCaseId);
                }}
                type="button"
              >
                {t("newChat", "New chat")}
              </button>
              <button
                className="ghost-button history-action"
                disabled={!activeChatSessionId}
                onClick={clearActiveCaseHistory}
                type="button"
              >
                {t("clearHistory", "Clear history")}
              </button>
            </div>
          </div>
          <div className="history-list">
            {historyPreview.length ? (
              historyPreview.map((item) => (
                <button
                  key={item.id}
                  className={`history-item ${item.id === activeChatSessionId ? "active" : ""}`}
                  onClick={() => {
                    if (!selectedCaseId) return;
                    selectChatSession(selectedCaseId, item.id);
                  }}
                  type="button"
                >
                  <strong>{item.title}</strong>
                  <p>{item.content}</p>
                  <small>
                    {compactDateTime(item.timestamp, dateLocale, t("noDate", "No date"))}
                    {" · "}
                    {item.promptCount} {item.promptCount === 1 ? t("promptLabel", "prompt") : t("promptsLabel", "prompts")}
                  </small>
                </button>
              ))
            ) : (
              <p className="muted">{t("noHistory", "No messages yet for this case.")}</p>
            )}
          </div>
        </section>

        <details className="left-extra-sections">
          <summary>{t("moreWorkspaceTools", "More workspace tools")}</summary>
          <div className="left-extra-body">

            <section className="left-section">
              <div className="history-heading-row">
                <h3>Prompt Library</h3>
                <div className="history-actions">
                  <button
                    className="ghost-button history-action"
                    disabled={!chatInput.trim() || savingPromptTemplate}
                    onClick={() => void saveCurrentPromptToLibrary()}
                    type="button"
                  >
                    {savingPromptTemplate ? "Saving..." : "Save prompt"}
                  </button>
                </div>
              </div>
              <div className="history-list prompt-library-list">
                {promptLibraryEntries.length ? (
                  promptLibraryEntries.slice(0, 8).map((entry) => (
                    <article key={entry.id} className="history-item prompt-library-item">
                      <button className="prompt-library-main" onClick={() => applyPromptLibraryEntry(entry)} type="button">
                        <strong>{entry.title}</strong>
                        <p>{entry.description || truncateText(entry.prompt_text, 96)}</p>
                        <small>
                          {(entry.category || "general").toUpperCase()}
                          {" · "}
                          {compactDateTime(entry.updated_at, dateLocale, t("noDate", "No date"))}
                        </small>
                      </button>
                      <button
                        aria-label={`Delete ${entry.title}`}
                        className="ghost-button history-action prompt-library-delete"
                        disabled={promptLibraryDeleteId === entry.id}
                        onClick={() => void deletePromptLibraryEntry(entry.id)}
                        type="button"
                      >
                        {promptLibraryDeleteId === entry.id ? "..." : "Delete"}
                      </button>
                    </article>
                  ))
                ) : (
                  <p className="muted">Save your best prompts here for drafting, legal research, and case workflows.</p>
                )}
              </div>
            </section>

            <section className="left-section">
              <h3>{t("evidenceFeed", "Evidence Feed")}</h3>
              <div className="simple-list">
                {documents.slice(0, 6).map((document) => (
                  <article key={document.id}>
                    <strong>{document.filename}</strong>
                    <small>
                      {t("documentsLabel", "Documents")} #{document.id} | {document.processing_status}
                    </small>
                  </article>
                ))}
                {!documents.length ? <p className="muted">{t("noEvidenceYet", "No evidence uploaded yet.")}</p> : null}
              </div>
            </section>
            <section className="left-section">
              <h3>Scanned Photos</h3>
              <div className="simple-list image-batch-list">
                {imageBatches.slice(0, 5).map((batch) => (
                  <article key={batch.id} className={`image-batch-card ${batch.status}`}>
                    <strong>{batch.title}</strong>
                    <small>
                      Batch #{batch.id} · {batch.asset_count} page{batch.asset_count === 1 ? "" : "s"} · {batch.status}
                    </small>
                    <small>
                      OCR doc: {batch.generated_document_id ? `#${batch.generated_document_id}` : "pending"}
                    </small>
                    {batch.run_authenticity_check ? <small>Authenticity review requested</small> : null}
                  </article>
                ))}
                {!imageBatches.length ? <p className="muted">No scanned photo batches yet.</p> : null}
              </div>
            </section>
            <section className="left-section">
              <h3>{t("ingestion", "Ingestion")}</h3>
              <div className="quick-actions">
                <button
                  className="secondary-button"
                  disabled={!selectedCaseId || uploadingPdf}
                  onClick={() => pdfInputRef.current?.click()}
                  type="button"
                >
                  {uploadingPdf ? t("uploadingPdf", "Uploading PDF...") : t("uploadPdf", "Upload PDF")}
                </button>
                <button
                  className="secondary-button"
                  disabled={!selectedCaseId || uploadingAudio}
                  onClick={() => audioInputRef.current?.click()}
                  type="button"
                >
                  {uploadingAudio ? t("uploadingAudio", "Uploading audio...") : t("uploadAudioFile", "Upload audio file")}
                </button>
                <button
                  className={`secondary-button ${recordingVoice ? "recording" : ""}`}
                  disabled={!selectedCaseId || composerRecording || composerTranscribing}
                  onClick={() => {
                    if (recordingVoice) stopVoiceRecording();
                    else void startVoiceRecording();
                  }}
                  type="button"
                >
                  {recordingVoice ? t("stopRecording", "Stop recording") : t("recordVoice", "Record voice")}
                </button>
                <button
                  className="secondary-button"
                  disabled={!selectedCaseId || uploadingScannedPhotos || visionUiDisabled}
                  onClick={() => scannedPhotoInputRef.current?.click()}
                  type="button"
                >
                  {uploadingScannedPhotos
                    ? "Uploading photos..."
                    : visionUiDisabled
                      ? "Scanned photos unavailable"
                      : "Upload scanned photos"}
                </button>
              </div>
              <label className="composer-save-toggle ingestion-toggle">
                <input
                  checked={runScannedAuthenticityCheck}
                  onChange={(event) => setRunScannedAuthenticityCheck(event.target.checked)}
                  type="checkbox"
                />
                <span>Run authenticity screening only when needed</span>
              </label>
              {visionUiDisabled ? (
                <p className="muted">{visionUnavailableReason || "Scanned-photo OCR is unavailable right now."}</p>
              ) : (
                <p className="muted">
                  {runScannedAuthenticityCheck
                    ? "The upload will run OCR and an authenticity review before the lawyer checks the papers."
                    : "The upload will run OCR only and skip authenticity screening."}
                </p>
              )}
            </section>
            <section className="left-section">
              <h3>Review Queue</h3>
              <div className="simple-list review-list">
                {evidenceReviews.slice(0, 6).map((review) => {
                  const canDecide = (user?.role === "lawyer" || user?.role === "admin") && review.status === "ready_for_review";
                  return (
                    <article key={review.id} className={`review-card review-${review.status}`}>
                      <strong>Review #{review.id}</strong>
                      <small>
                        Risk {review.risk_score}/100 · {review.confidence} · {review.status}
                      </small>
                      <p>{truncateText(review.analysis_text, 120)}</p>
                      {review.signals.length ? <small>Signals: {review.signals.slice(0, 2).join(" · ")}</small> : null}
                      {canDecide ? (
                        <div className="review-actions">
                          <button
                            className="ghost-button history-action"
                            disabled={reviewDecisionBusyId === review.id}
                            onClick={() => void handleEvidenceReviewDecision(review.id, "approved")}
                            type="button"
                          >
                            Approve
                          </button>
                          <button
                            className="ghost-button history-action"
                            disabled={reviewDecisionBusyId === review.id}
                            onClick={() => void handleEvidenceReviewDecision(review.id, "rejected")}
                            type="button"
                          >
                            Reject
                          </button>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
                {!evidenceReviews.length ? <p className="muted">No authenticity reviews yet.</p> : null}
              </div>
            </section>

            <section className="left-section">
              <h3>{t("workspaceFacts", "Workspace Facts")}</h3>
              <ul className="facts-list">
                <li>{t("lawyerId", "Lawyer ID")}: {selectedCase?.lawyer_id ?? t("notAvailable", "N/A")}</li>
                <li>{t("client", "Client")}: {selectedClient?.name || t("notAvailable", "N/A")}</li>
                <li>{t("documentsLabel", "Documents")}: {documents.length}</li>
                <li>{t("consultations", "Consultations")}: {consultations.length}</li>
                <li>{t("voiceNotes", "Voice notes")}: {recordings.length}</li>
                <li>Scanned batches: {imageBatches.length}</li>
                <li>Pending reviews: {evidenceReviews.filter((review) => review.status === "ready_for_review").length}</li>
                <li>{t("lastDocRefresh", "Last document refresh")}: {documents[0] ? compactDateTime(documents[0].upload_timestamp, dateLocale, t("noDate", "No date")) : t("notAvailable", "N/A")}</li>
              </ul>
            </section>
          </div>
        </details>

        <button className="ghost-button logout" onClick={logout} type="button">
          {t("logout", "Logout")}
        </button>
      </aside>

      <main className="center-panel glass">
        <header className="workspace-topbar">
          <div>
            <p className="meta">{t("setClientMatter", "Set client matter")}</p>
            <h1>{t("workspaceBrand", "Legal AI")}</h1>
            <p className="workspace-subtitle">
              {selectedCase
                ? `${selectedCase.title} · ${topMetaLine}`
                : t("workspaceTopDefault", "Select a case to start")}
            </p>
            <div className="workspace-context-chips">
              <span className="context-chip role">{roleLabel}</span>
              <span className="context-chip">{selectedCase ? `${t("caseLabel", "Case")} #${selectedCase.id}` : t("noCaseSelected", "No case selected")}</span>
              <span className="context-chip">{caseStatusLabel}</span>
            </div>
          </div>
          <div className="toolbar-controls">
            <label>
              {t("language", "Language")}
              <select value={language} onChange={(event) => setLanguage(event.target.value as UiLanguage)}>
                <option value="en">{t("languageEnglish", "English")}</option>
                <option value="de">{t("languageGerman", "German")}</option>
                <option value="ar">{t("languageArabic", "Arabic")}</option>
              </select>
            </label>
            <label>
              {t("reasoning", "Reasoning")}
              <select
                value={reasoningLevel}
                onChange={(event) => setReasoningLevel(event.target.value as ReasoningLevel)}
              >
                <option value="low">{t("reasoningLow", "Low")}</option>
                <option value="medium">{t("reasoningMedium", "Medium")}</option>
                <option value="high">{t("reasoningHigh", "High")}</option>
              </select>
            </label>
            <button
              className="secondary-button"
              onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
              type="button"
            >
              {theme === "dark" ? t("light", "Light") : t("dark", "Dark")}
            </button>
          </div>
        </header>

        <details className="workspace-collapsible">
          <summary>{t("matterDetails", "Matter details")}</summary>
          <section className="matter-overview-strip">
            <div className="matter-overview-card">
              <p className="section-kicker">Current Matter</p>
              <h2>{selectedCase ? selectedCase.title : t("noCaseSelected", "No case selected")}</h2>
              <div className="matter-overview-meta">
                <span>{selectedClient ? selectedClient.name : t("notAvailable", "N/A")}</span>
                <span>{selectedCase ? `${selectedCase.jurisdiction_country} · ${selectedCase.status}` : "Waiting for case selection"}</span>
                <span>{providerStatus?.provider_name || t("providerUnavailable", "Provider unavailable")}</span>
              </div>
            </div>
            <div className="matter-stat-grid">
              {workspaceSnapshot.map((item) => (
                <article key={item.label} className="matter-stat-card">
                  <small>{item.label}</small>
                  <strong>{item.value}</strong>
                  <span>{item.meta}</span>
                </article>
              ))}
            </div>
          </section>
        </details>

        <section className="copilot-shell">
          <details className="workspace-collapsible center-secondary-collapsible">
            <summary>{t("contextAnalysis", "Context and analysis")}</summary>
            <div className="workspace-collapsible-body">
              <header className="copilot-head">
                <div>
                  <h2>{t("copilotWorkspace", "Copilot Workspace")}</h2>
                  <p>{t("copilotWorkspaceDesc", "AI-grounded legal drafting and reasoning for active matter.")}</p>
                </div>
                <div className="capability-pill-row">
                  <span className="capability-pill">Grounded chat</span>
                  <span className="capability-pill">Drafting copilot</span>
                  <span className="capability-pill">Evidence OCR</span>
                  <span className="capability-pill">Verifier agent</span>
                </div>
              </header>

              {notice ? <div className="notice-banner">{notice}</div> : null}
              {error ? <div className="error-banner">{error}</div> : null}

              {selectedCase && caseReviewTable?.rows?.length ? (
                <details className="workspace-collapsible">
                  <summary>{t("reviewTable", "Review Table")} · {caseReviewTable.row_count} docs</summary>
                  <section className="review-table-shell">
                    <div className="review-table-head">
                      <div>
                        <h3>Review Table</h3>
                        <p>Structured extraction across {caseReviewTable.row_count} document(s) in this matter.</p>
                      </div>
                    </div>
                    <div className="review-table-wrap">
                      <table className="review-table">
                        <thead>
                          <tr>
                            <th>Document</th>
                            <th>Type</th>
                            <th>Parties</th>
                            <th>Important Dates</th>
                            <th>Risks</th>
                            <th>Next Actions</th>
                            <th>Source</th>
                          </tr>
                        </thead>
                        <tbody>
                          {caseReviewTable.rows.map((row) => (
                            <tr key={row.document_id}>
                              <td>
                                <strong>{row.filename}</strong>
                                <small>
                                  Doc #{row.document_id} · {row.processing_status} · {row.summary_status}
                                </small>
                              </td>
                              <td>
                                <span>{row.document_type || "Unknown"}</span>
                                {typeof row.document_type_confidence === "number" ? (
                                  <small>{Math.round(row.document_type_confidence * 100)}% confidence</small>
                                ) : null}
                              </td>
                              <td>
                                <div className="table-chip-list">
                                  {row.parties.length ? row.parties.map((party, index) => (
                                    <span key={`${party}-${index}`} className="table-chip">{party}</span>
                                  )) : <span className="table-empty">—</span>}
                                </div>
                              </td>
                              <td>
                                <div className="table-chip-list">
                                  {row.important_dates.length ? row.important_dates.map((item, index) => (
                                    <span key={`${item}-${index}`} className="table-chip date">{item}</span>
                                  )) : <span className="table-empty">—</span>}
                                </div>
                              </td>
                              <td>
                                <div className="table-chip-list">
                                  {row.legal_risks.length ? row.legal_risks.map((risk, index) => (
                                    <span key={`${risk}-${index}`} className="table-chip risk">{risk}</span>
                                  )) : <span className="table-empty">—</span>}
                                </div>
                              </td>
                              <td>
                                <div className="table-chip-list">
                                  {row.recommended_actions.length ? row.recommended_actions.map((item, index) => (
                                    <span key={`${item}-${index}`} className="table-chip action">{item}</span>
                                  )) : <span className="table-empty">—</span>}
                                </div>
                              </td>
                              <td>
                                <span className={`table-chip ${row.source_kind === "ocr_generated" ? "warning" : "stable"}`}>
                                  {row.source_kind === "ocr_generated" ? "Scanned OCR" : "Uploaded"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </details>
              ) : null}

              {workspaceLoading || caseContextLoading ? (
                <div className="workspace-skeleton-grid" aria-hidden="true">
                  <div className="skeleton-card tall" />
                  <div className="skeleton-card" />
                  <div className="skeleton-card" />
                </div>
              ) : null}
            </div>
          </details>

          <div className="chat-surface">
            <section className="workflow-primary">
              <h3>{t("recommendedWorkflows", "Recommended workflows")}</h3>
              <div className="workflow-grid">
                {suggestedActions.slice(0, 4).map((action) => (
                  <button key={action} className="workflow-card" onClick={() => setChatInput(action)} type="button">
                    <strong>{action}</strong>
                    <small>{t("draftLabel", "Draft")} · 2 steps</small>
                  </button>
                ))}
              </div>
              <div className="empty-chat-actions">
                {suggestedActions.slice(4).map((action) => (
                  <button key={action} className="ghost-button suggestion-chip" onClick={() => setChatInput(action)} type="button">
                    {action}
                  </button>
                ))}
              </div>
            </section>

            <details className="composer-advanced">
              <summary>{t("advancedPromptOptions", "Advanced prompt options")}</summary>
              <div className="composer-tool-row">
                <button
                  className="composer-tool"
                  onClick={() => setAttachmentMenuOpen((current) => !current)}
                  type="button"
                >
                  {t("plusAttachmentsTitle", "Files and sources")}
                </button>
                <button
                  className="composer-tool"
                  onClick={() => setAttachmentMenuOpen(true)}
                  type="button"
                >
                  {t("prompts", "Prompts")}
                </button>
                <button
                  className="composer-tool"
                  onClick={() => setAttachmentMenuOpen(true)}
                  type="button"
                >
                  {t("customize", "Customize")}
                </button>
                <button
                  className="composer-tool"
                  onClick={() => setAttachmentMenuOpen(true)}
                  type="button"
                >
                  {t("improve", "Improve")}
                </button>
              </div>
              <div className="mode-chip-row">
                <button
                  className={`mode-chip ${externalModeEnabled ? "external" : ""}`}
                  onClick={() => setExternalModeEnabled((current) => !current)}
                  type="button"
                >
                  {t("deepResearch", "Deep research")}
                </button>
                <span className="mode-chip">
                  {workspaceMode === "chat"
                    ? t("modeChat", "Chat Mode")
                    : workspaceMode === "agent"
                      ? t("modeAgent", "Agent Mode")
                      : t("modeLegalSearch", "Legal Search Mode")}
                </span>
                {externalModeEnabled ? <span className="mode-chip external">{t("modeExternal", "External Mode")}</span> : null}
              </div>
              <p className="composer-footnote">
                {workspaceMode === "legal_search"
                  ? t("legalSearchFootnote", "Legal Search Mode prioritizes jurisdiction-specific legal sources before fallback reasoning.")
                  : workspaceMode === "agent"
                    ? t("agentFootnote", "Agent Mode enables structured reasoning and legal workflow orchestration.")
                    : t("chatFootnote", "Chat Mode provides conversational legal support grounded in your case context.")}
              </p>
            </details>

            <details
              className="workspace-collapsible chat-history-collapsible"
              open={chatHistoryOpen}
              onToggle={(event) => setChatHistoryOpen((event.currentTarget as HTMLDetailsElement).open)}
            >
              <summary>{t("conversationAndOutputs", "Conversation and outputs")}</summary>
              <div ref={messageStreamRef} className="message-stream">
                {workspaceLoading || caseContextLoading ? (
                  <div className="loading-inline">{t("loadingWorkspace", "Loading workspace context...")}</div>
                ) : null}

                {!activeMessages.length && !copilotLoading ? (
                  <div className="empty-chat conversation-empty">
                    <h3>{t("noConversationYet", "No conversation yet")}</h3>
                    <p>{t("conversationHint", "Use the prompt box above to start.")}</p>
                  </div>
                ) : null}

                {activeMessages.map((message) => (
                  <ChatMessageBubble
                    key={message.id}
                    feedback={chatFeedback[message.id]}
                    language={language}
                    message={message}
                    onCopy={handleCopy}
                    onFeedback={handleFeedback}
                    onRegenerate={handleRegenerate}
                  />
                ))}

                {copilotLoading ? <TypingIndicator /> : null}
                <div ref={messageEndRef} aria-hidden="true" />
              </div>
            </details>

            <footer className="composer-shell">
              {attachmentMenuOpen ? (
                <div className="attachment-menu">
                  <div className="menu-group">
                    <small className="menu-group-title">{t("plusModesTitle", "Modes")}</small>
                    <button
                      className={`menu-item mode ${workspaceMode === "chat" ? "active" : ""}`}
                      onClick={() => {
                        setWorkspaceMode("chat");
                        setAttachmentMenuOpen(false);
                      }}
                      type="button"
                    >
                      <strong>{t("modeChat", "Chat Mode")}</strong>
                      <small>{t("modeChatDesc", "Fast legal discussion")}</small>
                    </button>
                    <button
                      className={`menu-item mode ${workspaceMode === "agent" ? "active" : ""}`}
                      onClick={() => {
                        setWorkspaceMode("agent");
                        setAttachmentMenuOpen(false);
                      }}
                      type="button"
                    >
                      <strong>{t("modeAgent", "Agent Mode")}</strong>
                      <small>{t("modeAgentDesc", "Step-by-step execution")}</small>
                    </button>
                    <button
                      className={`menu-item mode ${workspaceMode === "legal_search" ? "active" : ""}`}
                      onClick={() => {
                        setWorkspaceMode("legal_search");
                        setAttachmentMenuOpen(false);
                      }}
                      type="button"
                    >
                      <strong>{t("modeLegalSearch", "Legal Search Mode")}</strong>
                      <small>{t("modeLegalSearchDesc", "Source-grounded legal answers")}</small>
                    </button>
                    <button
                      className={`menu-item mode ${externalModeEnabled ? "active" : ""}`}
                      onClick={() => {
                        setExternalModeEnabled((current) => !current);
                        setAttachmentMenuOpen(false);
                      }}
                      type="button"
                    >
                      <strong>{t("modeExternal", "External Mode")}</strong>
                      <small>{t("modeExternalDesc", "Web-enhanced legal research")}</small>
                    </button>
                  </div>
                  <div className="menu-group">
                    <small className="menu-group-title">{t("plusAttachmentsTitle", "Attachments")}</small>
                    <p className="muted">Chat image analysis was removed. Use scanned-photo upload from the case workspace instead.</p>
                  </div>
                </div>
              ) : null}
              <form
                className={`composer ${copilotLoading || composerTranscribing || optimizingPrompt ? "busy" : ""}`}
                onSubmit={(event) => {
                  event.preventDefault();
                  void sendMessage(chatInput);
                }}
              >
                <button
                  className="composer-plus"
                  onClick={() => setAttachmentMenuOpen((current) => !current)}
                  type="button"
                >
                  +
                </button>

                <textarea
                  ref={composerTextareaRef}
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  onKeyDown={handleComposerKeyDown}
                  placeholder={t("askPlaceholder", "Ask about your case, risks, deadlines, or draft something...")}
                />

                <div className="composer-controls">
                  <button
                    aria-label={optimizingPrompt ? t("optimizingPrompt", "Optimizing...") : t("optimizePrompt", "Optimize")}
                    className={`composer-optimize ${optimizingPrompt ? "busy" : ""}`}
                    disabled={!chatInput.trim() || copilotLoading || composerRecording || composerTranscribing || optimizingPrompt}
                    onClick={() => void optimizePromptDraft()}
                    title={optimizingPrompt ? t("optimizingPrompt", "Optimizing...") : t("optimizePrompt", "Optimize")}
                    type="button"
                  >
                    <svg aria-hidden="true" viewBox="0 0 20 20">
                      <path d="M10 2.8 11.3 6l3.2 1.3-3.2 1.3L10 11.8 8.7 8.6 5.5 7.3 8.7 6 10 2.8Z" />
                      <path d="M15.5 11.2 16.2 13l1.8.7-1.8.7-0.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8Z" />
                      <path d="M5.1 11.8 5.7 13.3l1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6.6-1.5Z" />
                    </svg>
                  </button>
                  <button
                    aria-label={composerRecording ? t("stopVoiceInput", "Stop voice input") : t("voiceInput", "Voice input")}
                    className={`composer-icon-button ${composerRecording ? "recording" : ""}`}
                    disabled={!token || copilotLoading || composerTranscribing || optimizingPrompt || recordingVoice}
                    onClick={() => {
                      if (composerRecording) stopComposerRecording();
                      else void startComposerRecording();
                    }}
                    title={
                      composerTranscribing
                        ? t("transcribingVoiceInput", "Transcribing...")
                        : composerRecording
                          ? t("stopVoiceInput", "Stop voice input")
                          : t("voiceInput", "Voice input")
                    }
                    type="button"
                  >
                    <svg aria-hidden="true" viewBox="0 0 20 20">
                      <rect x="7" y="3.2" width="6" height="9.2" rx="3" />
                      <path d="M5.5 9.5a4.5 4.5 0 0 0 9 0" />
                      <path d="M10 14v3" />
                      <path d="M7 17h6" />
                    </svg>
                  </button>
                  <button
                    aria-label={t("send", "Send")}
                    className="composer-send"
                    disabled={!chatInput.trim() || copilotLoading || !selectedCaseId || composerRecording || composerTranscribing || optimizingPrompt}
                    type="submit"
                  >
                    {t("askHarvey", "Ask Legal AI")}
                  </button>
                </div>
              </form>
              {(composerRecording || composerTranscribing) ? (
                <div className="composer-status-row">
                  <span className={`mode-chip ${composerRecording ? "external" : ""}`}>
                    {composerRecording
                      ? t("stopVoiceInput", "Stop voice input")
                      : t("transcribingVoiceInput", "Transcribing...")}
                  </span>
                </div>
              ) : null}

              <div className="composer-selected-row">
                <button
                  className="selected-mode-chip primary"
                  onClick={() => setAttachmentMenuOpen(true)}
                  type="button"
                >
                  {workspaceMode === "chat"
                    ? t("modeChat", "Chat Mode")
                    : workspaceMode === "agent"
                      ? t("modeAgent", "Agent Mode")
                      : t("modeLegalSearch", "Legal Search Mode")}
                  {" "}v
                </button>
                {externalModeEnabled ? (
                  <button
                    className="selected-mode-chip external"
                    onClick={() => setExternalModeEnabled(false)}
                    type="button"
                  >
                    {t("modeExternal", "External Mode")}
                  </button>
                ) : null}
              </div>
            </footer>
          </div>
        </section>
      </main>

      <Suspense
        fallback={
          <aside className="right-panel glass">
            <div className="loading-inline">{t("loadingWorkspace", "Loading workspace context...")}</div>
          </aside>
        }
      >
        <IntelligencePanel
          analysis={selectedAnalysis}
          caseItem={selectedCase}
          client={selectedClient}
          consultations={consultations}
          documents={documents}
          language={language}
          latestAssistantMessage={latestAssistantMessage}
          recordings={recordings}
        />
      </Suspense>

      <input
        ref={pdfInputRef}
        accept=".pdf,application/pdf"
        onChange={onPdfFileSelected}
        style={{ display: "none" }}
        type="file"
      />
      <input
        ref={audioInputRef}
        accept="audio/webm,audio/wav,audio/x-wav,audio/mpeg,audio/mp4,audio/mp3,audio/ogg,audio/m4a,audio/x-m4a"
        onChange={onAudioFileSelected}
        style={{ display: "none" }}
        type="file"
      />
      <input
        ref={scannedPhotoInputRef}
        accept="image/*"
        multiple
        onChange={onScannedPhotosSelected}
        style={{ display: "none" }}
        type="file"
      />
    </div>
  );
}

