import { useCallback, useEffect, useMemo, useState } from "react";
import { usePortal } from "../context/PortalContext";
import { fetchPortalBilling, payPortalInvoice } from "../lib/api";
import { formatDate } from "../portalPresentation";
import type { ClientPortalBilling } from "../types";

function money(amount: number, currency: string): string {
    try {
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: currency || "USD",
        }).format(amount);
    } catch {
        return `$${amount.toFixed(2)}`;
    }
}

function isOutstanding(status: string): boolean {
    return ["outstanding", "overdue"].includes((status || "").toLowerCase());
}

export default function LexingtonBillingPage() {
    const { token } = usePortal();
    const [billing, setBilling] = useState<ClientPortalBilling | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [payingId, setPayingId] = useState<number | null>(null);
    const [notice, setNotice] = useState<{ kind: "info" | "ok"; text: string } | null>(null);

    const load = useCallback(async () => {
        if (!token) return;
        setLoading(true);
        setError(null);
        try {
            const data = await fetchPortalBilling(token);
            setBilling(data);
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Unable to load billing.");
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => {
        void load();
    }, [load]);

    async function handlePay(invoiceId: number) {
        if (!token) return;
        setPayingId(invoiceId);
        setNotice(null);
        setError(null);
        try {
            const result = await payPortalInvoice(token, invoiceId);
            setNotice({
                kind: result.status === "succeeded" ? "ok" : "info",
                text: result.message,
            });
            await load();
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Payment could not be initiated.");
        } finally {
            setPayingId(null);
        }
    }

    const currency = billing?.currency ?? "USD";
    const invoices = useMemo(() => billing?.invoices ?? [], [billing]);
    const totalOutstanding = billing?.total_outstanding ?? 0;

    return (
        <main className="lexington-scope max-w-container-max mx-auto px-gutter py-stack-lg">
            <section className="mb-stack-lg">
                <div className="flex flex-col md:flex-row md:items-end justify-between gap-stack-md">
                    <div>
                        <h1 className="font-display-lg text-display-lg text-primary mb-2">
                            Billing &amp; Invoices
                        </h1>
                        <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl">
                            Review your recent charges and manage outstanding balances. Plain-language
                            billing so you understand exactly what you're paying for.
                        </p>
                    </div>
                    <div className="bg-surface-container-low border border-outline-variant p-stack-md rounded-lg min-w-[280px]">
                        <span className="font-label-md text-label-md text-on-surface-variant block mb-1 uppercase tracking-widest">
                            Total Outstanding
                        </span>
                        <div className="font-headline-lg text-headline-lg text-primary">
                            {money(totalOutstanding, currency)}
                        </div>
                        <button
                            type="button"
                            disabled
                            title="Pay each invoice individually below"
                            className="mt-4 w-full bg-primary text-on-primary py-3 px-6 font-label-md text-label-md rounded opacity-60 cursor-not-allowed"
                        >
                            Pay Total Balance
                        </button>
                    </div>
                </div>
            </section>

            {notice ? (
                <div
                    className={
                        notice.kind === "ok"
                            ? "mb-stack-md bg-secondary-container text-on-secondary-container px-4 py-3 rounded-lg font-body-md text-body-md"
                            : "mb-stack-md bg-surface-container-high text-on-surface-variant px-4 py-3 rounded-lg font-body-md text-body-md"
                    }
                >
                    {notice.text}
                </div>
            ) : null}
            {error ? (
                <div className="mb-stack-md bg-error-container text-on-error-container px-4 py-3 rounded-lg font-body-md text-body-md">
                    {error}
                </div>
            ) : null}

            <section className="bg-surface-container-lowest border border-outline-variant rounded-lg shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-surface-container-low border-b border-outline-variant">
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Description</th>
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Hours</th>
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Amount</th>
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Status</th>
                                <th className="px-8 py-5 font-label-md text-label-md text-on-surface-variant uppercase tracking-wider text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-outline-variant">
                            {loading && !billing ? (
                                <tr>
                                    <td colSpan={5} className="px-8 py-12 text-center font-body-md text-on-surface-variant">
                                        Loading invoices…
                                    </td>
                                </tr>
                            ) : invoices.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="px-8 py-12 text-center font-body-md text-on-surface-variant">
                                        No invoices yet. Charges from your legal team will appear here.
                                    </td>
                                </tr>
                            ) : (
                                invoices.map((inv) => {
                                    const totalHours = inv.line_items.reduce(
                                        (sum, li) => sum + (li.hours ?? 0),
                                        0
                                    );
                                    const outstanding = isOutstanding(inv.status);
                                    const paid = (inv.status || "").toLowerCase() === "paid";
                                    return (
                                        <tr
                                            key={inv.id}
                                            className="hover:bg-surface-container-low transition-colors duration-200"
                                        >
                                            <td className="px-8 py-6">
                                                <div className="font-body-md text-body-md text-primary font-semibold">
                                                    {inv.description}
                                                </div>
                                                <div className="font-label-md text-label-md text-on-surface-variant mt-1">
                                                    {inv.invoice_number} · {formatDate(inv.issued_at)}
                                                </div>
                                            </td>
                                            <td className="px-8 py-6 font-body-md text-body-md text-on-surface-variant">
                                                {totalHours > 0 ? `${totalHours.toFixed(1)} hrs` : "—"}
                                            </td>
                                            <td className="px-8 py-6 font-body-md text-body-md text-primary">
                                                {money(inv.amount_total, inv.currency)}
                                            </td>
                                            <td className="px-8 py-6">
                                                <span
                                                    className={
                                                        paid
                                                            ? "inline-flex items-center px-3 py-1 rounded-full bg-secondary-container text-on-secondary-container font-label-md text-label-md"
                                                            : outstanding
                                                              ? "inline-flex items-center px-3 py-1 rounded-full bg-error-container text-on-error-container font-label-md text-label-md"
                                                              : "inline-flex items-center px-3 py-1 rounded-full bg-surface-container-high text-on-surface-variant font-label-md text-label-md"
                                                    }
                                                >
                                                    {paid
                                                        ? "Paid"
                                                        : outstanding
                                                          ? "Outstanding"
                                                          : inv.status}
                                                </span>
                                            </td>
                                            <td className="px-8 py-6 text-right">
                                                {outstanding ? (
                                                    <button
                                                        type="button"
                                                        onClick={() => void handlePay(inv.id)}
                                                        disabled={payingId === inv.id}
                                                        className="bg-primary text-on-primary py-2 px-6 font-label-md text-label-md rounded hover:opacity-90 transition-opacity disabled:opacity-50"
                                                    >
                                                        {payingId === inv.id ? "Processing…" : "Pay Now"}
                                                    </button>
                                                ) : (
                                                    <span className="material-symbols-outlined text-on-surface-variant">
                                                        description
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="mt-stack-lg grid grid-cols-1 md:grid-cols-2 gap-stack-md">
                <div className="bg-surface-container border border-outline-variant p-stack-md rounded-lg flex gap-6 items-start">
                    <div className="bg-primary-container p-3 rounded-lg">
                        <span className="material-symbols-outlined text-on-primary">payments</span>
                    </div>
                    <div>
                        <h3 className="font-headline-md text-headline-md text-primary mb-2">
                            Payment Methods
                        </h3>
                        <p className="font-body-md text-body-md text-on-surface-variant mb-4">
                            Online card payment is being set up for this firm. Until then, your legal
                            team will share secure payment instructions for outstanding invoices.
                        </p>
                        <span className="font-label-md text-label-md text-on-surface-variant">
                            Managed by your firm
                        </span>
                    </div>
                </div>
                <div className="bg-surface-container border border-outline-variant p-stack-md rounded-lg flex gap-6 items-start">
                    <div className="bg-primary-container p-3 rounded-lg">
                        <span className="material-symbols-outlined text-on-primary">chat_bubble</span>
                    </div>
                    <div>
                        <h3 className="font-headline-md text-headline-md text-primary mb-2">
                            Billing Questions?
                        </h3>
                        <p className="font-body-md text-body-md text-on-surface-variant mb-4">
                            Our team is here to clarify any item on your invoice.
                        </p>
                        <a
                            href="/messages"
                            className="font-label-md text-label-md text-primary border-b border-primary pb-1 hover:opacity-70 transition-opacity"
                        >
                            Contact support
                        </a>
                    </div>
                </div>
            </section>
        </main>
    );
}
