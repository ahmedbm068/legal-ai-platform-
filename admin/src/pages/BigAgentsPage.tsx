import { useEffect, useState } from "react";
import { apiListBigAgents, type BigAgent } from "../lib/api";
import { PageHeader, StateMsg } from "../components/ui";

const TIER_BADGE: Record<string, string> = {
    core: "badge badge-green",
    context: "badge badge-blue",
    workflow: "badge badge-yellow",
};

function AgentCard({ agent }: { agent: BigAgent }) {
    return (
        <div className="bg-surface-container-lowest rounded border border-outline-variant p-md mb-md">
            <div className="flex items-start justify-between mb-sm">
                <div>
                    <div className="flex items-center gap-sm">
                        <h3 className="text-on-surface font-section-header text-section-header">
                            {agent.name}
                        </h3>
                        <span className={TIER_BADGE[agent.tier] ?? "badge badge-gray"}>
                            {agent.tier}
                        </span>
                    </div>
                    {(agent.harvey_equivalent || agent.legora_equivalent) && (
                        <p className="text-secondary text-xs mt-0.5">
                            {agent.harvey_equivalent && <span>Harvey: {agent.harvey_equivalent}</span>}
                            {agent.harvey_equivalent && agent.legora_equivalent && " · "}
                            {agent.legora_equivalent && <span>Legora: {agent.legora_equivalent}</span>}
                        </p>
                    )}
                </div>
                <div className="text-right">
                    <p className="font-label-caps text-label-caps text-secondary uppercase">
                        Last 24h
                    </p>
                    <p className="text-primary font-page-header text-page-header">
                        {agent.last_24h_call_count ?? "—"}
                    </p>
                </div>
            </div>
            <p className="text-on-surface-variant font-body-md text-body-md leading-relaxed mb-md">
                {agent.description}
            </p>

            <div className="grid grid-cols-2 gap-md text-xs">
                <div>
                    <p className="font-label-caps text-label-caps text-secondary uppercase mb-1">
                        Intents
                    </p>
                    {agent.intents_handled.length === 0 ? (
                        <p className="text-secondary italic">always-on</p>
                    ) : (
                        <ul className="text-on-surface space-y-0.5">
                            {agent.intents_handled.map((intent) => (
                                <li key={intent} className="font-mono">
                                    {intent}
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
                <div>
                    <p className="font-label-caps text-label-caps text-secondary uppercase mb-1">
                        UI Route
                    </p>
                    <p className="text-on-surface font-mono">{agent.ui_route ?? "—"}</p>
                    <p className="font-label-caps text-label-caps text-secondary uppercase mt-3 mb-1">
                        Mini-agents ({agent.mini_agents_used.length})
                    </p>
                    <p className="text-secondary leading-snug">
                        {agent.mini_agents_used.slice(0, 4).join(", ")}
                        {agent.mini_agents_used.length > 4 && (
                            <span> +{agent.mini_agents_used.length - 4} more</span>
                        )}
                    </p>
                </div>
            </div>
        </div>
    );
}

export default function BigAgentsPage() {
    const [agents, setAgents] = useState<BigAgent[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        apiListBigAgents()
            .then((catalog) => setAgents(catalog.agents))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false));
    }, []);

    return (
        <div>
            <PageHeader
                title="Big Agents"
                subtitle="Specialist capabilities the orchestrator routes to. Each agent delegates to existing services and orchestrates a set of mini-agents."
            />

            {loading && <StateMsg>Loading agents…</StateMsg>}
            {error && <StateMsg kind="error">{error}</StateMsg>}

            {!loading &&
                !error &&
                agents.map((agent) => <AgentCard key={agent.name} agent={agent} />)}
        </div>
    );
}
