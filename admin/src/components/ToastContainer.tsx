import { useToastInternal } from "../context/ToastContext";
import type { Toast } from "../context/ToastContext";

const KIND_CLASSES: Record<Toast["kind"], { wrapper: string; icon: string; label: string }> = {
    success: {
        wrapper: "bg-emerald-950 border-emerald-700 text-emerald-100",
        icon: "bg-emerald-900 text-emerald-400",
        label: "✓",
    },
    error: {
        wrapper: "bg-red-950 border-red-700 text-red-100",
        icon: "bg-red-900 text-red-400",
        label: "✕",
    },
    warning: {
        wrapper: "bg-amber-950 border-amber-700 text-amber-100",
        icon: "bg-amber-900 text-amber-400",
        label: "!",
    },
    info: {
        wrapper: "bg-slate-800 border-slate-600 text-slate-100",
        icon: "bg-slate-700 text-slate-300",
        label: "i",
    },
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
        <div
            className="fixed bottom-5 right-5 z-[9000] flex flex-col gap-2 max-w-sm w-full pointer-events-none"
            aria-label="Notifications"
        >
            {toasts.map((t) => {
                const s = KIND_CLASSES[t.kind];
                return (
                    <div
                        key={t.id}
                        role={KIND_ROLE[t.kind]}
                        aria-live={t.kind === "error" || t.kind === "warning" ? "assertive" : "polite"}
                        aria-atomic="true"
                        className={`pointer-events-auto flex items-start gap-3 border rounded-xl px-4 py-3 text-left text-sm shadow-2xl w-full animate-toast-in ${s.wrapper}`}
                    >
                        <span
                            className={`flex-none w-5 h-5 rounded-full grid place-items-center text-xs font-black ${s.icon}`}
                            aria-hidden="true"
                        >
                            {s.label}
                        </span>
                        <span className="flex-1 leading-snug break-words">{t.message}</span>
                        <button
                            type="button"
                            onClick={() => removeToast(t.id)}
                            className="flex-none opacity-50 hover:opacity-100 text-base leading-none ml-1"
                            aria-label={`Dismiss: ${t.message}`}
                        >
                            ×
                        </button>
                    </div>
                );
            })}
        </div>
    );
}
