import { useEffect, useState } from "react";
import { apiListUsers, type AdminUser } from "../lib/api";

const ROLE_BADGE: Record<string, string> = {
    admin: "badge badge-red",
    lawyer: "badge badge-blue",
    client: "badge badge-green",
    assistant: "badge badge-yellow",
};

export default function UsersPage() {
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

    const filtered = users.filter(
        (u) =>
            u.name.toLowerCase().includes(search.toLowerCase()) ||
            u.email.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div>
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-lg font-semibold text-white">Users</h1>
                    <p className="text-slate-400 text-sm mt-0.5">{users.length} total accounts</p>
                </div>
                <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search name or email…"
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
                                <th>Name</th>
                                <th>Email</th>
                                <th>Role</th>
                                <th>Tenant</th>
                                <th>Joined</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={5} className="text-center text-slate-500 py-8">
                                        No users found
                                    </td>
                                </tr>
                            ) : (
                                filtered.map((u) => (
                                    <tr key={u.id}>
                                        <td className="text-white font-medium">{u.name}</td>
                                        <td>{u.email}</td>
                                        <td>
                                            <span className={ROLE_BADGE[u.role] ?? "badge badge-gray"}>
                                                {u.role}
                                            </span>
                                        </td>
                                        <td className="text-slate-500">#{u.tenant_id}</td>
                                        <td className="text-slate-500">
                                            {new Date(u.created_at).toLocaleDateString()}
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
