import { useEffect, useMemo, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import { Table } from "@tiptap/extension-table";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import TableRow from "@tiptap/extension-table-row";
import type { DraftDocument, DraftDocumentAiEditResponse, DraftDocumentPayload } from "../types";
import { workspaceApi } from "../workspaceApi";
import AISuggestionPanel from "./AISuggestionPanel";
import EditorCitationSidebar from "./EditorCitationSidebar";
import LegalEditorToolbar from "./LegalEditorToolbar";
import SendEmailModal from "./SendEmailModal";

interface LegalEditorPanelProps {
  token: string;
  payload: DraftDocumentPayload;
  onClose: () => void;
  onSaved?: (document: DraftDocument) => void;
  onFocusModeChange?: (enabled: boolean) => void;
}

type SaveState = "saved" | "unsaved" | "saving";
type SuggestionRange = { from: number; to: number; text: string };

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function LegalEditorPanel({ token, payload, onClose, onSaved, onFocusModeChange }: LegalEditorPanelProps) {
  const [documentRecord, setDocumentRecord] = useState<DraftDocument | null>(null);
  const [title, setTitle] = useState(payload.title || "Legal Draft");
  const [saveState, setSaveState] = useState<SaveState>("unsaved");
  const [focusMode, setFocusMode] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suggestion, setSuggestion] = useState<DraftDocumentAiEditResponse | null>(null);
  const [suggestionRange, setSuggestionRange] = useState<SuggestionRange | null>(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [sendEmailOpen, setSendEmailOpen] = useState(false);
  const autoCreatedRef = useRef(false);

  const citations = useMemo(() => payload.citations || documentRecord?.citations_json || [], [documentRecord?.citations_json, payload.citations]);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Underline,
      Link.configure({ openOnClick: false }),
      Placeholder.configure({ placeholder: "Start drafting..." }),
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: payload.content_html || "<p></p>",
    editorProps: {
      attributes: {
        class: "legal-tiptap-surface",
      },
    },
    onUpdate: () => {
      setSaveState("unsaved");
      setError(null);
    },
  });

  useEffect(() => {
    if (!token || autoCreatedRef.current) return;
    autoCreatedRef.current = true;
    setSaveState("saving");
    workspaceApi.createDraftDocument(token, payload)
      .then((created) => {
        setDocumentRecord(created);
        setTitle(created.title);
        setSaveState("saved");
        onSaved?.(created);
      })
      .catch((caught) => {
        setSaveState("unsaved");
        setError(caught instanceof Error ? caught.message : "Unable to save draft document.");
      });
  }, [onSaved, payload, token]);

  async function saveDocument(changeSummary = "Editor save"): Promise<DraftDocument | null> {
    if (!editor) return null;
    setSaveState("saving");
    setError(null);
    const contentHtml = editor.getHTML();
    const contentText = editor.getText({ blockSeparator: "\n" });
    const contentJson = editor.getJSON() as Record<string, unknown>;
    try {
      const saved = documentRecord
        ? await workspaceApi.updateDraftDocument(token, documentRecord.id, {
            title,
            document_type: payload.document_type,
            content_json: contentJson,
            content_html: contentHtml,
            content_text: contentText,
            citations_json: citations,
            source_context_json: payload.source_context || {},
            change_summary: changeSummary,
            create_version: true,
          })
        : await workspaceApi.createDraftDocument(token, {
            ...payload,
            title,
            content_json: contentJson,
            content_html: contentHtml,
            content_text: contentText,
          });
      setDocumentRecord(saved);
      setSaveState("saved");
      setNotice("Document saved.");
      onSaved?.(saved);
      return saved;
    } catch (caught) {
      setSaveState("unsaved");
      setError(caught instanceof Error ? caught.message : "Unable to save document.");
      return null;
    }
  }

  function selectedText(): SuggestionRange | null {
    if (!editor) return null;
    const { from, to } = editor.state.selection;
    if (from === to) return null;
    const text = editor.state.doc.textBetween(from, to, "\n").trim();
    return text ? { from, to, text } : null;
  }

  async function requestAiEdit(instruction: string) {
    if (!editor) return;
    const range = selectedText();
    if (!range) {
      setError("Highlight text in the document first.");
      return;
    }
    const activeDocument = documentRecord || await saveDocument("Auto-save before AI edit");
    const documentId = activeDocument?.id;
    if (!documentId) {
      setError("Save the document once before using AI edits.");
      return;
    }
    setSuggestionLoading(true);
    setSuggestion(null);
    setSuggestionRange(range);
    setError(null);
    try {
      const response = await workspaceApi.aiEditDraftDocument(token, documentId, {
        selected_text: range.text,
        instruction,
        full_document_context: editor.getText({ blockSeparator: "\n" }),
        case_id: payload.case_id ?? null,
        citation_mode: instruction.toLowerCase().includes("citation") ? "required" : "suggest",
      });
      setSuggestion(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to generate AI edit.");
    } finally {
      setSuggestionLoading(false);
    }
  }

  function acceptSuggestion() {
    if (!editor || !suggestion || !suggestionRange) return;
    editor.chain().focus().insertContentAt({ from: suggestionRange.from, to: suggestionRange.to }, suggestion.proposed_text).run();
    setSuggestion(null);
    setSuggestionRange(null);
    setSaveState("unsaved");
  }

  function toggleFocusMode() {
    const next = !focusMode;
    setFocusMode(next);
    onFocusModeChange?.(next);
  }

  function addCitationBadge(citation: { label: string }, index: number) {
    if (!editor) return;
    editor.chain().focus().insertContent(` <sup class="legal-citation-badge">[${index + 1}]</sup>`).run();
    setNotice(`Inserted citation badge for ${citation.label}.`);
  }

  async function exportDocx() {
    const activeDocument = documentRecord || await saveDocument("Save before DOCX export");
    const documentId = activeDocument?.id;
    if (!documentId) return;
    const blob = await workspaceApi.exportDraftDocumentDocx(token, documentId);
    downloadBlob(blob, `${title || "legal-draft"}.docx`);
  }

  async function exportPdf() {
    const activeDocument = documentRecord || await saveDocument("Save before PDF export");
    const documentId = activeDocument?.id;
    if (!documentId) return;
    const blob = await workspaceApi.exportDraftDocumentPdf(token, documentId);
    downloadBlob(blob, `${title || "legal-draft"}.pdf`);
  }

  async function sendEmail(payloadToSend: { to: string; subject: string; cc: string[] }) {
    if (!editor) return;
    const activeDocument = documentRecord || await saveDocument("Save before email send");
    const documentId = activeDocument?.id;
    if (!documentId) return;
    const response = await workspaceApi.sendDraftDocumentEmail(token, documentId, {
      ...payloadToSend,
      body_html: editor.getHTML(),
      body_text: editor.getText({ blockSeparator: "\n" }),
      confirm: true,
    });
    if (response.document) setDocumentRecord(response.document);
    setSendEmailOpen(false);
    setNotice(response.message);
  }

  return (
    <aside className={`premium-legal-editor flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl bg-[#f6f7f9] text-slate-950 shadow-editor-soft ring-1 ring-slate-900/[0.04] dark:bg-[#0f1115] dark:text-slate-100 dark:shadow-editor-dark dark:ring-white/[0.06] ${focusMode ? "is-focus-mode" : ""}`} aria-label="Legal document editor">
      <LegalEditorToolbar
        editor={editor}
        title={title}
        documentType={payload.document_type}
        saveState={saveState}
        canSendEmail={payload.document_type === "email"}
        disabled={!editor}
        onTitleChange={(value) => { setTitle(value); setSaveState("unsaved"); }}
        onSave={() => void saveDocument()}
        onExportDocx={() => void exportDocx()}
        onExportPdf={() => void exportPdf()}
        onSendEmail={() => setSendEmailOpen(true)}
        onAiAction={(instruction) => void requestAiEdit(instruction)}
        focusMode={focusMode}
        onToggleFocusMode={toggleFocusMode}
        onClose={onClose}
      />

      {notice ? <p className="mx-4 mt-3 rounded-xl bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-700 dark:text-emerald-300">{notice}</p> : null}
      {error ? <p className="mx-4 mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-700 dark:text-red-300">{error}</p> : null}

      <div className={`grid min-h-0 flex-1 gap-6 p-6 ${focusMode ? "grid-cols-1" : "grid-cols-[minmax(0,1fr)_minmax(230px,28%)]"}`}>
        <main className="min-h-0 min-w-0 overflow-hidden">
          <div className="editor-paper-stage h-full min-h-0 overflow-auto rounded-3xl bg-slate-200/30 px-8 py-10 dark:bg-black/15">
            <EditorContent editor={editor} />
          </div>
        </main>
        {!focusMode ? (
        <div className="grid min-h-0 content-start gap-3 overflow-auto">
          <EditorCitationSidebar citations={citations} onSelectCitation={addCitationBadge} />
          <AISuggestionPanel
            suggestion={suggestion}
            originalText={suggestionRange?.text || null}
            loading={suggestionLoading}
            error={null}
            onAccept={acceptSuggestion}
            onReject={() => { setSuggestion(null); setSuggestionRange(null); }}
          />
          <aside className="editor-side-card rounded-2xl bg-white/75 p-4 text-sm shadow-sm ring-1 ring-slate-900/[0.04] backdrop-blur dark:bg-[#151821]/78 dark:ring-white/[0.06]">
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">Document info</p>
            <dl className="mt-3 grid gap-2 text-xs">
              <div className="flex justify-between gap-3"><dt className="text-slate-500 dark:text-slate-400">Type</dt><dd className="font-semibold text-slate-800 dark:text-slate-200">{payload.document_type.replace(/_/g, " ")}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-slate-500 dark:text-slate-400">Version</dt><dd className="font-semibold text-slate-800 dark:text-slate-200">v{documentRecord?.version || 1}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-slate-500 dark:text-slate-400">Case</dt><dd className="font-semibold text-slate-800 dark:text-slate-200">{payload.case_id ? `Case #${payload.case_id}` : "Workspace"}</dd></div>
            </dl>
          </aside>
        </div>
        ) : null}
      </div>
      {sendEmailOpen ? (
        <SendEmailModal
          defaultSubject={title}
          onClose={() => setSendEmailOpen(false)}
          onSend={(payloadToSend) => void sendEmail(payloadToSend)}
        />
      ) : null}
    </aside>
  );
}
