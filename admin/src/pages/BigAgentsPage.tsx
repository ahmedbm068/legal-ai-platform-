import { useEffect, useState } from "react";
import { apiListBigAgents, type BigAgent } from "../lib/api";

const TIER_COLOR: Record<string, string> = {
    core: "border-brand-700 bg-brand-900/10",
    context: "border-blue-800 bg-blue-900/10",
    workflow: "border-purple-800 bg-purple-900/10",
};

const TIER_LABEL: Record<string, string> = {
    core: "CORE",
    context: "CONTEXT",
    workflow: "WORKFLOW",
};

function AgentCard({ agent }: { agent: BigAgent }) {
    const tierClass = TIER_COLOR[agent.tier] ?? "border-slate-700";
    return (
        <div className={`rounded-xl border ${tierClass} p-5 mb-4`}>
            <div className="flex items-start justify-between mb-2">
                <div>
                    <div className="flex items-center gap-2">
                        <h3 className="text-white text-base font-semibold">{agent.name}</h3>
                        <span className="text-[10px] font-bold tracking-wider text-slate-500">
                            {TIER_LABEL[agent.tier] ?? agent.tier.toUpperCase()}
                        </span>
                    </div>
                    {(agent.harvey_equivalent || agent.legora_equivalent) && (
                        <p className="text-slate-500 text-xs mt-0.5">
                            {agent.harvey_equivalent && <span>Harvey: {agent.harvey_equivalent}</span>}
                            {agent.harvey_equivalent && agent.legora_equivalent && " · "}
                            {agent.legora_equivalent && <span>Legora: {agent.legora_equivalent}</span>}
                        </p>
                    )}
                </div>
                <div className="text-right">
                    <p className="text-slate-500 text-[10px] uppercase tracking-wide">Last 24h</p>
                    <p className="text-white text-lg font-bold">
                        {agent.last_24h_call_count ?? "—"}
                    </p>
                </div>
            </div>
            <p className="text-slate-300 text-sm leading-relaxed mb-3">{agent.description}</p>

            <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                    <p className="text-slate-500 uppercase tracking-wide mb-1">Intents</p>
                    {agent.intents_handled.length === 0 ? (
                        <p className="text-slate-600 italic">always-on</p>
                    ) : (
                        <ul className="text-slate-300 space-y-0.5">
                            {agent.intents_handled.map((intent) => (
                                <li key={intent} className="font-mono">{intent}</li>
                            ))}
                        </ul>
                    )}
                </div>
                <div>
                    <p className="text-slate-500 uppercase tracking-wide mb-1">UI Route</p>
                    <p className="text-slate-300 font-mono">{agent.ui_route ?? "—"}</p>
                    <p className="text-slate-500 uppercase tracking-wide mt-3 mb-1">
                        Mini-agents ({agent.mini_agents_used.length})
                    </p>
                    <p className="text-slate-400 leading-snug">
                        {agent.mini_agents_used.slice(0, 4).join(", ")}
                        {agent.mini_agents_used.length > 4 && (
                            <span className="text-slate-600">
                                {" "}
                                +{agent.mini_agents_used.length - 4} more
                            </span>
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
            <div className="mb-6">
                <h1 className="text-lg font-semibold text-white">Big Agents</h1>
                <p className="text-slate-400 text-sm mt-0.5">
                    Specialist capabilities the orchestrator routes to. Each agent
                    delegates to existing services and orchestrates a set of mini-agents.
                </p>
            </div>

            {loading && <p className="text-slate-400 text-sm">Loading…</p>}
            {error && (
                <p className="text-yellow-400 text-sm bg-yellow-900/20 border border-yellow-800 rounded-lg px-3 py-2">
                    {error}
                </p>
            )}

            {!loading && !error && agents.map((agent) => (
                <AgentCard key={agent.name} agent={agent} />
            ))}
        </div>
    );
}
