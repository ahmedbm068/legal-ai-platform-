import type { CitationItem, SourceItem } from "./types";

export type EditorDraftSeedSource = "case" | "assistant";

export interface EditorDraftSeed {
  source: EditorDraftSeedSource;
  caseId: number;
  caseTitle?: string | null;
  prompt?: string | null;
  answer?: string | null;
  sources?: SourceItem[];
  citations?: CitationItem[];
  createdAt: string;
}

const EDITOR_DRAFT_SEED_STORAGE_KEY = "legal-ai-editor-draft-seed-v1";

export function saveEditorDraftSeed(seed: EditorDraftSeed) {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(EDITOR_DRAFT_SEED_STORAGE_KEY, JSON.stringify(seed));
}

export function loadEditorDraftSeed(caseId: number): EditorDraftSeed | null {
  if (typeof window === "undefined") return null;

  const raw = window.sessionStorage.getItem(EDITOR_DRAFT_SEED_STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as EditorDraftSeed;
    window.sessionStorage.removeItem(EDITOR_DRAFT_SEED_STORAGE_KEY);
    if (!parsed || parsed.caseId !== caseId || !parsed.source) {
      return null;
    }
    return parsed;
  } catch {
    window.sessionStorage.removeItem(EDITOR_DRAFT_SEED_STORAGE_KEY);
    return null;
  }
}
