import { useEffect, useMemo, useState } from "react";
import {
    apiListAuditLog,
    apiListUsers,
    type AuditLogEntry,
    type AdminUser,
} from "../lib/api";
import { useToast } from "../context/ToastContext";
import { PageHeader } from "../components/ui";

const PAGE_SIZE = 15;

type StatusClass = "" | "success" | "client_error" | "server_error";

interface DerivedAction {
    label: string;
    destructive: boolean;
}

/** Turn an HTTP method + path into a human-readable action label. */
function deriveAction(method: string, path: string): DerivedAction {
    const m = method.toUpperCase();
    // First meaningful path segment, e.g. /api/cases/42 -> "cases"
    const seg =
        path
            .split("?")[0]
            .split("/")
            .filter((s) => s && s !== "api")[0] ?? "resource";
    const noun = seg
        .replace(/[-_]/g, " ")
        .replace(/s$/, "")
        .replace(/\b\w/g, (c) => c.toUpperCase());

    switch (m) {
        case "POST":
            return { label: `${noun} Created`, destructive: false };
        case "PUT":
        case "PATCH":
            return { label: `${noun} Updated`, destructive: false };
        case "DELETE":
            return { label: `${noun} Deleted`, destructive: true };
        default:
            return { label: `${noun} ${m}`, destructive: false };
    }
}

function statusClassOf(code: number): StatusClass {
    if (code >= 500) return "server_error";
    if (code >= 400) return "client_error";
    return "success";
}

function monogram(name: string): string {
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function fmtTimestamp(iso: string): string {
    const d = new Date(iso);
    const date = d.toLocaleDateString("en-US", {
        month: "short",
        day: "2-digit",
        year: "numeric",
    });
    const time = d.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
    });
    return `${date} · ${time}`;
}

interface Row {
    entry: AuditLogEntry;
    actorName: string;
    actorEmail: string | null;
    isSystem: boolean;
    action: DerivedAction;
}

function DetailDrawer({ row, onClose }: { row: Row; onClose: () => void }) {
    const { entry } = row;
    const meta = {
        request_id: `req_${entry.id}`,
        method: entry.method,
        path: entry.path,
        status_code: entry.status_code,
        duration_ms: Number(entry.duration_ms.toFixed(1)),
        actor: row.isSystem
            ? "system"
            : `${row.actorName}${row.actorEmail ? ` <${row.actorEmail}>` : ""}`,
        user_id: entry.user_id,
        tenant_id: entry.tenant_id,
        created_at: entry.created_at,
    };
    return (
        <div
            className="fixed inset-0 z-[60] bg-inverse-surface/30 flex justify-end"
            onMouseDown={onClose}
        >
            <div
                className="h-full w-full max-w-[420px] bg-surface-container-lowest border-l border-outline-variant shadow-2xl flex flex-col"
                onMouseDown={(e) => e.stopPropagation()}
            >
                <div className="h-topbar-height flex items-center justify-between px-lg border-b border-outline-variant shrink-0">
                    <h2 className="font-section-header text-section-header text-on-surface">
                        Log Entry Details
                    </h2>
                    <button
                        onClick={onClose}
                        className="text-secondary hover:text-primary transition-colors"
                        aria-label="Close"
                    >
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </div>
                <div className="p-lg space-y-lg overflow-auto">
                    <div className="grid grid-cols-2 gap-md">
                        <Field label="Actor">
                            {row.isSystem ? "System" : row.actorName}
                        </Field>
                        <Field label="Tenant">
                            {entry.tenant_id != null ? `#${entry.tenant_id}` : "—"}
                        </Field>
                        <Field label="Action">{row.action.label}</Field>
                        <Field label="Status">
                            <span className={badgeForStatus(entry.status_code)}>
                                {entry.status_code}
                            </span>
                        </Field>
                        <Field label="Method">{entry.method}</Field>
                        <Field label="Duration">
                            {entry.duration_ms.toFixed(0)} ms
                        </Field>
                    </div>
                    <div className="space-y-sm">
                        <label className="font-label-caps text-label-caps text-secondary uppercase">
                            Entity / Path
                        </label>
                        <div className="bg-surface-container p-sm rounded font-mono text-[12px] text-on-surface-variant break-all">
                            {entry.path}
                        </div>
                    </div>
                    <div className="space-y-sm">
                        <label className="font-label-caps text-label-caps text-secondary uppercase">
                            Full Metadata
                        </label>
                        <pre className="bg-surface-container p-md rounded font-mono text-[11px] text-on-surface-variant overflow-x-auto">
                            {JSON.stringify(meta, null, 2)}
                        </pre>
                    </div>
                </div>
            </div>
        </div>
    );
}

