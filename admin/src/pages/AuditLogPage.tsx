import { useEffect, useMemo, useState } from "react";
import {
    apiGetCopilotTrace,
    apiListAuditLog,
    apiListCopilotTraces,
    type AuditLogEntry,
    type CopilotTrace,
} from "../lib/api";

type Tab = "http" | "trace";

function methodBadge(method: string) {
    const map: Record<string, string> = {
        GET: "badge badge-gray",
        POST: "badge badge-green",
        PUT: "badge badge-blue",
        PATCH: "badge badge-yellow",
        DELETE: "badge badge-red",
    };
    return map[method] ?? "badge badge-gray";
}

function statusBadge(code: number) {
    if (code < 300) return "badge badge-green";
    if (code < 400) return "badge badge-blue";
    if (code < 500) return "badge badge-yellow";
    return "badge badge-red";
}

function verdictBadge(verdict: string | null) {
    switch (verdict) {
        case "verified":
            return "badge badge-green";
        case "partial":
            return "badge badge-yellow";
        case "refused":
            return "badge badge-blue";
        case "error":
            return "badge badge-red";
        case "unverified":
        default:
            return "badge badge-gray";
    }
}

function HttpAuditTab() {
    const [entries, setEntries] = useState<AuditLogEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        apiListAuditLog(200)
            .then(setEntries)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    if (loading) return <p className="text-slate-400 text-sm">Loading…</p>;
    if (error)
        return (
            <p className="text-yellow-400 text-sm bg-yellow-900/20 border border-yellow-800 rounded-lg px-3 py-2">
                {error} — audit log endpoint may not be deployed yet.
            </p>
        );

    return (
        <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
            <table className="admin-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Method</th>
                        <th>Path</th>
                        <th>Status</th>
                        <th>Duration</th>
                        <th>User</th>
                        <th>Tenant</th>
                    </tr>
                </thead>
                <tbody>
                    {entries.length === 0 ? (
                        <tr>
                            <td colSpan={7} className="text-center text-slate-500 py-8">
                                No entries yet
                            </td>
                        </tr>
                    ) : (
                        entries.map((e) => (
                            <tr key={e.id}>
                                <td className="text-slate-500 font-mono text-xs whitespace-nowrap">
                                    {new Date(e.created_at).toLocaleTimeString()}
                                </td>
                                <td>
                                    <span className={methodBadge(e.method)}>{e.method}</span>
                                </td>
                                <td className="font-mono text-xs text-slate-300 max-w-xs truncate">
                                    {e.path}
                                </td>
                                <td>
                                    <span className={statusBadge(e.status_code)}>{e.status_code}</span>
                                </td>
                                <td className="text-slate-500 text-xs">{e.duration_ms.toFixed(0)}ms</td>
                                <td className="text-slate-500 text-xs">
                                    {e.user_id ? `#${e.user_id}` : "—"}
                                </td>
                                <td className="text-slate-500 text-xs">#{e.tenant_id}</td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}

function TraceDetail({ callId, onClose }: { callId: string; onClose: () => void }) {
    const [trace, setTrace] = useState<CopilotTrace | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        apiGetCopilotTrace(callId)
            .then(setTrace)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [callId]);

    return (
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-4 mb-4">
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-white font-semibold text-sm">
                    Reasoning trail · <span className="font-mono text-xs">{callId}</span>
                </h3>
                <button className="text-slate-400 hover:text-white text-xs" onClick={onClose}>
                    Close ✕
                </button>
            </div>
            {loading && <p className="text-slate-400 text-sm">Loading…</p>}
            {error && <p className="text-yellow-400 text-sm">{error}</p>}
            {trace && (
                <div className="space-y-3 text-sm">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                        <div>
                            <p className="text-slate-500 uppercase tracking-wide mb-0.5">Intent</p>
                            <p className="text-slate-200 font-mono">{trace.intent ?? "—"}</p>
                        </div>
                        <div>
                            <p className="text-slate-500 uppercase tracking-wide mb-0.5">Big Agent</p>
                            <p className="text-slate-200 font-mono">{trace.big_agent ?? "—"}</p>
                        </div>
                        <div>
                            <p className="text-slate-500 uppercase tracking-wide mb-0.5">Verdict</p>
                            <p>
                                <span className={verdictBadge(trace.verdict)}>
                                    {trace.verdict ?? "—"}
                                </span>
                            </p>
                        </div>
                        <div>
                            <p className="text-slate-500 uppercase tracking-wide mb-0.5">Duration</p>
                            <p className="text-slate-200">
                                {trace.duration_ms != null ? `${trace.duration_ms}ms` : "—"}
                            </p>
                        </div>
                    </div>

                    <div>
                        <p className="text-slate-500 uppercase tracking-wide text-[10px] mb-1">
                            Mini-agents used ({trace.mini_agents_used.length})
                        </p>
                        <div className="flex flex-wrap gap-1">
                            {trace.mini_agents_used.length === 0 ? (
                                <span className="text-slate-600 italic text-xs">none recorded</span>
                            ) : (
                                trace.mini_agents_used.map((a) => (
                                    <span
                                        key={a}
                                        className="bg-slate-800 border border-slate-700 rounded px-2 py-0.5 text-xs font-mono text-slate-300"
                                    >
                                        {a}
                                    </span>
                                ))
                            )}
                        </div>
                    </div>

                    <div>
                        <p className="text-slate-500 uppercase tracking-wide text-[10px] mb-1">
                            Pipeline stages ({trace.stages.length})
                        </p>
                        <ol className="space-y-1">
                            {trace.stages.map((s, idx) => (
                                <li key={`${s.name}-${idx}`} className="flex items-start gap-2 text-xs">
                                    <span className="text-slate-600 font-mono w-6 shrink-0">
                                        {String(idx + 1).padStart(2, "0")}
                                    </span>
                                    <span className="text-slate-300 font-mono w-48 shrink-0">
                                        {s.name}
                                    </span>
                                    <span
                                        className={
                                            s.status === "success"
                                                ? "badge badge-green"
                                                : s.status === "skipped"
                                                    ? "badge badge-gray"
                                                    : "badge badge-yellow"
                                        }
                                    >
                                        {s.status}
                                    </span>
                                    <span className="text-slate-500 truncate">{s.detail}</span>
                                </li>
                            ))}
                        </ol>
                    </div>
                </div>
            )}
        </div>
    );
}

function CopilotTraceTab() {
    const [traces, setTraces] = useState<CopilotTrace[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [verdictFilter, setVerdictFilter] = useState<string>("");
    const [selected, setSelected] = useState<string | null>(null);

    useEffect(() => {
        setLoading(true);
        setError(null);
        apiListCopilotTraces({ limit: 100, verdict: verdictFilter || undefined })
            .then((data) => setTraces(data.traces))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [verdictFilter]);

    const verdictCounts = useMemo(() => {
        const acc: Record<string, number> = {};
        for (const t of traces) {
            const v = t.verdict ?? "unknown";
            acc[v] = (acc[v] ?? 0) + 1;
        }
        return acc;
    }, [traces]);

    return (
        <div>
            {selected && <TraceDetail callId={selected} onClose={() => setSelected(null)} />}

            <div className="flex items-center gap-2 mb-3 text-xs">
                <span className="text-slate-500">Verdict:</span>
                {["", "verified", "partial", "unverified", "refused", "error"].map((v) => (
                    <button
                        key={v || "all"}
                        onClick={() => setVerdictFilter(v)}
                        className={`px-2 py-0.5 rounded ${verdictFilter === v
                                ? "bg-slate-700 text-white"
                                : "bg-slate-900 text-slate-400 hover:text-white border border-slate-800"
                            }`}
                    >
                        {v || "all"}
                        {v && verdictCounts[v] != null && (
                            <span className="text-slate-500 ml-1">({verdictCounts[v]})</span>
                        )}
                    </button>
                ))}
            </div>

            {loading && <p className="text-slate-400 text-sm">Loading…</p>}
            {error && (
                <p className="text-yellow-400 text-sm bg-yellow-900/20 border border-yellow-800 rounded-lg px-3 py-2">
                    {error}
                </p>
            )}

            {!loading && !error && (
                <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                    <table className="admin-table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Call ID</th>
                                <th>Intent</th>
                                <th>Big Agent</th>
                                <th>Mini agents</th>
                                <th>Verdict</th>
                                <th>Duration</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {traces.length === 0 ? (
                                <tr>
                                    <td colSpan={8} className="text-center text-slate-500 py-8">
                                        No traces yet
                                    </td>
                                </tr>
                            ) : (
                                traces.map((t) => (
                                    <tr key={t.id}>
                                        <td className="text-slate-500 font-mono text-xs whitespace-nowrap">
                                            {t.created_at
                                                ? new Date(t.created_at).toLocaleTimeString()
                                                : "—"}
                                        </td>
                                        <td className="font-mono text-xs text-slate-400 max-w-[140px] truncate">
                                            {t.call_id}
                                        </td>
                                        <td className="font-mono text-xs text-slate-300">
                                            {t.intent ?? "—"}
                                        </td>
                                        <td className="font-mono text-xs text-slate-200">
                                            {t.big_agent ?? "—"}
                                        </td>
                                        <td className="text-slate-400 text-xs">
                                            {t.mini_agents_used.length === 0
                                                ? "—"
                                                : `${t.mini_agents_used.length} (${t.mini_agents_used
                                                    .slice(0, 2)
                                                    .join(", ")}${t.mini_agents_used.length > 2 ? "…" : ""
                                                })`}
                                        </td>
                                        <td>
                                            <span className={verdictBadge(t.verdict)}>
                                                {t.verdict ?? "—"}
                                            </span>
                                        </td>
                                        <td className="text-slate-500 text-xs">
                                            {t.duration_ms != null ? `${t.duration_ms}ms` : "—"}
                                        </td>
                                        <td>
                                            <button
                                                className="text-emerald-400 hover:text-emerald-300 text-xs"
                                                onClick={() => setSelected(t.call_id)}
                                            >
                                                View →
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

export default function AuditLogPage() {
    const [tab, setTab] = useState<Tab>("http");

    return (
        <div>
            <div className="mb-6">
                <h1 className="text-lg font-semibold text-white">Audit & Trace</h1>
                <p className="text-slate-400 text-sm mt-0.5">
                    HTTP request log and copilot reasoning trail
                </p>
            </div>

            <div className="flex items-center gap-1 mb-4 border-b border-slate-800">
                {([
                    { id: "http" as const, label: "HTTP Audit" },
                    { id: "trace" as const, label: "Copilot Trace" },
                ]).map((t) => (
                    <button
                        key={t.id}
                        onClick={() => setTab(t.id)}
                        className={`px-3 py-2 text-sm border-b-2 -mb-px transition ${tab === t.id
                                ? "border-emerald-500 text-white"
                                : "border-transparent text-slate-400 hover:text-white"
                            }`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {tab === "http" && <HttpAuditTab />}
            {tab === "trace" && <CopilotTraceTab />}
        </div>
    );
}
