import { useEffect, useState } from "react";
import { apiListCases, type AdminCase } from "../lib/api";
import { PageHeader, Panel, SearchInput, StateMsg } from "../components/ui";

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
            <PageHeader
                title="Cases"
                subtitle={`${cases.length} total cases across all tenants.`}
                actions={
                    <SearchInput
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search title…"
                    />
                }
            />

            {loading && <StateMsg>Loading cases…</StateMsg>}
            {error && <StateMsg kind="error">{error}</StateMsg>}

            {!loading && !error && (
                <Panel className="overflow-hidden">
                    <div className="overflow-auto">
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
                            <tbody className="font-table-data text-table-data">
                                {filtered.length === 0 ? (
                                    <tr>
                                        <td colSpan={6} className="text-center text-secondary py-8">
                                            No cases found
                                        </td>
                                    </tr>
                                ) : (
                                    filtered.map((c) => (
                                        <tr key={c.id}>
                                            <td className="text-secondary font-mono text-xs">#{c.id}</td>
                                            <td className="text-on-surface font-semibold">{c.title}</td>
                                            <td>
                                                <span className={STATUS_BADGE[c.status] ?? "badge badge-gray"}>
                                                    {c.status}
                                                </span>
                                            </td>
                                            <td className="capitalize text-secondary">
                                                {c.jurisdiction_country}
                                            </td>
                                            <td className="text-secondary">#{c.tenant_id}</td>
                                            <td className="text-secondary">
                                                {new Date(c.created_at).toLocaleDateString()}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </Panel>
            )}
        </div>
    );
}
