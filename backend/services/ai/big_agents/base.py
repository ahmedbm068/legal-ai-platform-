"""Big Agent base + registry.

A Big Agent is a *declarative descriptor* of one specialist capability
that the orchestrator already routes to. It does NOT contain business
logic — it points at the existing services and intents that implement
the capability.

Tiers (informational, used by the admin catalog UI):
  - "core"      — primary user-facing flows (research, drafting, review)
  - "context"   — always-on state agents (workspace memory)
  - "workflow"  — multi-step pipelines (legal workflow / IRAC)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class BigAgent:
    """Declarative descriptor of a specialist capability.

    All fields are metadata. The runtime behavior lives in
    `delegates_to` services, which the orchestrator already calls.
    """

    name: str
    tier: str
    description: str
    mini_agents_used: tuple[str, ...] = field(default_factory=tuple)
    intents_handled: tuple[str, ...] = field(default_factory=tuple)
    delegates_to: tuple[str, ...] = field(default_factory=tuple)
    ui_route: Optional[str] = None
    harvey_equivalent: Optional[str] = None
    legora_equivalent: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tier": self.tier,
            "description": self.description,
            "mini_agents_used": list(self.mini_agents_used),
            "intents_handled": list(self.intents_handled),
            "delegates_to": list(self.delegates_to),
            "ui_route": self.ui_route,
            "harvey_equivalent": self.harvey_equivalent,
            "legora_equivalent": self.legora_equivalent,
        }


class BigAgentRegistry:
    """Process-wide singleton. Agents register on import."""

    def __init__(self) -> None:
        self._agents: dict[str, BigAgent] = {}

    def register(self, agent: BigAgent) -> None:
        if agent.name in self._agents:
            # Idempotent on re-import (e.g. test runs)
            return
        self._agents[agent.name] = agent

    def list_all(self) -> list[BigAgent]:
        return sorted(self._agents.values(), key=lambda a: (a.tier, a.name))

    def get(self, name: str) -> Optional[BigAgent]:
        return self._agents.get(name)

    def find_by_intent(self, intent: str) -> Optional[BigAgent]:
        """Return the first agent that handles the given intent.

        Order is deterministic (insertion-priority). The orchestrator's
        actual routing logic is the source of truth — this is a lookup
        helper used by the trace logger and the admin catalog.
        """
        normalized = (intent or "").strip()
        if not normalized:
            return None
        for agent in self._agents.values():
            if normalized in agent.intents_handled:
                return agent
        return None

    def find_by_route(self, route: str) -> Optional[BigAgent]:
        normalized = (route or "").strip()
        if not normalized:
            return None
        for agent in self._agents.values():
            if agent.ui_route == normalized:
                return agent
        return None

    def reset_for_tests(self, agents: Iterable[BigAgent] | None = None) -> None:
        """Test helper: clear and optionally seed."""
        self._agents.clear()
        for agent in agents or ():
            self.register(agent)


# Process-wide singleton.
big_agent_registry = BigAgentRegistry()
