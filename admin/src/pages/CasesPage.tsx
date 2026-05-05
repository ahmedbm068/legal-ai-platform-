import { useEffect, useState } from "react";
import { apiListCases, type AdminCase } from "../lib/api";

const STATUS_BADGE: Record<string, string> = {
    open: "badge badge-green",
    in_progress: "badge badge-blue",
    closed: "badge badge-gray",
    archived: "badge badge-yellow",
};

export default function CasesPage() {
    const [cases, setCases] = useState<AdminCase[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [search, setSearch] = useState("");

    useEffect(() => {
        apiListCases()
            .then(setCases)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    const filtered = cases.filter((c) =>
        c.title.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div>
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-lg font-semibold text-white">Cases</h1>
                    <p className="text-slate-400 text-sm mt-0.5">{cases.length} total cases</p>
                </div>
                <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search title…"
                    className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500 w-64"
                />
            </div>

            {loading && <p className="text-slate-400 text-sm">Loading…</p>}
            {error && <p className="text-red-400 text-sm">{error}</p>}

            {!loading && !error && (
                <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                    <table className="admin-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Title</th>
                                <th>Status</th>
                                <th>Jurisdiction</th>
                                <th>Tenant</th>
                                <th>Created</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="text-center text-slate-500 py-8">
                                        No cases found
                                    </td>
                                </tr>
                            ) : (
                                filtered.map((c) => (
                                    <tr key={c.id}>
                                        <td className="text-slate-500 font-mono text-xs">#{c.id}</td>
                                        <td className="text-white font-medium">{c.title}</td>
                                        <td>
                                            <span className={STATUS_BADGE[c.status] ?? "badge badge-gray"}>
                                                {c.status}
                                            </span>
                                        </td>
                                        <td className="capitalize">{c.jurisdiction_country}</td>
                                        <td className="text-slate-500">#{c.tenant_id}</td>
                                        <td className="text-slate-500">
                                            {new Date(c.created_at).toLocaleDateString()}
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
