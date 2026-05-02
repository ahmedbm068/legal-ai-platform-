import type { DraftDocument } from "../types";

interface DraftDocumentListProps {
  documents: DraftDocument[];
  onOpen: (document: DraftDocument) => void;
}

export default function DraftDocumentList({ documents, onOpen }: DraftDocumentListProps) {
  return (
    <aside className="draft-document-list">
      <p className="shell-page-kicker">Drafts</p>
      {documents.length ? documents.map((document) => (
        <button key={document.id} onClick={() => onOpen(document)} type="button">
          <strong>{document.title}</strong>
          <span>{document.document_type} | v{document.version}</span>
        </button>
      )) : <p className="editor-muted">No saved drafts yet.</p>}
    </aside>
  );
}
