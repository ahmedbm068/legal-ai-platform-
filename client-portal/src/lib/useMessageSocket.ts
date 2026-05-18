import { useEffect, useRef, useState } from "react";

export type WsStatus = "connecting" | "open" | "closed";

type ServerEvent =
    | { type: "message"; message: Record<string, unknown> }
    | { type: "typing"; role: string }
    | { type: "pong" };

interface Options {
    /** Portal JWT (query-param auth — browsers can't set WS headers). */
    token: string | null;
    /** Active case id, or null to stay disconnected. */
    caseId: number | null;
    onMessage: (raw: Record<string, unknown>) => void;
    onTyping: (role: string) => void;
}

function wsUrl(caseId: number, token: string): string {
    const configured = import.meta.env.VITE_API_BASE_URL?.trim();
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";

    let base: string;
    if (configured) {
        base = configured.replace(/^http/, "ws");
    } else if (import.meta.env.DEV) {
        base = `${proto}//${window.location.host}/api`;
    } else {
        base = `${proto}//${window.location.hostname}:8000`;
    }
    return `${base}/ws/portal/messages/${caseId}?token=${encodeURIComponent(token)}`;
}

/** Live message socket (portal side) with auto-reconnect and heartbeat.
 *  Consumers fall back to polling when status !== "open". */
export function useMessageSocket({ token, caseId, onMessage, onTyping }: Options) {
    const [status, setStatus] = useState<WsStatus>("closed");
    const socketRef = useRef<WebSocket | null>(null);
    const retryRef = useRef(0);
    const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);
    const closedByUs = useRef(false);

    const cbRef = useRef({ onMessage, onTyping });
    cbRef.current = { onMessage, onTyping };

    useEffect(() => {
        if (!token || caseId == null) {
            setStatus("closed");
            return;
        }
        closedByUs.current = false;

        const cleanupTimers = () => {
            if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
            if (pingTimer.current) clearInterval(pingTimer.current);
        };

        const connect = () => {
            setStatus("connecting");
            let ws: WebSocket;
            try {
                ws = new WebSocket(wsUrl(caseId, token));
            } catch {
                scheduleReconnect();
                return;
            }
            socketRef.current = ws;

            ws.onopen = () => {
                retryRef.current = 0;
                setStatus("open");
                if (pingTimer.current) clearInterval(pingTimer.current);
                pingTimer.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ type: "ping" }));
                    }
                }, 25000);
            };

            ws.onmessage = (ev) => {
                let data: ServerEvent;
                try {
                    data = JSON.parse(ev.data);
                } catch {
                    return;
                }
                if (data.type === "message") cbRef.current.onMessage(data.message);
                else if (data.type === "typing") cbRef.current.onTyping(data.role);
            };

            ws.onclose = () => {
                setStatus("closed");
                if (pingTimer.current) clearInterval(pingTimer.current);
                if (!closedByUs.current) scheduleReconnect();
            };

            ws.onerror = () => {
                ws.close();
            };
        };

        const scheduleReconnect = () => {
            retryRef.current += 1;
            const delay = Math.min(1000 * 2 ** retryRef.current, 15000);
            reconnectTimer.current = setTimeout(connect, delay);
        };

        connect();

        return () => {
            closedByUs.current = true;
            cleanupTimers();
            socketRef.current?.close();
            socketRef.current = null;
        };
    }, [token, caseId]);

    const sendTyping = () => {
        const ws = socketRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "typing" }));
        }
    };

    return { status, sendTyping };
}
