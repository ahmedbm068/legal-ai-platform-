import { useEffect, useMemo, useRef, useState } from "react";
import { apiListUsers, type AdminUser } from "../lib/api";
import { useToast } from "../context/ToastContext";
import { PageHeader } from "../components/ui";

type Tab = "staff" | "invites";

const PAGE_SIZE = 12;

const ROLE_LABEL: Record<string, string> = {
    admin: "Admin",
    lawyer: "Lawyer",
    client: "Client",
    assistant: "Assistant",
};

function initials(name: string): string {
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function Dropdown({
    value,
    onChange,
    options,
    placeholder,
}: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder: string;
}) {
    return (
        <div className="relative">
            <select
                value={value}
                onChange={(e) => onChange(e.target.value)}
                className="appearance-none bg-transparent border-0 font-body-sm text-body-sm text-on-surface pr-6 pl-0 py-sm focus:outline-none cursor-pointer"
            >
                <option value="">{placeholder}</option>
                {options.map((o) => (
                    <option key={o.value} value={o.value}>
                        {o.label}
                    </option>
                ))}
            </select>
            <span className="material-symbols-outlined text-[18px] text-secondary absolute right-0 top-1/2 -translate-y-1/2 pointer-events-none">
                expand_more
            </span>
        </div>
    );
}

