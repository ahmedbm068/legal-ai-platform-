"""Big Agent layer — declarative metadata wrappers around the
orchestrator's specialist execution paths.

These are *not* new agents. Each Big Agent is a one-screen description
of a specialist capability that already exists somewhere in
`backend/services/ai/`, expressed in the same shape the runtime
orchestrator uses to route intents.

The registry lets the admin console answer:
  - "Which big agents does this product expose?"
  - "Which intent triggers which big agent?"
  - "Which mini-agents did call X actually use?"

Loading this package eagerly registers all 5 wrappers via their import
side-effects.

Phase A0 — 2026-05-05.
"""

from __future__ import annotations

from .base import BigAgent, BigAgentRegistry, big_agent_registry  # noqa: F401

# Eager registration — importing each module registers the agent.
from . import research_agent  # noqa: F401
from . import drafting_agent  # noqa: F401
from . import review_agent  # noqa: F401
from . import workspace_agent  # noqa: F401
from . import workflow_agent  # noqa: F401

__all__ = [
    "BigAgent",
    "BigAgentRegistry",
    "big_agent_registry",
]
