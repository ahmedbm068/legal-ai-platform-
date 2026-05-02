interface ExportMenuProps {
  disabled: boolean;
  onDocx: () => void;
  onPdf: () => void;
}

export default function ExportMenu({ disabled, onDocx, onPdf }: ExportMenuProps) {
  return (
    <div className="flex items-center gap-1">
      <button className="premium-editor-ghost-button" disabled={disabled} onClick={onDocx} type="button">DOCX</button>
      <button className="premium-editor-ghost-button" disabled={disabled} onClick={onPdf} type="button">PDF</button>
    </div>
  );
}
