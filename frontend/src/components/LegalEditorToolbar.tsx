import { useState } from "react";
import type { Editor } from "@tiptap/react";
import ExportMenu from "./ExportMenu";

interface LegalEditorToolbarProps {
  editor: Editor | null;
  title: string;
  documentType: string;
  saveState: "saved" | "unsaved" | "saving";
  canSendEmail: boolean;
  disabled: boolean;
  onTitleChange: (value: string) => void;
  onSave: () => void;
  onExportDocx: () => void;
  onExportPdf: () => void;
  onSendEmail: () => void;
  onAiAction: (instruction: string) => void;
  focusMode: boolean;
  onToggleFocusMode: () => void;
  onClose: () => void;
}

export default function LegalEditorToolbar({
  editor,
  title,
  documentType,
  saveState,
  canSendEmail,
  disabled,
  onTitleChange,
  onSave,
  onExportDocx,
  onExportPdf,
  onSendEmail,
  onAiAction,
  focusMode,
  onToggleFocusMode,
  onClose,
}: LegalEditorToolbarProps) {
  const [moreOpen, setMoreOpen] = useState(false);
  const active = (name: string) => editor?.isActive(name) ? "bg-slate-200 text-slate-950 dark:bg-white/10 dark:text-slate-50" : "";
  const toolButton = "h-8 rounded-lg px-2.5 text-xs font-semibold text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 disabled:opacity-40 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-slate-100";
  const aiButton = "h-8 rounded-lg bg-emerald-500/10 px-3 text-xs font-bold text-emerald-700 transition hover:bg-emerald-500/15 dark:text-emerald-300";

  return (
    <header className="premium-editor-header shrink-0 bg-white/90 px-5 py-4 shadow-sm backdrop-blur-xl dark:bg-[#0f131a]/90">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <input
            className="w-full min-w-0 bg-transparent text-base font-bold tracking-[-0.01em] text-slate-950 outline-none placeholder:text-slate-400 dark:text-slate-100"
            value={title}
            onChange={(event) => onTitleChange(event.target.value)}
            aria-label="Document title"
          />
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold ${saveState === "saved" ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300" : saveState === "saving" ? "bg-amber-500/10 text-amber-700 dark:text-amber-300" : "bg-slate-500/10 text-slate-600 dark:text-slate-300"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${saveState === "saving" ? "animate-pulse bg-amber-400" : saveState === "saved" ? "bg-emerald-400" : "bg-slate-400"}`} />
              {saveState === "saved" ? "Saved" : saveState === "saving" ? "Saving..." : "Unsaved"}
            </span>
            <span>{documentType.replace(/_/g, " ")}</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button className="premium-editor-ghost-button" disabled={disabled || saveState === "saving"} onClick={onSave} type="button">Save</button>
          <ExportMenu disabled={disabled} onDocx={onExportDocx} onPdf={onExportPdf} />
          {canSendEmail ? <button className="rounded-lg bg-emerald-500 px-3 py-2 text-xs font-bold text-white shadow-sm transition hover:bg-emerald-400 disabled:opacity-50" disabled={disabled} onClick={onSendEmail} type="button">Send email</button> : null}
          <button className="premium-editor-ghost-button" onClick={onToggleFocusMode} type="button">{focusMode ? "Exit focus" : "Focus"}</button>
          <button className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-slate-100" onClick={onClose} type="button" aria-label="Close editor">x</button>
        </div>
      </div>
      <div className="premium-editor-toolbar-row mt-4 flex items-center gap-1 overflow-x-auto rounded-xl bg-slate-100/75 p-1 dark:bg-white/[0.04]" role="toolbar" aria-label="Text formatting and AI actions">
        <span className="px-2 text-[11px] font-bold uppercase tracking-[0.12em] text-slate-400">Format</span>
        <button className={toolButton} onClick={() => editor?.chain().focus().setParagraph().run()} type="button">Normal</button>
        <button className={`${toolButton} ${editor?.isActive("heading", { level: 2 }) ? "bg-slate-200 text-slate-950 dark:bg-white/10 dark:text-slate-50" : ""}`} onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()} type="button">H2</button>
        <span className="mx-1 h-5 w-px bg-slate-200 dark:bg-white/10" />
        <button className={`${toolButton} ${active("bold")}`} onClick={() => editor?.chain().focus().toggleBold().run()} type="button"><strong>B</strong></button>
        <button className={`${toolButton} ${active("italic")}`} onClick={() => editor?.chain().focus().toggleItalic().run()} type="button"><em>I</em></button>
        <button className={`${toolButton} ${active("underline")}`} onClick={() => editor?.chain().focus().toggleUnderline().run()} type="button"><u>U</u></button>
        <span className="mx-1 h-5 w-px bg-slate-200 dark:bg-white/10" />
        <button className={`${toolButton} ${active("bulletList")}`} onClick={() => editor?.chain().focus().toggleBulletList().run()} type="button">List</button>
        <button className={`${toolButton} ${active("orderedList")}`} onClick={() => editor?.chain().focus().toggleOrderedList().run()} type="button">1.</button>
        <button className={`${toolButton} ${active("blockquote")}`} onClick={() => editor?.chain().focus().toggleBlockquote().run()} type="button">Quote</button>
        <span className="mx-1 h-5 w-px bg-slate-200 dark:bg-white/10" />
        <button className={toolButton} onClick={() => editor?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()} type="button">Table</button>
        <span className="mx-2 h-5 w-px bg-slate-200 dark:bg-white/10" />
        <span className="px-2 text-[11px] font-bold uppercase tracking-[0.12em] text-slate-400">AI</span>
        <button className={aiButton} onClick={() => onAiAction("Rewrite")} type="button">Rewrite</button>
        <button className={aiButton} onClick={() => onAiAction("Make more formal")} type="button">Formalize</button>
        <button className={aiButton} onClick={() => onAiAction("Simplify")} type="button">Simplify</button>
        <div className="relative">
          <button className={toolButton} onClick={() => setMoreOpen((current) => !current)} type="button">More</button>
          {moreOpen ? (
            <div className="absolute right-0 top-9 z-30 grid min-w-44 gap-1 rounded-xl bg-white p-1.5 shadow-xl ring-1 ring-slate-900/10 dark:bg-[#151821] dark:ring-white/10">
              {["Make more aggressive", "Make more diplomatic", "Translate", "Add legal reasoning", "Expand"].map((instruction) => (
                <button
                  className="rounded-lg px-3 py-2 text-left text-xs font-semibold text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-300 dark:hover:bg-white/10 dark:hover:text-white"
                  key={instruction}
                  onClick={() => {
                    setMoreOpen(false);
                    onAiAction(instruction);
                  }}
                  type="button"
                >
                  {instruction}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
