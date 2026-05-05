"""Research Big Agent — Harvey "Assist" / Legora "Research" equivalent.

Answers legal questions by combining internal case retrieval, external
web research, and high-reasoning synthesis. Routed by the orchestrator
when the user is in search mode or asks an explicit analysis intent.
"""

from __future__ import annotations

from .base import BigAgent, big_agent_registry


research_agent = BigAgent(
    name="research_agent",
    tier="core",
    description=(
        "Answers grounded legal questions across internal case material "
        "and external sources. Combines retrieval, jurisdiction context, "
        "and high-reasoning synthesis with verifier-gated citations."
    ),
    mini_agents_used=(
        "retrieval_agent",
        "article_applicability_agent",
        "case_reasoning_agent",
        "summarization_agent",
        "strict_verifier_agent",
        "evidence_trace_agent",
        "agent_output_formatter",
    ),
    intents_handled=(
        "ask_document",
        "ask_case",
        "ask_global",
        "summarize_global",
    ),
    delegates_to=(
        "backend.services.ai.copilot_legal_search_execution_service",
        "backend.services.ai.copilot_high_reasoning_service",
        "backend.services.ai.external_research_service",
        "backend.services.ai.legal_search_mode_service",
    ),
    ui_route="/copilot",
    harvey_equivalent="Assist",
    legora_equivalent="Research",
)

big_agent_registry.register(research_agent)
