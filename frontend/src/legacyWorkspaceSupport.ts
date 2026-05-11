import type { ChatMessage } from "./types";

export const TOKEN_STORAGE_KEY = "legal-ai-platform-token";
export const THEME_STORAGE_KEY = "legal-ai-platform-theme-v3";
export const LANGUAGE_STORAGE_KEY = "legal-ai-platform-language-v2";
export const LEGACY_CHAT_STORAGE_KEY = "legal-ai-platform-chat-map-v2";
export const CHAT_STORAGE_KEY = "legal-ai-platform-chat-sessions-v3";
export const IMAGE_BATCH_POLL_INTERVAL_MS = 4500;
export const IMAGE_BATCH_POLL_MAX_CYCLES = 30;
export const IMAGE_BATCH_POLL_STALL_MAX_CYCLES = 6;
export const DEFAULT_LAWYER_PHONE = "+216 24 996 073";
export const CHAT_GLOBAL_SCOPE_ID = 0;

export type ThemeMode = "dark" | "light";
export type UiLanguage = "en" | "fr" | "de" | "ar";
export type WorkspaceMode = "chat" | "agent" | "legal_search";
export type ReasoningLevel = "low" | "medium" | "high";
export type FeedbackValue = "up" | "down";
export type SidebarTab = "navigator" | "bibliotheque" | "calendar";
export type LibraryFilter = "all" | "pdf" | "voice" | "image";

export interface BibliothequeItem {
  id: string;
  sourceId: number;
  kind: Exclude<LibraryFilter, "all">;
  title: string;
  subtitle: string;
  status: string;
  sizeLabel: string;
  createdAt: string;
  sortTime: number;
  generatedDocumentId?: number | null;
}

export interface LibraryPreviewAsset {
  id: number;
  filename: string;
  mimeType: string;
  url: string;
  pageOrder?: number | null;
  extractedText?: string | null;
}

export interface AuthFormState {
  name: string;
  tenant: string;
  inviteToken: string;
  email: string;
  password: string;
  role: "admin" | "lawyer" | "assistant";
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface StoredChatSessionsState {
  sessionsByCase: Record<number, ChatSession[]>;
  activeSessionIdByCase: Record<number, string>;
}

export const REASONING_TOP_K: Record<ReasoningLevel, number> = {
  low: 3,
  medium: 6,
  high: 9,
};

export function generateId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `m-${Date.now()}-${Math.round(Math.random() * 1_000_000)}`;
}

export function compactDate(value: string | null | undefined, locale = "en-US", noDateLabel = "No date"): string {
  if (!value) return noDateLabel;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return noDateLabel;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(parsed);
}

export function compactDateTime(value: string | null | undefined, locale = "en-US", noDateLabel = "No date"): string {
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

export function truncateText(value: string, max = 92): string {
  const cleaned = (value || "").replace(/\s+/g, " ").trim();
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max - 1)}...`;
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "0 KB";
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.max(1, Math.round(kb))} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(1)} MB`;
}

export function normalizeError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

export type MarkdownPreviewBlock =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };

export function parseMarkdownPreview(text: string): MarkdownPreviewBlock[] {
  const blocks: MarkdownPreviewBlock[] = [];
  const lines = (text || "").split(/\r?\n/);
  let paragraphLines: string[] = [];
  let listItems: string[] = [];

  const flushParagraph = () => {
    if (!paragraphLines.length) return;
    blocks.push({ kind: "paragraph", text: paragraphLines.join(" ").replace(/\s+/g, " ").trim() });
    paragraphLines = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push({ kind: "list", items: listItems });
    listItems = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      blocks.push({
        kind: "heading",
        level: headingMatch[1].length as 1 | 2 | 3,
        text: headingMatch[2].trim(),
      });
      continue;
    }

    const bulletMatch = line.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph();
      listItems.push(bulletMatch[1].trim());
      continue;
    }

    const numberedMatch = line.match(/^\d+[\).]\s+(.+)$/);
    if (numberedMatch) {
      flushParagraph();
      listItems.push(numberedMatch[1].trim());
      continue;
    }

    flushList();
    paragraphLines.push(line);
  }

  flushParagraph();
  flushList();
  return blocks;
}

function normalizeArray(value: unknown) {
  return Array.isArray(value) ? value : [];
}

export function normalizeStoredMessage(message: Partial<ChatMessage> | null | undefined): ChatMessage {
  const meta = message && typeof message.meta === "object" && message.meta ? message.meta : {};
  const rawAnswer = typeof meta.rawAnswer === "string" ? meta.rawAnswer : null;
  const normalized: ChatMessage = {
    id: String(message?.id || generateId()),
    role: message?.role === "user" || message?.role === "assistant" ? message.role : "assistant",
    content: String(message?.content || rawAnswer || ""),
    timestamp: String(message?.timestamp || new Date().toISOString()),
    meta: {
      ...meta,
      sources: normalizeArray(meta.sources),
      citations: normalizeArray(meta.citations),
      executionTrace: normalizeArray(meta.executionTrace),
      steps: normalizeArray(meta.steps),
      savedAssetIds: normalizeArray(meta.savedAssetIds),
      rawAnswer,
    },
  };
  if (normalized.role === "assistant" && rawAnswer && normalized.content !== rawAnswer) {
    return {
      ...normalized,
      content: rawAnswer,
    };
  }
  return normalized;
}

export function buildChatSessionTitle(messages: ChatMessage[], fallback = "New chat"): string {
  const firstUserMessage = messages.find((message) => message.role === "user")?.content || "";
  return truncateText(firstUserMessage, 52) || fallback;
}

export function normalizeStoredSession(rawSession: Partial<ChatSession> | null | undefined): ChatSession | null {
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

export function parseStoredChatState(): StoredChatSessionsState {
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

export function createMessage(role: "user" | "assistant", content: string, meta?: ChatMessage["meta"]): ChatMessage {
  return {
    id: generateId(),
    role,
    content,
    timestamp: new Date().toISOString(),
    meta,
  };
}
