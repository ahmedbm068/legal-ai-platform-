import type { CitationItem } from "../types";

interface EditorCitationSidebarProps {
  citations: CitationItem[];
  onSelectCitation?: (citation: CitationItem, index: number) => void;
}

export default function EditorCitationSidebar({ citations, onSelectCitation }: EditorCitationSidebarProps) {
  return (
    <aside className="editor-side-card rounded-2xl bg-white/75 p-4 shadow-sm ring-1 ring-slate-900/[0.04] backdrop-blur dark:bg-[#151821]/78 dark:ring-white/[0.06]" aria-label="Document citations">
      <div className="mb-3">
        <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">Sources</p>
        <h3 className="mt-1 text-sm font-bold text-slate-950 dark:text-slate-100">Citations ({citations.length})</h3>
      </div>
      {citations.length ? (
        <ul className="space-y-2">
          {citations.map((citation, index) => (
            <li key={`${citation.label}-${index}`}>
              <button
                className="group w-full rounded-xl bg-slate-950/[0.03] p-3 text-left transition hover:bg-emerald-500/10 dark:bg-white/[0.04] dark:hover:bg-emerald-400/10"
                onClick={() => onSelectCitation?.(citation, index)}
                type="button"
              >
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 rounded-md bg-indigo-500/10 px-1.5 py-0.5 text-[11px] font-bold text-indigo-600 dark:text-indigo-300">{index + 1}</span>
                  <strong className="min-w-0 flex-1 text-xs font-bold leading-5 text-slate-900 group-hover:text-emerald-700 dark:text-slate-100 dark:group-hover:text-emerald-300">{citation.label}</strong>
                </div>
                {citation.snippet ? <span className="mt-2 line-clamp-3 block text-xs leading-5 text-slate-500 dark:text-slate-400">{citation.snippet}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm leading-6 text-slate-500 dark:text-slate-400">No citations attached yet. Use AI Add citation after selecting text.</p>
      )}
    </aside>
  );
}
