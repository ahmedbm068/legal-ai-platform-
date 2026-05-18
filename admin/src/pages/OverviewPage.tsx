import { useCallback, useEffect, useMemo, useState } from "react";
import {
    apiListAuditLog,
    apiSystemHealth,
    type AuditLogEntry,
    type SystemHealth,
} from "../lib/api";
import { useToast } from "../context/ToastContext";
import { Button, PageHeader, Panel, StateMsg } from "../components/ui";

/* ── helpers ─────────────────────────────────────────────────────────────── */

function relativeTime(iso: string): string {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} hr${hrs === 1 ? "" : "s"} ago`;
    const days = Math.floor(hrs / 24);
    return days === 1 ? "Yesterday" : `${days} days ago`;
}

function timeOnly(iso: string): string {
    const d = new Date(iso);
    return new Date().toDateString() === d.toDateString()
        ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : d.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
}

/** Human-readable action from HTTP method + path — consistent with Audit Log. */
function deriveAction(method: string, path: string): { label: string; danger: boolean } {
    const m = method.toUpperCase();
    const seg =
        path.split("?")[0].split("/").filter((s) => s && s !== "api")[0] ?? "resource";
    const noun = seg
        .replace(/[-_]/g, " ")
        .replace(/s$/, "")
        .replace(/\b\w/g, (c) => c.toUpperCase());
    if (m === "POST") return { label: `${noun} Created`, danger: false };
    if (m === "PUT" || m === "PATCH") return { label: `${noun} Updated`, danger: false };
    if (m === "DELETE") return { label: `${noun} Deleted`, danger: true };
    return { label: `${noun} Accessed`, danger: false };
}

function statusBadge(code: number): string {
    if (code < 400) return "badge badge-green";
    if (code < 500) return "badge badge-yellow";
    return "badge badge-red";
}

/* ── KPI tile ────────────────────────────────────────────────────────────── */

interface KpiProps {
    label: string;
    value: string;
    icon: string;
    foot: string;
    tone?: "neutral" | "good" | "warn" | "error";
    loading: boolean;
}

function Kpi({ label, value, icon, foot, tone = "neutral", loading }: KpiProps) {
    const footTone =
        tone === "error"
            ? "text-error"
            : tone === "warn"
                ? "text-warn-fg"
                : tone === "good"
                    ? "text-on-surface"
                    : "text-secondary";
    return (
        <div className="bg-surface-container-lowest border border-outline-variant p-md rounded flex flex-col gap-sm min-h-[116px]">
            <div className="flex justify-between items-start">
                <span className="font-label-caps text-label-caps text-secondary uppercase tracking-wider">
                    {label}
                </span>
                <span className="material-symbols-outlined text-secondary text-[20px]">
                    {icon}
                </span>
            </div>
            {loading ? (
                <div className="h-8 w-20 rounded bg-surface-container animate-pulse" />
            ) : (
                <div className="font-page-header text-page-header text-primary">{value}</div>
            )}
            <div className={`flex items-center gap-xs mt-auto ${footTone}`}>
                <span className="font-body-sm text-body-sm">{foot}</span>
            </div>
        </div>
    );
}

/* ── page ────────────────────────────────────────────────────────────────── */

export default function OverviewPage() {
    const { addToast } = useToast();
    const [health, setHealth] = useState<SystemHealth | null>(null);
    const [healthErr, setHealthErr] = useState<string | null>(null);
    const [audit, setAudit] = useState<AuditLogEntry[]>([]);
    const [auditErr, setAuditErr] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

    const fetchAll = useCallback(async (isRefresh: boolean) => {
        if (isRefresh) setRefreshing(true);
        const [h, a] = await Promise.allSettled([
            apiSystemHealth(),
            apiListAuditLog(120),
        ]);
        if (h.status === "fulfilled") {
            setHealth(h.value);
            setHealthErr(null);
        } else setHealthErr(h.reason?.message ?? "Health unavailable");
        if (a.status === "fulfilled") {
            setAudit(a.value);
            setAuditErr(null);
        } else setAuditErr(a.reason?.message ?? "Audit log unavailable");
        setLoading(false);
        setRefreshing(false);
        setUpdatedAt(new Date());
    }, []);

    useEffect(() => {
        fetchAll(false);
    }, [fetchAll]);

    // Light auto-refresh so the status board stays current (every 60s).
    useEffect(() => {
        const id = setInterval(() => fetchAll(true), 60_000);
        return () => clearInterval(id);
    }, [fetchAll]);

    const recent = useMemo(() => audit.slice(0, 14), [audit]);

    const needsAttention = useMemo(
        () =>
            audit
                .filter((e) => e.status_code >= 500 || e.duration_ms > 3000)
                .slice(0, 8)
                .map((e) => {
                    const act = deriveAction(e.method, e.path);
                    const failed = e.status_code >= 500;
                    return {
                        id: e.id,
                        tag: failed ? "Failed Request" : "Slow Request",
                        tagError: failed,
                        title: act.label,
                        detail: failed
                            ? `HTTP ${e.status_code} · tenant #${e.tenant_id ?? "—"}`
                            : `${e.duration_ms.toFixed(0)}ms · tenant #${e.tenant_id ?? "—"}`,
                        when: relativeTime(e.created_at),
                    };
                }),
        [audit]
    );

    const errorRatePct =
        health?.error_rate_24h != null ? health.error_rate_24h * 100 : null;

    const exportCsv = () => {
        if (recent.length === 0) {
            addToast("No recent activity to export.", "info");
            return;
        }
        const esc = (v: unknown) => {
            const s = String(v ?? "");
            return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        };
        const header = ["Action", "Method", "Path", "Status", "Duration_ms", "Tenant", "Timestamp"];
        const lines = audit.slice(0, 120).map((e) =>
            [
                deriveAction(e.method, e.path).label,
                e.method,
                e.path,
                e.status_code,
                e.duration_ms.toFixed(1),
                e.tenant_id ?? "",
                e.created_at,
            ]
                .map(esc)
                .join(",")
        );
        const blob = new Blob([[header.join(","), ...lines].join("\n")], {
            type: "text/csv;charset=utf-8;",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `overview-activity-${new Date().toISOString().slice(0, 10)}.csv`;
        link.click();
        URL.revokeObjectURL(url);
        addToast(`Exported ${Math.min(audit.length, 120)} entries.`, "success");
    };

    return (
        <div>
            <PageHeader
                title="Overview"
                subtitle="System status and critical metrics across all tenants."
                actions={
                    <div className="flex items-center gap-sm">
                        {updatedAt && (
                            <span className="font-body-sm text-body-sm text-secondary hidden sm:inline">
                                Updated {timeOnly(updatedAt.toISOString())}
                            </span>
                        )}
                        <button
                            onClick={() => fetchAll(true)}
                            disabled={refreshing}
                            className="p-sm text-secondary hover:text-primary rounded-full hover:bg-surface-container transition-colors disabled:opacity-50"
                            aria-label="Refresh"
                            title="Refresh"
                        >
                            <span
                                className={`material-symbols-outlined text-[20px] ${refreshing ? "animate-spin" : ""
                                    }`}
                            >
                                refresh
                            </span>
                        </button>
                        <Button icon="download" onClick={exportCsv}>
                            Export CSV
                        </Button>
                    </div>
                }
            />

            {/* KPI tiles — all values are real backend metrics */}
            <section className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-md mb-xl">
                <Kpi
                    loading={loading}
                    label="Total Users"
                    value={health ? health.total_users.toLocaleString() : "—"}
                    icon="group"
                    foot="All tenants"
                />
                <Kpi
                    loading={loading}
                    label="Total Cases"
                    value={health ? health.total_cases.toLocaleString() : "—"}
                    icon="folder_shared"
                    foot="Open + closed"
                />
                <Kpi
                    loading={loading}
                    label="Documents"
                    value={health ? health.total_documents.toLocaleString() : "—"}
                    icon="description"
                    foot="Active files"
                />
                <Kpi
                    loading={loading}
                    label="Active Tenants"
                    value={
                        health?.active_tenants_24h != null
                            ? health.active_tenants_24h.toLocaleString()
                            : "—"
                    }
                    icon="domain"
                    foot="Last 24h"
                />
                <Kpi
                    loading={loading}
                    label="Error Rate"
                    value={errorRatePct != null ? `${errorRatePct.toFixed(1)}%` : "—"}
                    icon="error"
                    foot={
                        health?.requests_24h != null
                            ? `${health.requests_24h.toLocaleString()} req / 24h`
                            : "Last 24h"
                    }
                    tone={
                        errorRatePct == null
                            ? "neutral"
                            : errorRatePct >= 5
                                ? "error"
                                : errorRatePct >= 1
                                    ? "warn"
                                    : "good"
                    }
                />
                <Kpi
                    loading={loading}
                    label="p95 Latency"
                    value={
                        health?.p95_latency_ms != null
                            ? `${Math.round(health.p95_latency_ms)}ms`
                            : "—"
                    }
                    icon="speed"
                    foot="Last 24h"
                    tone={
                        health?.p95_latency_ms == null
                            ? "neutral"
                            : health.p95_latency_ms >= 3000
                                ? "error"
                                : health.p95_latency_ms >= 1000
                                    ? "warn"
                                    : "good"
                    }
                />
            </section>

            {healthErr && (
                <div className="mb-md">
                    <StateMsg kind="error">
                        {healthErr} — health endpoint may not be deployed yet.
                    </StateMsg>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-md">
                {/* Recent Activity */}
                <Panel
                    title="Recent Activity"
                    className="lg:col-span-2 min-h-[420px] max-h-[560px]"
                >
                    <div className="flex-grow overflow-auto">
                        {loading ? (
                            <div className="p-md">
                                <StateMsg>Loading activity…</StateMsg>
                            </div>
                        ) : auditErr ? (
                            <div className="p-md">
                                <StateMsg kind="error">{auditErr}</StateMsg>
                            </div>
                        ) : recent.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-full text-center px-md py-xl">
                                <span className="material-symbols-outlined text-[40px] text-secondary mb-sm">
                                    inbox
                                </span>
                                <p className="font-body-sm text-body-sm text-secondary">
                                    No recent activity recorded.
                                </p>
                            </div>
                        ) : (
                            <table className="admin-table">
                                <thead className="bg-surface-container-lowest sticky top-0 z-10">
                                    <tr>
                                        <th>Action</th>
                                        <th>Status</th>
                                        <th>Tenant</th>
                                        <th className="text-right">Timestamp</th>
                                    </tr>
                                </thead>
                                <tbody className="font-table-data text-table-data">
                                    {recent.map((e) => {
                                        const act = deriveAction(e.method, e.path);
                                        return (
                                            <tr key={e.id}>
                                                <td>
                                                    <span
                                                        className={
                                                            act.danger
                                                                ? "text-error font-semibold inline-flex items-center gap-xs"
                                                                : "text-on-surface"
                                                        }
                                                    >
                                                        {act.danger && (
                                                            <span className="material-symbols-outlined text-[15px]">
                                                                warning
                                                            </span>
                                                        )}
                                                        {act.label}
                                                    </span>
                                                </td>
                                                <td>
                                                    <span className={statusBadge(e.status_code)}>
                                                        {e.status_code}
                                                    </span>
                                                </td>
                                                <td className="text-secondary">
                                                    {e.tenant_id != null ? `#${e.tenant_id}` : "—"}
                                                </td>
                                                <td className="text-right text-secondary">
                                                    {timeOnly(e.created_at)}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>
                </Panel>

                {/* Needs Attention */}
                <Panel
                    title="Needs Attention"
                    className="min-h-[420px] max-h-[560px]"
                    icon={
                        <span className="material-symbols-outlined text-error text-[20px]">
                            error
                        </span>
                    }
                >
                    <div className="flex-grow overflow-auto p-sm flex flex-col gap-sm">
                        {loading ? (
                            <div className="p-sm">
                                <StateMsg>Scanning…</StateMsg>
                            </div>
                        ) : needsAttention.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-full text-center px-md">
                                <span className="material-symbols-outlined text-[40px] text-secondary mb-sm">
                                    task_alt
                                </span>
                                <p className="font-body-sm text-body-sm text-secondary">
                                    Nothing needs attention. All requests healthy.
                                </p>
                            </div>
                        ) : (
                            needsAttention.map((item) => (
                                <div
                                    key={item.id}
                                    className="p-sm border border-outline-variant rounded bg-surface hover:bg-surface-container transition-colors"
                                >
                                    <div className="flex justify-between items-start mb-xs">
                                        <span
                                            className={`font-label-caps text-label-caps px-2 py-0.5 rounded uppercase ${item.tagError
                                                ? "bg-err-bg text-on-error-container"
                                                : "bg-warn-bg text-warn-fg"
                                                }`}
                                        >
                                            {item.tag}
                                        </span>
                                        <span className="font-body-sm text-body-sm text-secondary">
                                            {item.when}
                                        </span>
                                    </div>
                                    <div className="font-body-sm text-body-sm text-on-surface font-semibold truncate">
                                        {item.title}
                                    </div>
                                    <div className="font-body-sm text-body-sm text-secondary truncate">
                                        {item.detail}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </Panel>
            </div>
        </div>
    );
}
