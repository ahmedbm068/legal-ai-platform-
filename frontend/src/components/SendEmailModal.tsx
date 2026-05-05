import { useState } from "react";

interface SendEmailModalProps {
  defaultSubject: string;
  onClose: () => void;
  onSend: (payload: { to: string; subject: string; cc: string[] }) => void;
}

export default function SendEmailModal({ defaultSubject, onClose, onSend }: SendEmailModalProps) {
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState(defaultSubject);

  return (
    <div className="calendar-modal-backdrop" role="presentation">
      <div className="calendar-event-modal send-email-modal" role="dialog" aria-modal="true" aria-label="Send email confirmation">
        <div className="calendar-modal-head">
          <div>
            <p className="shell-page-kicker">Confirm email</p>
            <h3>Send after lawyer review</h3>
          </div>
          <button onClick={onClose} type="button" aria-label="Close">×</button>
        </div>
        <label className="editor-field">
          <span>To</span>
          <input value={to} onChange={(event) => setTo(event.target.value)} placeholder="client@example.com" />
        </label>
        <label className="editor-field">
          <span>CC</span>
          <input value={cc} onChange={(event) => setCc(event.target.value)} placeholder="optional@example.com" />
        </label>
        <label className="editor-field">
          <span>Subject</span>
          <input value={subject} onChange={(event) => setSubject(event.target.value)} />
        </label>
        <div className="calendar-modal-actions">
          <button className="shell-secondary-button" onClick={onClose} type="button">Cancel</button>
          <button
            className="shell-primary-button"
            disabled={!to.trim() || !to.includes("@") || !subject.trim()}
            onClick={() => onSend({ to: to.trim(), subject: subject.trim(), cc: cc.split(",").map((item) => item.trim()).filter(Boolean) })}
            type="button"
          >
            Confirm send
          </button>
        </div>
      </div>
    </div>
  );
}
