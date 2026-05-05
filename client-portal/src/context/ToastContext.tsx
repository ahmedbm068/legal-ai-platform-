import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
} from "react";

export type ToastKind = "success" | "error" | "info" | "warning";

export interface Toast {
    id: string;
    kind: ToastKind;
    message: string;
    duration: number;
}

interface ToastContextValue {
    toasts: Toast[];
    /** duration=0 creates a persistent toast that must be dismissed manually */
    addToast: (message: string, kind?: ToastKind, duration?: number) => void;
    removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_DURATION_MS = 4000;
const MAX_TOASTS = 5;

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);
    const timers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

    const removeToast = useCallback((id: string) => {
        clearTimeout(timers.current.get(id));
        timers.current.delete(id);
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const addToast = useCallback(
        (message: string, kind: ToastKind = "info", duration: number = DEFAULT_DURATION_MS) => {
            const id = crypto.randomUUID();
            setToasts((prev) => {
                // Deduplicate: ignore if the same message+kind is already visible
                if (prev.some((t) => t.message === message && t.kind === kind)) {
                    return prev;
                }
                const next = [...prev, { id, kind, message, duration }];
                return next.length > MAX_TOASTS ? next.slice(-MAX_TOASTS) : next;
            });
            if (duration > 0) {
                const timer = setTimeout(() => removeToast(id), duration);
                timers.current.set(id, timer);
            }
        },
        [removeToast],
    );

    // Prevent timer leaks when the provider unmounts
    useEffect(() => {
        const timerMap = timers.current;
        return () => {
            timerMap.forEach((t) => clearTimeout(t));
            timerMap.clear();
        };
    }, []);

    return (
        <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
            {children}
        </ToastContext.Provider>
    );
}

export function useToast(): Pick<ToastContextValue, "addToast"> {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error("useToast must be used inside ToastProvider");
    return { addToast: ctx.addToast };
}

export function useToastInternal(): ToastContextValue {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error("useToastInternal must be used inside ToastProvider");
    return ctx;
}
