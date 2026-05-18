import { useEffect, useMemo, useState } from "react";
import { apiListUsers, type AdminUser } from "../lib/api";
import { PageHeader, Panel, SearchInput, StateMsg } from "../components/ui";

export default function ClientsPage() {
    const [users, setUsers] = useState<AdminUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [search, setSearch] = useState("");

    useEffect(() => {
        apiListUsers()
            .then(setUsers)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    const clients = useMemo(
        () => users.filter((u) => u.role === "client"),
        [users]
    );

    const filtered = clients.filter(
        (u) =>
            u.name.toLowerCase().includes(search.toLowerCase()) ||
            u.email.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div>
            <PageHeader
                title="Clients"
                subtitle={`${clients.length} client accounts across all tenants.`}
                actions={
                    <SearchInput
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search name or email…"
                    />
                }
            />

            {loading && <StateMsg>Loading clients…</StateMsg>}
            {error && <StateMsg kind="error">{error}</StateMsg>}

            {!loading && !error && (
                <Panel className="overflow-hidden">
                    <div className="overflow-auto">
                        <table className="admin-table">
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>Email</th>
                                    <th>Tenant</th>
                                    <th>Joined</th>
                                </tr>
                            </thead>
                            <tbody className="font-table-data text-table-data">
                                {filtered.length === 0 ? (
                                    <tr>
                                        <td colSpan={4} className="text-center text-secondary py-8">
                                            No clients found
                                        </td>
                                    </tr>
                                ) : (
                                    filtered.map((u) => (
                                        <tr key={u.id}>
                                            <td className="text-on-surface font-semibold">{u.name}</td>
                                            <td className="text-secondary">{u.email}</td>
                                            <td className="text-secondary">#{u.tenant_id}</td>
                                            <td className="text-secondary">
                                                {new Date(u.created_at).toLocaleDateString()}
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
