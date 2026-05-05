import { useToastInternal } from "../context/ToastContext";
import type { Toast } from "../context/ToastContext";

const KIND_ICON: Record<Toast["kind"], string> = {
    success: "✓",
    error: "✕",
    info: "i",
    warning: "!",
};

const KIND_ROLE: Record<Toast["kind"], string> = {
    success: "status",
    error: "alert",
    warning: "alert",
    info: "status",
};

export default function ToastContainer() {
    const { toasts, removeToast } = useToastInternal();

    if (toasts.length === 0) return null;

    return (
        <div className="portal-toast-container" aria-label="Notifications">
            {toasts.map((t) => (
                <div
                    key={t.id}
                    className={`portal-toast portal-toast-${t.kind}`}
                    role={KIND_ROLE[t.kind]}
                    aria-live={t.kind === "error" || t.kind === "warning" ? "assertive" : "polite"}
                    aria-atomic="true"
                >
                    <span className="portal-toast-icon" aria-hidden="true">{KIND_ICON[t.kind]}</span>
                    <span className="portal-toast-message">{t.message}</span>
                    <button
                        type="button"
                        className="portal-toast-close"
                        onClick={() => removeToast(t.id)}
                        aria-label={`Dismiss: ${t.message}`}
                    >
                        ×
                    </button>
                </div>
            ))}
        </div>
    );
}
