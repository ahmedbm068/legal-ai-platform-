"""Drafting Big Agent — Harvey "Draft" equivalent.

Produces clause-cited legal drafts: client emails, internal memos,
partner strategy notes, negotiation strategy, contract redlines.
"""

from __future__ import annotations

from .base import BigAgent, big_agent_registry


drafting_agent = BigAgent(
    name="drafting_agent",
    tier="core",
    description=(
        "Drafts client communications, internal memos, strategy notes, "
        "negotiation positions, and contract redlines. Each clause is "
        "tied to retrieved evidence and validated before release."
    ),
    mini_agents_used=(
        "drafting_agent",
        "contract_redline_agent",
        "negotiation_strategy_agent",
        "claim_validation_agent",
        "evidence_trace_agent",
        "strict_verifier_agent",
    ),
    intents_handled=(
        "draft_client_email_case",
        "draft_internal_email_case",
        "draft_partner_strategy_note_case",
        "draft_negotiation_strategy",
        "draft_contract_redline_case",
    ),
    delegates_to=(
        "backend.services.ai.copilot_drafting_execution_service",
        "backend.services.ai.artifact_versioning_service",
    ),
    ui_route="/draft-documents",
    harvey_equivalent="Draft",
    legora_equivalent="Draft",
)

big_agent_registry.register(drafting_agent)
