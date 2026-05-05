"""Workspace Big Agent — Legora-style case-aware context layer.

Always-on (state, not intent-routed). Maintains conversation history,
case context, and case snapshots so every other Big Agent operates
with the right matter context.
"""

from __future__ import annotations

from .base import BigAgent, big_agent_registry


workspace_agent = BigAgent(
    name="workspace_agent",
    tier="context",
    description=(
        "Always-on context layer. Maintains case-aware conversation "
        "memory, case snapshots, and scoped retrieval boundaries so "
        "every other Big Agent operates inside the correct matter."
    ),
    mini_agents_used=(
        "case_memory_agent",
        "intake_agent",
        "insight_agent",
    ),
    intents_handled=(),  # state agent — invoked on every call regardless of intent
    delegates_to=(
        "backend.services.ai.copilot_memory_service",
        "backend.services.ai.case_context_service",
        "backend.services.ai.case_snapshot_service",
    ),
    ui_route="/cases/{case_id}/workspace",
    harvey_equivalent=None,
    legora_equivalent="Workspace",
)

big_agent_registry.register(workspace_agent)
