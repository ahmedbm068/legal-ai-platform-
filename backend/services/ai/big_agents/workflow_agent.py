"""Workflow Big Agent — multi-step IRAC reasoning pipeline.

Wraps the 21-class `legal_workflow_agent_pack` and `agent_workflow_service`.
Triggered for explicit analysis intents (risk analysis, evidence
evaluation, timeline construction, evidence tracing, deadline
monitoring) where the orchestrator needs a multi-step legal-reasoning
pipeline rather than a single-shot answer.
"""

from __future__ import annotations

from .base import BigAgent, big_agent_registry


workflow_agent = BigAgent(
    name="workflow_agent",
    tier="workflow",
    description=(
        "Runs a 12-step IRAC-style reasoning pipeline (facts → rules → "
        "application → counter-analysis → contradictions → verifier → "
        "position strength → strategy → memo). Used for explicit "
        "analysis intents where a single LLM call is not enough."
    ),
    mini_agents_used=(
        # Drawn from legal_workflow_agent_pack.py
        "FactExtractionAgent",
        "RetrievalAgent",
        "RuleSynthesisAgent",
        "ApplicationAgent",
        "MissingFactsAgent",
        "CounterAnalysisAgent",
        "ContradictionAgent",
        "VerifierAgent",
        "PositionStrengthAgent",
        "StrategyAgent",
        "TimelineImpactAgent",
        "ClientRiskAgent",
        "MemoDraftingAgent",
        "ClientExplanationAgent",
        "DraftingAgent",
        # Plus orchestration helpers
        "case_memory_agent",
        "evidence_strength_agent",
        "timeline_agent",
    ),
    intents_handled=(
        "summarize_case",
        "summarize_and_analyze_risks_case",
        "analyze_risks_case",
        "evaluate_case_evidence",
        "build_timeline_case",
        "trace_case_evidence",
        "monitor_deadlines_case",
    ),
    delegates_to=(
        "backend.services.ai.agent_workflow_service",
        "backend.services.ai.agents.legal_workflow_agent_pack",
    ),
    ui_route="/cases/{case_id}/workflow",
    harvey_equivalent="Workflows",
    legora_equivalent=None,
)

big_agent_registry.register(workflow_agent)
