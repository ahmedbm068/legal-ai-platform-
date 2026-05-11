
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { persistChatStateToLocalStorage } from "./chatStorage";
import { workspaceApi as api } from "./workspaceApi";
import ChatMessageBubble, { type MessageFeedbackState } from "./components/ChatMessageBubble";
import CaseCalendarPanel from "./components/CaseCalendarPanel";
import {
  CHAT_GLOBAL_SCOPE_ID,
  CHAT_STORAGE_KEY,
  DEFAULT_LAWYER_PHONE,
  IMAGE_BATCH_POLL_INTERVAL_MS,
  IMAGE_BATCH_POLL_MAX_CYCLES,
  IMAGE_BATCH_POLL_STALL_MAX_CYCLES,
  LANGUAGE_STORAGE_KEY,
  REASONING_TOP_K,
  THEME_STORAGE_KEY,
  TOKEN_STORAGE_KEY,
  compactDateTime,
  createMessage,
  formatFileSize,
  generateId,
  normalizeError,
  parseMarkdownPreview,
  parseStoredChatState,
  truncateText,
  type AuthFormState,
  type BibliothequeItem,
  type ChatSession,
  type FeedbackValue,
  type LibraryFilter,
  type LibraryPreviewAsset,
  type ReasoningLevel,
  type SidebarTab,
  type StoredChatSessionsState,
  type ThemeMode,
  type UiLanguage,
  type WorkspaceMode,
} from "./legacyWorkspaceSupport";
import type {
  AIResponseAuditLog,
  CaseItem,
  ChatMessage,
  CallSession,
  CalendarAppointment,
  Client,
  ConsultationRequest,
  DocumentItem,
  EvidenceAnalysisReview,
  FeedbackRootCause,
  ImageBatchDetailResponse,
  ImageDocumentBatch,
  PromptLibraryEntry,
  ProviderStatusResponse,
  CaseReviewTable,
  User,
  VoiceRecording,
} from "./types";

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
    languageFrench: "French",
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
  fr: {
    noDate: "Aucune date",
    modelLabel: "modèle",
    notAvailable: "N/D",
    caseIdLabel: "ID",
    providerUnavailable: "Fournisseur indisponible",
    noCaseSelected: "Aucun dossier sélectionné",
    noCasesForClient: "Aucun dossier trouvé pour le client sélectionné.",
    noEvidenceYet: "Aucune pièce téléversée pour le moment.",
    loadingWorkspace: "Chargement du contexte de l'espace de travail...",
    startQuestionTitle: "Commencez par une question juridique",
    startQuestionBody: "Posez une question sur les risques, les obligations, les délais, les contradictions, ou rédigez une réponse juridique professionnelle.",
    focusedDocumentNone: "aucun",
    caseLabel: "Dossier",
    documentsLabel: "Documents",
    consultationsLabel: "Consultations",
    focusedDocumentLabel: "Document ciblé",
    attachPdf: "Joindre un PDF",
    attachVoice: "Joindre un fichier audio",
    recordFromMic: "Enregistrer depuis le micro",
    stopMicRecording: "Arrêter l'enregistrement",
    askPlaceholder: "Posez une question sur votre dossier, les risques, les délais, ou rédigez quelque chose...",
    send: "Envoyer",
    optimizePrompt: "Optimiser",
    optimizingPrompt: "Optimisation...",
    voiceInput: "Saisie vocale",
    stopVoiceInput: "Arrêter la saisie vocale",
    transcribingVoiceInput: "Transcription...",
    liveVoiceInputNotice: "La dictée vocale en direct est active.",
    liveVoiceFallbackNotice: "La dictée en direct n'est pas disponible dans ce navigateur. Repli sur une transcription plus lente.",
    promptOptimizedNotice: "Invite optimisée pour un raisonnement juridique plus clair.",
    promptOptimizeFailed: "Impossible d'optimiser l'invite.",
    voiceTranscriptFailed: "Impossible de transcrire votre saisie vocale.",
    voiceTranscriptInserted: "Transcription vocale ajoutée à l'invite.",
    stopCaseRecordingFirst: "Arrêtez l'enregistrement du dossier avant de démarrer la dictée.",
    legalSearchFootnote: "Le mode Recherche juridique privilégie les sources juridiques propres à la juridiction avant tout raisonnement de repli.",
    agentFootnote: "Le mode Agent active un raisonnement structuré et l'orchestration des workflows juridiques.",
    chatFootnote: "Le mode Chat fournit une assistance juridique conversationnelle ancrée dans le contexte de votre dossier.",
    modeChat: "Mode Chat",
    modeChatDesc: "Discussion juridique rapide",
    modeAgent: "Mode Agent",
    modeAgentDesc: "Exécution étape par étape",
    modeLegalSearch: "Mode Recherche juridique",
    modeLegalSearchDesc: "Réponses juridiques sourcées",
    modeExternal: "Mode Externe",
    modeExternalDesc: "Recherche juridique enrichie par le web",
    plusModesTitle: "Modes",
    plusAttachmentsTitle: "Pièces jointes",
    language: "Langue",
    languageEnglish: "Anglais",
    languageFrench: "Français",
    languageGerman: "Allemand",
    languageArabic: "Arabe",
    reasoning: "Raisonnement",
    reasoningLow: "Faible",
    reasoningMedium: "Moyen",
    reasoningHigh: "Élevé",
    light: "Clair",
    dark: "Sombre",
    authKicker: "Espace de travail juridique IA nouvelle génération",
    authTitle: "Calme. Intelligent. Puissant.",
    authSubtitle: "Un copilote juridique haut de gamme avec un raisonnement ancré dans le dossier, des analyses structurées et une rédaction guidée par les preuves.",
    authPoint1: "Chat juridique natif IA",
    authPoint2: "Tableau de bord d'intelligence du dossier",
    authPoint3: "Ingestion de documents et de la voix",
    signIn: "Se connecter",
    createAccountTitle: "Créer un compte",
    secureAccess: "Accès sécurisé à votre espace juridique.",
    login: "Connexion",
    register: "Inscription",
    fullName: "Nom complet",
    tenant: "Locataire / Cabinet",
    role: "Rôle",
    lawyer: "Avocat",
    assistant: "Assistant",
    admin: "Admin",
    email: "E-mail",
    password: "Mot de passe",
    working: "Traitement en cours...",
    enterWorkspace: "Entrer dans l'espace",
    createAccount: "Créer un compte",
    accountCreated: "Compte créé. Connectez-vous pour continuer.",
    authFailed: "Échec de l'authentification.",
    unableLoadWorkspace: "Impossible de charger l'espace de travail.",
    unableLoadCaseContext: "Impossible de charger le contexte du dossier.",
    uploadPdfOnly: "Seuls les fichiers PDF sont autorisés.",
    uploadPdfFailed: "Impossible de téléverser le PDF.",
    uploadAudioFailed: "Impossible de téléverser l'audio.",
    uploadPdfSuccess: "PDF téléversé et mis en file d'attente pour traitement.",
    uploadAudioSuccess: "Fichier audio téléversé. La transcription est en cours.",
    micUnsupported: "L'enregistrement micro n'est pas pris en charge dans ce navigateur.",
    micAccessFailed: "Impossible d'accéder au microphone.",
    copilotFailed: "Échec de la requête du copilote.",
    copiedClipboard: "Copié dans le presse-papiers.",
    legalAiPlatform: "Plateforme juridique IA",
    premiumWorkspace: "Espace Copilote Premium",
    matterNavigator: "Navigateur de dossiers",
    client: "Client",
    evidenceFeed: "Flux de preuves",
    ingestion: "Ingestion",
    workspaceFacts: "Faits de l'espace de travail",
    logout: "Déconnexion",
    uploadPdf: "Téléverser un PDF",
    uploadingPdf: "Téléversement du PDF...",
    uploadAudioFile: "Téléverser un fichier audio",
    uploadingAudio: "Téléversement de l'audio...",
    stopRecording: "Arrêter l'enregistrement",
    recordVoice: "Enregistrer la voix",
    lawyerId: "ID Avocat",
    consultations: "Consultations",
    voiceNotes: "Notes vocales",
    lastDocRefresh: "Dernière actualisation des documents",
    workspaceTopDefault: "Sélectionnez un dossier pour commencer",
    copilotWorkspace: "Espace Copilote",
    copilotWorkspaceDesc: "Rédaction et raisonnement juridiques alimentés par l'IA pour le dossier actif.",
    chatHistory: "Historique du chat",
    noHistory: "Aucun message pour ce dossier.",
    clearHistory: "Effacer l'historique",
    userLabel: "Vous",
    assistantLabel: "IA",
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
    languageFrench: "Französisch",
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
    languageFrench: "الفرنسية",
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
  const [callSessions, setCallSessions] = useState<CallSession[]>([]);
  const [calendarAppointments, setCalendarAppointments] = useState<CalendarAppointment[]>([]);
  const [consultations, setConsultations] = useState<ConsultationRequest[]>([]);
  const [imageBatches, setImageBatches] = useState<ImageDocumentBatch[]>([]);
  const [evidenceReviews, setEvidenceReviews] = useState<EvidenceAnalysisReview[]>([]);
  const [promptLibraryEntries, setPromptLibraryEntries] = useState<PromptLibraryEntry[]>([]);
  const [caseReviewTable, setCaseReviewTable] = useState<CaseReviewTable | null>(null);

  const [selectedClientId, setSelectedClientId] = useState<number | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<number | null>(null);
  const [activeCallSessionId, setActiveCallSessionId] = useState<number | null>(null);
  const [lawyerPhoneDraft, setLawyerPhoneDraft] = useState(DEFAULT_LAWYER_PHONE);
  const [callNotesDraft, setCallNotesDraft] = useState("");
  const [creatingCallSession, setCreatingCallSession] = useState(false);
  const [savingLawyerPhone, setSavingLawyerPhone] = useState(false);

  const [leftRailOpen, setLeftRailOpen] = useState(true);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("navigator");
  const [bibliothequeFilter, setBibliothequeFilter] = useState<LibraryFilter>("all");
  const [bibliothequeQuery, setBibliothequeQuery] = useState("");
  const [bibliothequeGlobalItems, setBibliothequeGlobalItems] = useState<BibliothequeItem[]>([]);
  const [bibliothequeLoading, setBibliothequeLoading] = useState(false);
  const [libraryPreviewItem, setLibraryPreviewItem] = useState<BibliothequeItem | null>(null);
  const [libraryPreviewLoading, setLibraryPreviewLoading] = useState(false);
  const [libraryPreviewError, setLibraryPreviewError] = useState<string | null>(null);
  const [libraryPreviewUrl, setLibraryPreviewUrl] = useState<string | null>(null);
  const [libraryPreviewBatch, setLibraryPreviewBatch] = useState<ImageBatchDetailResponse | null>(null);
  const [libraryPreviewAssets, setLibraryPreviewAssets] = useState<LibraryPreviewAsset[]>([]);
  const [libraryPreviewAssetId, setLibraryPreviewAssetId] = useState<number | null>(null);
  const [libraryPreviewMarkdownText, setLibraryPreviewMarkdownText] = useState<string | null>(null);
  const [selectionGateOpen, setSelectionGateOpen] = useState(false);
  const [selectionGateDone, setSelectionGateDone] = useState(false);
  const [gateClientId, setGateClientId] = useState<number | null>(null);
  const [gateCaseId, setGateCaseId] = useState<number | null>(null);

  const [chatState, setChatState] = useState<StoredChatSessionsState>(() => parseStoredChatState());
  const [chatInput, setChatInput] = useState("");
  const [chatFeedback, setChatFeedback] = useState<Record<string, MessageFeedbackState>>({});
  const [auditLogs, setAuditLogs] = useState<AIResponseAuditLog[]>([]);
  const [auditPanelOpen, setAuditPanelOpen] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);

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
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const [uploadingAudio, setUploadingAudio] = useState(false);
  const [uploadingScannedPhotos, setUploadingScannedPhotos] = useState(false);
  const [runScannedAuthenticityCheck, setRunScannedAuthenticityCheck] = useState(false);
  const [recordingVoice, setRecordingVoice] = useState(false);
  const [summarizingCallRecordingId, setSummarizingCallRecordingId] = useState<number | null>(null);
  const [composerRecording, setComposerRecording] = useState(false);
  const [composerTranscribing, setComposerTranscribing] = useState(false);
  const [optimizingPrompt, setOptimizingPrompt] = useState(false);
  const [savingPromptTemplate, setSavingPromptTemplate] = useState(false);
  const [promptLibraryDeleteId, setPromptLibraryDeleteId] = useState<number | null>(null);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [chatHistoryOpen, setChatHistoryOpen] = useState(true);
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
  const libraryPreviewObjectUrlsRef = useRef<string[]>([]);
  const libraryPreviewRequestIdRef = useRef(0);
  const callRecordingFollowUpTimeoutRef = useRef<number | null>(null);
  const copilotAbortControllerRef = useRef<AbortController | null>(null);

  const t = useCallback(
    (key: string, fallback: string) => APP_TEXT[language]?.[key] || APP_TEXT.en[key] || fallback,
    [language]
  );
  const dateLocale = language === "de" ? "de-DE" : language === "ar" ? "ar-TN" : "en-US";
  const chatSessionsByCase = chatState.sessionsByCase;
  const activeSessionIdByCase = chatState.activeSessionIdByCase;
  const activeChatScopeId = selectedCaseId ?? CHAT_GLOBAL_SCOPE_ID;

  const selectedCase = useMemo(
    () => cases.find((item) => item.id === selectedCaseId) || null,
    [cases, selectedCaseId]
  );
  const selectedDocument = useMemo(
    () => documents.find((item) => item.id === selectedDocumentId) || null,
    [documents, selectedDocumentId]
  );
  const activeCallSession = useMemo(
    () => callSessions.find((item) => item.id === activeCallSessionId) || null,
    [activeCallSessionId, callSessions]
  );
  const selectedClient = useMemo(
    () => clients.find((item) => item.id === selectedClientId) || null,
    [clients, selectedClientId]
  );
  const activeSessions = useMemo(
    () => chatSessionsByCase[activeChatScopeId] || [],
    [chatSessionsByCase, activeChatScopeId]
  );
  const activeChatSessionId = useMemo(() => {
    const explicit = activeSessionIdByCase[activeChatScopeId];
    if (explicit && activeSessions.some((session) => session.id === explicit)) {
      return explicit;
    }
    return [...activeSessions]
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))[0]?.id ?? null;
  }, [activeSessionIdByCase, activeSessions, activeChatScopeId]);
  const activeSession = useMemo(
    () => activeSessions.find((session) => session.id === activeChatSessionId) || null,
    [activeSessions, activeChatSessionId]
  );
  const activeMessages = activeSession?.messages || [];
  const latestAssistantMessage = useMemo(
    () => [...activeMessages].reverse().find((message) => message.role === "assistant") || null,
    [activeMessages]
  );
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
  const chatStarterPrompts = useMemo(() => {
    const caseAwarePrompt = selectedCase
      ? `Summarize the main legal risks in case #${selectedCase.id} and propose the next 5 actions.`
      : "Help me structure a legal issue analysis in 5 clear steps.";
    return [
      caseAwarePrompt,
      "Draft a professional client update email about current legal posture and next steps.",
      "Create a deadline checklist and missing-information list for this matter.",
    ];
  }, [selectedCase]);
  const workflowPackPrompts = useMemo(() => ([
    "Run a civil dispute analysis: identify issue, articles, application, weaknesses, contradictions, and next steps.",
    "Run a succession analysis: identify heirs, relevant succession rules, missing documents, and preliminary distribution logic.",
    "Run an international private law screening: identify connecting factors, governing-law questions, and missing jurisdiction facts.",
    "Create a structured internal legal memo draft with evidence mapping and lawyer-review caveats.",
    "Run an article applicability review: explain whether the selected article may apply, may not apply, and what facts are missing.",
  ]), []);
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
  const gateCases = useMemo(() => {
    if (!gateClientId) return cases;
    return cases.filter((item) => item.client_id === gateClientId);
  }, [cases, gateClientId]);
  const bibliothequeItems = useMemo<BibliothequeItem[]>(() => {
    const docItems: BibliothequeItem[] = documents.map((document) => {
      const sortTime = new Date(document.upload_timestamp).getTime();
      return {
        id: `pdf-${document.id}`,
        sourceId: document.id,
        kind: "pdf",
        title: document.filename,
        subtitle: `Document #${document.id}`,
        status: document.processing_status,
        sizeLabel: formatFileSize(document.file_size),
        createdAt: compactDateTime(document.upload_timestamp, dateLocale, t("noDate", "No date")),
        sortTime: Number.isNaN(sortTime) ? 0 : sortTime,
      };
    });

    const voiceItems: BibliothequeItem[] = recordings.map((recording) => {
      const sortTime = new Date(recording.created_at).getTime();
      return {
        id: `voice-${recording.id}`,
        sourceId: recording.id,
        kind: "voice",
        title: recording.filename,
        subtitle: `Voice #${recording.id}`,
        status: recording.transcription_status,
        sizeLabel: formatFileSize(recording.file_size),
        createdAt: compactDateTime(recording.created_at, dateLocale, t("noDate", "No date")),
        sortTime: Number.isNaN(sortTime) ? 0 : sortTime,
      };
    });

    const imageItems: BibliothequeItem[] = imageBatches.map((batch) => {
      const sortTime = new Date(batch.created_at).getTime();
      const imageWord = batch.asset_count === 1 ? "image" : "images";
      const generated = batch.generated_document_id ? ` -> Doc #${batch.generated_document_id}` : "";
      return {
        id: `image-${batch.id}`,
        sourceId: batch.id,
        kind: "image",
        title: batch.title,
        subtitle: `Batch #${batch.id}${generated}`,
        status: batch.status,
        sizeLabel: `${batch.asset_count} ${imageWord}`,
        createdAt: compactDateTime(batch.created_at, dateLocale, t("noDate", "No date")),
        sortTime: Number.isNaN(sortTime) ? 0 : sortTime,
        generatedDocumentId: batch.generated_document_id ?? null,
      };
    });

    return [...docItems, ...voiceItems, ...imageItems].sort((left, right) => right.sortTime - left.sortTime);
  }, [documents, recordings, imageBatches, dateLocale, t]);
  const bibliothequeSourceItems = bibliothequeGlobalItems.length ? bibliothequeGlobalItems : bibliothequeItems;
  const bibliothequeVisibleItems = useMemo(() => {
    const query = bibliothequeQuery.trim().toLowerCase();
    return bibliothequeSourceItems.filter((item) => {
      if (bibliothequeFilter !== "all" && item.kind !== bibliothequeFilter) {
        return false;
      }
      if (!query) return true;
      return [item.title, item.subtitle, item.status, item.sizeLabel]
        .join(" ")
        .toLowerCase()
        .includes(query);
    });
  }, [bibliothequeFilter, bibliothequeQuery, bibliothequeSourceItems]);

  const libraryPreviewMarkdownBlocks = useMemo(
    () => (libraryPreviewMarkdownText ? parseMarkdownPreview(libraryPreviewMarkdownText) : []),
    [libraryPreviewMarkdownText]
  );

  const releaseLibraryPreviewObjectUrls = useCallback(() => {
    libraryPreviewObjectUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
    libraryPreviewObjectUrlsRef.current = [];
  }, []);

  const resetLibraryPreview = useCallback(() => {
    libraryPreviewRequestIdRef.current += 1;
    releaseLibraryPreviewObjectUrls();
    setLibraryPreviewLoading(false);
    setLibraryPreviewError(null);
    setLibraryPreviewUrl(null);
    setLibraryPreviewBatch(null);
    setLibraryPreviewAssets([]);
    setLibraryPreviewAssetId(null);
    setLibraryPreviewMarkdownText(null);
  }, [releaseLibraryPreviewObjectUrls]);

  const closeLibraryPreview = useCallback(() => {
    resetLibraryPreview();
    setLibraryPreviewItem(null);
  }, [resetLibraryPreview]);

  const trackLibraryPreviewUrl = useCallback((url: string) => {
    libraryPreviewObjectUrlsRef.current.push(url);
    return url;
  }, []);

  useEffect(
    () => () => {
      releaseLibraryPreviewObjectUrls();
    },
    [releaseLibraryPreviewObjectUrls]
  );

  useEffect(() => {
    if (!libraryPreviewItem) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [libraryPreviewItem]);

  const openLibraryPreview = useCallback(
    async (item: BibliothequeItem) => {
      if (!token) return;

      resetLibraryPreview();
      const requestId = libraryPreviewRequestIdRef.current;
      setLibraryPreviewItem(item);
      setLibraryPreviewLoading(true);

      try {
        if (item.kind === "pdf") {
          const blob = await api.getDocumentFile(token, item.sourceId);
          if (requestId !== libraryPreviewRequestIdRef.current) return;
          const looksLikeMarkdown = item.title.toLowerCase().endsWith(".md") || item.title.toLowerCase().endsWith(".markdown");
          const blobText = looksLikeMarkdown || (blob.type.startsWith("text/") && blob.type !== "text/html") ? await blob.text() : null;
          if (requestId !== libraryPreviewRequestIdRef.current) return;
          if (blobText) {
            setLibraryPreviewMarkdownText(blobText);
            return;
          }
          const objectUrl = trackLibraryPreviewUrl(URL.createObjectURL(blob));
          setLibraryPreviewUrl(`${objectUrl}#page=1&zoom=80&toolbar=0&navpanes=0&scrollbar=0`);
          return;
        }

        if (item.kind === "voice") {
          const blob = await api.getVoiceRecordingFile(token, item.sourceId);
          if (requestId !== libraryPreviewRequestIdRef.current) return;
          const objectUrl = trackLibraryPreviewUrl(URL.createObjectURL(blob));
          setLibraryPreviewUrl(objectUrl);
          return;
        }

        const batchDetail = await api.getImageBatch(token, item.sourceId);
        if (requestId !== libraryPreviewRequestIdRef.current) return;
        const sortedAssets = [...batchDetail.assets].sort((left, right) => (left.page_order ?? 0) - (right.page_order ?? 0));
        const assetPreviews = await Promise.all(
          sortedAssets.map(async (asset) => {
            const blob = await api.getImageAssetFile(token, asset.id);
            if (requestId !== libraryPreviewRequestIdRef.current) return null;
            const objectUrl = trackLibraryPreviewUrl(URL.createObjectURL(blob));
            return {
              id: asset.id,
              filename: asset.filename,
              mimeType: asset.mime_type,
              url: objectUrl,
              pageOrder: asset.page_order,
              extractedText: asset.extracted_text,
            } satisfies LibraryPreviewAsset;
          })
        );

        if (requestId !== libraryPreviewRequestIdRef.current) return;
        setLibraryPreviewBatch(batchDetail);
        const validAssetPreviews = assetPreviews.filter((asset) => asset !== null) as LibraryPreviewAsset[];
        setLibraryPreviewAssets(validAssetPreviews);
        setLibraryPreviewAssetId(validAssetPreviews[0]?.id ?? null);
      } catch (caught) {
        if (requestId !== libraryPreviewRequestIdRef.current) return;
        setLibraryPreviewError(normalizeError(caught, t("unableOpenPreview", "Unable to open preview.")));
      } finally {
        if (requestId !== libraryPreviewRequestIdRef.current) return;
        setLibraryPreviewLoading(false);
      }
    },
    [resetLibraryPreview, t, token, trackLibraryPreviewUrl]
  );

  const openLibraryGeneratedDocument = useCallback(
    async (documentId: number) => {
      if (!token) return;

      resetLibraryPreview();
      const requestId = libraryPreviewRequestIdRef.current;
      setLibraryPreviewItem({
        id: `pdf-generated-${documentId}`,
        sourceId: documentId,
        kind: "pdf",
        title: `Generated document #${documentId}`,
        subtitle: "Generated from scanned images",
        status: "ready",
        sizeLabel: "Generated PDF",
        createdAt: t("noDate", "No date"),
        sortTime: Date.now(),
      });
      setLibraryPreviewLoading(true);

      try {
        const blob = await api.getDocumentFile(token, documentId);
        if (requestId !== libraryPreviewRequestIdRef.current) return;
        const blobText = blob.type.startsWith("text/") && blob.type !== "text/html" ? await blob.text() : null;
        if (requestId !== libraryPreviewRequestIdRef.current) return;
        if (blobText) {
          setLibraryPreviewMarkdownText(blobText);
          return;
        }
        const objectUrl = trackLibraryPreviewUrl(URL.createObjectURL(blob));
        setLibraryPreviewUrl(objectUrl);
      } catch (caught) {
        if (requestId !== libraryPreviewRequestIdRef.current) return;
        setLibraryPreviewError(normalizeError(caught, t("unableOpenPreview", "Unable to open preview.")));
      } finally {
        if (requestId !== libraryPreviewRequestIdRef.current) return;
        setLibraryPreviewLoading(false);
      }
    },
    [resetLibraryPreview, t, token, trackLibraryPreviewUrl]
  );

  useEffect(() => {
    if (!libraryPreviewItem) return undefined;

    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        closeLibraryPreview();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeLibraryPreview, libraryPreviewItem]);

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
    const compacted = persistChatStateToLocalStorage(CHAT_STORAGE_KEY, chatState);
    if (compacted) {
      setChatState(compacted);
    }
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
        const [docs, voiceRows, callRows, calendarRows, consultationRows, imageBatchRows, reviewRows, reviewTableRows] = await Promise.all([
          api.listCaseDocuments(token, caseId),
          api.listVoiceRecordings(token, caseId),
          api.listCallSessions(token, caseId),
          api.listCalendarAppointments(token, caseId),
          api.listConsultationRequests(token, caseId),
          api.listCaseImageBatches(token, caseId),
          api.listEvidenceReviews(token, caseId),
          api.getCaseReviewTable(token, caseId),
        ]);
        setDocuments(docs);
        setRecordings(voiceRows);
        setCallSessions(callRows);
        setCalendarAppointments(calendarRows);
        setConsultations(consultationRows);
        setImageBatches(imageBatchRows);
        setEvidenceReviews(reviewRows.reviews || []);
        setCaseReviewTable(reviewTableRows);
        setSelectedDocumentId((current) => {
          if (current && docs.some((document) => document.id === current)) return current;
          return docs[0]?.id ?? null;
        });
        setLawyerPhoneDraft((current) => current || user?.phone || DEFAULT_LAWYER_PHONE);
        setActiveCallSessionId((current) => {
          if (current && callRows.some((session) => session.id === current)) return current;
          return callRows[0]?.id ?? null;
        });
      } catch (caught) {
        setError(normalizeError(caught, t("unableLoadCaseContext", "Unable to load case context.")));
      } finally {
        setCaseContextLoading(false);
      }
    },
    [token, t, selectedClient?.phone]
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
    if (!token) {
      setSelectionGateOpen(false);
      setSelectionGateDone(false);
      return;
    }

    if (
      user?.role === "lawyer"
      && !selectionGateDone
      && clients.length > 0
      && cases.length > 0
    ) {
      setSelectionGateOpen(true);
      return;
    }

    setSelectionGateOpen(false);
  }, [token, user?.role, selectionGateDone, clients.length, cases.length]);

  useEffect(() => {
    if (!selectionGateOpen) return;
    setGateClientId((current) => {
      if (current && clients.some((client) => client.id === current)) return current;
      if (selectedClientId && clients.some((client) => client.id === selectedClientId)) return selectedClientId;
      return clients[0]?.id ?? null;
    });
  }, [selectionGateOpen, clients, selectedClientId]);

  useEffect(() => {
    if (!selectionGateOpen) return;
    setGateCaseId((current) => {
      if (current && gateCases.some((item) => item.id === current)) return current;
      if (selectedCaseId && gateCases.some((item) => item.id === selectedCaseId)) return selectedCaseId;
      return gateCases[0]?.id ?? null;
    });
  }, [selectionGateOpen, gateCases, selectedCaseId]);

  useEffect(() => {
    if (!token || sidebarTab !== "bibliotheque" || !cases.length) {
      setBibliothequeLoading(false);
      return;
    }

    let active = true;
    setBibliothequeLoading(true);

    const loadBibliotheque = async () => {
      const grouped = await Promise.all(
        cases.map(async (caseItem) => {
          const [caseDocuments, caseRecordings, caseBatches] = await Promise.all([
            api.listCaseDocuments(token, caseItem.id).catch(() => [] as DocumentItem[]),
            api.listVoiceRecordings(token, caseItem.id).catch(() => [] as VoiceRecording[]),
            api.listCaseImageBatches(token, caseItem.id).catch(() => [] as ImageDocumentBatch[]),
          ]);

          const docItems: BibliothequeItem[] = caseDocuments.map((document) => {
            const sortTime = new Date(document.upload_timestamp).getTime();
            return {
              id: `pdf-${caseItem.id}-${document.id}`,
              sourceId: document.id,
              kind: "pdf",
              title: document.filename,
              subtitle: `${caseItem.title} · Document #${document.id}`,
              status: document.processing_status,
              sizeLabel: formatFileSize(document.file_size),
              createdAt: compactDateTime(document.upload_timestamp, dateLocale, t("noDate", "No date")),
              sortTime: Number.isNaN(sortTime) ? 0 : sortTime,
            };
          });

          const voiceItems: BibliothequeItem[] = caseRecordings.map((recording) => {
            const sortTime = new Date(recording.created_at).getTime();
            const isCallRecording = recording.recording_kind === "call_recording";
            return {
              id: `voice-${caseItem.id}-${recording.id}`,
              sourceId: recording.id,
              kind: "voice",
              title: isCallRecording ? `Call recording #${recording.id}` : recording.filename,
              subtitle: `${caseItem.title} · ${isCallRecording ? "Call" : "Voice"} #${recording.id}`,
              status: recording.transcription_status,
              sizeLabel: formatFileSize(recording.file_size),
              createdAt: compactDateTime(recording.created_at, dateLocale, t("noDate", "No date")),
              sortTime: Number.isNaN(sortTime) ? 0 : sortTime,
            };
          });

          const imageItems: BibliothequeItem[] = caseBatches.map((batch) => {
            const sortTime = new Date(batch.created_at).getTime();
            const imageWord = batch.asset_count === 1 ? "image" : "images";
            return {
              id: `image-${caseItem.id}-${batch.id}`,
              sourceId: batch.id,
              kind: "image",
              title: batch.title,
              subtitle: `${caseItem.title} · Batch #${batch.id}`,
              status: batch.status,
              sizeLabel: `${batch.asset_count} ${imageWord}`,
              createdAt: compactDateTime(batch.created_at, dateLocale, t("noDate", "No date")),
              sortTime: Number.isNaN(sortTime) ? 0 : sortTime,
              generatedDocumentId: batch.generated_document_id ?? null,
            };
          });

          return [...docItems, ...voiceItems, ...imageItems];
        })
      );

      if (!active) return;
      setBibliothequeGlobalItems(grouped.flat().sort((left, right) => right.sortTime - left.sortTime));
    };

    void loadBibliotheque()
      .catch(() => {
        if (active) setBibliothequeGlobalItems([]);
      })
      .finally(() => {
        if (active) setBibliothequeLoading(false);
      });

    return () => {
      active = false;
    };
  }, [token, sidebarTab, cases, dateLocale, t]);

  useEffect(() => {
    if (!selectedCaseId) {
      setDocuments([]);
      setRecordings([]);
      setCallSessions([]);
      setCalendarAppointments([]);
      setConsultations([]);
      setImageBatches([]);
      setEvidenceReviews([]);
      setCaseReviewTable(null);
      return;
    }
    void loadCaseContext(selectedCaseId);
  }, [selectedCaseId, loadCaseContext]);

  useEffect(() => {
    setActiveCallSessionId(null);
    setCallNotesDraft("");
  }, [selectedCaseId, selectedClient?.phone]);

  useEffect(() => {
    if (!token || !selectedCaseId || !hasPendingImageBatch) {
      return undefined;
    }

    let isCancelled = false;
    let timeoutId: number | undefined;
    let pollCycles = 0;
    let stalledCycles = 0;
    let previousPendingSignature = "";

    const buildPendingSignature = (batches: ImageDocumentBatch[]) => {
      return batches
        .filter((batch) => batch.status === "queued" || batch.status === "processing")
        .map((batch) => `${batch.id}:${batch.status}:${batch.updated_at}`)
        .sort()
        .join("|");
    };

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

      if (stalledCycles >= IMAGE_BATCH_POLL_STALL_MAX_CYCLES) {
        setNotice(
          t(
            "imageBatchPollingStalled",
            "Automatic refresh paused because image processing appears stalled."
          )
        );
        return;
      }

      pollCycles += 1;

      try {
        const latestBatches = await api.listCaseImageBatches(token, selectedCaseId);
        if (isCancelled) {
          return;
        }

        setImageBatches(latestBatches);

        const currentPendingSignature = buildPendingSignature(latestBatches);
        const hasPendingNow = currentPendingSignature.length > 0;
        const pendingChanged = currentPendingSignature !== previousPendingSignature;
        previousPendingSignature = currentPendingSignature;
        stalledCycles = pendingChanged ? 0 : stalledCycles + 1;

        if (!hasPendingNow || pendingChanged) {
          await loadCaseContext(selectedCaseId);
        }

        if (!hasPendingNow) {
          return;
        }
      } catch {
        stalledCycles += 1;
      }

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

  const refreshWorkspaceAfterCrud = useCallback(async () => {
    if (!token) return;
    const caseIdToRefresh = selectedCaseId;
    await bootstrapWorkspace(token);
    if (caseIdToRefresh) {
      try {
        await loadCaseContext(caseIdToRefresh);
      } catch {
        // The selected case may have been deleted or moved by the CRUD action.
      }
    }
  }, [bootstrapWorkspace, loadCaseContext, selectedCaseId, token]);

  const loadAuditLogs = useCallback(async () => {
    if (!token) return;
    setAuditLoading(true);
    try {
      const response = await api.listAiAuditLogs(token, {
        caseId: selectedCaseId,
        documentId: selectedDocumentId,
        limit: 20,
      });
      setAuditLogs(response.rows || []);
      setAuditPanelOpen(true);
    } catch (caught) {
      setError(normalizeError(caught, "Unable to load AI audit logs."));
    } finally {
      setAuditLoading(false);
    }
  }, [selectedCaseId, selectedDocumentId, token]);

  const sendMessage = useCallback(
    async (promptText: string) => {
      if (!token) return;
      const trimmed = promptText.trim();
      if (!trimmed) return;

      const outboundPrompt = trimmed;
      const chatScopeId = selectedCaseId ?? CHAT_GLOBAL_SCOPE_ID;
      const sessionId = activeChatSessionId || createChatSession(chatScopeId, outboundPrompt);
      const userMessage = createMessage("user", outboundPrompt);
      const caseMessages = activeSession?.messages || [];
      appendMessage(chatScopeId, sessionId, userMessage);
      setChatInput("");
      setAttachmentMenuOpen(false);
      setCopilotLoading(true);
      setError(null);

      const abortController = new AbortController();
      copilotAbortControllerRef.current = abortController;

      try {
        const response = await api.copilot(token, outboundPrompt, {
          topK: REASONING_TOP_K[reasoningLevel],
          reasoningLevel,
          useExternalResearch: externalModeEnabled || workspaceMode === "legal_search",
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
          signal: abortController.signal,
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
          trustPanel: response.trust_panel,
          sources: response.sources,
          citations: response.citations,
          executionTrace: response.execution_trace,
          cache: response.cache,
          jobId: response.job_id,
          caseSnapshotVersion: response.case_snapshot_version,
          artifact: response.artifact,
          jurisdiction: response.jurisdiction,
          reasoningResult: response.reasoning_result,
          rawAnswer: response.answer,
        });

        if (response.action_category === "crud" && response.action_status === "completed") {
          void refreshWorkspaceAfterCrud();
        }

        animateAssistantMessage(chatScopeId, sessionId, assistantMessage);
      } catch (caught) {
        const message = normalizeError(caught, t("copilotFailed", "Copilot request failed."));
        if (message !== "Request stopped.") {
          setError(message);
        } else {
          setNotice("Request stopped.");
        }
      } finally {
        if (copilotAbortControllerRef.current === abortController) {
          copilotAbortControllerRef.current = null;
        }
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
      refreshWorkspaceAfterCrud,
      t,
    ]
  );
  const handleFeedback = useCallback(
    async (message: ChatMessage, value: FeedbackValue, rootCause?: FeedbackRootCause | null) => {
      if (!token || !selectedCaseId) return;
      if (value === "down" && !rootCause) {
        setNotice("Select a downvote reason before submitting feedback.");
        return;
      }
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
        [message.id]: { value, status: "saving", rootCause: value === "down" ? (rootCause || null) : null },
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
          root_cause: value === "down" ? (rootCause || null) : null,
          legal_domain: true,
          jurisdiction: selectedCase?.jurisdiction_country || null,
          source_count: message.meta?.sources?.length || 0,
          metadata: {
            mode: workspaceMode,
            action_category: message.meta?.actionCategory || null,
            action_status: message.meta?.actionStatus || null,
            root_cause: value === "down" ? (rootCause || null) : null,
            legal_domain: true,
            jurisdiction: selectedCase?.jurisdiction_country || null,
          },
        });
        setChatFeedback((current) => ({
          ...current,
          [message.id]: { value, status: "submitted", rootCause: value === "down" ? (rootCause || null) : null },
        }));
      } catch {
        setChatFeedback((current) => ({
          ...current,
          [message.id]: { value, status: "error", rootCause: value === "down" ? (rootCause || null) : null },
        }));
      }
    },
    [activeMessages, selectedCase?.jurisdiction_country, selectedCaseId, selectedDocumentId, token, workspaceMode]
  );

  const handleAskMissingInfo = useCallback(
    (_message: ChatMessage, missingInfo: string) => {
      const prompt = [
        "Missing information follow-up:",
        missingInfo,
        "",
        "Explain why this missing fact matters, what document or fact the lawyer should request, and how it could change the analysis.",
      ].join("\n");
      void sendMessage(prompt);
    },
    [sendMessage]
  );

  const handleTrustReview = useCallback(
    async (message: ChatMessage, decision: "approved" | "needs_revision") => {
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
        [message.id]: {
          value: decision === "approved" ? "up" : "down",
          status: "saving",
          rootCause: decision === "needs_revision" ? "other" : null,
        },
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
          feedback_value: decision === "approved" ? "up" : "down",
          root_cause: decision === "needs_revision" ? "other" : null,
          legal_domain: true,
          jurisdiction: selectedCase?.jurisdiction_country || null,
          source_count: message.meta?.sources?.length || 0,
          metadata: {
            review_decision: decision,
            review_surface: "trust_panel",
            trust_panel: message.meta?.trustPanel || null,
            mode: workspaceMode,
          },
        });
        setChatFeedback((current) => ({
          ...current,
          [message.id]: {
            value: decision === "approved" ? "up" : "down",
            status: "submitted",
            rootCause: decision === "needs_revision" ? "other" : null,
          },
        }));
        setNotice(decision === "approved" ? "AI output marked reviewed." : "AI output marked for correction.");
      } catch {
        setChatFeedback((current) => ({
          ...current,
          [message.id]: {
            value: decision === "approved" ? "up" : "down",
            status: "error",
            rootCause: decision === "needs_revision" ? "other" : null,
          },
        }));
      }
    },
    [activeMessages, selectedCase?.jurisdiction_country, selectedCaseId, selectedDocumentId, token, workspaceMode]
  );

  const stopCopilotRequest = useCallback(() => {
    copilotAbortControllerRef.current?.abort();
  }, []);

  const handleCopy = useCallback((message: ChatMessage) => {
    void navigator.clipboard.writeText(message.content);
    setNotice(t("copiedClipboard", "Copied to clipboard."));
  }, [t]);

  const handleRegenerate = useCallback(
    (message: ChatMessage) => {
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
    [activeMessages, sendMessage]
  );

  const clearActiveCaseHistory = useCallback(() => {
    if (!activeChatSessionId) return;
    const chatScopeId = activeChatScopeId;
    setChatState((current) => {
      const nextSessions = (current.sessionsByCase[chatScopeId] || []).filter((session) => session.id !== activeChatSessionId);
      const nextActiveId = nextSessions[0]?.id;
      const nextActiveSessionIdByCase = { ...current.activeSessionIdByCase };
      if (nextActiveId) {
        nextActiveSessionIdByCase[chatScopeId] = nextActiveId;
      } else {
        delete nextActiveSessionIdByCase[chatScopeId];
      }
      return {
        sessionsByCase: {
          ...current.sessionsByCase,
          [chatScopeId]: nextSessions,
        },
        activeSessionIdByCase: nextActiveSessionIdByCase,
      };
    });
    setChatFeedback({});
    setNotice(`${t("chatHistory", "Chat History")}: ${t("clearHistory", "Clear history")}`);
  }, [activeChatScopeId, activeChatSessionId, t]);

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
    setCalendarAppointments([]);
    setConsultations([]);
    setImageBatches([]);
    setEvidenceReviews([]);
    setPromptLibraryEntries([]);
    setCaseReviewTable(null);
    setSelectedCaseId(null);
    setSelectedClientId(null);
    setSelectedDocumentId(null);
    setLawyerPhoneDraft(DEFAULT_LAWYER_PHONE);
    setChatInput("");
    setExternalModeEnabled(false);
    setWorkspaceMode("chat");
    setLeftRailOpen(true);
    setSidebarTab("navigator");
    setBibliothequeFilter("all");
    setBibliothequeQuery("");
    setBibliothequeGlobalItems([]);
    setBibliothequeLoading(false);
    setSelectionGateOpen(false);
    setSelectionGateDone(false);
    setGateClientId(null);
    setGateCaseId(null);
  }

  function buildPromptTemplateTitle(prompt: string) {
    const clean = prompt.replace(/\s+/g, " ").trim();
    if (!clean) return "Saved prompt";
    return truncateText(clean, 48);
  }

  function normalizePhoneForWhatsApp(phone: string) {
    return phone.replace(/[^\d]/g, "");
  }

  function openWhatsAppForPhone(phone: string, note?: string) {
    const normalized = normalizePhoneForWhatsApp(phone);
    if (!normalized) {
      setError("No phone number is available for WhatsApp.");
      return;
    }

    const text = note ? `&text=${encodeURIComponent(note)}` : "";
    const deepLink = `whatsapp://send?phone=${normalized}${text}`;
    const link = document.createElement("a");
    link.href = deepLink;
    link.rel = "noopener noreferrer";
    link.style.display = "none";
    document.body.appendChild(link);
    link.click();
    window.setTimeout(() => {
      link.remove();
    }, 0);
  }

  function openPhoneDialer(phone: string) {
    const normalized = phone.trim();
    if (!normalized) {
      setError("No phone number is available to call.");
      return;
    }

    window.open(`tel:${normalized}`, "_self");
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

  async function saveLawyerPhone() {
    if (!token) return;
    const phone = lawyerPhoneDraft.trim();
    if (!phone) {
      setError("Lawyer phone number is required.");
      return;
    }

    setSavingLawyerPhone(true);
    setError(null);
    try {
      const updatedUser = await api.updateMyPhone(token, phone);
      setUser(updatedUser);
      setNotice("Lawyer outbound number saved.");
    } catch (caught) {
      setError(normalizeError(caught, "Unable to save the lawyer phone number."));
    } finally {
      setSavingLawyerPhone(false);
    }
  }

  async function uploadAudioFile(file: File) {
    if (!token || !selectedCaseId) return;
    setUploadingAudio(true);
    setError(null);
    try {
      const callSessionId = activeCallSessionId ?? undefined;
      const response = await api.uploadVoiceRecording(token, selectedCaseId, file, {
        recordingKind: callSessionId ? "call_recording" : "voice_note",
        callSessionId,
      });
      await loadCaseContext(selectedCaseId);
      if (callSessionId) {
        setNotice(
          response.job?.id
            ? `Call recording uploaded. Transcription is running. Job: ${response.job.id}`
            : "Call recording uploaded. Transcription is running."
        );
        clearCallRecordingFollowUp();
        void pollCallRecordingUntilReady(response.recording.id);
      } else {
        setNotice(
          response.job?.id
            ? `Voice file uploaded. Transcription is running. Job: ${response.job.id}`
            : "Voice file uploaded. Transcription is running."
        );
      }
    } catch (caught) {
      setError(normalizeError(caught, t("uploadAudioFailed", "Unable to upload audio.")));
    } finally {
      setUploadingAudio(false);
    }
  }

  async function summarizeCallRecording(recordingId: number) {
    if (!token || !selectedCaseId) return;

    setSummarizingCallRecordingId(recordingId);
    setError(null);

    try {
      const response = await api.createConsultationFromRecording(token, recordingId);
      await loadCaseContext(selectedCaseId);
      setNotice(response.message || "Call recording summarized and added to the case.");
    } catch (caught) {
      setError(normalizeError(caught, "Unable to summarize the call recording."));
    } finally {
      setSummarizingCallRecordingId(null);
    }
  }

  const clearCallRecordingFollowUp = useCallback(() => {
    if (callRecordingFollowUpTimeoutRef.current !== null) {
      window.clearTimeout(callRecordingFollowUpTimeoutRef.current);
      callRecordingFollowUpTimeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearCallRecordingFollowUp();
    };
  }, [clearCallRecordingFollowUp]);

  const pollCallRecordingUntilReady = useCallback(
    async (recordingId: number, attempt = 0) => {
      if (!token || !selectedCaseId) return;

      try {
        const current = await api.getVoiceRecording(token, recordingId);
        if (current.transcription_status === "completed" && current.transcript_text?.trim()) {
          await summarizeCallRecording(recordingId);
          return;
        }

        if (current.transcription_status === "failed") {
          setError(current.transcription_error || "The call recording transcription failed.");
          return;
        }
      } catch {
        // Keep polling until the recording is ready or we hit the retry cap.
      }

      if (attempt >= 20) {
        setNotice("Call recording uploaded. You can summarize it later from the case library.");
        return;
      }

      clearCallRecordingFollowUp();
      callRecordingFollowUpTimeoutRef.current = window.setTimeout(() => {
        void pollCallRecordingUntilReady(recordingId, attempt + 1);
      }, 3000);
    },
    [clearCallRecordingFollowUp, selectedCaseId, summarizeCallRecording, token]
  );

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

  async function createCallSession() {
    if (!token || !selectedCaseId) return;
    const phone = selectedClient?.phone || "";
    if (!phone) {
      setError("The client must have a phone number before creating a call session.");
      return;
    }

    const callerPhone = lawyerPhoneDraft.trim() || user?.phone || DEFAULT_LAWYER_PHONE;
    if (!callerPhone) {
      setError("The lawyer phone number is required before creating a call session.");
      return;
    }

    setCreatingCallSession(true);
    setError(null);

    try {
      const response = await api.createCallSession(token, selectedCaseId, {
        providerName: "whatsapp",
        callerPhone,
        clientPhone: phone,
        notes: callNotesDraft.trim() || null,
      });
      await loadCaseContext(selectedCaseId);
      setActiveCallSessionId(response.call_session.id);
      if (response.consent_delivery_mode === "manual" && response.whatsapp_chat_url) {
        window.open(response.whatsapp_chat_url, "_blank", "noopener,noreferrer");
      }
      setNotice(response.message);
    } catch (caught) {
      setError(normalizeError(caught, "Unable to create the call session."));
    } finally {
      setCreatingCallSession(false);
    }
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
        title: selectedCase ? `${selectedCase.title} - scanned documents` : "Scanned documents",
        generateDocument: true,
        runAuthenticityCheck: runScannedAuthenticityCheck,
      });
      await loadCaseContext(selectedCaseId);
      setNotice(
        response.job?.id
          ? `Scanned documents uploaded and queued for OCR${runScannedAuthenticityCheck ? " with authenticity screening" : ""}. Job: ${response.job.id}`
          : `Scanned documents uploaded and queued for OCR${runScannedAuthenticityCheck ? " with authenticity screening" : ""}.`
      );
    } catch (caught) {
      setError(normalizeError(caught, "Unable to upload scanned documents."));
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

      const optimizedPrompt = String(response.optimized_prompt || trimmed).trim() || trimmed;
      const unchanged = Boolean(response.unchanged) || optimizedPrompt === trimmed;

      if (unchanged) {
        const strongerHint = response.notes?.trim()
          || "Prompt already strong. Add specific output format, constraints, or priority focus for a stronger rewrite.";
        setNotice(strongerHint);
        focusComposer();
        return;
      }

      setChatInput(optimizedPrompt);
      const strategyLabel = response.used_llm
        ? "LLM"
        : String(response.strategy || "heuristic").toUpperCase();
      const note = response.notes?.trim() || "Prompt optimized for clearer legal reasoning.";
      const improvements = (response.applied_improvements || []).slice(0, 2);
      const improvementText = improvements.length ? ` ${improvements.join(" ")}` : "";
      setNotice(`[${strategyLabel}] ${note}${improvementText}`);
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
  const suggestedActions = useMemo(
    () => [
      selectedCase ? `Summarize case #${selectedCase.id}` : "Summarize this matter",
      "List the main legal risks",
      "Draft a client update email",
      "Show missing evidence and next steps",
    ],
    [selectedCase]
  );
  const buildWorkflowSeedPrompt = useCallback(
    (action: string) => {
      const lowered = action.toLowerCase();
      if (lowered.includes("summarize")) {
        const caseLabel = selectedCase
          ? `case #${selectedCase.id} (${selectedCase.title})`
          : "the active case";
        return [
          `Summarize ${caseLabel} for a lawyer briefing note.`,
          "",
          "Format:",
          "- One short executive summary paragraph.",
          "- Main points (3-5 bullets).",
          "- Important dates/deadlines (if available).",
          "- Immediate next steps (2-4 bullets).",
          "",
          "Rules:",
          "- Use only known case facts from available evidence.",
          "- If data is missing, explicitly say what is still pending.",
          "- Keep it concise and practical.",
        ].join("\n");
      }
      if (lowered.includes("draft") && lowered.includes("email")) {
        const caseLabel = selectedCase
          ? `case #${selectedCase.id} (${selectedCase.title})`
          : "the active case";
        return [
          `Draft a client update email for ${caseLabel}.`,
          "",
          "Requirements:",
          "- Keep it client-friendly, professional, and reassuring.",
          "- Include: current status, key points, and immediate next steps.",
          "- Use only known case facts; if a fact is missing, state that clearly.",
          "- End with one clear call to action for the client.",
        ].join("\n");
      }
      return action;
    },
    [selectedCase]
  );
  const showMinimalSearchOnly = !workspaceLoading
    && !caseContextLoading
    && !copilotLoading
    && activeMessages.length === 0;

  const confirmLawyerInitialSelection = useCallback(() => {
    if (gateClientId && clients.some((client) => client.id === gateClientId)) {
      setSelectedClientId(gateClientId);
    }
    if (gateCaseId && cases.some((item) => item.id === gateCaseId)) {
      setSelectedCaseId(gateCaseId);
    }
    setSelectionGateDone(true);
    setSelectionGateOpen(false);
  }, [gateClientId, gateCaseId, clients, cases]);

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
    <div className={`workspace-shell ${leftRailOpen ? "" : "sidebar-collapsed"}`}>
      {leftRailOpen ? (
        <aside className="left-rail glass">
          <header className="left-brand">
            <div className="brand-mark">LA</div>
            <div>
              <strong>Legal AI</strong>
              <small>{t("premiumWorkspace", "Evidence-first legal workspace")}</small>
            </div>
            <button
              aria-label="Collapse sidebar"
              className="rail-toggle"
              onClick={() => setLeftRailOpen(false)}
              type="button"
            >
              &lt;
            </button>
          </header>

          <div className="sidebar-tab-row">
            <button
              className={`sidebar-tab ${sidebarTab === "navigator" ? "active" : ""}`}
              onClick={() => setSidebarTab("navigator")}
              type="button"
            >
              {t("matterNavigator", "Navigator")}
            </button>
            <button
              className={`sidebar-tab ${sidebarTab === "bibliotheque" ? "active" : ""}`}
              onClick={() => setSidebarTab("bibliotheque")}
              type="button"
            >
              {t("bibliotheque", "Bibliotheque")}
            </button>
            <button
              className={`sidebar-tab ${sidebarTab === "calendar" ? "active" : ""}`}
              onClick={() => setSidebarTab("calendar")}
              type="button"
            >
              Calendar
            </button>
          </div>

          {sidebarTab === "navigator" ? (
            <>
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

                <label>
                  {t("caseLabel", "Case")}
                  <select
                    disabled={!filteredCases.length}
                    value={selectedCaseId ?? ""}
                    onChange={(event) => setSelectedCaseId(event.target.value ? Number(event.target.value) : null)}
                  >
                    {filteredCases.length ? (
                      filteredCases.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.title} · #{item.id} · {item.jurisdiction_country}
                        </option>
                      ))
                    ) : (
                      <option value="">{t("noCasesForClient", "No cases found for selected client.")}</option>
                    )}
                  </select>
                </label>

                {selectedCase ? (
                  <p className="muted">
                    {selectedCase.jurisdiction_country} · {selectedCase.status}
                  </p>
                ) : null}
              </section>

              <section className="left-section">
                <div className="history-heading-row">
                  <h3>{t("chatHistory", "Chat History")}</h3>
                  <div className="history-actions">
                    <button
                      className="ghost-button history-action"
                      disabled={false}
                      onClick={() => {
                        createChatSession(activeChatScopeId);
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
                        onClick={() => selectChatSession(activeChatScopeId, item.id)}
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

              <section className="left-section left-extra-sections">
                <h3>{t("moreWorkspaceTools", "Workspace tools")}</h3>
                <div className="left-extra-body">
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
                        {uploadingAudio
                          ? t("uploadingAudio", "Uploading audio...")
                          : activeCallSession
                            ? "Upload call recording"
                            : t("uploadAudioFile", "Upload audio file")}
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
                        {recordingVoice
                          ? activeCallSession
                            ? "Stop and save call recording"
                            : t("stopRecording", "Stop recording")
                          : activeCallSession
                            ? "Start call recording"
                            : t("recordVoice", "Record voice")}
                      </button>
                      <button
                        className="secondary-button"
                        disabled={!selectedCaseId || uploadingScannedPhotos || visionUiDisabled}
                        onClick={() => scannedPhotoInputRef.current?.click()}
                        type="button"
                      >
                        {uploadingScannedPhotos
                          ? "Uploading documents..."
                          : visionUiDisabled
                            ? "Scanned documents unavailable"
                            : "Upload scanned documents"}
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
                      <p className="muted">{visionUnavailableReason || "Scanned-document OCR is unavailable right now."}</p>
                    ) : (
                      <p className="muted">
                        {runScannedAuthenticityCheck
                          ? "The upload will run OCR and an authenticity review before the lawyer checks the papers."
                          : "The upload will run OCR only and skip authenticity screening."}
                      </p>
                    )}
                  </section>

                  <section className="left-section call-section">
                    <h3>Client call</h3>
                    <div className="call-form">
                      <label>
                        Lawyer outbound number
                        <input
                          onChange={(event) => setLawyerPhoneDraft(event.target.value)}
                          placeholder={DEFAULT_LAWYER_PHONE}
                          value={lawyerPhoneDraft}
                        />
                      </label>
                      <button
                        className="ghost-button history-action"
                        disabled={savingLawyerPhone}
                        onClick={() => void saveLawyerPhone()}
                        type="button"
                      >
                        {savingLawyerPhone ? "Saving..." : "Save lawyer number"}
                      </button>
                      <div className="call-phone-summary">
                        <span>Client phone</span>
                        <strong>{selectedClient?.phone || "No phone saved for this client"}</strong>
                      </div>
                      <label>
                        Call notes
                        <textarea
                          onChange={(event) => setCallNotesDraft(event.target.value)}
                          placeholder="Call goal, client context, and follow-up items"
                          value={callNotesDraft}
                        />
                      </label>
                      <button
                        className="primary-button call-create-button"
                        disabled={!selectedCaseId || creatingCallSession || !selectedClient?.phone || !(lawyerPhoneDraft.trim() || user?.phone)}
                        onClick={() => void createCallSession()}
                        type="button"
                      >
                        {creatingCallSession ? "Calling..." : "Call"}
                      </button>
                      <p className="muted call-flow-note">
                        After consent, start call recording from this page. The audio is saved to the case library as a call recording and can be summarized automatically when transcription finishes.
                      </p>
                    </div>

                    <div className="call-session-list">
                      {callSessions.length ? (
                        callSessions.slice(0, 4).map((session) => {
                          const isActive = session.id === activeCallSessionId;
                          const voiceRecording = session.voice_recording;
                          return (
                            <article key={session.id} className={`call-session-card ${isActive ? "active" : ""}`}>
                              <div className="call-session-card-head">
                                <strong>Call #{session.id}</strong>
                                <span>{session.call_status}</span>
                              </div>
                              <small>{session.client_phone || selectedClient?.phone || "No phone captured yet"}</small>
                              <small>{session.caller_phone || lawyerPhoneDraft || user?.phone || DEFAULT_LAWYER_PHONE}</small>
                              <small>{session.provider_name || "whatsapp"}</small>
                              <small>
                                Consent: {session.consent_request_status || (session.consent_accepted ? "accepted" : "pending")}
                              </small>
                              {session.summary_text ? <p>{truncateText(session.summary_text, 120)}</p> : <p className="muted">Summary will appear after transcription.</p>}
                              <div className="call-session-actions">
                                <button
                                  className="ghost-button history-action"
                                  onClick={() => setActiveCallSessionId(session.id)}
                                  type="button"
                                >
                                  {isActive ? "Selected" : "Select"}
                                </button>
                                <button
                                  className="ghost-button history-action"
                                  onClick={() => openWhatsAppForPhone(
                                    session.client_phone || selectedClient?.phone || "",
                                    `Hello, this is Legal AI regarding case #${selectedCase?.id || session.case_id}.`
                                  )}
                                  type="button"
                                >
                                  WhatsApp
                                </button>
                                <button
                                  className="ghost-button history-action"
                                  onClick={() => openPhoneDialer(session.client_phone || selectedClient?.phone || "")}
                                  type="button"
                                >
                                  Call number
                                </button>
                                {voiceRecording ? (
                                  <>
                                    <button
                                      className="ghost-button history-action"
                                      onClick={() => void openLibraryPreview({
                                        id: `voice-${voiceRecording.id}`,
                                        sourceId: voiceRecording.id,
                                        kind: "voice",
                                        title: voiceRecording.recording_kind === "call_recording"
                                          ? `Call recording #${voiceRecording.id}`
                                          : voiceRecording.filename,
                                        subtitle: `Call #${session.id}`,
                                        status: voiceRecording.transcription_status,
                                        sizeLabel: formatFileSize(voiceRecording.file_size),
                                        createdAt: compactDateTime(voiceRecording.created_at, dateLocale, t("noDate", "No date")),
                                        sortTime: new Date(voiceRecording.created_at).getTime(),
                                      })}
                                      type="button"
                                    >
                                      Open recording
                                    </button>
                                    <button
                                      className="ghost-button history-action"
                                      disabled={
                                        summarizingCallRecordingId === voiceRecording.id
                                        || voiceRecording.transcription_status !== "completed"
                                      }
                                      onClick={() => void summarizeCallRecording(voiceRecording.id)}
                                      type="button"
                                    >
                                      {summarizingCallRecordingId === voiceRecording.id ? "Summarizing..." : "Summarize call"}
                                    </button>
                                  </>
                                ) : null}
                              </div>
                            </article>
                          );
                        })
                      ) : (
                        <p className="muted">No call sessions yet.</p>
                      )}
                    </div>

                    {activeCallSession ? (
                      <article className="call-session-detail">
                        <div className="call-session-detail-head">
                          <strong>Active call session</strong>
                          <span>{activeCallSession.consent_request_status || activeCallSession.recording_status}</span>
                        </div>
                        {activeCallSession.consent_message ? <p>{activeCallSession.consent_message}</p> : null}
                        <p>{activeCallSession.summary_text ? activeCallSession.summary_text : "The summary will appear here after transcription."}</p>
                        <pre className="call-transcript">
                          {activeCallSession.conversation_transcript_text || activeCallSession.transcript_text ? (activeCallSession.conversation_transcript_text || activeCallSession.transcript_text) : "The transcript will appear here after transcription."}
                        </pre>
                      </article>
                    ) : null}
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
                </div>
              </section>

              <button className="ghost-button logout" onClick={logout} type="button">
                {t("logout", "Logout")}
              </button>
            </>
          ) : sidebarTab === "calendar" ? (
            <CaseCalendarPanel
              caseItem={selectedCase}
              client={selectedClient}
              user={user}
              appointments={calendarAppointments}
              consultations={consultations}
              loading={caseContextLoading}
              locale={dateLocale}
              onCreateAppointment={async (payload) => {
                if (!token || !selectedCaseId) {
                  throw new Error("Select a case before creating a calendar appointment.");
                }

                await api.createCalendarAppointment(token, selectedCaseId, payload);
                await loadCaseContext(selectedCaseId);
                setNotice("Calendar appointment created and AI notes updated.");
              }}
            />
          ) : (
            <>
              <section className="left-section bibliotheque-section">
                <div className="section-heading">
                  <div>
                    <p className="section-kicker">Library</p>
                    <h3>{t("bibliotheque", "Bibliotheque")}</h3>
                  </div>
                  <span className="section-count">{bibliothequeVisibleItems.length}</span>
                </div>

                <input
                  aria-label="Search library files"
                  className="bibliotheque-search"
                  onChange={(event) => setBibliothequeQuery(event.target.value)}
                  placeholder={t("searchLibrary", "Search files")}
                  value={bibliothequeQuery}
                />

                <div className="bibliotheque-filter-row">
                  <button
                    className={`ghost-button history-action ${bibliothequeFilter === "all" ? "active-filter" : ""}`}
                    onClick={() => setBibliothequeFilter("all")}
                    type="button"
                  >
                    All
                  </button>
                  <button
                    className={`ghost-button history-action ${bibliothequeFilter === "pdf" ? "active-filter" : ""}`}
                    onClick={() => setBibliothequeFilter("pdf")}
                    type="button"
                  >
                    PDF
                  </button>
                  <button
                    className={`ghost-button history-action ${bibliothequeFilter === "voice" ? "active-filter" : ""}`}
                    onClick={() => setBibliothequeFilter("voice")}
                    type="button"
                  >
                    Voice
                  </button>
                  <button
                    className={`ghost-button history-action ${bibliothequeFilter === "image" ? "active-filter" : ""}`}
                    onClick={() => setBibliothequeFilter("image")}
                    type="button"
                  >
                    Images
                  </button>
                </div>

                {bibliothequeLoading ? <p className="muted">Loading uploaded files...</p> : null}

                <div className="bibliotheque-list">
                  {bibliothequeVisibleItems.length ? (
                    bibliothequeVisibleItems.map((item) => (
                      <button
                        key={item.id}
                        className="bibliotheque-item bibliotheque-item-button"
                        onClick={() => void openLibraryPreview(item)}
                        type="button"
                      >
                        <div className="bibliotheque-item-head">
                          <strong>{item.title}</strong>
                          <span className={`bibliotheque-kind ${item.kind}`}>{item.kind.toUpperCase()}</span>
                        </div>
                        <small>{item.subtitle}</small>
                        <small>{item.status}</small>
                        <small>{item.sizeLabel} · {item.createdAt}</small>
                      </button>
                    ))
                  ) : (
                    <p className="muted">No uploaded files match this filter.</p>
                  )}
                </div>
              </section>

              <section className="left-section">
                <h3>{t("plusModesTitle", "Modes")}</h3>
                <div className="mode-row">
                  <button className={`mode-button ${workspaceMode === "chat" ? "active" : ""}`} onClick={() => setWorkspaceMode("chat")} type="button">
                    <strong>{t("modeChat", "Chat Mode")}</strong>
                    <small>{t("modeChatDesc", "Fast legal discussion")}</small>
                  </button>
                  <button className={`mode-button ${workspaceMode === "agent" ? "active" : ""}`} onClick={() => setWorkspaceMode("agent")} type="button">
                    <strong>{t("modeAgent", "Agent Mode")}</strong>
                    <small>{t("modeAgentDesc", "Step-by-step execution")}</small>
                  </button>
                  <button className={`mode-button ${workspaceMode === "legal_search" ? "active" : ""}`} onClick={() => setWorkspaceMode("legal_search")} type="button">
                    <strong>{t("modeLegalSearch", "Legal Search Mode")}</strong>
                    <small>{t("modeLegalSearchDesc", "Source-grounded legal answers")}</small>
                  </button>
                  <button className={`mode-button ${externalModeEnabled ? "active" : ""}`} onClick={() => setExternalModeEnabled((current) => !current)} type="button">
                    <strong>{t("modeExternal", "External Mode")}</strong>
                    <small>{t("modeExternalDesc", "Web-enhanced legal research")}</small>
                  </button>
                </div>
              </section>

              <button className="ghost-button logout" onClick={logout} type="button">
                {t("logout", "Logout")}
              </button>
            </>
          )
          }
        </aside >
      ) : (
        <aside className="left-rail-collapsed glass" aria-label="Collapsed sidebar">
          <button
            aria-label="Open sidebar"
            className="rail-toggle open"
            onClick={() => setLeftRailOpen(true)}
            type="button"
          >
            &gt;
          </button>
          <button
            aria-label="Open navigator"
            className="collapsed-rail-button"
            onClick={() => {
              setLeftRailOpen(true);
              setSidebarTab("navigator");
            }}
            title="Navigator"
            type="button"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20">
              <circle cx="10" cy="10" r="6.8" />
              <path d="M8 8.3l5.6-2-2 5.6-5.6 2 2-5.6z" />
            </svg>
          </button>
          <button
            aria-label="Open bibliotheque"
            className="collapsed-rail-button"
            onClick={() => {
              setLeftRailOpen(true);
              setSidebarTab("bibliotheque");
            }}
            title="Bibliotheque"
            type="button"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20">
              <path d="M3.4 4.6a1 1 0 0 1 1-1h2.7a1 1 0 0 1 1 1v10.8a1 1 0 0 1-1 1H4.4a1 1 0 0 1-1-1V4.6z" />
              <path d="M8.8 4.6a1 1 0 0 1 1-1h2.7a1 1 0 0 1 1 1v10.8a1 1 0 0 1-1 1H9.8a1 1 0 0 1-1-1V4.6z" />
              <path d="M14.2 6.1a1 1 0 0 1 1.2-.8l1.7.4a1 1 0 0 1 .8 1.2l-2.3 9.7a1 1 0 0 1-1.2.8l-1.7-.4" />
            </svg>
          </button>

          <div className="collapsed-rail-divider" />

          <button
            className={`collapsed-mode-button ${workspaceMode === "chat" ? "active" : ""}`}
            aria-label={t("modeChat", "Chat Mode")}
            onClick={() => setWorkspaceMode("chat")}
            title={t("modeChat", "Chat Mode")}
            type="button"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20">
              <path d="M4.1 4.4h11.8a1.9 1.9 0 0 1 1.9 1.9v6.6a1.9 1.9 0 0 1-1.9 1.9H9.4l-3.3 2.6v-2.6H4.1a1.9 1.9 0 0 1-1.9-1.9V6.3a1.9 1.9 0 0 1 1.9-1.9z" />
            </svg>
          </button>
          <button
            className={`collapsed-mode-button ${workspaceMode === "agent" ? "active" : ""}`}
            aria-label={t("modeAgent", "Agent Mode")}
            onClick={() => setWorkspaceMode("agent")}
            title={t("modeAgent", "Agent Mode")}
            type="button"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20">
              <path d="M10 2.8l1.9 4.1L16 8.8l-4.1 1.9L10 14.8l-1.9-4.1L4 8.8l4.1-1.9L10 2.8z" />
              <path d="M15.8 12.9l.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8.8-1.7z" />
            </svg>
          </button>
          <button
            className={`collapsed-mode-button ${workspaceMode === "legal_search" ? "active" : ""}`}
            aria-label={t("modeLegalSearch", "Legal Search Mode")}
            onClick={() => setWorkspaceMode("legal_search")}
            title={t("modeLegalSearch", "Legal Search Mode")}
            type="button"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20">
              <circle cx="8.8" cy="8.8" r="4.6" />
              <path d="M12.2 12.2l4 4" />
              <path d="M8.8 6.8v4" />
              <path d="M6.8 8.8h4" />
            </svg>
          </button>
          <button
            className={`collapsed-mode-button ${externalModeEnabled ? "active" : ""}`}
            aria-label={t("modeExternal", "External Mode")}
            onClick={() => setExternalModeEnabled((current) => !current)}
            title={t("modeExternal", "External Mode")}
            type="button"
          >
            <svg aria-hidden="true" viewBox="0 0 20 20">
              <circle cx="10" cy="10" r="6.8" />
              <path d="M3.2 10h13.6" />
              <path d="M10 3.2c2 2 2 11.6 0 13.6" />
              <path d="M10 3.2c-2 2-2 11.6 0 13.6" />
            </svg>
          </button>
        </aside>
      )}

      <main className="center-panel glass center-panel-full">
        <header className="workspace-topbar">
          <div>
            <p className="meta">{t("workspaceOverview", "Workspace overview")}</p>
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
                <option value="fr">{t("languageFrench", "French")}</option>
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
              disabled={!token || auditLoading}
              onClick={() => {
                if (auditPanelOpen) {
                  setAuditPanelOpen(false);
                } else {
                  void loadAuditLogs();
                }
              }}
              type="button"
            >
              {auditLoading ? "Loading audit..." : auditPanelOpen ? "Hide audit" : "Trust audit"}
            </button>
            <button
              className="secondary-button"
              onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
              type="button"
            >
              {theme === "dark" ? t("light", "Light") : t("dark", "Dark")}
            </button>
          </div>
        </header>

        <section className="copilot-shell chat-only-shell">
          {notice ? <div className="notice-banner">{notice}</div> : null}
          {error ? <div className="error-banner">{error}</div> : null}

          {auditPanelOpen ? (
            <section className="trust-audit-panel">
              <div className="trust-audit-head">
                <div>
                  <h3>AI Response Audit</h3>
                  <p>Recent model outputs, validation status, sources, and trust metadata for this scope.</p>
                </div>
                <button type="button" onClick={() => void loadAuditLogs()} disabled={auditLoading}>
                  Refresh
                </button>
              </div>
              {auditLogs.length ? (
                <div className="trust-audit-list">
                  {auditLogs.map((row) => {
                    const validation = row.validation || {};
                    const trustPanel = row.trust_panel || {};
                    const metrics = (trustPanel.metrics || {}) as Record<string, unknown>;
                    const confidenceScore = Number(trustPanel.confidence_score || 0);
                    return (
                      <article className="trust-audit-item" key={row.id}>
                        <div>
                          <strong>{row.endpoint} · {row.parsed_intent || "unknown"}</strong>
                          <small>{new Date(row.created_at).toLocaleString()}</small>
                        </div>
                        <p>{row.question_text}</p>
                        <small>Validation: {String(validation.is_valid ?? "unknown")} · Confidence: {Math.round(confidenceScore * 100)}% · Citation coverage: {Math.round(Number(metrics.citation_coverage || 0) * 100)}%</small>
                        <details>
                          <summary>Answer preview and sources</summary>
                          <p>{row.answer_preview}</p>
                          <small>Model: {row.model_name || "unknown"} · Prompt: {row.prompt_version || "n/a"} · Response: {row.response_version}</small>
                        </details>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <p className="muted">No audit logs found for this scope yet.</p>
              )}
            </section>
          ) : null}

          <div className={`chat-surface ${showMinimalSearchOnly ? "chat-surface-minimal" : ""}`}>
            <details
              className="workspace-collapsible chat-history-collapsible chat-history-collapsible-main"
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
                    <p>{t("conversationHint", "Use the prompt box below to start.")}</p>
                    {workspaceMode === "chat" ? (
                      <>
                        <p className="starter-prompt-note">
                          {t("chatStarterHint", "Starter prompts")}
                        </p>
                        <div className="empty-chat-actions starter-prompt-actions">
                          {chatStarterPrompts.map((prompt) => (
                            <button
                              key={prompt}
                              className="starter-prompt-chip"
                              disabled={copilotLoading}
                              onClick={() => void sendMessage(prompt)}
                              type="button"
                            >
                              {prompt}
                            </button>
                          ))}
                        </div>
                        <p className="starter-prompt-note">
                          Workflow packs
                        </p>
                        <div className="empty-chat-actions starter-prompt-actions workflow-pack-actions">
                          {workflowPackPrompts.map((prompt) => (
                            <button
                              key={prompt}
                              className="starter-prompt-chip"
                              disabled={copilotLoading}
                              onClick={() => void sendMessage(prompt)}
                              type="button"
                            >
                              {prompt.split(":")[0]}
                            </button>
                          ))}
                        </div>
                      </>
                    ) : null}
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
                    onAskMissingInfo={handleAskMissingInfo}
                    onRegenerate={handleRegenerate}
                    onTrustReview={handleTrustReview}
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
                    <p className="muted">Chat image analysis was removed. Use scanned-document upload from the case workspace instead.</p>
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
                  aria-label={attachmentMenuOpen ? t("closeMenu", "Close menu") : t("openMenu", "Open menu")}
                  className="composer-plus"
                  onClick={() => setAttachmentMenuOpen((current) => !current)}
                  title={attachmentMenuOpen ? t("closeMenu", "Close menu") : t("openMenu", "Open menu")}
                  type="button"
                >
                  {attachmentMenuOpen ? "-" : "+"}
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
                    aria-label={copilotLoading ? t("stopRequest", "Stop request") : t("send", "Send")}
                    className={`composer-send ${copilotLoading ? "is-stop" : ""}`}
                    disabled={!copilotLoading && (!chatInput.trim() || composerRecording || composerTranscribing || optimizingPrompt)}
                    onClick={copilotLoading ? () => stopCopilotRequest() : undefined}
                    title={copilotLoading ? t("stopRequest", "Stop request") : t("send", "Send")}
                    type={copilotLoading ? "button" : "submit"}
                  >
                    {copilotLoading ? (
                      <svg aria-hidden="true" viewBox="0 0 20 20">
                        <rect x="5.5" y="5.5" width="9" height="9" rx="1.6" />
                      </svg>
                    ) : (
                      <svg aria-hidden="true" viewBox="0 0 20 20">
                        <path d="M4.5 10h9.8" />
                        <path d="m10.2 5.2 4.8 4.8-4.8 4.8" />
                      </svg>
                    )}
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

        {selectionGateOpen ? (
          <div className="selection-gate-backdrop">
            <section className="selection-gate-card">
              <p className="section-kicker">Lawyer Setup</p>
              <h3>{t("chooseClientCase", "Choose client and case")}</h3>
              <p className="muted">
                {t("chooseClientCaseHint", "Select the matter you want to open first. You can change it anytime from the sidebar.")}
              </p>

              <label>
                {t("client", "Client")}
                <select
                  value={gateClientId ?? ""}
                  onChange={(event) => setGateClientId(event.target.value ? Number(event.target.value) : null)}
                >
                  {clients.map((client) => (
                    <option key={client.id} value={client.id}>
                      {client.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                {t("caseLabel", "Case")}
                <select
                  value={gateCaseId ?? ""}
                  onChange={(event) => setGateCaseId(event.target.value ? Number(event.target.value) : null)}
                >
                  {gateCases.map((item) => (
                    <option key={item.id} value={item.id}>
                      #{item.id} · {item.title}
                    </option>
                  ))}
                </select>
              </label>

              <div className="selection-gate-actions">
                <button
                  className="primary-button"
                  disabled={!gateClientId || !gateCaseId}
                  onClick={confirmLawyerInitialSelection}
                  type="button"
                >
                  {t("startWorkspace", "Start workspace")}
                </button>
              </div>
            </section>
          </div>
        ) : null}

        {libraryPreviewItem ? (
          <div className="bibliotheque-preview-backdrop" onClick={closeLibraryPreview}>
            <section
              aria-label={`Preview ${libraryPreviewItem.title}`}
              aria-modal="true"
              className="bibliotheque-preview-card glass"
              onClick={(event) => event.stopPropagation()}
              role="dialog"
            >
              <header className="bibliotheque-preview-header">
                <div>
                  <p className="section-kicker">Library preview</p>
                  <h3>{libraryPreviewItem.title}</h3>
                  <p className="bibliotheque-preview-meta">
                    {libraryPreviewItem.subtitle} · {libraryPreviewItem.status}
                  </p>
                </div>
                <div className="bibliotheque-preview-actions">
                  {libraryPreviewBatch?.generated_document?.id ? (
                    <button
                      className="ghost-button history-action"
                      onClick={() => void openLibraryGeneratedDocument(libraryPreviewBatch.generated_document!.id)}
                      type="button"
                    >
                      Open generated document
                    </button>
                  ) : null}
                  <button className="ghost-button history-action" onClick={closeLibraryPreview} type="button">
                    Close
                  </button>
                </div>
              </header>

              {libraryPreviewLoading ? (
                <div className="bibliotheque-preview-loading">Opening preview...</div>
              ) : libraryPreviewError ? (
                <div className="bibliotheque-preview-error">{libraryPreviewError}</div>
              ) : libraryPreviewMarkdownText ? (
                <div className="bibliotheque-preview-markdown-shell">
                  <article className="bibliotheque-preview-markdown-paper">
                    {libraryPreviewMarkdownBlocks.map((block, index) => {
                      if (block.kind === "heading") {
                        const HeadingTag = `h${Math.min(3, Math.max(1, block.level))}` as keyof JSX.IntrinsicElements;
                        return (
                          <HeadingTag key={`${block.kind}-${index}`} className={`markdown-heading level-${block.level}`}>
                            {block.text}
                          </HeadingTag>
                        );
                      }

                      if (block.kind === "list") {
                        return (
                          <ul key={`${block.kind}-${index}`} className="markdown-list">
                            {block.items.map((item, itemIndex) => (
                              <li key={`${block.kind}-${index}-${itemIndex}`}>{item}</li>
                            ))}
                          </ul>
                        );
                      }

                      return (
                        <p key={`${block.kind}-${index}`} className="markdown-paragraph">
                          {block.text}
                        </p>
                      );
                    })}
                  </article>
                </div>
              ) : libraryPreviewItem.kind === "pdf" && libraryPreviewUrl ? (
                <iframe className="bibliotheque-preview-frame" src={libraryPreviewUrl} title={libraryPreviewItem.title} />
              ) : libraryPreviewItem.kind === "voice" && libraryPreviewUrl ? (
                <div className="bibliotheque-preview-voice">
                  <audio autoPlay controls src={libraryPreviewUrl} />
                  <p className="muted">Use the audio controls to play the recording in place.</p>
                </div>
              ) : libraryPreviewItem.kind === "image" ? (
                <div className="bibliotheque-preview-image-shell">
                  <div className="bibliotheque-preview-image-main">
                    {libraryPreviewAssets.length ? (
                      <img
                        alt={libraryPreviewAssets.find((asset) => asset.id === libraryPreviewAssetId)?.filename || libraryPreviewAssets[0].filename}
                        src={
                          libraryPreviewAssets.find((asset) => asset.id === libraryPreviewAssetId)?.url || libraryPreviewAssets[0].url
                        }
                      />
                    ) : (
                      <div className="bibliotheque-preview-loading">No image pages were returned for this batch.</div>
                    )}
                  </div>

                  {libraryPreviewBatch?.generated_document?.id ? (
                    <div className="bibliotheque-preview-note">
                      <strong>Generated document available</strong>
                      <p>
                        This image batch produced document #{libraryPreviewBatch.generated_document.id}. Open it from the
                        button above to read the generated case document.
                      </p>
                    </div>
                  ) : null}

                  {libraryPreviewAssets.length > 1 ? (
                    <div className="bibliotheque-preview-thumbs">
                      {libraryPreviewAssets.map((asset) => (
                        <button
                          key={asset.id}
                          className={`bibliotheque-preview-thumb ${libraryPreviewAssetId === asset.id ? "active" : ""}`}
                          onClick={() => setLibraryPreviewAssetId(asset.id)}
                          type="button"
                        >
                          <img alt={asset.filename} src={asset.url} />
                          <span>{asset.pageOrder ?? asset.id}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </section>
          </div>
        ) : null}
      </main>

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
        accept="image/*,.pdf,application/pdf"
        multiple
        onChange={onScannedPhotosSelected}
        style={{ display: "none" }}
        type="file"
      />
    </div >
  );
}

