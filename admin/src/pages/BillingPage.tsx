import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    apiCreateInvoice,
    apiListInvoices,
    apiMarkInvoicePaid,
    apiVoidInvoice,
    type Invoice,
    type InvoiceList,
} from "../lib/api";
import { useToast } from "../context/ToastContext";
import { PageHeader } from "../components/ui";

const PAGE_SIZE = 25;

const STATUS_OPTIONS = ["", "outstanding", "overdue", "paid", "void"];

function money(amount: number, currency = "USD"): string {
    try {
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: currency || "USD",
        }).format(amount);
    } catch {
        return `$${amount.toFixed(2)}`;
    }
}

function compactMoney(amount: number): string {
    if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`;
    if (amount >= 1_000) return `$${Math.round(amount / 1_000)}k`;
    return `$${amount.toFixed(0)}`;
}

function fmtDate(iso: string | null): string {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("en-US", {
        month: "short",
        day: "2-digit",
        year: "numeric",
    });
}

function statusBadge(status: string): string {
    const s = (status || "").toLowerCase();
    if (s === "paid") return "badge badge-green";
    if (s === "overdue") return "badge badge-red";
    if (s === "outstanding") return "badge badge-yellow";
    return "badge badge-gray"; // draft / void
}

function isOverdue(inv: Invoice): boolean {
    const s = (inv.status || "").toLowerCase();
    if (s === "paid" || s === "void") return false;
    if (s === "overdue") return true;
    return inv.due_at != null && new Date(inv.due_at).getTime() < Date.now();
}

function Kpi({ label, value }: { label: string; value: string }) {
    return (
        <div className="bg-surface-container-lowest border border-outline-variant rounded p-md flex flex-col justify-between h-[104px]">
            <span className="font-label-caps text-label-caps text-secondary uppercase tracking-wider">
                {label}
            </span>
            <span className="font-page-header text-page-header text-primary">{value}</span>
        </div>
    );
}

function RowActions({
    onMarkPaid,
    onVoid,
    canMarkPaid,
    canVoid,
    busy,
}: {
    onMarkPaid: () => void;
    onVoid: () => void;
    canMarkPaid: boolean;
    canVoid: boolean;
    busy: boolean;
}) {
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
        <div className="relative inline-block" ref={ref}>
            <button
                onClick={() => setOpen((v) => !v)}
                disabled={busy}
                className="text-secondary hover:text-primary p-xs rounded-full hover:bg-surface-container transition-colors disabled:opacity-40"
                aria-label="Invoice actions"
            >
                <span className="material-symbols-outlined text-[18px]">more_vert</span>
            </button>
            {open && (
                <div className="absolute right-0 top-full mt-xs w-44 bg-surface-container-lowest border border-outline-variant rounded shadow-lg z-20 py-xs">
                    <button
                        onClick={() => {
                            setOpen(false);
                            onMarkPaid();
                        }}
                        disabled={!canMarkPaid}
                        className="w-full text-left px-md py-sm font-body-sm text-body-sm text-on-surface hover:bg-surface-container transition-colors disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                        Mark as paid
                    </button>
                    <button
                        onClick={() => {
                            setOpen(false);
                            onVoid();
                        }}
                        disabled={!canVoid}
                        className="w-full text-left px-md py-sm font-body-sm text-body-sm text-error hover:bg-surface-container transition-colors disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                        Void invoice
                    </button>
                </div>
            )}
        </div>
    );
}

interface LineItemDraft {
    description: string;
    hours: string;
    amount: string;
}

function CreateInvoiceModal({
    onClose,
    onCreated,
}: {
    onClose: () => void;
    onCreated: () => void;
}) {
    const { addToast } = useToast();
    const [caseId, setCaseId] = useState("");
    const [description, setDescription] = useState("");
    const [notes, setNotes] = useState("");
    const [currency, setCurrency] = useState("USD");
    const [items, setItems] = useState<LineItemDraft[]>([
        { description: "", hours: "", amount: "" },
    ]);
    const [submitting, setSubmitting] = useState(false);

    const updateItem = (i: number, patch: Partial<LineItemDraft>) =>
        setItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));

    const total = items.reduce((sum, it) => sum + (parseFloat(it.amount) || 0), 0);

    const submit = async () => {
        const cid = parseInt(caseId, 10);
        if (!cid || Number.isNaN(cid)) {
            addToast("A valid Case ID is required.", "warning");
            return;
        }
        if (!description.trim()) {
            addToast("Description is required.", "warning");
            return;
        }
        const lineItems = items
            .filter((it) => it.description.trim() && it.amount !== "")
            .map((it) => ({
                description: it.description.trim(),
                hours: it.hours === "" ? null : parseFloat(it.hours),
                amount: parseFloat(it.amount),
            }));
        if (lineItems.length === 0) {
            addToast("Add at least one line item with a description and amount.", "warning");
            return;
        }
        setSubmitting(true);
        try {
            await apiCreateInvoice({
                case_id: cid,
                description: description.trim(),
                notes: notes.trim() || null,
                currency: currency.trim().toUpperCase() || "USD",
                line_items: lineItems,
            });
            addToast("Invoice created.", "success");
            onCreated();
            onClose();
        } catch (e) {
            addToast(e instanceof Error ? e.message : "Failed to create invoice.", "error");
        } finally {
            setSubmitting(false);
        }
    };

    const inputCls =
        "w-full bg-surface border border-outline-variant rounded px-sm py-1.5 font-body-sm text-body-sm text-on-surface focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all";

    return (
        <div
            className="fixed inset-0 z-[8000] bg-inverse-surface/40 flex items-center justify-center p-md"
            onMouseDown={onClose}
        >
            <div
                className="bg-surface-container-lowest border border-outline-variant rounded w-full max-w-lg max-h-[90vh] overflow-auto"
                onMouseDown={(e) => e.stopPropagation()}
            >
                <div className="flex justify-between items-center px-lg py-md border-b border-outline-variant">
                    <h3 className="font-section-header text-section-header text-on-surface">
                        Create Invoice
                    </h3>
                    <button
                        onClick={onClose}
                        className="text-secondary hover:text-primary transition-colors"
                        aria-label="Close"
                    >
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </div>

                <div className="p-lg flex flex-col gap-md">
                    <div className="grid grid-cols-2 gap-md">
                        <div className="flex flex-col gap-xs">
                            <label className="font-body-sm text-body-sm text-on-surface">
                                Case ID
                            </label>
                            <input
                                value={caseId}
                                onChange={(e) => setCaseId(e.target.value)}
                                inputMode="numeric"
                                placeholder="e.g. 42"
                                className={inputCls}
                            />
                        </div>
                        <div className="flex flex-col gap-xs">
                            <label className="font-body-sm text-body-sm text-on-surface">
                                Currency
                            </label>
                            <input
                                value={currency}
                                onChange={(e) => setCurrency(e.target.value)}
                                maxLength={3}
                                className={inputCls}
                            />
                        </div>
                    </div>

                    <div className="flex flex-col gap-xs">
                        <label className="font-body-sm text-body-sm text-on-surface">
                            Description
                        </label>
                        <input
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="Invoice summary"
                            className={inputCls}
                        />
                    </div>

                    <div className="flex flex-col gap-xs">
                        <label className="font-body-sm text-body-sm text-on-surface">
                            Notes <span className="text-secondary">(optional)</span>
                        </label>
                        <textarea
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            rows={2}
                            className={inputCls}
                        />
                    </div>

                    <div className="flex flex-col gap-xs">
                        <div className="flex justify-between items-center">
                            <label className="font-body-sm text-body-sm text-on-surface">
                                Line Items
                            </label>
                            <button
                                onClick={() =>
                                    setItems((p) => [
                                        ...p,
                                        { description: "", hours: "", amount: "" },
                                    ])
                                }
                                className="font-body-sm text-body-sm text-on-primary-container hover:text-primary-container flex items-center gap-xs"
                            >
                                <span className="material-symbols-outlined text-[16px]">
                                    add
                                </span>
                                Add item
                            </button>
                        </div>
                        {items.map((it, i) => (
                            <div key={i} className="flex gap-xs items-center">
                                <input
                                    value={it.description}
                                    onChange={(e) =>
                                        updateItem(i, { description: e.target.value })
                                    }
                                    placeholder="Description"
                                    className={`${inputCls} flex-1`}
                                />
                                <input
                                    value={it.hours}
                                    onChange={(e) => updateItem(i, { hours: e.target.value })}
                                    placeholder="Hrs"
                                    inputMode="decimal"
                                    className={`${inputCls} w-16`}
                                />
                                <input
                                    value={it.amount}
                                    onChange={(e) => updateItem(i, { amount: e.target.value })}
                                    placeholder="Amount"
                                    inputMode="decimal"
                                    className={`${inputCls} w-24`}
                                />
                                {items.length > 1 && (
                                    <button
                                        onClick={() =>
                                            setItems((p) => p.filter((_, idx) => idx !== i))
                                        }
                                        className="text-secondary hover:text-error transition-colors"
                                        aria-label="Remove line item"
                                    >
                                        <span className="material-symbols-outlined text-[18px]">
                                            delete
                                        </span>
                                    </button>
                                )}
                            </div>
                        ))}
                        <p className="text-right font-body-sm text-body-sm text-secondary mt-xs">
                            Total:{" "}
                            <span className="text-on-surface font-semibold">
                                {money(total, currency)}
                            </span>
                        </p>
                    </div>
                </div>

                <div className="flex justify-end gap-sm px-lg py-md border-t border-outline-variant">
                    <button
                        onClick={onClose}
                        className="px-md py-sm font-body-sm text-body-sm text-on-surface border border-outline rounded hover:bg-surface-container transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={submit}
                        disabled={submitting}
                        className="px-md py-sm font-body-sm text-body-sm font-semibold bg-primary-container text-on-primary rounded hover:bg-surface-tint disabled:opacity-60 transition-colors flex items-center gap-xs"
                    >
                        {submitting && (
                            <span className="material-symbols-outlined text-[16px] animate-spin">
                                progress_activity
                            </span>
                        )}
                        Create Invoice
                    </button>
                </div>
            </div>
        </div>
    );
}

export default function BillingPage() {
    const { addToast } = useToast();
    const [data, setData] = useState<InvoiceList | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [statusFilter, setStatusFilter] = useState("");
    const [filterOpen, setFilterOpen] = useState(false);
    const [page, setPage] = useState(1);
    const [showCreate, setShowCreate] = useState(false);
    const [busyId, setBusyId] = useState<number | null>(null);

    const load = useCallback(() => {
        setLoading(true);
        setError(null);
        apiListInvoices({
            status: statusFilter || undefined,
            limit: PAGE_SIZE,
            offset: (page - 1) * PAGE_SIZE,
        })
            .then(setData)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, [statusFilter, page]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        setPage(1);
    }, [statusFilter]);

    const invoices = data?.invoices ?? [];
    const total = data?.total ?? 0;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const rangeEnd = Math.min(page * PAGE_SIZE, total);

    const pageNumbers = useMemo(() => {
        const nums: (number | "…")[] = [];
        for (let i = 1; i <= totalPages; i++) {
            if (i <= 2 || i === totalPages || Math.abs(i - page) <= 1) nums.push(i);
            else if (nums[nums.length - 1] !== "…") nums.push("…");
        }
        return nums;
    }, [totalPages, page]);

    const handleMarkPaid = async (inv: Invoice) => {
        setBusyId(inv.id);
        try {
            await apiMarkInvoicePaid(inv.id);
            addToast(`${inv.invoice_number} marked as paid.`, "success");
            load();
        } catch (e) {
            addToast(e instanceof Error ? e.message : "Failed to mark paid.", "error");
        } finally {
            setBusyId(null);
        }
    };

    const handleVoid = async (inv: Invoice) => {
        setBusyId(inv.id);
        try {
            await apiVoidInvoice(inv.id);
            addToast(`${inv.invoice_number} voided.`, "success");
            load();
        } catch (e) {
            addToast(e instanceof Error ? e.message : "Failed to void invoice.", "error");
        } finally {
            setBusyId(null);
        }
    };

    return (
        <div>
            <PageHeader
                title="Billing & Invoices"
                actions={
                    <button
                        onClick={() => setShowCreate(true)}
                        className="bg-primary-container text-on-primary font-body-sm text-body-sm font-semibold px-md py-sm rounded flex items-center gap-xs hover:bg-surface-tint transition-colors"
                    >
                        <span className="material-symbols-outlined text-[18px]">add</span>
                        Create Invoice
                    </button>
                }
            />

            <div className="grid grid-cols-2 gap-md mb-lg">
                <Kpi
                    label="Outstanding"
                    value={data ? compactMoney(data.total_outstanding) : "—"}
                />
                <Kpi
                    label="Collected"
                    value={data ? compactMoney(data.total_collected) : "—"}
                />
            </div>

            <div className="bg-surface-container-lowest border border-outline-variant rounded overflow-hidden">
                <div className="px-md py-sm border-b border-outline-variant flex items-center gap-sm relative">
                    <button
                        onClick={() => setFilterOpen((v) => !v)}
                        className="px-sm py-1 border border-outline-variant rounded text-secondary font-body-sm text-body-sm hover:bg-surface-container transition-colors flex items-center gap-1"
                    >
                        <span className="material-symbols-outlined text-[16px]">
                            filter_list
                        </span>
                        Filter
                        {statusFilter && (
                            <span className="ml-1 text-on-surface capitalize">
                                · {statusFilter}
                            </span>
                        )}
                    </button>
                    {filterOpen && (
                        <div className="absolute left-md top-full mt-xs w-44 bg-surface-container-lowest border border-outline-variant rounded shadow-lg z-20 py-xs">
                            {STATUS_OPTIONS.map((s) => (
                                <button
                                    key={s || "all"}
                                    onClick={() => {
                                        setStatusFilter(s);
                                        setFilterOpen(false);
                                    }}
                                    className={`w-full text-left px-md py-sm font-body-sm text-body-sm capitalize hover:bg-surface-container transition-colors ${statusFilter === s
                                        ? "text-primary font-semibold"
                                        : "text-on-surface"
                                        }`}
                                >
                                    {s || "All statuses"}
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                <div className="overflow-x-auto">
                    <table className="admin-table">
                        <thead>
                            <tr>
                                <th>Invoice #</th>
                                <th>Tenant</th>
                                <th>Client</th>
                                <th className="text-right">Amount</th>
                                <th>Status</th>
                                <th>Issue Date</th>
                                <th>Due Date</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody className="font-table-data text-table-data">
                            {loading ? (
                                <tr>
                                    <td colSpan={8} className="text-center text-secondary py-12">
                                        Loading invoices…
                                    </td>
                                </tr>
                            ) : error ? (
                                <tr>
                                    <td colSpan={8} className="py-8">
                                        <p className="text-center font-body-sm text-body-sm text-on-error-container">
                                            {error}
                                        </p>
                                    </td>
                                </tr>
                            ) : invoices.length === 0 ? (
                                <tr>
                                    <td colSpan={8} className="text-center text-secondary py-12">
                                        No invoices found
                                        {statusFilter ? ` for status "${statusFilter}"` : ""}.
                                    </td>
                                </tr>
                            ) : (
                                invoices.map((inv) => {
                                    const overdue = isOverdue(inv);
                                    const st = (inv.status || "").toLowerCase();
                                    return (
                                        <tr key={inv.id}>
                                            <td className="font-semibold text-primary">
                                                {inv.invoice_number}
                                            </td>
                                            <td className="text-on-surface">
                                                {inv.tenant_name ?? `#${inv.tenant_id}`}
                                            </td>
                                            <td className="text-secondary">
                                                {inv.client_name ??
                                                    (inv.client_id
                                                        ? `#${inv.client_id}`
                                                        : "—")}
                                            </td>
                                            <td className="text-right font-semibold text-on-surface">
                                                {money(inv.amount_total, inv.currency)}
                                            </td>
                                            <td>
                                                <span
                                                    className={statusBadge(
                                                        overdue ? "overdue" : inv.status
                                                    )}
                                                >
                                                    {overdue ? "Overdue" : inv.status}
                                                </span>
                                            </td>
                                            <td className="text-secondary">
                                                {fmtDate(inv.issued_at)}
                                            </td>
                                            <td
                                                className={
                                                    overdue
                                                        ? "text-error font-medium"
                                                        : "text-secondary"
                                                }
                                            >
                                                {fmtDate(inv.due_at)}
                                            </td>
                                            <td className="text-right">
                                                <RowActions
                                                    busy={busyId === inv.id}
                                                    canMarkPaid={
                                                        st !== "paid" && st !== "void"
                                                    }
                                                    canVoid={st !== "paid" && st !== "void"}
                                                    onMarkPaid={() => handleMarkPaid(inv)}
                                                    onVoid={() => handleVoid(inv)}
                                                />
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>

                <div className="px-md py-sm border-t border-outline-variant flex justify-between items-center text-secondary font-body-sm text-body-sm">
                    <span>
                        {total === 0
                            ? "Showing 0 of 0 entries"
                            : `Showing ${rangeStart} to ${rangeEnd} of ${total} entries`}
                    </span>
                    <div className="flex gap-1 items-center">
                        <button
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            disabled={page <= 1 || loading}
                            className="px-2 py-1 rounded enabled:hover:bg-surface-container disabled:opacity-50 transition-colors"
                        >
                            Prev
                        </button>
                        {pageNumbers.map((n, i) =>
                            n === "…" ? (
                                <span key={`g${i}`} className="px-2">
                                    …
                                </span>
                            ) : (
                                <button
                                    key={n}
                                    onClick={() => setPage(n)}
                                    className={`px-2 py-1 rounded transition-colors ${n === page
                                        ? "bg-secondary-container text-primary font-medium"
                                        : "hover:bg-surface-container"
                                        }`}
                                >
                                    {n}
                                </button>
                            )
                        )}
                        <button
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            disabled={page >= totalPages || loading}
                            className="px-2 py-1 rounded enabled:hover:bg-surface-container disabled:opacity-50 transition-colors"
                        >
                            Next
                        </button>
                    </div>
                </div>
            </div>

            {showCreate && (
                <CreateInvoiceModal
                    onClose={() => setShowCreate(false)}
                    onCreated={load}
                />
            )}
        </div>
    );
}
