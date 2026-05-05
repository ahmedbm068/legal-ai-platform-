"""Phase A0 — Big Agent registry tests.

Verifies that the 5 declared Big Agents are correctly registered with
the metadata the admin catalog and orchestrator both rely on.
"""

from __future__ import annotations

import unittest

from backend.services.ai.big_agents import big_agent_registry
from backend.services.ai.big_agents.base import BigAgent


EXPECTED_AGENTS: tuple[str, ...] = (
    "research_agent",
    "drafting_agent",
    "review_agent",
    "workspace_agent",
    "workflow_agent",
)


class BigAgentRegistryRegistrationTest(unittest.TestCase):
    def test_all_five_agents_register(self) -> None:
        names = {agent.name for agent in big_agent_registry.list_all()}
        for expected in EXPECTED_AGENTS:
            self.assertIn(expected, names, f"missing big agent: {expected}")

    def test_each_agent_has_non_empty_mini_agents_or_is_context_tier(self) -> None:
        for name in EXPECTED_AGENTS:
            agent = big_agent_registry.get(name)
            self.assertIsNotNone(agent, f"{name} not registered")
            assert agent is not None  # for type narrowing
            self.assertIsInstance(agent, BigAgent)
            # Every agent must declare at least one mini-agent worker.
            self.assertGreater(
                len(agent.mini_agents_used),
                0,
                f"{name} declares no mini-agents — this is what makes it 'big'",
            )

    def test_each_agent_delegates_to_existing_service(self) -> None:
        for name in EXPECTED_AGENTS:
            agent = big_agent_registry.get(name)
            assert agent is not None
            self.assertGreater(
                len(agent.delegates_to),
                0,
                f"{name} must delegate to at least one existing service",
            )
            for module_path in agent.delegates_to:
                self.assertTrue(
                    module_path.startswith("backend.services.ai."),
                    f"{name} delegates_to '{module_path}' is outside the AI services package",
                )


class BigAgentRegistryLookupTest(unittest.TestCase):
    def test_find_by_intent_routes_drafting(self) -> None:
        agent = big_agent_registry.find_by_intent("draft_client_email_case")
        self.assertIsNotNone(agent)
        assert agent is not None
        self.assertEqual(agent.name, "drafting_agent")

    def test_find_by_intent_routes_review(self) -> None:
        agent = big_agent_registry.find_by_intent("compare_case_documents")
        self.assertIsNotNone(agent)
        assert agent is not None
        # compare_case_documents is in both review and workflow intents on
        # purpose — the registry returns the first match deterministically;
        # both are acceptable answers for this lookup.
        self.assertIn(agent.name, {"review_agent", "workflow_agent"})

    def test_find_by_intent_routes_workflow(self) -> None:
        agent = big_agent_registry.find_by_intent("analyze_risks_case")
        self.assertIsNotNone(agent)
        assert agent is not None
        self.assertEqual(agent.name, "workflow_agent")

    def test_find_by_intent_returns_none_for_unknown(self) -> None:
        self.assertIsNone(big_agent_registry.find_by_intent("nonsense_intent_xyz"))
        self.assertIsNone(big_agent_registry.find_by_intent(""))


class BigAgentSerializationTest(unittest.TestCase):
    def test_to_dict_contains_all_metadata_fields(self) -> None:
        agent = big_agent_registry.get("research_agent")
        assert agent is not None
        payload = agent.to_dict()
        for field in (
            "name",
            "tier",
            "description",
            "mini_agents_used",
            "intents_handled",
            "delegates_to",
            "ui_route",
            "harvey_equivalent",
            "legora_equivalent",
        ):
            self.assertIn(field, payload, f"to_dict() missing field: {field}")
        self.assertEqual(payload["name"], "research_agent")
        self.assertEqual(payload["tier"], "core")
        self.assertIsInstance(payload["mini_agents_used"], list)


class BigAgentTierTaxonomyTest(unittest.TestCase):
    def test_tiers_are_constrained_to_known_set(self) -> None:
        valid_tiers = {"core", "context", "workflow"}
        for agent in big_agent_registry.list_all():
            self.assertIn(
                agent.tier,
                valid_tiers,
                f"{agent.name} has unknown tier '{agent.tier}'",
            )

    def test_workspace_agent_is_context_tier_and_always_on(self) -> None:
        agent = big_agent_registry.get("workspace_agent")
        assert agent is not None
        self.assertEqual(agent.tier, "context")
        # Always-on agents do NOT declare intents — they participate on every call.
        self.assertEqual(len(agent.intents_handled), 0)


if __name__ == "__main__":
    unittest.main()