function Field({
    label,
    children,
}: {
    label: string;
    children: React.ReactNode;
}) {
    return (
        <div className="space-y-xs">
            <label className="font-label-caps text-label-caps text-secondary uppercase">
                {label}
            </label>
            <div className="font-body-sm text-body-sm text-on-surface">{children}</div>
        </div>
    );
}

function badgeForStatus(code: number): string {
    const cls = statusClassOf(code);
    if (cls === "server_error") return "badge badge-red";
    if (cls === "client_error") return "badge badge-yellow";
    return "badge badge-green";
}

export default function AuditLogPage() {
    const { addToast } = useToast();
    const [entries, setEntries] = useState<AuditLogEntry[]>([]);
    const [users, setUsers] = useState<Map<number, AdminUser>>(new Map());
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [search, setSearch] = useState("");
    const [methodFilter, setMethodFilter] = useState("");
    const [statusFilter, setStatusFilter] = useState<StatusClass>("");
    const [page, setPage] = useState(1);
    const [selected, setSelected] = useState<Row | null>(null);

    useEffect(() => {
        Promise.allSettled([apiListAuditLog(500), apiListUsers()]).then(
            ([a, u]) => {
                if (a.status === "fulfilled") setEntries(a.value);
                else
                    setError(
                        a.reason?.message ?? "Audit log endpoint unavailable."
                    );
                if (u.status === "fulfilled") {
                    setUsers(new Map(u.value.map((x) => [x.id, x])));
                }
                setLoading(false);
            }
        );
    }, []);

    useEffect(() => {
        setPage(1);
    }, [search, methodFilter, statusFilter]);

    const rows = useMemo<Row[]>(
        () =>
            entries.map((entry) => {
                const isSystem = entry.user_id == null;
                const user = entry.user_id != null ? users.get(entry.user_id) : undefined;
                return {
                    entry,
                    isSystem,
                    actorName: isSystem
                        ? "System Automator"
                        : user
                            ? user.name
                            : `User #${entry.user_id}`,
                    actorEmail: user?.email ?? null,
                    action: deriveAction(entry.method, entry.path),
                };
            }),
        [entries, users]
    );

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        return rows.filter((r) => {
            if (methodFilter && r.entry.method.toUpperCase() !== methodFilter)
                return false;
            if (statusFilter && statusClassOf(r.entry.status_code) !== statusFilter)
                return false;
            if (q) {
                const hay = `${r.actorName} ${r.actorEmail ?? ""} ${r.entry.path} ${r.action.label
                    }`.toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });
    }, [rows, search, methodFilter, statusFilter]);

    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const safePage = Math.min(page, totalPages);
    const pageRows = filtered.slice(
        (safePage - 1) * PAGE_SIZE,
        safePage * PAGE_SIZE
    );
    const rangeStart = total === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
    const rangeEnd = Math.min(safePage * PAGE_SIZE, total);

    const pageNumbers = useMemo(() => {
        const nums: (number | "…")[] = [];
        for (let i = 1; i <= totalPages; i++) {
            if (i <= 3 || i === totalPages || Math.abs(i - safePage) <= 1)
                nums.push(i);
            else if (nums[nums.length - 1] !== "…") nums.push("…");
        }
        return nums;
    }, [totalPages, safePage]);

    const exportCsv = () => {
        if (filtered.length === 0) {
            addToast("Nothing to export with the current filters.", "info");
            return;
        }
        const header = [
            "Actor",
            "Email",
            "Action",
            "Method",
            "Entity",
            "Status",
            "Duration_ms",
            "Tenant",
            "Timestamp",
        ];
        const csvEscape = (v: unknown) => {
            const s = String(v ?? "");
            return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
        };
        const lines = filtered.map((r) =>
            [
                r.actorName,
                r.actorEmail ?? "",
                r.action.label,
                r.entry.method,
                r.entry.path,
                r.entry.status_code,
                r.entry.duration_ms.toFixed(1),
                r.entry.tenant_id ?? "",
                r.entry.created_at,
            ]
                .map(csvEscape)
                .join(",")
        );
        const blob = new Blob([[header.join(","), ...lines].join("\n")], {
            type: "text/csv;charset=utf-8;",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `audit-log-${new Date().toISOString().slice(0, 10)}.csv`;
        link.click();
        URL.revokeObjectURL(url);
        addToast(`Exported ${filtered.length} entries.`, "success");
    };

    const methodOptions = useMemo(() => {
        const set = new Set(entries.map((e) => e.method.toUpperCase()));
        return [...set].sort();
    }, [entries]);

    const selectCls =
        "block bg-surface-container-lowest border border-outline-variant rounded px-sm py-xs font-body-sm text-body-sm text-on-surface focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all";

    return (
        <div>
            <PageHeader title="Audit Log" />

            {/* Filters + actions */}
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-md mb-lg">
                <div className="flex flex-wrap gap-md">
                    <div className="space-y-xs">
                        <label className="font-label-caps text-label-caps text-secondary uppercase">
                            Search
                        </label>
                        <div className="relative">
                            <span className="material-symbols-outlined absolute left-sm top-1/2 -translate-y-1/2 text-[18px] text-secondary pointer-events-none">
                                search
                            </span>
                            <input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Actor, path, action…"
                                className={`${selectCls} pl-8 w-60`}
                            />
                        </div>
                    </div>
                    <div className="space-y-xs">
                        <label className="font-label-caps text-label-caps text-secondary uppercase">
                            Method
                        </label>
                        <select
                            value={methodFilter}
                            onChange={(e) => setMethodFilter(e.target.value)}
                            className={`${selectCls} w-36`}
                        >
                            <option value="">All Methods</option>
                            {methodOptions.map((m) => (
                                <option key={m} value={m}>
                                    {m}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="space-y-xs">
                        <label className="font-label-caps text-label-caps text-secondary uppercase">
                            Status
                        </label>
                        <select
                            value={statusFilter}
                            onChange={(e) =>
                                setStatusFilter(e.target.value as StatusClass)
                            }
                            className={`${selectCls} w-44`}
                        >
                            <option value="">All Statuses</option>
                            <option value="success">Success (2xx/3xx)</option>
                            <option value="client_error">Client Error (4xx)</option>
                            <option value="server_error">Server Error (5xx)</option>
                        </select>
                    </div>
                </div>
                <button
                    onClick={exportCsv}
                    className="flex items-center gap-xs px-md py-sm bg-surface-container-lowest border border-outline-variant rounded text-on-surface font-body-sm text-body-sm hover:bg-surface-container transition-colors h-fit"
                >
                    <span className="material-symbols-outlined text-[18px]">
                        download
                    </span>
                    Export CSV
                </button>
            </div>

            {/* Table */}
            <div className="bg-surface-container-lowest border border-outline-variant rounded overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="admin-table">
                        <thead>
                            <tr>
                                <th>Actor</th>
                                <th>Action</th>
                                <th>Entity</th>
                                <th>Tenant</th>
                                <th className="text-right">Timestamp</th>
                            </tr>
                        </thead>
                        <tbody className="font-table-data text-table-data">
                            {loading ? (
                                <tr>
                                    <td colSpan={5} className="text-center text-secondary py-12">
                                        Loading audit log…
                                    </td>
                                </tr>
                            ) : error ? (
                                <tr>
                                    <td colSpan={5} className="py-8">
                                        <p className="text-center font-body-sm text-body-sm text-on-error-container">
                                            {error}
                                        </p>
                                    </td>
                                </tr>
                            ) : pageRows.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="text-center text-secondary py-12">
                                        No log entries match the current filters.
                                    </td>
                                </tr>
                            ) : (
                                pageRows.map((r) => (
                                    <tr
                                        key={r.entry.id}
                                        onClick={() => setSelected(r)}
                                        className="cursor-pointer"
                                    >
                                        <td>
                                            <div className="flex items-center gap-sm">
                                                {r.isSystem ? (
                                                    <span className="w-7 h-7 rounded-full bg-primary-container flex items-center justify-center shrink-0">
                                                        <span className="material-symbols-outlined text-on-primary text-[15px]">
                                                            settings_suggest
                                                        </span>
                                                    </span>
                                                ) : (
                                                    <span className="w-7 h-7 rounded-full bg-surface-container-high border border-outline-variant flex items-center justify-center text-[10px] font-bold text-secondary shrink-0">
                                                        {monogram(r.actorName)}
                                                    </span>
                                                )}
                                                <div className="min-w-0">
                                                    <div className="text-on-surface font-semibold truncate">
                                                        {r.actorName}
                                                    </div>
                                                    {r.actorEmail && (
                                                        <div className="text-secondary text-[11px] truncate">
                                                            {r.actorEmail}
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            {r.action.destructive ? (
                                                <span className="inline-flex items-center gap-xs text-error font-bold uppercase tracking-tight">
                                                    <span className="material-symbols-outlined text-[16px]">
                                                        warning
                                                    </span>
                                                    {r.action.label}
                                                </span>
                                            ) : (
                                                <span className="text-on-surface inline-flex items-center gap-sm">
                                                    {r.action.label}
                                                    <span
                                                        className={badgeForStatus(
                                                            r.entry.status_code
                                                        )}
                                                    >
                                                        {r.entry.status_code}
                                                    </span>
                                                </span>
                                            )}
                                        </td>
                                        <td className="text-secondary font-mono text-[12px] max-w-[260px] truncate">
                                            {r.entry.path}
                                        </td>
                                        <td>
                                            {r.entry.tenant_id != null ? (
                                                <span className="px-sm py-[2px] bg-surface-container text-on-secondary-container rounded text-[11px] font-bold">
                                                    TENANT #{r.entry.tenant_id}
                                                </span>
                                            ) : (
                                                <span className="text-secondary">—</span>
                                            )}
                                        </td>
                                        <td className="text-right text-secondary whitespace-nowrap">
                                            {fmtTimestamp(r.entry.created_at)}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Pagination */}
            <div className="mt-md flex items-center justify-between">
                <span className="font-body-sm text-body-sm text-secondary">
                    {total === 0
                        ? "Showing 0 of 0 entries"
                        : `Showing ${rangeStart} to ${rangeEnd} of ${total.toLocaleString()} entries`}
                </span>
                <div className="flex items-center gap-xs">
                    <button
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={safePage <= 1}
                        className="w-8 h-8 flex items-center justify-center border border-outline-variant rounded disabled:opacity-40 enabled:hover:bg-surface-container transition-colors"
                        aria-label="Previous page"
                    >
                        <span className="material-symbols-outlined text-[16px]">
                            chevron_left
                        </span>
                    </button>
                    {pageNumbers.map((n, i) =>
                        n === "…" ? (
                            <span
                                key={`g${i}`}
                                className="px-xs text-secondary font-body-sm text-body-sm"
                            >
                                …
                            </span>
                        ) : (
                            <button
                                key={n}
                                onClick={() => setPage(n)}
                                className={`w-8 h-8 flex items-center justify-center rounded text-xs font-bold border transition-colors ${n === safePage
                                    ? "border-primary bg-primary text-on-primary"
                                    : "border-outline-variant text-on-surface hover:bg-surface-container"
                                    }`}
                            >
                                {n}
                            </button>
                        )
                    )}
                    <button
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={safePage >= totalPages}
                        className="w-8 h-8 flex items-center justify-center border border-outline-variant rounded disabled:opacity-40 enabled:hover:bg-surface-container transition-colors"
                        aria-label="Next page"
                    >
                        <span className="material-symbols-outlined text-[16px]">
                            chevron_right
                        </span>
                    </button>
                </div>
            </div>

            {selected && (
                <DetailDrawer row={selected} onClose={() => setSelected(null)} />
            )}
        </div>
    );
}
