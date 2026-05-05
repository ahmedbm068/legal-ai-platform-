import { useEffect, useState } from "react";
import { apiSystemHealth, type SystemHealth } from "../lib/api";

interface StatCardProps {
    label: string;
    value: number | string;
    icon: string;
    color: string;
}

function StatCard({ label, value, icon, color }: StatCardProps) {
    return (
        <div className={`bg-slate-900 border ${color} rounded-xl p-5`}>
            <div className="flex items-start justify-between">
                <div>
                    <p className="text-slate-400 text-xs font-medium uppercase tracking-wide">{label}</p>
                    <p className="text-white text-2xl font-bold mt-1">
                        {typeof value === "number" ? value.toLocaleString() : value}
                    </p>
                </div>
                <span className="text-2xl">{icon}</span>
            </div>
        </div>
    );
}

export default function HealthPage() {
    const [health, setHealth] = useState<SystemHealth | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        apiSystemHealth()
            .then(setHealth)
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    return (
        <div>
            <div className="mb-6">
                <h1 className="text-lg font-semibold text-white">System Health</h1>
                <p className="text-slate-400 text-sm mt-0.5">Live platform counters</p>
            </div>

            {loading && <p className="text-slate-400 text-sm">Loading…</p>}
            {error && (
                <p className="text-yellow-400 text-sm bg-yellow-900/20 border border-yellow-800 rounded-lg px-3 py-2">
                    {error} — health endpoint may not be deployed yet.
                </p>
            )}

            {!loading && !error && health && (
                <div className="grid grid-cols-2 gap-4">
                    <StatCard
                        label="Total Users"
                        value={health.total_users}
                        icon="👤"
                        color="border-blue-800"
                    />
                    <StatCard
                        label="Total Cases"
                        value={health.total_cases}
                        icon="📁"
                        color="border-brand-800"
                    />
                    <StatCard
                        label="Total Documents"
                        value={health.total_documents}
                        icon="📄"
                        color="border-purple-800"
                    />
                    <StatCard
                        label="Audit Entries"
                        value={health.total_audit_entries}
                        icon="📋"
                        color="border-slate-700"
                    />
                </div>
            )}
        </div>
    );
}
