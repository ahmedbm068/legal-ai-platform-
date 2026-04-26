import type { ChatMessage } from "./types";

type ChatMessageMeta = NonNullable<ChatMessage["meta"]>;

export interface ChatSessionSnapshot {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface StoredChatStateSnapshot {
  sessionsByCase: Record<number, ChatSessionSnapshot[]>;
  activeSessionIdByCase: Record<number, string>;
}

const STANDARD_SESSION_LIMIT = 6;
const STANDARD_MESSAGE_LIMIT = 36;
const AGGRESSIVE_SESSION_LIMIT = 3;
const AGGRESSIVE_MESSAGE_LIMIT = 14;

function trimText(value: unknown, limit: number): string {
  const text = String(value || "").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, Math.max(0, limit - 3)).trim()}...`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function compactRecordList(value: unknown, limit: number, textLimit: number): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.slice(0, limit).map((item) => {
    const record = asRecord(item);
    if (!record) {
      return { value: trimText(item, textLimit) };
    }

    const compacted: Record<string, unknown> = {};
    Object.entries(record).forEach(([key, entry]) => {
      if (typeof entry === "string") {
        compacted[key] = trimText(entry, textLimit);
      } else if (typeof entry === "number" || typeof entry === "boolean" || entry === null) {
        compacted[key] = entry;
      }
    });
    return compacted;
  });
}

function compactStringList(value: unknown, limit: number, textLimit: number): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .slice(0, limit)
    .map((item) => trimText(item, textLimit))
    .filter(Boolean);
}

function compactReasoningResult(value: unknown, aggressive: boolean): Record<string, unknown> | null {
  const record = asRecord(value);
  if (!record) return null;
  const candidateLimit = aggressive ? 1 : 2;
  const answerLimit = aggressive ? 450 : 900;
  const candidates = Array.isArray(record.candidates)
    ? record.candidates.slice(0, candidateLimit).map((candidate) => {
      const candidateRecord = asRecord(candidate);
      const score = asRecord(candidateRecord?.score);
      return {
        rank: Number(candidateRecord?.rank) || 0,
        style: trimText(candidateRecord?.style, 80),
        answer: trimText(candidateRecord?.answer, answerLimit),
        score,
      };
    })
    : [];

  return {
    reasoning_level: record.reasoning_level,
    activated: Boolean(record.activated),
    winner_index: record.winner_index ?? null,
    second_best_index: record.second_best_index ?? null,
    winner_reason: trimText(record.winner_reason, aggressive ? 180 : 360),
    candidates,
  };
}

function compactMessage(message: ChatMessage, aggressive: boolean): ChatMessage {
  const meta = asRecord(message.meta);
  if (!meta) {
    return {
      ...message,
      content: trimText(message.content, aggressive ? 1600 : 6000),
    };
  }

  const compactedMeta: ChatMessage["meta"] = {
    parsedIntent: typeof meta.parsedIntent === "string" ? trimText(meta.parsedIntent, 120) : undefined,
    confidence: typeof meta.confidence === "string" ? trimText(meta.confidence, 40) : undefined,
    fallbackReason: typeof meta.fallbackReason === "string" ? trimText(meta.fallbackReason, 220) : null,
    actionCategory: typeof meta.actionCategory === "string" ? trimText(meta.actionCategory, 120) : undefined,
    actionStatus: typeof meta.actionStatus === "string" ? trimText(meta.actionStatus, 120) : null,
    permissionDenied: typeof meta.permissionDenied === "boolean" ? meta.permissionDenied : undefined,
    steps: compactStringList(meta.steps, aggressive ? 6 : 12, 220),
    sources: compactRecordList(meta.sources, aggressive ? 4 : 10, aggressive ? 320 : 700) as unknown as ChatMessageMeta["sources"],
    citations: compactRecordList(meta.citations, aggressive ? 4 : 10, aggressive ? 320 : 700) as unknown as ChatMessageMeta["citations"],
    executionTrace: compactRecordList(meta.executionTrace, aggressive ? 4 : 10, 260),
    cache: (asRecord(meta.cache) || undefined) as unknown as ChatMessageMeta["cache"],
    jobId: typeof meta.jobId === "string" ? trimText(meta.jobId, 120) : null,
    caseSnapshotVersion: typeof meta.caseSnapshotVersion === "number" ? meta.caseSnapshotVersion : null,
    jurisdiction: asRecord(meta.jurisdiction) as ChatMessageMeta["jurisdiction"],
    reasoningResult: compactReasoningResult(meta.reasoningResult, aggressive) as ChatMessageMeta["reasoningResult"],
    savedAssetIds: Array.isArray(meta.savedAssetIds) ? meta.savedAssetIds.slice(0, aggressive ? 8 : 24).map(Number).filter(Number.isFinite) : [],
    reviewRecordId: typeof meta.reviewRecordId === "number" ? meta.reviewRecordId : null,
    rawAnswer: null,
  };

  return {
    ...message,
    content: trimText(message.content, aggressive ? 1600 : 6000),
    meta: compactedMeta,
  };
}

export function compactChatStateForStorage(
  state: StoredChatStateSnapshot,
  aggressive = false
): StoredChatStateSnapshot {
  const sessionLimit = aggressive ? AGGRESSIVE_SESSION_LIMIT : STANDARD_SESSION_LIMIT;
  const messageLimit = aggressive ? AGGRESSIVE_MESSAGE_LIMIT : STANDARD_MESSAGE_LIMIT;
  const sessionsByCase: Record<number, ChatSessionSnapshot[]> = {};
  const activeSessionIdByCase: Record<number, string> = {};

  Object.entries(state.sessionsByCase || {}).forEach(([key, sessions]) => {
    const numeric = Number(key);
    if (Number.isNaN(numeric) || !Array.isArray(sessions)) return;

    const compactedSessions = sessions
      .slice()
      .sort((a, b) => new Date(b.updatedAt || 0).getTime() - new Date(a.updatedAt || 0).getTime())
      .slice(0, sessionLimit)
      .map((session) => ({
        ...session,
        title: trimText(session.title, 80),
        messages: session.messages.slice(-messageLimit).map((message) => compactMessage(message, aggressive)),
      }));

    sessionsByCase[numeric] = compactedSessions;
    const activeSessionId = state.activeSessionIdByCase?.[numeric];
    if (activeSessionId && compactedSessions.some((session) => session.id === activeSessionId)) {
      activeSessionIdByCase[numeric] = activeSessionId;
    } else if (compactedSessions[0]) {
      activeSessionIdByCase[numeric] = compactedSessions[0].id;
    }
  });

  return { sessionsByCase, activeSessionIdByCase };
}

export function persistChatStateToLocalStorage(
  storageKey: string,
  state: StoredChatStateSnapshot
): StoredChatStateSnapshot | null {
  try {
    localStorage.setItem(storageKey, JSON.stringify(compactChatStateForStorage(state)));
    return null;
  } catch (firstError) {
    console.warn("Chat cache exceeded browser storage quota; compacting aggressively.", firstError);
  }

  const compacted = compactChatStateForStorage(state, true);
  try {
    localStorage.setItem(storageKey, JSON.stringify(compacted));
    return compacted;
  } catch (secondError) {
    console.warn("Unable to persist chat cache after compaction; clearing local cache.", secondError);
    localStorage.removeItem(storageKey);
    return { sessionsByCase: {}, activeSessionIdByCase: {} };
  }
}