function RowActions({ onAction }: { onAction: () => void }) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
        const handler = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, [open]);

    return (
        <div className="relative" ref={ref}>
            <button
                onClick={() => setOpen((v) => !v)}
                className="text-secondary hover:text-primary p-xs rounded-full hover:bg-surface-container transition-colors"
                aria-label="Row actions"
            >
                <span className="material-symbols-outlined text-[18px]">more_vert</span>
            </button>
            {open && (
                <div className="absolute right-0 top-full mt-xs w-44 bg-surface-container-lowest border border-outline-variant rounded shadow-lg z-20 py-xs">
                    {["Edit", "Reset password", "Deactivate"].map((label) => (
                        <button
                            key={label}
                            onClick={() => {
                                setOpen(false);
                                onAction();
                            }}
                            className="w-full text-left px-md py-sm font-body-sm text-body-sm text-on-surface hover:bg-surface-container transition-colors"
                        >
                            {label}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

export default function UsersPage() {
    const { addToast } = useToast();
    const [users, setUsers] = useState<AdminUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [tab, setTab] = useState<Tab>("staff");
    const [search, setSearch] = useState("");
    const [roleFilter, setRoleFilter] = useState("");
    const [tenantFilter, setTenantFilter] = useState("");
    const [page, setPage] = useState(1);

    useEffect(() => {
        apiListUsers()
            .then(setUsers)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    // Reset to first page whenever filters change
    useEffect(() => {
        setPage(1);
    }, [search, roleFilter, tenantFilter]);

    const roleOptions = useMemo(() => {
        const set = new Set(users.map((u) => u.role));
        return [...set].sort().map((r) => ({
            value: r,
            label: ROLE_LABEL[r] ?? r,
        }));
    }, [users]);

    const tenantOptions = useMemo(() => {
        const set = new Set(users.map((u) => u.tenant_id));
        return [...set]
            .sort((a, b) => a - b)
            .map((t) => ({ value: String(t), label: `Tenant #${t}` }));
    }, [users]);

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        return users.filter((u) => {
            if (q && !u.name.toLowerCase().includes(q) && !u.email.toLowerCase().includes(q))
                return false;
            if (roleFilter && u.role !== roleFilter) return false;
            if (tenantFilter && String(u.tenant_id) !== tenantFilter) return false;
            return true;
        });
    }, [users, search, roleFilter, tenantFilter]);

    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    const safePage = Math.min(page, totalPages);
    const pageRows = filtered.slice(
        (safePage - 1) * PAGE_SIZE,
        safePage * PAGE_SIZE
    );
    const rangeStart = filtered.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
    const rangeEnd = Math.min(safePage * PAGE_SIZE, filtered.length);

    const notAvailable = () =>
        addToast("Staff management is not available yet — backend pending.", "info");

    const pageNumbers = useMemo(() => {
        const nums: (number | "…")[] = [];
        for (let i = 1; i <= totalPages; i++) {
            if (i <= 3 || i === totalPages || Math.abs(i - safePage) <= 1) {
                nums.push(i);
            } else if (nums[nums.length - 1] !== "…") {
                nums.push("…");
            }
        }
        return nums;
    }, [totalPages, safePage]);

    return (
        <div>
            <PageHeader title="Users & Staff" />

            {/* Tabs */}
            <div className="flex items-center gap-lg border-b border-outline-variant mb-lg">
                {(
                    [
                        { id: "staff" as const, label: "Staff List" },
                        { id: "invites" as const, label: "Invites" },
                    ]
                ).map((t) => (
                    <button
                        key={t.id}
                        onClick={() => setTab(t.id)}
                        className={`pb-sm -mb-px border-b-2 font-section-header text-section-header transition-colors ${tab === t.id
                            ? "border-primary text-primary"
                            : "border-transparent text-secondary hover:text-on-surface"
                            }`}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            {tab === "invites" ? (
                <div className="bg-surface-container-lowest border border-outline-variant rounded h-[360px] flex flex-col items-center justify-center text-center px-xl">
                    <div className="w-16 h-16 rounded-full bg-surface-container-high border border-outline-variant flex items-center justify-center mb-md">
                        <span className="material-symbols-outlined text-[28px] text-secondary">
                            mail
                        </span>
                    </div>
                    <h3 className="font-section-header text-section-header text-on-surface mb-xs">
                        Invites are not yet available
                    </h3>
                    <p className="font-body-sm text-body-sm text-secondary max-w-md">
                        There is no invitation endpoint on the backend yet. Pending staff
                        invites will appear here once the API is available.
                    </p>
                </div>
            ) : (
                <>
                    {/* Toolbar */}
                    <div className="bg-surface-container-lowest border border-outline-variant rounded flex items-center gap-md px-md py-sm mb-md">
                        <div className="relative flex-1 max-w-md">
                            <span className="material-symbols-outlined absolute left-0 top-1/2 -translate-y-1/2 text-[18px] text-secondary pointer-events-none">
                                search
                            </span>
                            <input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Search staff…"
                                className="w-full bg-transparent border-0 pl-7 py-sm font-body-sm text-body-sm text-on-surface placeholder:text-secondary focus:outline-none"
                            />
                        </div>
                        <div className="h-6 w-px bg-outline-variant" />
                        <Dropdown
                            value={roleFilter}
                            onChange={setRoleFilter}
                            options={roleOptions}
                            placeholder="All Roles"
                        />
                        <Dropdown
                            value={tenantFilter}
                            onChange={setTenantFilter}
                            options={tenantOptions}
                            placeholder="All Tenants"
                        />
                        <button
                            onClick={notAvailable}
                            className="ml-auto bg-primary-container text-on-primary font-body-sm text-body-sm font-semibold px-md py-sm rounded flex items-center gap-xs hover:bg-surface-tint transition-colors"
                        >
                            <span className="material-symbols-outlined text-[16px]">add</span>
                            Add Staff
                        </button>
                    </div>

                    {loading && (
                        <p className="font-body-sm text-body-sm text-secondary py-sm">
                            Loading staff…
                        </p>
                    )}
                    {error && (
                        <p className="font-body-sm text-body-sm text-on-error-container bg-err-bg border border-error-container rounded px-md py-sm">
                            {error}
                        </p>
                    )}

                    {!loading && !error && (
                        <>
                            <div className="bg-surface-container-lowest border border-outline-variant rounded overflow-hidden">
                                <div className="overflow-auto">
                                    <table className="admin-table">
                                        <thead>
                                            <tr>
                                                <th>Name</th>
                                                <th>Email</th>
                                                <th>Role</th>
                                                <th>Tenant</th>
                                                <th>Status</th>
                                                <th>Joined</th>
                                                <th className="text-right">Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody className="font-table-data text-table-data">
                                            {pageRows.length === 0 ? (
                                                <tr>
                                                    <td
                                                        colSpan={7}
                                                        className="text-center text-secondary py-8"
                                                    >
                                                        No staff found
                                                    </td>
                                                </tr>
                                            ) : (
                                                pageRows.map((u) => (
                                                    <tr key={u.id}>
                                                        <td>
                                                            <div className="flex items-center gap-sm">
                                                                <span className="w-7 h-7 rounded-full bg-surface-container-high border border-outline-variant flex items-center justify-center text-[10px] font-bold text-secondary">
                                                                    {initials(u.name)}
                                                                </span>
                                                                <span className="text-on-surface font-semibold">
                                                                    {u.name}
                                                                </span>
                                                            </div>
                                                        </td>
                                                        <td className="text-secondary">{u.email}</td>
                                                        <td className="text-on-surface">
                                                            {ROLE_LABEL[u.role] ?? u.role}
                                                        </td>
                                                        <td className="text-secondary">
                                                            #{u.tenant_id}
                                                        </td>
                                                        <td>
                                                            <span className="badge badge-green">
                                                                Active
                                                            </span>
                                                        </td>
                                                        <td className="text-secondary">
                                                            {new Date(
                                                                u.created_at
                                                            ).toLocaleDateString()}
                                                        </td>
                                                        <td>
                                                            <div className="flex justify-end">
                                                                <RowActions
                                                                    onAction={notAvailable}
                                                                />
                                                            </div>
                                                        </td>
                                                    </tr>
                                                ))
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                            {/* Pagination */}
                            <div className="flex justify-between items-center mt-md">
                                <p className="font-body-sm text-body-sm text-secondary">
                                    {filtered.length === 0
                                        ? "No entries"
                                        : `Showing ${rangeStart} to ${rangeEnd} of ${filtered.length} entries`}
                                </p>
                                <div className="flex items-center gap-xs">
                                    <button
                                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                                        disabled={safePage <= 1}
                                        className="px-md py-xs font-body-sm text-body-sm text-secondary border border-outline-variant rounded disabled:opacity-40 enabled:hover:bg-surface-container transition-colors"
                                    >
                                        Previous
                                    </button>
                                    {pageNumbers.map((n, i) =>
                                        n === "…" ? (
                                            <span
                                                key={`gap-${i}`}
                                                className="px-2 text-secondary font-body-sm text-body-sm"
                                            >
                                                …
                                            </span>
                                        ) : (
                                            <button
                                                key={n}
                                                onClick={() => setPage(n)}
                                                className={`w-8 h-8 font-body-sm text-body-sm rounded border transition-colors ${n === safePage
                                                    ? "bg-primary-container text-on-primary border-primary-container"
                                                    : "text-on-surface border-outline-variant hover:bg-surface-container"
                                                    }`}
                                            >
                                                {n}
                                            </button>
                                        )
                                    )}
                                    <button
                                        onClick={() =>
                                            setPage((p) => Math.min(totalPages, p + 1))
                                        }
                                        disabled={safePage >= totalPages}
                                        className="px-md py-xs font-body-sm text-body-sm text-secondary border border-outline-variant rounded disabled:opacity-40 enabled:hover:bg-surface-container transition-colors"
                                    >
                                        Next
                                    </button>
                                </div>
                            </div>
                        </>
                    )}
                </>
            )}
        </div>
    );
}
