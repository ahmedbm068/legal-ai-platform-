import type { DraftDocumentAiEditResponse } from "../types";

interface AISuggestionPanelProps {
  suggestion: DraftDocumentAiEditResponse | null;
  originalText: string | null;
  loading: boolean;
  error: string | null;
  onAccept: () => void;
  onReject: () => void;
}

function DiffPreview({ original, proposed }: { original: string; proposed: string }) {
  const oldWords = original.split(/\s+/).filter(Boolean);
  const newWords = proposed.split(/\s+/).filter(Boolean);
  const removed = oldWords.filter((word) => !newWords.includes(word)).slice(0, 80).join(" ");
  const added = newWords.filter((word) => !oldWords.includes(word)).slice(0, 80).join(" ");
  return (
    <div className="space-y-2 rounded-xl bg-slate-950/[0.03] p-3 text-sm dark:bg-black/20">
      <div className="rounded-lg bg-red-500/10 px-3 py-2 text-red-700 dark:text-red-300">
        <span className="mr-2 font-bold">Removed</span>
        {removed || original}
      </div>
      <div className="rounded-lg bg-emerald-500/10 px-3 py-2 text-emerald-700 dark:text-emerald-300">
        <span className="mr-2 font-bold">Added</span>
        {added || proposed}
      </div>
    </div>
  );
}

export default function AISuggestionPanel({ suggestion, originalText, loading, error, onAccept, onReject }: AISuggestionPanelProps) {
  return (
    <aside className="editor-side-card rounded-2xl bg-white/75 p-4 shadow-sm ring-1 ring-slate-900/[0.04] backdrop-blur dark:bg-[#151821]/78 dark:ring-white/[0.06]" aria-label="AI suggestions">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">AI Review</p>
          <h3 className="mt-1 text-sm font-bold text-slate-950 dark:text-slate-100">Suggested edit</h3>
        </div>
        {suggestion ? <span className="rounded-full bg-emerald-500/10 px-2 py-1 text-[11px] font-bold text-emerald-700 dark:text-emerald-300">{suggestion.confidence} confidence</span> : null}
      </div>
      {loading ? (
        <div className="space-y-2 animate-pulse">
          <div className="h-3 w-3/4 rounded bg-slate-200 dark:bg-white/10" />
          <div className="h-20 rounded-xl bg-slate-100 dark:bg-white/[0.06]" />
        </div>
      ) : null}
      {error ? <p className="shell-error-text">{error}</p> : null}
      {suggestion ? (
        <div className="space-y-3 transition duration-200 ease-out">
          <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">{suggestion.explanation}</p>
          <DiffPreview original={originalText || ""} proposed={suggestion.proposed_text} />
          <div className="flex items-center gap-2">
            <button className="rounded-lg bg-emerald-500 px-3 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-emerald-400" onClick={onAccept} type="button">Accept</button>
            <button className="premium-editor-ghost-button" onClick={onReject} type="button">Reject</button>
          </div>
        </div>
      ) : !loading ? (
        <p className="text-sm leading-6 text-slate-500 dark:text-slate-400">Highlight text, then choose a rewrite action. Suggestions stay reviewable until accepted.</p>
      ) : null}
    </aside>
  );
}
